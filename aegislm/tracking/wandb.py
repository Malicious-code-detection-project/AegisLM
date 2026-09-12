"""Privacy-bounded Weights & Biases tracking for AegisLM experiments."""

from __future__ import annotations

import importlib
import math
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aegislm.inference.source import source_generation_protocol_metadata
from aegislm.schemas import SOURCE_ASSESSMENTS

WANDB_PROJECT = "aegislm"
WANDB_GROUP = "source-v2"
SAFE_OUTBOUND_STRING = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+:-]{0,255}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+:-]{0,254}$")
PACKAGE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
ALLOWED_PACKAGES = ("torch", "transformers", "unsloth", "unsloth-zoo")
SOURCE_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SOURCE_CWE = re.compile(r"^CWE-[1-9][0-9]*$")
SOURCE_BASE_MODEL_ID = "openai/gpt-oss-20b"
SOURCE_RUNTIME_MODEL_ID = "unsloth/gpt-oss-20b-unsloth-bnb-4bit"
SOURCE_RUNTIME_MODEL_REVISION = "093fba6992ef5a7152481afec0bdfca1ac486998"
SOURCE_OPTIMIZERS = {"adamw_8bit"}
SOURCE_SCHEDULERS = {"cosine"}
SOURCE_ATTENTION_TARGET_MODULES = {"q_proj", "k_proj", "v_proj", "o_proj"}
SOURCE_TRAINING_RECIPES = {
    "legacy_unsloth",
    "unsloth_v2",
    "peft_split_control",
}
SOURCE_REASONING_EFFORTS = {"low", "medium", "high"}
SOURCE_TRAIN_SELECTION_STRATEGIES = {
    "assessment_round_robin_v1",
    "target_cwe_assessment_round_robin_v1",
}

_ACTIVE_RUN: Any | None = None


def init_wandb_run(
    *,
    job_type: str,
    name: str,
    config: Mapping[str, Any],
    tags: Sequence[str] = (),
    run_id: str | None = None,
    resume: str | None = None,
) -> Any:
    """Start an online W&B run after enforcing the repository privacy policy."""
    global _ACTIVE_RUN
    if _ACTIVE_RUN is not None:
        raise RuntimeError("a W&B run is already active in this process")
    require_wandb_api_key()
    validate_wandb_payload(
        {
            "job_type": job_type,
            "name": name,
            "config": config,
            "tags": tags,
            "run_id": run_id,
            "resume": resume,
        },
        "run",
    )

    # These are policy controls, not user preferences: never upload source, diffs,
    # console output, model weights, or checkpoints from this security project.
    os.environ["WANDB_MODE"] = "online"
    os.environ["WANDB_DISABLE_CODE"] = "true"
    os.environ["WANDB_DISABLE_GIT"] = "true"
    os.environ["WANDB_CONSOLE"] = "off"
    os.environ["WANDB_LOG_MODEL"] = "false"

    wandb = importlib.import_module("wandb")
    original_argv = sys.argv
    try:
        # W&B derives its private Settings._args field directly from sys.argv.
        # Clear it only for initialization so local artifact paths cannot leave.
        sys.argv = original_argv[:1]
        settings = wandb.Settings(
            mode="online",
            console="off",
            disable_code=True,
            disable_git=True,
            save_code=False,
            program="",
            program_abspath="",
            program_relpath="",
            host="",
            x_disable_meta=True,
            x_disable_stats=True,
            x_disable_machine_info=True,
            x_save_requirements=False,
        )
        kwargs: dict[str, Any] = {
            "project": WANDB_PROJECT,
            "group": WANDB_GROUP,
            "job_type": job_type,
            "name": name,
            "config": dict(config),
            "tags": list(tags),
            "settings": settings,
        }
        if run_id is not None:
            kwargs["id"] = run_id
        if resume is not None:
            kwargs["resume"] = resume
        run = wandb.init(**kwargs)
    finally:
        sys.argv = original_argv
    if run is None:
        raise RuntimeError("W&B did not return an active run")
    _ACTIVE_RUN = run
    return run


def require_wandb_api_key() -> None:
    """Fail without ever returning or displaying the credential."""
    if not os.environ.get("WANDB_API_KEY", "").strip():
        raise RuntimeError(
            "WANDB_API_KEY is required for --wandb; add it to the repository .env"
        )


