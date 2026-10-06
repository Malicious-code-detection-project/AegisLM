"""Strict configuration contract for source-v2 QLoRA experiments."""

from __future__ import annotations

import json
import hashlib
import math
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from aegislm.artifacts import (
    load_bounded_json_object,
    validate_artifact_output_location,
    validate_no_symlink_components,
)
from aegislm.inference.source import SOURCE_MAX_NEW_TOKENS, SOURCE_MAX_SEQ_LENGTH
from aegislm.training.config import is_git_safe_path
from aegislm.training.source_gate import (
    SOURCE_CANARY_GATE_REPORT_SCHEMA_VERSION,
    GateRunSummary,
    GenerationContract,
    rescore_source_gate_predictions,
)

SOURCE_TRAINING_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["model", "dataset", "training", "canary"],
    "properties": {
        "recipe": {
            "type": "string",
            "enum": [
                "legacy_unsloth",
                "unsloth_v2",
                "peft_split_control",
                "unsloth_fresh_v1",
            ],
        },
        "protocol": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "reasoning_effort",
                "padding_side",
                "pad_token_id",
                "eos_token_ids",
                "do_sample",
            ],
            "properties": {
                "reasoning_effort": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
                "padding_side": {"const": "left"},
                "pad_token_id": {"type": "integer", "minimum": 0},
                "eos_token_ids": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"type": "integer", "minimum": 0},
                },
                "do_sample": {"const": False},
            },
        },
        "model": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "base_model_id",
                "runtime_model_id",
                "revision",
                "cache_dir",
            ],
            "properties": {
                "base_model_id": {"type": "string", "minLength": 1},
                "runtime_model_id": {"type": "string", "minLength": 1},
                "revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                "cache_dir": {"type": "string", "minLength": 1},
            },
        },
        "dataset": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "train_path",
                "train_sha256",
                "validation_path",
                "validation_sha256",
            ],
            "properties": {
                "train_path": {"type": "string", "minLength": 1},
                "train_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "validation_path": {"type": "string", "minLength": 1},
                "validation_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "challenge_path": {"type": "string", "minLength": 1},
                "challenge_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
            },
        },
        "training": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "output_dir",
                "checkpoint_dir",
                "max_seq_length",
                "batch_size",
                "eval_batch_size",
                "gradient_accumulation_steps",
                "epochs",
                "learning_rate",
                "warmup_ratio",
                "lr_scheduler_type",
                "optimizer",
                "weight_decay",
                "lora_r",
                "lora_alpha",
                "lora_dropout",
                "attention_target_modules",
                "expert_target_layers",
                "eval_steps",
                "save_steps",
                "save_total_limit",
                "seed",
            ],
            "properties": {
                "output_dir": {"type": "string", "minLength": 1},
                "checkpoint_dir": {"type": "string", "minLength": 1},
                "max_seq_length": {"type": "integer", "minimum": 128},
                "batch_size": {"type": "integer", "minimum": 1},
                "eval_batch_size": {"type": "integer", "minimum": 1},
                "gradient_accumulation_steps": {"type": "integer", "minimum": 1},
                "epochs": {"type": "integer", "minimum": 1},
                "learning_rate": {"type": "number", "exclusiveMinimum": 0},
                "warmup_ratio": {"type": "number", "minimum": 0, "maximum": 1},
                "lr_scheduler_type": {"type": "string", "minLength": 1},
                "optimizer": {"type": "string", "minLength": 1},
                "weight_decay": {"type": "number", "minimum": 0},
                "lora_r": {"type": "integer", "minimum": 1},
                "lora_alpha": {"type": "integer", "minimum": 1},
                "lora_dropout": {"type": "number", "minimum": 0, "maximum": 1},
                "attention_target_modules": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1},
                },
                "expert_target_layers": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"type": "integer", "minimum": 0},
                },
                "eval_steps": {"type": "integer", "minimum": 1},
                "save_steps": {"type": "integer", "minimum": 1},
                "save_total_limit": {"type": "integer", "minimum": 1},
                "seed": {"type": "integer", "minimum": 0},
            },
        },
        "canary": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "train_size",
                "validation_size",
                "minimum_schema_pass_rate",
                "generation_batch_size",
                "max_new_tokens",
            ],
            "properties": {
                "train_size": {"type": "integer", "minimum": 1},
                "validation_size": {"type": "integer", "minimum": 1},
                "minimum_schema_pass_rate": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "generation_batch_size": {"type": "integer", "minimum": 1},
                "max_new_tokens": {"type": "integer", "minimum": 1},
                "train_selection_strategy": {
                    "type": "string",
                    "enum": [
                        "assessment_round_robin_v1",
                        "target_cwe_assessment_round_robin_v1",
                    ],
                },
            },
        },
    },
}

