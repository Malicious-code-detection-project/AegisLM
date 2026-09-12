"""Diagnose preserved source-v2 canary artifacts without model execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.artifacts import validate_no_symlink_components  # noqa: E402
from aegislm.schemas import SOURCE_ASSESSMENTS  # noqa: E402
from aegislm.tracking import validate_wandb_payload  # noqa: E402

HARMONY_ANALYSIS_PREFIX = "<|channel|>analysis<|message|>"
HARMONY_FINAL_MARKER = "<|channel|>final<|message|>"
HARMONY_EOS = "<|return|>"
PARSE_ERROR_CATEGORIES = (
    "expecting_value",
    "delimiter",
    "extra_data",
    "unterminated_string",
    "other",
)
ASSESSMENT_CATEGORIES = (*SOURCE_ASSESSMENTS, "invalid", "missing")
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_PREDICTION_BYTES = 128 * 1024 * 1024
MAX_PREDICTION_RECORDS = 100_000

TokenCounter = Callable[[str], int]


def main() -> None:
    from aegislm.artifacts import validate_artifact_path_plan, write_text_artifact

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--gate-report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--adapter",
        type=Path,
        required=True,
        help="Saved adapter directory or adapter_model.safetensors file.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        action="append",
        default=[],
        help="Checkpoint directory or adapter_model.safetensors file; repeatable.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protected_dirs = [
        path for path in (args.adapter, *args.checkpoint) if path.is_dir()
    ]
    try:
        validate_artifact_path_plan(
            inputs=(
                args.predictions,
                args.gate_report,
                args.manifest,
                args.adapter,
                *args.checkpoint,
            ),
            outputs=(args.output,),
            protected_roots=tuple(protected_dirs),
            require_new=True,
        )
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))

    report = diagnose_source_canary(
        predictions_path=args.predictions,
        gate_report_path=args.gate_report,
        manifest_path=args.manifest,
        adapter_path=args.adapter,
        checkpoint_paths=args.checkpoint,
    )
    write_text_artifact(
        args.output,
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    print(
        "source-v2 canary diagnosis complete: "
        f"records={report['prediction_analysis']['record_count']} "
        f"valid={report['prediction_analysis']['taxonomy']['valid']}"
    )


def diagnose_source_canary(
    *,
    predictions_path: Path,
    gate_report_path: Path,
    manifest_path: Path,
    adapter_path: Path,
    checkpoint_paths: Sequence[Path],
    token_counter: TokenCounter | None = None,
) -> dict[str, Any]:
    """Build a source-free aggregate diagnosis from preserved local artifacts."""
    prediction_rows = _load_prediction_rows(predictions_path)
    gate = _load_object(gate_report_path, "gate report")
    manifest = _load_object(manifest_path, "training manifest")
    adapter_file, adapter_dir = _adapter_locations(adapter_path)
    counter = token_counter or _load_token_counter(adapter_dir)

    max_new_tokens = _positive_int(gate.get("max_new_tokens"), "max_new_tokens")
    prediction_analysis = _diagnose_predictions(
        prediction_rows, max_new_tokens=max_new_tokens, token_counter=counter
    )
    adapter = _inspect_adapter(adapter_file)
    checkpoints = _inspect_checkpoints(checkpoint_paths, adapter["sha256"])
    consistency = _artifact_consistency(
        prediction_analysis=prediction_analysis,
        gate=gate,
        manifest=manifest,
        adapter_sha256=adapter["sha256"],
    )
    wandb_safe_summary = _wandb_safe_summary(
        prediction_analysis, adapter, checkpoints, consistency
    )
    validate_wandb_payload(wandb_safe_summary)

    report = {
        "schema_version": "aegislm.source-canary-diagnosis.v1",
        "privacy": {
            "source_included": False,
            "raw_generation_included": False,
            "record_ids_included": False,
            "validation_error_text_included": False,
            "input_paths_included": False,
        },
        "artifact_identity": {
            "predictions_sha256": _file_sha256(predictions_path),
            "gate_report_sha256": _file_sha256(gate_report_path),
            "manifest_sha256": _file_sha256(manifest_path),
            "adapter_sha256": adapter["sha256"],
        },
        "prediction_analysis": prediction_analysis,
        "adapter": adapter,
        "checkpoints": checkpoints,
        "consistency": consistency,
        "wandb_safe_summary": wandb_safe_summary,
    }
    # This also rejects non-finite values and unexpected object types before writing.
    json.dumps(report, allow_nan=False)
    return report


def _load_prediction_rows(path: Path) -> list[dict[str, Any]]:
    validate_no_symlink_components(path, description="prediction artifact")
    if path.is_symlink() or not path.is_file():
        raise ValueError("prediction artifact must be a regular non-symlink file")
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total_bytes = 0
    with path.open("rb") as stream:
        line_number = 0
        while True:
            encoded = stream.readline(MAX_JSON_BYTES + 1)
            if not encoded:
                break
            line_number += 1
            total_bytes += len(encoded)
            if len(encoded) > MAX_JSON_BYTES:
                raise ValueError(
                    f"prediction artifact line {line_number} exceeds the size limit"
                )
            if total_bytes > MAX_PREDICTION_BYTES:
                raise ValueError("prediction artifact exceeds the total size limit")
            try:
                line = encoded.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"prediction artifact line {line_number} is not UTF-8"
                ) from exc
            if not line.strip():
                continue
            try:
                value = _strict_json_loads(line)
            except (json.JSONDecodeError, RecursionError, ValueError) as exc:
                raise ValueError(
                    f"prediction artifact line {line_number} is invalid JSON"
                ) from exc
            if not isinstance(value, dict):
                raise ValueError(
                    f"prediction artifact line {line_number} is not an object"
                )
            record_id = value.get("id")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(
                    f"prediction artifact line {line_number} has invalid id"
                )
            if record_id in seen_ids:
                raise ValueError("prediction artifact contains a duplicate id")
            seen_ids.add(record_id)
            if len(seen_ids) > MAX_PREDICTION_RECORDS:
                raise ValueError("prediction artifact exceeds the record count limit")
            raw = value.get("raw_generation")
            parsed = value.get("parsed_output")
            errors = value.get("validation_errors")
            if not isinstance(raw, str):
                raise ValueError(
                    f"prediction artifact line {line_number} has invalid raw_generation"
                )
            if parsed is not None and not isinstance(parsed, dict):
                raise ValueError(
                    f"prediction artifact line {line_number} has invalid parsed_output"
                )
            if not isinstance(errors, list) or not all(
                isinstance(error, str) for error in errors
            ):
                raise ValueError(
                    f"prediction artifact line {line_number} has invalid validation_errors"
                )
            rows.append(value)
    if not rows:
        raise ValueError("prediction artifact is empty")
    return rows


def _load_object(path: Path, label: str) -> dict[str, Any]:
    content = _read_bounded_bytes(path, label, MAX_JSON_BYTES)
    try:
        value = _strict_json_loads(content.decode("utf-8"))
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        raise ValueError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not an object")
    return value


def _read_bounded_bytes(path: Path, label: str, limit: int) -> bytes:
    """Read at most ``limit`` bytes without a stat/read race."""
    validate_no_symlink_components(path, description=label)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f"{label} exceeds the size limit")
    return content


def _strict_json_loads(text: str) -> Any:
    def reject_constant(_value: str) -> None:
        raise ValueError("non-standard JSON constant")

    value = json.loads(text, parse_constant=reject_constant)
    _reject_nonfinite_numbers(value)
    return value


def _reject_nonfinite_numbers(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    if isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite_numbers(item)
    elif isinstance(value, list):
        for item in value:
            _reject_nonfinite_numbers(item)


def _diagnose_predictions(
    rows: list[dict[str, Any]], *, max_new_tokens: int, token_counter: TokenCounter
) -> dict[str, Any]:
    taxonomy = Counter(
        {
            "valid": 0,
            "parsed_contract_invalid": 0,
            "unparsed_with_eos": 0,
            "unparsed_no_eos": 0,
        }
    )
    parse_errors = Counter({category: 0 for category in PARSE_ERROR_CATEGORIES})
    assessments = Counter({category: 0 for category in ASSESSMENT_CATEGORIES})
    token_counts: list[int] = []
    first_eos_positions: list[int] = []
    repeated_eos_rows = 0
    repeated_eos_tokens = 0
    harmony = Counter(
        {
            "canonical_prefix": 0,
            "premature_end_start": 0,
            "missing_final_marker": 0,
            "duplicate_final_marker": 0,
            "tool_call_marker": 0,
            "excess_channel_marker": 0,
            "extreme_start_repetition": 0,
        }
    )

    for row in rows:
        raw = row["raw_generation"]
        parsed = row["parsed_output"]
        errors = row["validation_errors"]
        eos_count = raw.count(HARMONY_EOS)
        token_count = token_counter(raw)
        if type(token_count) is not int or token_count < 0:
            raise ValueError("token counter returned an invalid length")
        token_counts.append(token_count)
        if eos_count:
            first_eos_positions.append(token_counter(raw.split(HARMONY_EOS, 1)[0]))
        if eos_count > 1:
            repeated_eos_rows += 1
            repeated_eos_tokens += eos_count - 1

        contract_valid = isinstance(parsed, dict) and not errors
        if contract_valid:
            taxonomy["valid"] += 1
        elif isinstance(parsed, dict):
            taxonomy["parsed_contract_invalid"] += 1
        elif eos_count:
            taxonomy["unparsed_with_eos"] += 1
        else:
            taxonomy["unparsed_no_eos"] += 1
        if parsed is None:
            parse_errors[_parse_error_category(errors)] += 1

        assessment = parsed.get("assessment") if isinstance(parsed, dict) else None
        if assessment is None:
            assessments["missing"] += 1
        elif assessment in SOURCE_ASSESSMENTS:
            assessments[str(assessment)] += 1
        else:
            assessments["invalid"] += 1

        harmony["canonical_prefix"] += raw.startswith(HARMONY_ANALYSIS_PREFIX)
        harmony["premature_end_start"] += raw.startswith("<|end|><|start|>")
        final_count = raw.count(HARMONY_FINAL_MARKER)
        harmony["missing_final_marker"] += final_count == 0
        harmony["duplicate_final_marker"] += final_count > 1
        harmony["tool_call_marker"] += "<|call|>" in raw
        harmony["excess_channel_marker"] += raw.count("<|channel|>") > 2
        harmony["extreme_start_repetition"] += raw.count("<|start|>") > 10

    valid_assessment_counts = {
        label: assessments[label] for label in SOURCE_ASSESSMENTS
    }
    dominant = max(
        SOURCE_ASSESSMENTS,
        key=lambda label: (valid_assessment_counts[label], label),
    )
    dominant_count = valid_assessment_counts[dominant]
    parsed_count = sum(valid_assessment_counts.values()) + assessments["invalid"]
    if dominant_count == 0:
        dominant_value: str | None = None
    else:
        dominant_value = dominant

    return {
        "record_count": len(rows),
        "taxonomy": dict(taxonomy),
        "parse_error_categories": dict(parse_errors),
        "generation_length": {
            "configured_max_new_tokens": max_new_tokens,
            "reencoded_token_min": min(token_counts),
            "reencoded_token_p50": _percentile(token_counts, 0.50),
            "reencoded_token_max": max(token_counts),
            "at_or_near_ceiling_without_eos": sum(
                row["raw_generation"].count(HARMONY_EOS) == 0
                and count >= max(0, max_new_tokens - 2)
                for row, count in zip(rows, token_counts, strict=True)
            ),
            "eos_row_count": len(first_eos_positions),
            "first_eos_token_position_min": (
                min(first_eos_positions) if first_eos_positions else None
            ),
            "first_eos_token_position_p50": (
                _percentile(first_eos_positions, 0.50) if first_eos_positions else None
            ),
            "first_eos_token_position_max": (
                max(first_eos_positions) if first_eos_positions else None
            ),
            "repeated_eos_row_count": repeated_eos_rows,
            "repeated_eos_token_count_after_first": repeated_eos_tokens,
        },
        "harmony": dict(harmony),
        "mode_collapse": {
            "assessment_counts": dict(assessments),
            "parsed_assessment_count": parsed_count,
            "distinct_valid_assessment_count": sum(
                count > 0 for count in valid_assessment_counts.values()
            ),
            "dominant_assessment": dominant_value,
            "dominant_assessment_count": dominant_count,
            "dominant_assessment_fraction": (
                dominant_count / parsed_count if parsed_count else None
            ),
            "all_parsed_same_valid_assessment": (
                parsed_count > 0
                and assessments["invalid"] == 0
                and dominant_count == parsed_count
            ),
        },
    }


def _parse_error_category(errors: list[str]) -> str:
    joined = "\n".join(errors).lower()
    if "expecting value" in joined:
        return "expecting_value"
    if "delimiter" in joined:
        return "delimiter"
    if "extra data" in joined:
        return "extra_data"
    if "unterminated string" in joined:
        return "unterminated_string"
    return "other"


def _load_token_counter(adapter_dir: Path) -> TokenCounter:
    from transformers import AutoTokenizer

    validate_no_symlink_components(adapter_dir, description="adapter tokenizer")
    tokenizer = AutoTokenizer.from_pretrained(adapter_dir, local_files_only=True)

    def count_tokens(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    return count_tokens


def _adapter_locations(path: Path) -> tuple[Path, Path]:
    validate_no_symlink_components(path, description="adapter artifact")
    if path.is_dir():
        adapter_file = path / "adapter_model.safetensors"
        adapter_dir = path
    else:
        adapter_file = path
        adapter_dir = path.parent
    validate_no_symlink_components(adapter_file, description="adapter weights")
    if adapter_file.is_symlink() or not adapter_file.is_file():
        raise FileNotFoundError("adapter_model.safetensors is missing")
    return adapter_file, adapter_dir


def _inspect_adapter(path: Path) -> dict[str, Any]:
    import torch
    from safetensors import safe_open

    validate_no_symlink_components(path, description="adapter weights")
    tensor_count = 0
    expert_tensor_count = 0
    attention_tensor_count = 0
    element_count = 0
    nonfinite_element_count = 0
    maximum_absolute_value = 0.0
    with safe_open(path, framework="pt", device="cpu") as tensors:
        for key in tensors.keys():
            tensor = tensors.get_tensor(key).float()
            tensor_count += 1
            expert_tensor_count += ".experts." in key
            attention_tensor_count += ".self_attn." in key
            element_count += tensor.numel()
            finite = torch.isfinite(tensor)
            nonfinite_element_count += int((~finite).sum().item())
            if tensor.numel() and bool(finite.any()):
                finite_values = tensor[finite]
                maximum_absolute_value = max(
                    maximum_absolute_value,
                    float(finite_values.abs().max().item()),
                )
    if not math.isfinite(maximum_absolute_value):
        raise ValueError("adapter aggregate contains a non-finite value")
    return {
        "sha256": _file_sha256(path),
        "tensor_count": tensor_count,
        "expert_tensor_count": expert_tensor_count,
        "attention_tensor_count": attention_tensor_count,
        "element_count": element_count,
        "nonfinite_element_count": nonfinite_element_count,
        "all_finite": nonfinite_element_count == 0,
        "maximum_absolute_value": maximum_absolute_value,
    }


def _inspect_checkpoints(
    paths: Sequence[Path], final_adapter_sha256: str
) -> list[dict[str, Any]]:
    checkpoints: list[dict[str, Any]] = []
    for path in paths:
        adapter_file, checkpoint_dir = _adapter_locations(path)
        state_path = checkpoint_dir / "trainer_state.json"
        state = _load_object(state_path, "checkpoint trainer state")
        step = _nonnegative_int(state.get("global_step"), "checkpoint global_step")
        digest = _file_sha256(adapter_file)
        checkpoints.append(
            {
                "global_step": step,
                "adapter_sha256": digest,
                "matches_final_adapter": digest == final_adapter_sha256,
            }
        )
    checkpoints.sort(key=lambda checkpoint: checkpoint["global_step"])
    if len({checkpoint["global_step"] for checkpoint in checkpoints}) != len(
        checkpoints
    ):
        raise ValueError("checkpoint global steps must be unique")
    return checkpoints


def _artifact_consistency(
    *,
    prediction_analysis: dict[str, Any],
    gate: dict[str, Any],
    manifest: dict[str, Any],
    adapter_sha256: str,
) -> dict[str, Any]:
    gate_record_count = gate.get("record_count")
    schema_pass_rate = gate.get("schema_pass_rate")
    threshold = gate.get("minimum_schema_pass_rate")
    reported_adapter_sha256 = manifest.get("adapter_sha256")
    return {
        "gate_record_count_matches_predictions": (
            type(gate_record_count) is int
            and gate_record_count == prediction_analysis["record_count"]
        ),
        "gate_schema_rate_matches_valid_count": (
            isinstance(schema_pass_rate, (int, float))
            and not isinstance(schema_pass_rate, bool)
            and math.isfinite(float(schema_pass_rate))
            and float(schema_pass_rate)
            == prediction_analysis["taxonomy"]["valid"]
            / prediction_analysis["record_count"]
        ),
        "gate_passed": gate.get("passed") is True,
        "gate_adapter_reload": gate.get("adapter_reload") is True,
        "gate_rate_meets_threshold": (
            isinstance(schema_pass_rate, (int, float))
            and not isinstance(schema_pass_rate, bool)
            and isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and math.isfinite(float(schema_pass_rate))
            and math.isfinite(float(threshold))
            and float(schema_pass_rate) >= float(threshold)
        ),
        "manifest_validation_count_matches_predictions": (
            type(manifest.get("validation_record_count")) is int
            and manifest.get("validation_record_count")
            == prediction_analysis["record_count"]
        ),
        "manifest_adapter_digest_present": isinstance(reported_adapter_sha256, str),
        "manifest_adapter_digest_matches": (
            reported_adapter_sha256 == adapter_sha256
            if isinstance(reported_adapter_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", reported_adapter_sha256) is not None
            else None
        ),
    }


def _wandb_safe_summary(
    prediction_analysis: dict[str, Any],
    adapter: dict[str, Any],
    checkpoints: list[dict[str, Any]],
    consistency: dict[str, Any],
) -> dict[str, Any]:
    taxonomy = prediction_analysis["taxonomy"]
    generation = prediction_analysis["generation_length"]
    harmony = prediction_analysis["harmony"]
    collapse = prediction_analysis["mode_collapse"]
    return {
        "diagnosis/record_count": prediction_analysis["record_count"],
        "diagnosis/valid_count": taxonomy["valid"],
        "diagnosis/parsed_contract_invalid_count": taxonomy["parsed_contract_invalid"],
        "diagnosis/unparsed_with_eos_count": taxonomy["unparsed_with_eos"],
        "diagnosis/unparsed_no_eos_count": taxonomy["unparsed_no_eos"],
        "diagnosis/near_ceiling_no_eos_count": generation[
            "at_or_near_ceiling_without_eos"
        ],
        "diagnosis/canonical_harmony_prefix_count": harmony["canonical_prefix"],
        "diagnosis/premature_end_start_count": harmony["premature_end_start"],
        "diagnosis/dominant_assessment": collapse["dominant_assessment"],
        "diagnosis/dominant_assessment_fraction": collapse[
            "dominant_assessment_fraction"
        ],
        "diagnosis/adapter_tensor_count": adapter["tensor_count"],
        "diagnosis/adapter_expert_tensor_count": adapter["expert_tensor_count"],
        "diagnosis/adapter_nonfinite_element_count": adapter["nonfinite_element_count"],
        "diagnosis/checkpoint_count": len(checkpoints),
        "diagnosis/gate_count_consistent": consistency[
            "gate_record_count_matches_predictions"
        ],
        "diagnosis/gate_rate_consistent": consistency[
            "gate_schema_rate_matches_valid_count"
        ],
    }


def _percentile(values: list[int], quantile: float) -> int:
    ordered = sorted(values)
    index = int((len(ordered) - 1) * quantile)
    return ordered[index]


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _file_sha256(path: Path) -> str:
    validate_no_symlink_components(path, description="hashed artifact")
    if path.is_symlink() or not path.is_file():
        raise ValueError("hashed artifact must be a regular non-symlink file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