def _reject_sensitive_config(value: Any, path: str = "config") -> None:
    if isinstance(value, Mapping):
        for index, (key, nested) in enumerate(value.items()):
            key_text = str(key)
            if _looks_sensitive_key(key_text):
                raise ValueError(
                    "sensitive field is not allowed in W&B payload: "
                    f"{path}.item_{index}.key"
                )
            _reject_sensitive_config(nested, f"{path}.item_{index}.value")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_sensitive_config(nested, f"{path}.{index}")


def _looks_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return (
        "api_key" in normalized
        or "apikey" in normalized
        or normalized == "token"
        or normalized.endswith("_token")
        or normalized == "password"
        or normalized.endswith("_password")
        or normalized == "passwd"
        or normalized.endswith("_passwd")
        or normalized == "secret"
        or normalized.endswith("_secret")
        or normalized
        in {
            "access_key",
            "auth",
            "authorization",
            "cookie",
            "credential",
            "credentials",
            "private_key",
            "secret_key",
            "session_cookie",
        }
        or normalized.endswith("_credentials")
        or normalized.endswith("_credential")
        or normalized.endswith("_private_key")
    )


def validate_wandb_payload(value: Any, path: str = "payload") -> None:
    """Reject credentials and unsupported values before outbound logging."""
    _reject_sensitive_config(value, path)
    credential_values = tuple(
        secret
        for key in ("WANDB_API_KEY", "HF_TOKEN", "AEGISLM_INFERENCE_API_KEY")
        if (secret := os.environ.get(key, "").strip())
    )
    _reject_credential_values(value, credential_values, path)
    _reject_unsafe_values(value, path)


