"""Shared deterministic generation and strict gate helpers for source-v2."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal, Protocol

from aegislm.artifacts import (
    strict_json_loads,
    validate_artifact_path_plan,
    validate_no_symlink_components,
)
from aegislm.evaluation import parse_model_output, validate_source_assessment
from aegislm.inference.source import extract_harmony_final

HARMONY_ANALYSIS_PREFIX = "<|channel|>analysis<|message|>"
HARMONY_FINAL_MARKER = "<|channel|>final<|message|>"
_HARMONY_EOS_MARKERS = {200002: "<|return|>", 199999: "<|endoftext|>"}
MAX_GATE_PREDICTION_BYTES = 128 * 1024 * 1024
MAX_GATE_PREDICTION_LINE_BYTES = 2 * 1024 * 1024
SOURCE_CANARY_GATE_REPORT_SCHEMA_VERSION = "aegislm.source-canary-gate.v2"


class GateTokenizer(Protocol):
    """Tokenizer operations used by the GPU gate runner."""

    padding_side: str
    pad_token_id: int | None
    eos_token_id: int | None

    def apply_chat_template(self, conversation: Any, **kwargs: Any) -> Any: ...

    def decode(self, token_ids: Any, *, skip_special_tokens: bool) -> str: ...


class GateModel(Protocol):
    """Model operation used by the GPU gate runner."""

    def generate(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class GenerationContract:
    """Resolved generation settings that are bound into gate evidence."""

    reasoning_effort: Literal["low", "medium", "high"]
    padding_side: Literal["left"]
    pad_token_id: int | None
    eos_token_ids: tuple[int, ...] | None
    do_sample: Literal[False]
    max_new_tokens: int


@dataclass(frozen=True)
class TrimmedGeneration:
    """One generated suffix truncated at its first configured EOS token."""

    token_ids: list[int]
    generated_token_count: int
    finish_reason: Literal["eos", "length", "unknown"]
    eos_token_id: int | None


@dataclass(frozen=True)
class GateRunSummary:
    """Aggregate result of a strict held-out gate."""

    record_count: int
    passed_count: int
    schema_pass_rate: float
    parsed_count: int
    harmony_prefix_count: int
    harmony_final_count: int
    finish_reasons: dict[str, int]


@dataclass(frozen=True)
class VerifiedGateEvidence:
    """Independently rescored promotion evidence and its file digest."""

    summary: GateRunSummary
    predictions_sha256: str


def trim_generated_token_ids(
    token_ids: list[int],
    *,
    eos_token_ids: tuple[int, ...] | None,
    max_new_tokens: int,
) -> TrimmedGeneration:
    """Remove batch padding after the first EOS and classify termination."""
    if max_new_tokens <= 0:
        raise ValueError("max_new_tokens must be positive")
    eos_set = set(eos_token_ids or ())
    for index, token_id in enumerate(token_ids):
        if token_id in eos_set:
            trimmed = token_ids[: index + 1]
            return TrimmedGeneration(trimmed, len(trimmed), "eos", token_id)
    reason: Literal["length", "unknown"] = (
        "length" if len(token_ids) >= max_new_tokens else "unknown"
    )
    return TrimmedGeneration(list(token_ids), len(token_ids), reason, None)


def validate_runtime_tokenizer(
    tokenizer: GateTokenizer, contract: GenerationContract
) -> None:
    """Reject tokenizer drift rather than silently rewriting special tokens."""
    if tokenizer.padding_side != contract.padding_side:
        raise ValueError(
            f"tokenizer padding_side mismatch: expected {contract.padding_side}"
        )
    if (
        contract.pad_token_id is not None
        and tokenizer.pad_token_id != contract.pad_token_id
    ):
        raise ValueError(
            f"tokenizer pad_token_id mismatch: expected {contract.pad_token_id}"
        )
    if (
        contract.eos_token_ids is not None
        and tokenizer.eos_token_id not in contract.eos_token_ids
    ):
        raise ValueError("tokenizer eos_token_id is outside the configured EOS set")


def validate_generation_contract(contract: GenerationContract) -> None:
    """Reject incomplete or nonsensical resolved generation settings."""
    if contract.reasoning_effort not in {"low", "medium", "high"}:
        raise ValueError("generation reasoning_effort is invalid")
    if contract.padding_side != "left" or contract.do_sample is not False:
        raise ValueError("source-v2 generation must use deterministic left padding")
    if contract.pad_token_id is not None and (
        isinstance(contract.pad_token_id, bool) or contract.pad_token_id < 0
    ):
        raise ValueError("generation pad_token_id is invalid")
    if contract.eos_token_ids is not None and (
        not contract.eos_token_ids
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in contract.eos_token_ids
        )
        or len(set(contract.eos_token_ids)) != len(contract.eos_token_ids)
    ):
        raise ValueError("generation EOS token IDs are invalid")
    if (
        isinstance(contract.max_new_tokens, bool)
        or not isinstance(contract.max_new_tokens, int)
        or contract.max_new_tokens <= 0
    ):
        raise ValueError("generation max_new_tokens must be positive")


def run_source_schema_gate(
    *,
    model: GateModel,
    tokenizer: GateTokenizer,
    records: list[Any],
    prediction_path: Path,
    batch_size: int,
    contract: GenerationContract,
    device: str = "cuda",
    require_harmony: bool = True,
) -> GateRunSummary:
    """Generate, persist private predictions, and score strict source-v2 output."""
    validate_artifact_path_plan(inputs=(), outputs=(prediction_path,), require_new=True)
    validate_generation_contract(contract)
    if not records:
        raise ValueError("gate records must not be empty")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    validate_runtime_tokenizer(tokenizer, contract)
    prediction_path.parent.mkdir(parents=True, exist_ok=True)
    passed = 0
    parsed = 0
    harmony_prefix = 0
    harmony_final = 0
    finish_reasons: Counter[str] = Counter()
    descriptor, temporary_name = tempfile.mkstemp(
        dir=prediction_path.parent,
        prefix=f".{prediction_path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            for start in range(0, len(records), batch_size):
                batch_records = records[start : start + batch_size]
                inputs = tokenizer.apply_chat_template(
                    [list(record.prompt_messages) for record in batch_records],
                    tokenize=True,
                    add_generation_prompt=True,
                    padding=True,
                    return_tensors="pt",
                    return_dict=True,
                    reasoning_effort=contract.reasoning_effort,
                ).to(device)
                generation_kwargs: dict[str, Any] = {
                    **inputs,
                    "max_new_tokens": contract.max_new_tokens,
                    "do_sample": contract.do_sample,
                    "use_cache": True,
                }
                if contract.pad_token_id is not None:
                    generation_kwargs["pad_token_id"] = contract.pad_token_id
                if contract.eos_token_ids is not None:
                    generation_kwargs["eos_token_id"] = list(contract.eos_token_ids)
                output_ids = model.generate(**generation_kwargs)
                prompt_width = inputs["input_ids"].shape[1]
                for batch_idx, (record, sequence) in enumerate(
                    zip(batch_records, output_ids, strict=True)
                ):
                    prompt_token_ids = inputs["input_ids"][batch_idx].tolist()
                    prompt_attention_mask = inputs["attention_mask"][batch_idx].tolist()
                    generated = sequence[prompt_width:].tolist()
                    trimmed = trim_generated_token_ids(
                        generated,
                        eos_token_ids=contract.eos_token_ids,
                        max_new_tokens=contract.max_new_tokens,
                    )
                    raw = tokenizer.decode(trimmed.token_ids, skip_special_tokens=False)
                    clean = tokenizer.decode(
                        trimmed.token_ids, skip_special_tokens=True
                    )
                    has_prefix = raw.startswith(HARMONY_ANALYSIS_PREFIX)
                    has_final = HARMONY_FINAL_MARKER in raw
                    harmony_prefix += has_prefix
                    harmony_final += has_final
                    finish_reasons[trimmed.finish_reason] += 1
                    artifact: dict[str, Any] = {
                        "id": record.record_id,
                        "input": {
                            "messages": list(record.prompt_messages),
                            "target_cwe": record.target_cwe,
                            "input_ids": prompt_token_ids,
                            "attention_mask": prompt_attention_mask,
                            "decoded_input": tokenizer.decode(
                                prompt_token_ids,
                                skip_special_tokens=False,
                            ),
                        },
                        "raw_generation": raw,
                        "extracted_final": None,
                        "parsed_output": None,
                        "validation_errors": [],
                        "generation": {
                            "generated_token_count": trimmed.generated_token_count,
                            "finish_reason": trimmed.finish_reason,
                            "eos_token_id": trimmed.eos_token_id,
                            "generated_token_ids": trimmed.token_ids,
                            "harmony_prefix": has_prefix,
                            "harmony_final": has_final,
                        },
                    }
                    errors: list[str] = []
                    if require_harmony and not has_prefix:
                        errors.append("missing canonical Harmony analysis prefix")
                    if require_harmony and not has_final:
                        errors.append("missing Harmony final channel")
                    if require_harmony and trimmed.finish_reason != "eos":
                        errors.append("generation did not finish with configured EOS")
                    try:
                        final = extract_harmony_final(raw, fallback=clean)
                        artifact["extracted_final"] = final
                        output = parse_model_output(final)
                        parsed += 1
                        validation = validate_source_assessment(
                            output,
                            source_code=record.source_code,
                            target_cwe=record.target_cwe,
                        )
                        artifact["parsed_output"] = output
                        errors.extend(validation.errors)
                        if validation.ok and not errors:
                            passed += 1
                    except ValueError as exc:
                        errors.append(str(exc))
                    artifact["validation_errors"] = errors
                    stream.write(
                        json.dumps(artifact, ensure_ascii=False, allow_nan=False) + "\n"
                    )
                print(
                    f"[GATE] completed={min(start + batch_size, len(records))}/"
                    f"{len(records)} passed={passed}"
                )
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, prediction_path, follow_symlinks=False)
        except FileExistsError as exc:
            raise FileExistsError(
                f"artifact output already exists: {prediction_path}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return GateRunSummary(
        record_count=len(records),
        passed_count=passed,
        schema_pass_rate=passed / len(records),
        parsed_count=parsed,
        harmony_prefix_count=harmony_prefix,
        harmony_final_count=harmony_final,
        finish_reasons=dict(sorted(finish_reasons.items())),
    )


def rescore_source_gate_predictions(
    *,
    records: list[Any],
    prediction_path: Path,
    contract: GenerationContract,
    require_harmony: bool = True,
) -> VerifiedGateEvidence:
    """Bounded-load and independently score persisted gate predictions.

    Stored ``parsed_output`` and ``validation_errors`` fields are deliberately
    ignored. Record identity and order must exactly match the selected held-out
    records, so an aggregate-only or substituted prediction file cannot grant
    promotion authority.
    """
    if not records:
        raise ValueError("gate records must not be empty")
    validate_generation_contract(contract)
    validate_no_symlink_components(prediction_path, description="gate predictions")
    if prediction_path.is_symlink() or not prediction_path.is_file():
        raise ValueError("gate predictions must be a regular non-symlink file")

    expected_ids = [record.record_id for record in records]
    rows, predictions_sha256 = _load_gate_prediction_rows(prediction_path)
    if len(rows) != len(expected_ids):
        raise ValueError(
            "gate prediction count mismatch: "
            f"expected {len(expected_ids)}, got {len(rows)}"
        )

    passed = 0
    parsed = 0
    harmony_prefix = 0
    harmony_final = 0
    finish_reasons: Counter[str] = Counter()
    for index, (record, expected_id, row) in enumerate(
        zip(records, expected_ids, rows, strict=True), start=1
    ):
        if row.get("id") != expected_id:
            raise ValueError(
                f"gate prediction id/order mismatch at record {index}: "
                f"expected {expected_id!r}"
            )
        raw = row.get("raw_generation")
        if not isinstance(raw, str):
            raise ValueError(
                f"gate prediction {expected_id!r} requires raw_generation text"
            )
        generation = row.get("generation")
        finish_reason = _validate_generation_metadata(
            generation,
            expected_id,
            raw_generation=raw,
            contract=contract,
        )
        finish_reasons[finish_reason] += 1

        has_prefix = raw.startswith(HARMONY_ANALYSIS_PREFIX)
        has_final = HARMONY_FINAL_MARKER in raw
        harmony_prefix += has_prefix
        harmony_final += has_final
        _validate_harmony_metadata(
            generation,
            record_id=expected_id,
            has_prefix=has_prefix,
            has_final=has_final,
        )
        harmony_ok = not require_harmony or (
            has_prefix and has_final and finish_reason == "eos"
        )
        try:
            final = extract_harmony_final(raw, fallback=raw)
            output = parse_model_output(final)
            parsed += 1
            validation = validate_source_assessment(
                output,
                source_code=record.source_code,
                target_cwe=record.target_cwe,
            )
            if validation.ok and harmony_ok:
                passed += 1
        except ValueError:
            pass

    summary = GateRunSummary(
        record_count=len(records),
        passed_count=passed,
        schema_pass_rate=passed / len(records),
        parsed_count=parsed,
        harmony_prefix_count=harmony_prefix,
        harmony_final_count=harmony_final,
        finish_reasons=dict(sorted(finish_reasons.items())),
    )
    return VerifiedGateEvidence(
        summary=summary,
        predictions_sha256=predictions_sha256,
    )


def canary_gate_evidence_fields(
    *,
    summary: GateRunSummary,
    predictions_sha256: str,
    adapter_artifact_sha256: str,
) -> dict[str, Any]:
    """Build the mandatory, versioned promotion-evidence report fields."""
    for label, digest in (
        ("predictions_sha256", predictions_sha256),
        ("adapter_artifact_sha256", adapter_artifact_sha256),
    ):
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return {
        "report_schema_version": SOURCE_CANARY_GATE_REPORT_SCHEMA_VERSION,
        "promotion_authority": True,
        "record_count": summary.record_count,
        "passed_count": summary.passed_count,
        "schema_pass_rate": summary.schema_pass_rate,
        "parsed_count": summary.parsed_count,
        "harmony_prefix_count": summary.harmony_prefix_count,
        "harmony_final_count": summary.harmony_final_count,
        "finish_reasons": dict(summary.finish_reasons),
        "predictions_sha256": predictions_sha256,
        "adapter_artifact_sha256": adapter_artifact_sha256,
    }


def _load_gate_prediction_rows(path: Path) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    total_bytes = 0
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            raw_line = stream.readline(MAX_GATE_PREDICTION_LINE_BYTES + 1)
            if not raw_line:
                break
            total_bytes += len(raw_line)
            if total_bytes > MAX_GATE_PREDICTION_BYTES:
                raise ValueError("gate predictions exceed the total byte limit")
            if len(raw_line) > MAX_GATE_PREDICTION_LINE_BYTES:
                raise ValueError("gate prediction line exceeds the byte limit")
            digest.update(raw_line)
            try:
                row = strict_json_loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(
                    f"invalid gate prediction JSON at line {len(rows) + 1}"
                ) from exc
            if not isinstance(row, dict):
                raise ValueError(
                    f"gate prediction line {len(rows) + 1} must be an object"
                )
            rows.append(row)
    return rows, digest.hexdigest()


def _validate_generation_metadata(
    generation: Any,
    record_id: str,
    *,
    raw_generation: str,
    contract: GenerationContract,
) -> str:
    if not isinstance(generation, dict):
        raise ValueError(f"gate prediction {record_id!r} requires generation metadata")
    token_count = generation.get("generated_token_count")
    if (
        isinstance(token_count, bool)
        or not isinstance(token_count, int)
        or token_count < 1
        or token_count > contract.max_new_tokens
    ):
        raise ValueError(
            f"gate prediction {record_id!r} has invalid generated_token_count"
        )
    finish_reason = generation.get("finish_reason")
    if finish_reason not in {"eos", "length", "unknown"}:
        raise ValueError(f"gate prediction {record_id!r} has invalid finish_reason")
    eos_token_id = generation.get("eos_token_id")
    if eos_token_id is not None and (
        isinstance(eos_token_id, bool) or not isinstance(eos_token_id, int)
    ):
        raise ValueError(f"gate prediction {record_id!r} has invalid eos_token_id")
    if finish_reason == "eos" and eos_token_id is None:
        raise ValueError(f"gate prediction {record_id!r} EOS finish lacks eos_token_id")
    if finish_reason != "eos" and eos_token_id is not None:
        raise ValueError(f"gate prediction {record_id!r} has unexpected eos_token_id")
    token_ids = generation.get("generated_token_ids")
    if contract.eos_token_ids is None:
        # Historical recipes inherited runtime EOS semantics and did not persist
        # IDs. Their bounded count is still checked, but they cannot authorize
        # the non-legacy, independently verifiable promotion path.
        if token_ids is not None:
            _validated_token_ids(token_ids, token_count, record_id)
        return finish_reason
    ids = _validated_token_ids(token_ids, token_count, record_id)
    trimmed = trim_generated_token_ids(
        ids,
        eos_token_ids=contract.eos_token_ids,
        max_new_tokens=contract.max_new_tokens,
    )
    if (
        trimmed.generated_token_count != token_count
        or trimmed.finish_reason != finish_reason
        or trimmed.eos_token_id != eos_token_id
    ):
        raise ValueError(f"gate prediction {record_id!r} termination metadata is false")
    if finish_reason == "eos":
        if not isinstance(eos_token_id, int):
            raise ValueError(f"gate prediction {record_id!r} EOS finish lacks an ID")
        marker = _HARMONY_EOS_MARKERS.get(eos_token_id)
        if marker is None or not raw_generation.rstrip().endswith(marker):
            raise ValueError(
                f"gate prediction {record_id!r} raw EOS marker does not match IDs"
            )
    elif any(
        raw_generation.rstrip().endswith(marker)
        for marker in _HARMONY_EOS_MARKERS.values()
    ):
        raise ValueError(
            f"gate prediction {record_id!r} raw EOS marker lacks token evidence"
        )
    return finish_reason


def _validated_token_ids(token_ids: Any, token_count: int, record_id: str) -> list[int]:
    if (
        not isinstance(token_ids, list)
        or len(token_ids) != token_count
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in token_ids
        )
    ):
        raise ValueError(
            f"gate prediction {record_id!r} requires bounded generated token IDs"
        )
    return token_ids


def _validate_harmony_metadata(
    generation: Any,
    *,
    record_id: str,
    has_prefix: bool,
    has_final: bool,
) -> None:
    if not isinstance(generation, dict):
        raise ValueError(f"gate prediction {record_id!r} requires generation metadata")
    if (
        generation.get("harmony_prefix") is not has_prefix
        or generation.get("harmony_final") is not has_final
    ):
        raise ValueError(f"gate prediction {record_id!r} Harmony flags are false")