_VALIDATOR = Draft202012Validator(SOURCE_TRAINING_CONFIG_SCHEMA)
MAX_CANARY_GATE_REPORT_BYTES = 1024 * 1024


def load_source_training_config(path: Path) -> dict[str, Any]:
    """Read and validate a source-v2 experiment config."""
    try:
        config, _digest = load_bounded_json_object(
            path, description="source-v2 training config"
        )
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc
    _reject_nonfinite_numbers(config)
    errors = sorted(_VALIDATOR.iter_errors(config), key=str)
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path) or "<root>"
        raise ValueError(f"{path}: {location}: {error.message}")
    recipe = source_training_recipe(config)
    if recipe != "legacy_unsloth":
        if "protocol" not in config:
            raise ValueError(f"{path}: protocol is required for recipe={recipe}")
        threshold = float(config["canary"]["minimum_schema_pass_rate"])
        if threshold < 0.9:
            raise ValueError(
                f"{path}: non-legacy recipe requires minimum_schema_pass_rate >= 0.9"
            )
        if config["training"]["max_seq_length"] != SOURCE_MAX_SEQ_LENGTH:
            raise ValueError(
                f"{path}: non-legacy recipe requires max_seq_length="
                f"{SOURCE_MAX_SEQ_LENGTH}"
            )
        if config["canary"]["max_new_tokens"] != SOURCE_MAX_NEW_TOKENS:
            raise ValueError(
                f"{path}: non-legacy recipe requires max_new_tokens="
                f"{SOURCE_MAX_NEW_TOKENS}"
            )
    return config


def load_canary_gate_report(path: Path) -> dict[str, Any]:
    """Bounded-load a regular canary promotion report using strict JSON."""
    try:
        report, _digest = load_bounded_json_object(
            path,
            description="canary gate report",
            max_bytes=MAX_CANARY_GATE_REPORT_BYTES,
        )
    except ValueError as exc:
        raise ValueError(f"invalid canary gate report: {path}: {exc}") from exc
    return report


def validate_source_training_paths(config: dict[str, Any]) -> None:
    """Require frozen inputs and Git-ignored/external model artifact paths."""
    for key in ("train_path", "validation_path"):
        path = Path(config["dataset"][key])
        if not path.is_file():
            raise FileNotFoundError(f"dataset.{key} does not exist: {path}")
        digest_key = key.replace("_path", "_sha256")
        actual_digest = file_sha256(path)
        if actual_digest != config["dataset"][digest_key]:
            raise ValueError(
                f"dataset.{key} SHA-256 mismatch: expected "
                f"{config['dataset'][digest_key]}, got {actual_digest}"
            )
    for section, key in (
        ("model", "cache_dir"),
        ("training", "output_dir"),
        ("training", "checkpoint_dir"),
    ):
        path = Path(config[section][key])
        if not is_git_safe_path(str(path)):
            raise ValueError(f"{section}.{key} must be Git-ignored or outside the repo")
        validate_artifact_output_location(path)
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir() or path.is_symlink():
            raise ValueError(f"{section}.{key} must be a real directory")