def _reject_unsafe_values(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for index, (key, nested) in enumerate(value.items()):
            if not isinstance(key, str):
                raise ValueError(
                    f"W&B payload keys must be strings: {path}.item_{index}.key"
                )
            _reject_unsafe_values(nested, f"{path}.item_{index}.value")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_unsafe_values(nested, f"{path}.{index}")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite value is not allowed in W&B payload: {path}")
    elif isinstance(value, str) and SAFE_OUTBOUND_STRING.fullmatch(value) is None:
        raise ValueError(f"unsafe string is not allowed in W&B payload: {path}")
    elif value is not None and not isinstance(value, (str, bool, int, float)):
        raise ValueError(f"unsupported value is not allowed in W&B payload: {path}")


def _reject_credential_values(
    value: Any, credential_values: tuple[str, ...], path: str
) -> None:
    if isinstance(value, Mapping):
        for index, (key, nested) in enumerate(value.items()):
            key_text = str(key)
            if any(credential in key_text for credential in credential_values):
                raise ValueError(
                    "credential value is not allowed in W&B payload: "
                    f"{path}.item_{index}.key"
                )
            _reject_credential_values(
                nested, credential_values, f"{path}.item_{index}.value"
            )
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_credential_values(nested, credential_values, f"{path}.{index}")
    elif isinstance(value, str) and any(
        credential in value for credential in credential_values
    ):
        raise ValueError(f"credential value is not allowed in W&B payload: {path}")


def log_wandb_payload(
    run: Any, payload: Mapping[str, Any], *, step: int | None = None
) -> None:
    """Validate and log a scalar/table-free payload."""
    validate_wandb_payload(payload)
    if step is None:
        run.log(dict(payload))
    else:
        run.log(dict(payload), step=step)


def update_wandb_summary(run: Any, payload: Mapping[str, Any]) -> None:
    """Validate and update the remote run summary."""
    validate_wandb_payload(payload)
    run.summary.update(dict(payload))


def safe_training_log_payload(logs: Mapping[str, Any]) -> dict[str, float]:
    """Select only finite numeric learning-curve fields from Trainer logs."""
    payload: dict[str, float] = {}
    for key in ("loss", "learning_rate", "grad_norm", "epoch"):
        value = logs.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        numeric = float(value)
        if math.isfinite(numeric):
            payload[f"training/{key}"] = numeric
    return payload


def source_evaluation_wandb_config(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Project only domain-checked source-v2 provenance into W&B config."""
    provenance = _mapping(summary.get("provenance"), "provenance")
    role = _choice(provenance.get("run_role"), "run_role", {"base", "adapter"})
    adapter_artifact_sha256 = _optional_digest(
        provenance.get("adapter_artifact_sha256"), "adapter artifact"
    )
    adapter_sha256 = _optional_digest(
        provenance.get("adapter_sha256"), "adapter weights"
    )
    if role == "base" and (
        adapter_artifact_sha256 is not None or adapter_sha256 is not None
    ):
        raise ValueError("adapter fingerprint does not match the source-v2 run role")
    if role == "adapter" and adapter_artifact_sha256 is None:
        raise ValueError(
            "adapter evaluation requires a complete adapter artifact fingerprint"
        )
    packages = _mapping(provenance.get("packages"), "packages")
    if set(packages) - set(ALLOWED_PACKAGES):
        raise ValueError("source-v2 provenance contains an unsupported package key")
    safe_packages = {
        package: _matched_string(packages[package], "package version", PACKAGE_VERSION)
        for package in ALLOWED_PACKAGES
        if package in packages
    }
    if not safe_packages:
        raise ValueError("source-v2 provenance requires package versions")
    model_id = _matched_string(summary.get("model_id"), "model_id", MODEL_ID)
    if model_id == "mixed":
        raise ValueError("source-v2 W&B evaluation requires one model ID")
    backend = _choice(
        provenance.get("backend"),
        "backend",
        {"mock", "openai-compatible", "unsloth"},
    )
    mode = _choice(provenance.get("mode"), "mode", {"raw", "constrained"})
    max_new_tokens = _positive_int(provenance.get("max_new_tokens"), "max_new_tokens")
    max_seq_length = _positive_int(provenance.get("max_seq_length"), "max_seq_length")
    temperature = _bounded_number(
        provenance.get("temperature"), "temperature", 0.0, 2.0
    )
    expected_protocol = source_generation_protocol_metadata(
        backend=backend,
        mode=mode,
        max_new_tokens=max_new_tokens,
        max_seq_length=max_seq_length,
        temperature=temperature,
    )
    protocol_keys = tuple(expected_protocol)
    if any(provenance.get(key) != expected_protocol[key] for key in protocol_keys):
        raise ValueError("source-v2 generation protocol provenance is inconsistent")
    return {
        "model_id": model_id,
        "case_set_sha256": _digest(summary.get("case_set_sha256"), "case set"),
        "gold_sha256": _digest(summary.get("gold_sha256"), "gold"),
        "predictions_sha256": _digest(
            summary.get("predictions_sha256"), "prediction file"
        ),
        "provenance": {
            "backend": backend,
            "mode": mode,
            "max_new_tokens": max_new_tokens,
            "max_seq_length": max_seq_length,
            "temperature": temperature,
            **expected_protocol,
            "base_model_revision": _matched_string(
                provenance.get("base_model_revision"),
                "base_model_revision",
                GIT_REVISION,
            ),
            "resolved_model_id": _matched_string(
                provenance.get("resolved_model_id"), "resolved_model_id", MODEL_ID
            ),
            "adapter_artifact_sha256": adapter_artifact_sha256,
            "adapter_sha256": adapter_sha256,
            "tokenizer_contract_sha256": _digest(
                provenance.get("tokenizer_contract_sha256"), "tokenizer contract"
            ),
            "hardware_signature": _digest(
                provenance.get("hardware_signature"), "hardware signature"
            ),
            "run_role": role,
            "packages": safe_packages,
            "challenge_file_sha256": _digest(
                provenance.get("challenge_file_sha256"), "challenge file"
            ),
            "challenge_records_sha256": _digest(
                provenance.get("challenge_records_sha256"), "challenge records"
            ),
        },
    }


def source_training_wandb_config(
    config: Mapping[str, Any], stage: str, gate_only: bool
) -> dict[str, Any]:
    """Project a source-v2 training config through strict semantic domains."""
    if type(gate_only) is not bool:
        raise ValueError("source-v2 gate_only must be boolean")
    safe_stage = _choice(stage, "stage", {"canary", "full"})
    model = _mapping(config.get("model"), "training model")
    dataset = _mapping(config.get("dataset"), "training dataset")
    training = _mapping(config.get("training"), "training parameters")
    canary = _mapping(config.get("canary"), "canary parameters")
    recipe = _choice(
        config.get("recipe", "legacy_unsloth"),
        "recipe",
        SOURCE_TRAINING_RECIPES,
    )
    raw_protocol = config.get("protocol")
    if raw_protocol is None:
        if recipe != "legacy_unsloth":
            raise ValueError("non-legacy source-v2 recipe requires protocol")
        protocol: Mapping[str, Any] = {
            "reasoning_effort": "medium",
            "padding_side": "left",
            "pad_token_id": None,
            "eos_token_ids": None,
            "do_sample": False,
        }
    else:
        protocol = _mapping(raw_protocol, "protocol")
    base_model_id = _choice(
        model.get("base_model_id"), "base_model_id", {SOURCE_BASE_MODEL_ID}
    )
    runtime_model_id = _choice(
        model.get("runtime_model_id"),
        "runtime_model_id",
        {SOURCE_RUNTIME_MODEL_ID},
    )
    modules_value = training.get("attention_target_modules")
    if (
        not isinstance(modules_value, list)
        or not modules_value
        or not all(
            isinstance(module, str) and module in SOURCE_ATTENTION_TARGET_MODULES
            for module in modules_value
        )
        or len(set(modules_value)) != len(modules_value)
    ):
        raise ValueError("source-v2 attention target modules are outside the domain")
    layers_value = training.get("expert_target_layers")
    if (
        not isinstance(layers_value, list)
        or not layers_value
        or not all(type(layer) is int and 0 <= layer <= 23 for layer in layers_value)
        or len(set(layers_value)) != len(layers_value)
    ):
        raise ValueError("source-v2 expert target layers are outside the domain")
    safe_training: dict[str, Any] = {
        "max_seq_length": _bounded_int(
            training.get("max_seq_length"), "max_seq_length", 128, 32768
        ),
        "batch_size": _bounded_int(training.get("batch_size"), "batch_size", 1, 4096),
        "eval_batch_size": _bounded_int(
            training.get("eval_batch_size"), "eval_batch_size", 1, 4096
        ),
        "gradient_accumulation_steps": _bounded_int(
            training.get("gradient_accumulation_steps"),
            "gradient_accumulation_steps",
            1,
            65536,
        ),
        "epochs": _bounded_int(training.get("epochs"), "epochs", 1, 100),
        "learning_rate": _bounded_number(
            training.get("learning_rate"), "learning_rate", 0.0, 1.0
        ),
        "warmup_ratio": _bounded_number(
            training.get("warmup_ratio"), "warmup_ratio", 0.0, 1.0
        ),
        "lr_scheduler_type": _choice(
            training.get("lr_scheduler_type"),
            "lr_scheduler_type",
            SOURCE_SCHEDULERS,
        ),
        "optimizer": _choice(training.get("optimizer"), "optimizer", SOURCE_OPTIMIZERS),
        "weight_decay": _bounded_number(
            training.get("weight_decay"), "weight_decay", 0.0, 10.0
        ),
        "lora_r": _bounded_int(training.get("lora_r"), "lora_r", 1, 4096),
        "lora_alpha": _bounded_int(training.get("lora_alpha"), "lora_alpha", 1, 65536),
        "lora_dropout": _bounded_number(
            training.get("lora_dropout"), "lora_dropout", 0.0, 1.0
        ),
        "attention_target_modules": list(modules_value),
        "expert_target_layers": list(layers_value),
        "eval_steps": _bounded_int(
            training.get("eval_steps"), "eval_steps", 1, 1_000_000_000
        ),
        "save_steps": _bounded_int(
            training.get("save_steps"), "save_steps", 1, 1_000_000_000
        ),
        "save_total_limit": _bounded_int(
            training.get("save_total_limit"), "save_total_limit", 1, 1_000_000
        ),
        "seed": _bounded_int(training.get("seed"), "seed", 0, 2**32 - 1),
    }
    projected = {
        "stage": safe_stage,
        "gate_only": gate_only,
        "recipe": recipe,
        "protocol": {
            "reasoning_effort": _choice(
                protocol.get("reasoning_effort"),
                "reasoning_effort",
                SOURCE_REASONING_EFFORTS,
            ),
            "padding_side": _choice(
                protocol.get("padding_side"), "padding_side", {"left"}
            ),
            "pad_token_id": _optional_nonnegative_int(
                protocol.get("pad_token_id"), "pad_token_id"
            ),
            "eos_token_ids": _optional_token_id_list(
                protocol.get("eos_token_ids"), "eos_token_ids"
            ),
            "do_sample": _false_boolean(protocol.get("do_sample"), "do_sample"),
        },
        "base_model_id": base_model_id,
        "runtime_model_id": runtime_model_id,
        "runtime_model_revision": _choice(
            model.get("revision"),
            "runtime_model_revision",
            {SOURCE_RUNTIME_MODEL_REVISION},
        ),
        "train_file_sha256": _digest(dataset.get("train_sha256"), "train file"),
        "validation_file_sha256": _digest(
            dataset.get("validation_sha256"), "validation file"
        ),
        "training": safe_training,
        "canary": {
            "train_selection_strategy": _choice(
                canary.get("train_selection_strategy", "assessment_round_robin_v1"),
                "train_selection_strategy",
                SOURCE_TRAIN_SELECTION_STRATEGIES,
            ),
            "train_size": _bounded_int(
                canary.get("train_size"), "canary train_size", 1, 10_000_000
            ),
            "validation_size": _bounded_int(
                canary.get("validation_size"),
                "canary validation_size",
                1,
                10_000_000,
            ),
            "minimum_schema_pass_rate": _bounded_number(
                canary.get("minimum_schema_pass_rate"),
                "minimum_schema_pass_rate",
                0.0,
                1.0,
            ),
            "generation_batch_size": _bounded_int(
                canary.get("generation_batch_size"),
                "generation_batch_size",
                1,
                4096,
            ),
            "max_new_tokens": _bounded_int(
                canary.get("max_new_tokens"), "max_new_tokens", 1, 32768
            ),
        },
    }
    validate_wandb_payload(projected)
    return projected


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"source-v2 {label} must be a string-keyed object")
    return value


def _optional_nonnegative_int(value: Any, label: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"source-v2 {label} must be a non-negative integer or null")
    return value


def _optional_token_id_list(value: Any, label: str) -> list[int] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or not value
        or len(set(value)) != len(value)
        or not all(type(item) is int and item >= 0 for item in value)
    ):
        raise ValueError(f"source-v2 {label} must contain unique token IDs")
    return list(value)


def _false_boolean(value: Any, label: str) -> bool:
    if value is not False:
        raise ValueError(f"source-v2 {label} must be false")
    return False


def _choice(value: Any, label: str, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"source-v2 {label} is outside the allowed domain")
    return value


def _matched_string(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"source-v2 {label} has an unsafe format")
    return value


def _digest(value: Any, label: str) -> str:
    return _matched_string(value, label, SHA256)


def _optional_digest(value: Any, label: str) -> str | None:
    return None if value is None else _digest(value, label)


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"source-v2 {label} must be a positive integer")
    return value


def _bounded_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"source-v2 {label} is outside the allowed range")
    return value


def _bounded_number(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"source-v2 {label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"source-v2 {label} is outside the allowed range")
    return number


def _optional_bounded_number(
    value: Any, label: str, minimum: float, maximum: float
) -> float | None:
    return None if value is None else _bounded_number(value, label, minimum, maximum)


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"source-v2 {label} must be boolean")
    return value


def _optional_boolean(value: Any, label: str) -> bool | None:
    return None if value is None else _boolean(value, label)


def finish_active_wandb(exit_code: int) -> None:
    """Finish the active run exactly once."""
    global _ACTIVE_RUN
    run = _ACTIVE_RUN
    _ACTIVE_RUN = None
    if run is not None:
        run.finish(exit_code=exit_code)


def wandb_run_reference(run: Any | None) -> dict[str, Any] | None:
    """Return non-secret linkage metadata for a local experiment manifest."""
    if run is None:
        return None
    return {
        "project": WANDB_PROJECT,
        "group": WANDB_GROUP,
        "run_id": getattr(run, "id", None),
        "run_url": getattr(run, "url", None),
    }


def git_reference(repo_root: Path) -> dict[str, Any]:
    """Return commit identity and dirty state without uploading Git contents."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}
    return {"commit": commit or None, "dirty": bool(status)}


def source_evaluation_wandb_payload(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare and validate all evaluation data before a W&B run starts."""
    metrics = _mapping(summary.get("metrics"), "evaluation metrics")
    payload: dict[str, Any] = {
        "evaluation/accuracy": _bounded_number(
            metrics.get("accuracy"), "accuracy", 0.0, 1.0
        ),
        "evaluation/macro_f1": _bounded_number(
            metrics.get("macro_f1"), "macro_f1", 0.0, 1.0
        ),
        "evaluation/json_parse_success_rate": _bounded_number(
            metrics.get("json_parse_success_rate"),
            "json_parse_success_rate",
            0.0,
            1.0,
        ),
        "evaluation/schema_validation_pass_rate": _bounded_number(
            metrics.get("schema_validation_pass_rate"),
            "schema_validation_pass_rate",
            0.0,
            1.0,
        ),
        "evaluation/field_completeness": _bounded_number(
            metrics.get("field_completeness"), "field_completeness", 0.0, 1.0
        ),
        "evaluation/safety_violation_count": _bounded_int(
            metrics.get("safety_violation_count"),
            "safety_violation_count",
            0,
            10_000_000,
        ),
        "evaluation/safety_evaluated_count": _bounded_int(
            metrics.get("safety_evaluated_count"),
            "safety_evaluated_count",
            0,
            10_000_000,
        ),
        "evaluation/evidence_precision": _optional_bounded_number(
            metrics.get("evidence_precision"), "evidence_precision", 0.0, 1.0
        ),
        "evaluation/evidence_recall": _optional_bounded_number(
            metrics.get("evidence_recall"), "evidence_recall", 0.0, 1.0
        ),
        "evaluation/evidence_f1": _optional_bounded_number(
            metrics.get("evidence_f1"), "evidence_f1", 0.0, 1.0
        ),
        "evaluation/grounded_span_rate": _optional_bounded_number(
            metrics.get("grounded_span_rate"), "grounded_span_rate", 0.0, 1.0
        ),
        "evaluation/missing_span_count": _bounded_int(
            metrics.get("missing_span_count"), "missing_span_count", 0, 10_000_000
        ),
        "evaluation/hallucinated_span_count": _bounded_int(
            metrics.get("hallucinated_span_count"),
            "hallucinated_span_count",
            0,
            10_000_000,
        ),
        "evaluation/mean_latency_ms": _optional_bounded_number(
            metrics.get("mean_latency_ms"), "mean_latency_ms", 0.0, 86_400_000.0
        ),
    }
    recalls = _mapping(metrics.get("recall_by_label"), "recall_by_label")
    for label, recall in recalls.items():
        safe_label = _choice(label, "assessment label", set(SOURCE_ASSESSMENTS))
        payload[f"evaluation/recall/{safe_label}"] = _bounded_number(
            recall, "label recall", 0.0, 1.0
        )
    case_columns = [
        "record_id",
        "target_cwe",
        "expected_assessment",
        "predicted_assessment",
        "correct",
        "json_parse_success",
        "schema_valid",
        "safety_pass",
        "missing_span_count",
        "hallucinated_span_count",
        "latency_ms",
    ]
    cases = summary.get("cases")
    if not isinstance(cases, list):
        raise ValueError("source-v2 evaluation cases must be an array")
    case_data: list[list[Any]] = []
    for index, case_value in enumerate(cases):
        case = _mapping(case_value, f"evaluation case {index}")
        predicted = case.get("predicted_assessment")
        safe_predicted = predicted if predicted in SOURCE_ASSESSMENTS else "invalid"
        case_data.append(
            [
                _matched_string(case.get("record_id"), "record_id", SOURCE_RECORD_ID),
                _matched_string(case.get("target_cwe"), "target_cwe", SOURCE_CWE),
                _choice(
                    case.get("expected_assessment"),
                    "expected_assessment",
                    set(SOURCE_ASSESSMENTS),
                ),
                safe_predicted,
                _boolean(case.get("correct"), "correct"),
                _boolean(case.get("json_parse_success"), "json_parse_success"),
                _boolean(case.get("schema_valid"), "schema_valid"),
                _optional_boolean(case.get("safety_pass"), "safety_pass"),
                _bounded_int(
                    case.get("missing_span_count"),
                    "case missing_span_count",
                    0,
                    10_000_000,
                ),
                _bounded_int(
                    case.get("hallucinated_span_count"),
                    "case hallucinated_span_count",
                    0,
                    10_000_000,
                ),
                _optional_bounded_number(
                    case.get("latency_ms"), "case latency_ms", 0.0, 86_400_000.0
                ),
            ]
        )
    per_cwe = _mapping(metrics.get("per_cwe"), "per_cwe")
    per_cwe_data: list[list[Any]] = []
    for cwe, row_value in per_cwe.items():
        row = _mapping(row_value, "per_cwe row")
        per_cwe_data.append(
            [
                _matched_string(cwe, "per_cwe target_cwe", SOURCE_CWE),
                _bounded_int(row.get("count"), "per_cwe count", 1, 10_000_000),
                _bounded_number(row.get("accuracy"), "per_cwe accuracy", 0.0, 1.0),
            ]
        )
    prepared = {
        "metrics": payload,
        "case_columns": case_columns,
        "case_data": case_data,
        "per_cwe_data": per_cwe_data,
    }
    validate_wandb_payload(prepared)
    return prepared


def log_source_evaluation(run: Any, summary: Mapping[str, Any]) -> None:
    """Re-project and log a source-free evaluation summary."""
    prepared = source_evaluation_wandb_payload(summary)
    wandb = importlib.import_module("wandb")
    payload = dict(_mapping(prepared.get("metrics"), "prepared metrics"))
    payload["evaluation/cases"] = wandb.Table(
        columns=prepared["case_columns"],
        data=prepared["case_data"],
    )
    payload["evaluation/per_cwe"] = wandb.Table(
        columns=["target_cwe", "count", "accuracy"], data=prepared["per_cwe_data"]
    )
    run.log(payload)


def source_comparison_wandb_payload(comparison: Mapping[str, Any]) -> dict[str, Any]:
    """Project comparison aggregates through fixed semantic domains."""
    outcome = _choice(
        comparison.get("outcome"),
        "comparison outcome",
        {"improved", "equivalent", "regressed"},
    )
    mode = _choice(
        comparison.get("comparison_mode"),
        "comparison mode",
        {"decision_only", "full_report"},
    )
    deltas = _mapping(comparison.get("deltas"), "comparison deltas")
    expected_deltas = {
        "macro_f1",
        "evidence_f1",
        "accuracy",
        "schema_validation_pass_rate",
    }
    if set(deltas) != expected_deltas:
        raise ValueError("source-v2 comparison delta keys are outside the domain")
    quality_targets = _mapping(
        comparison.get("quality_targets"), "comparison quality targets"
    )
    expected_targets = {
        "json_parse_success_rate",
        "schema_validation_pass_rate",
        "grounded_span_rate",
        "safety_violation_count",
    }
    if set(quality_targets) != expected_targets:
        raise ValueError("source-v2 quality target keys are outside the domain")
    reasons = _mapping(
        comparison.get("regression_reasons"), "comparison regression reasons"
    )
    if set(reasons) != {"label_recall", "major_cwe_accuracy"}:
        raise ValueError("source-v2 regression reason keys are outside the domain")
    label_reasons = _mapping(reasons["label_recall"], "label regression reasons")
    for label, delta in label_reasons.items():
        _choice(label, "regression assessment label", set(SOURCE_ASSESSMENTS))
        _bounded_number(delta, "label regression delta", -1.0, 0.0)
    cwe_reasons = _mapping(reasons["major_cwe_accuracy"], "CWE regression reasons")
    for cwe, delta in cwe_reasons.items():
        _matched_string(cwe, "regression target_cwe", SOURCE_CWE)
        _bounded_number(delta, "CWE regression delta", -1.0, 0.0)
    payload: dict[str, Any] = {
        "comparison/outcome": outcome,
        "comparison/mode": mode,
    }
    for metric in sorted(expected_deltas):
        value = deltas[metric]
        payload[f"comparison/delta/{metric}"] = (
            _optional_bounded_number(value, f"comparison delta {metric}", -1.0, 1.0)
            if metric == "evidence_f1"
            else _bounded_number(value, f"comparison delta {metric}", -1.0, 1.0)
        )
    for target in sorted(expected_targets):
        payload[f"comparison/quality_target/{target}"] = _boolean(
            quality_targets[target], f"quality target {target}"
        )
    payload["comparison/label_regression_count"] = len(label_reasons)
    payload["comparison/cwe_regression_count"] = len(cwe_reasons)
    validate_wandb_payload(payload)
    return payload


def log_source_comparison(run: Any, comparison: Mapping[str, Any]) -> None:
    """Re-project and log a validated base/adapter comparison."""
    payload = source_comparison_wandb_payload(comparison)
    log_wandb_payload(run, payload)