def file_sha256(path: Path) -> str:
    """Hash a file without loading the complete artifact into memory."""
    validate_no_symlink_components(path, description="hashed file")
    if path.is_symlink() or not path.is_file():
        raise ValueError("hashed file must be a regular non-symlink file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_directory_sha256(path: Path) -> str:
    """Hash every regular file in a symlink-free persisted adapter directory."""
    validate_no_symlink_components(path, description="adapter artifact")
    if not path.is_dir() or path.is_symlink():
        raise ValueError("adapter artifact must be a real directory")
    digest = hashlib.sha256()
    entries = sorted(path.rglob("*"))
    if any(candidate.is_symlink() for candidate in entries):
        raise ValueError("adapter artifact directory must not contain symlinks")
    files = [candidate for candidate in entries if candidate.is_file()]
    if not files:
        raise ValueError("adapter artifact directory is empty")
    for candidate in files:
        relative = candidate.relative_to(path).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        with candidate.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\n")
    return digest.hexdigest()


def create_exclusive_artifact_directory(
    path: Path, *, forbidden_roots: tuple[Path, ...] = ()
) -> None:
    """Create a new Git-safe artifact directory outside protected inputs."""
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"artifact output already exists: {path}")
    validate_artifact_output_location(path)
    resolved = path.resolve(strict=False)
    if not is_git_safe_path(str(resolved)):
        raise ValueError(
            "artifact output must be Git-ignored or outside the repository"
        )
    for root in forbidden_roots:
        if resolved.is_relative_to(root.resolve(strict=False)):
            raise ValueError(
                "artifact output must be outside protected input directories"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()
    if path.is_symlink() or path.resolve() != resolved:
        raise RuntimeError("artifact output path changed during creation")


def reserve_training_stage(
    *,
    adapter_stage: Path,
    checkpoint_stage: Path,
    resume_from_checkpoint: Path | None,
    config_sha256: str,
    stage: str,
) -> None:
    """Reserve a fresh stage or validate an explicitly resumed incomplete stage."""
    if not re.fullmatch(r"[0-9a-f]{64}", config_sha256):
        raise ValueError("training reservation requires a config SHA-256")
    if stage not in {"smoke", "canary", "full"}:
        raise ValueError("training reservation has an invalid stage")
    validate_no_symlink_components(adapter_stage, description="adapter stage")
    validate_no_symlink_components(checkpoint_stage, description="checkpoint stage")
    if resume_from_checkpoint is not None:
        validate_no_symlink_components(
            resume_from_checkpoint, description="resume checkpoint"
        )
    resolved_adapter_stage = adapter_stage.resolve(strict=False)
    resolved_checkpoint_stage = checkpoint_stage.resolve(strict=False)
    if (
        resolved_adapter_stage == resolved_checkpoint_stage
        or resolved_adapter_stage.is_relative_to(resolved_checkpoint_stage)
        or resolved_checkpoint_stage.is_relative_to(resolved_adapter_stage)
    ):
        raise ValueError("adapter and checkpoint stages must not overlap")
    reservation_name = ".aegislm-stage-reservation.json"
    adapter_reservation = adapter_stage / reservation_name
    checkpoint_reservation = checkpoint_stage / reservation_name
    expected = {"config_sha256": config_sha256, "stage": stage}

    if resume_from_checkpoint is None:
        for label, candidate in (
            ("adapter", adapter_stage),
            ("checkpoint", checkpoint_stage),
        ):
            if candidate.exists() or candidate.is_symlink():
                raise FileExistsError(f"{label} stage already exists: {candidate}")
        create_exclusive_artifact_directory(checkpoint_stage)
        _write_stage_reservation(checkpoint_reservation, expected)
        create_exclusive_artifact_directory(adapter_stage)
        _write_stage_reservation(adapter_reservation, expected)
        return

    if not adapter_stage.is_dir() or adapter_stage.is_symlink():
        raise ValueError("resume requires the original reserved adapter stage")
    if not checkpoint_stage.is_dir() or checkpoint_stage.is_symlink():
        raise ValueError("resume requires the original reserved checkpoint stage")
    if {entry.name for entry in adapter_stage.iterdir()} != {reservation_name}:
        raise FileExistsError("resume refuses a finalized or mixed adapter stage")
    if (
        _load_stage_reservation(adapter_reservation) != expected
        or _load_stage_reservation(checkpoint_reservation) != expected
    ):
        raise ValueError("training stage reservation does not match this run")
    checkpoint_entries = {
        entry.name: entry
        for entry in checkpoint_stage.iterdir()
        if entry.name != reservation_name
    }
    invalid_checkpoint_entries = {
        name
        for name, entry in checkpoint_entries.items()
        if re.fullmatch(r"checkpoint-[1-9][0-9]*", name) is None
        or entry.is_symlink()
        or not entry.is_dir()
    }
    if invalid_checkpoint_entries:
        raise FileExistsError("resume refuses a mixed checkpoint stage")
    for checkpoint_entry in checkpoint_entries.values():
        _validate_checkpoint_tree(checkpoint_entry)

    resolved_resume = resume_from_checkpoint.resolve(strict=False)
    trainer_state = resume_from_checkpoint / "trainer_state.json"
    if (
        resume_from_checkpoint.is_symlink()
        or not resume_from_checkpoint.is_dir()
        or resolved_resume.parent != resolved_checkpoint_stage
        or re.fullmatch(r"checkpoint-[1-9][0-9]*", resolved_resume.name) is None
        or trainer_state.is_symlink()
        or not trainer_state.is_file()
    ):
        raise ValueError(
            "resume checkpoint must be a direct configured checkpoint stage child"
        )


def _validate_checkpoint_tree(path: Path) -> None:
    validate_no_symlink_components(path, description="checkpoint tree")
    for entry in path.rglob("*"):
        if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
            raise ValueError("checkpoint tree must contain only real files/directories")


def _write_stage_reservation(path: Path, value: dict[str, str]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _load_stage_reservation(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("invalid training stage reservation")
    try:
        saved = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid training stage reservation") from exc
    if not isinstance(saved, dict):
        raise ValueError("invalid training stage reservation")
    return saved


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-standard JSON constants are not allowed")


def _reject_nonfinite_numbers(value: Any, path: str = "config") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} contains a non-finite number")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_nonfinite_numbers(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_nonfinite_numbers(item, f"{path}[{index}]")


def source_training_config_sha256(config: dict[str, Any]) -> str:
    """Return the canonical fingerprint used to reject stale canary gates."""
    frozen = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(frozen).hexdigest()


def source_training_recipe(config: dict[str, Any]) -> str:
    """Resolve the recipe while preserving the original canary semantics."""
    recipe = config.get("recipe", "legacy_unsloth")
    if not isinstance(recipe, str):
        raise ValueError("source-v2 recipe must be a string")
    return recipe


def source_train_selection_strategy(config: dict[str, Any]) -> str:
    """Resolve the versioned train-canary selector without changing legacy runs."""
    strategy = config["canary"].get(
        "train_selection_strategy", "assessment_round_robin_v1"
    )
    if not isinstance(strategy, str):
        raise ValueError("source-v2 train selection strategy must be a string")
    return strategy


def source_protocol_config(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve the pinned Harmony protocol for legacy and new experiments."""
    protocol = config.get("protocol")
    if protocol is None:
        return {
            "reasoning_effort": "medium",
            "padding_side": "left",
            "pad_token_id": None,
            "eos_token_ids": None,
            "do_sample": False,
        }
    if not isinstance(protocol, dict):
        raise ValueError("source-v2 protocol must be an object")
    return dict(protocol)


def source_protocol_sha256(config: dict[str, Any]) -> str:
    """Fingerprint the resolved Harmony/generation protocol."""
    frozen = json.dumps(
        source_protocol_config(config),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(frozen).hexdigest()


def resolved_source_generation_contract(config: dict[str, Any]) -> GenerationContract:
    """Bind rescoring to the same resolved protocol and configured ceiling."""
    protocol = source_protocol_config(config)
    pad_token_id = protocol["pad_token_id"]
    eos_token_ids = protocol["eos_token_ids"]
    return GenerationContract(
        reasoning_effort=protocol["reasoning_effort"],
        padding_side=protocol["padding_side"],
        pad_token_id=pad_token_id,
        eos_token_ids=(tuple(eos_token_ids) if eos_token_ids is not None else None),
        do_sample=protocol["do_sample"],
        max_new_tokens=int(config["canary"]["max_new_tokens"]),
    )


def validate_canary_gate_report(
    report: dict[str, Any],
    config: dict[str, Any],
    *,
    train_records_sha256: str,
    validation_records_sha256: str,
    adapter_dir: Path,
    prediction_path: Path,
    validation_records: list[Any],
) -> GateRunSummary:
    """Independently verify exact canary evidence before a full run.

    The report is only an index over immutable-by-digest local evidence. Its
    aggregate fields never authorize promotion by themselves: predictions are
    loaded with bounds, matched to the exact held-out record order, and rescored.
    """
    if source_training_recipe(config) == "legacy_unsloth":
        raise ValueError("legacy Unsloth evidence cannot authorize a full stage")
    evidence = rescore_source_gate_predictions(
        records=validation_records,
        prediction_path=prediction_path,
        contract=resolved_source_generation_contract(config),
        require_harmony=source_training_recipe(config) != "legacy_unsloth",
    )
    require_harmony = source_training_recipe(config) != "legacy_unsloth"
    summary = evidence.summary
    configured_record_count = int(config["canary"]["validation_size"])
    if summary.record_count != configured_record_count:
        raise ValueError(
            "full stage requires exact configured held-out evidence: "
            f"expected {configured_record_count}, got {summary.record_count}"
        )
    adapter_digest = artifact_directory_sha256(adapter_dir)
    expected = {
        "report_schema_version": SOURCE_CANARY_GATE_REPORT_SCHEMA_VERSION,
        "promotion_authority": True,
        "recipe": source_training_recipe(config),
        "protocol_sha256": source_protocol_sha256(config),
        "config_sha256": source_training_config_sha256(config),
        "train_records_sha256": train_records_sha256,
        "validation_records_sha256": validation_records_sha256,
        "runtime_model_id": config["model"]["runtime_model_id"],
        "runtime_model_revision": config["model"]["revision"],
        "minimum_schema_pass_rate": config["canary"]["minimum_schema_pass_rate"],
        "generation_batch_size": config["canary"]["generation_batch_size"],
        "max_new_tokens": config["canary"]["max_new_tokens"],
        "record_count": summary.record_count,
        "passed_count": summary.passed_count,
        "parsed_count": summary.parsed_count,
        "harmony_prefix_count": summary.harmony_prefix_count,
        "harmony_final_count": summary.harmony_final_count,
        "finish_reasons": summary.finish_reasons,
        "predictions_sha256": evidence.predictions_sha256,
        "adapter_artifact_sha256": adapter_digest,
        "prediction_path": str(prediction_path),
    }
    mismatches = [key for key, value in expected.items() if report.get(key) != value]
    if report.get("promotion_authority") is not True:
        mismatches.append("promotion_authority")
    if report.get("passed") is not True:
        mismatches.append("passed")
    if report.get("adapter_reload") is not True:
        mismatches.append("adapter_reload")
    _validate_report_counts(
        report,
        summary.record_count,
        mismatches,
        require_harmony=require_harmony,
    )
    for field in ("generation_batch_size", "max_new_tokens"):
        value = report.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            mismatches.append(field)
    reported_threshold = report.get("minimum_schema_pass_rate")
    if isinstance(reported_threshold, bool) or not isinstance(
        reported_threshold, (int, float)
    ):
        mismatches.append("minimum_schema_pass_rate")
    rate = report.get("schema_pass_rate")
    threshold = float(config["canary"]["minimum_schema_pass_rate"])
    expected_rate = summary.passed_count / summary.record_count
    if (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(float(rate))
        or not 0.0 <= float(rate) <= 1.0
        or float(rate) != expected_rate
        or float(rate) < threshold
    ):
        mismatches.append("schema_pass_rate")
    if mismatches:
        raise ValueError(
            "full stage requires a current passing canary gate; mismatched fields: "
            + ", ".join(sorted(set(mismatches)))
        )
    return summary


def _validate_report_counts(
    report: dict[str, Any],
    expected_record_count: int,
    mismatches: list[str],
    *,
    require_harmony: bool,
) -> None:
    count_fields = (
        "record_count",
        "passed_count",
        "parsed_count",
        "harmony_prefix_count",
        "harmony_final_count",
    )
    for field in count_fields:
        value = report.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > expected_record_count
        ):
            mismatches.append(field)
    if report.get("record_count") != expected_record_count or expected_record_count < 1:
        mismatches.append("record_count")
    required_nonzero = ["passed_count", "parsed_count"]
    if require_harmony:
        required_nonzero.extend(("harmony_prefix_count", "harmony_final_count"))
    for field in required_nonzero:
        value = report.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            mismatches.append(field)

    finish_reasons = report.get("finish_reasons")
    if not isinstance(finish_reasons, dict) or not finish_reasons:
        mismatches.append("finish_reasons")
        return
    total = 0
    for reason, count in finish_reasons.items():
        if reason not in {"eos", "length", "unknown"} or (
            isinstance(count, bool) or not isinstance(count, int) or count < 0
        ):
            mismatches.append("finish_reasons")
            return
        total += count
    if total != expected_record_count:
        mismatches.append("finish_reasons")
