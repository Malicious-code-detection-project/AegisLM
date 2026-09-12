"""Train the source-v2 PEFT split-expert control with the pinned Unsloth loader.

This is deliberately not a vanilla Transformers model-loading path.  The pinned
bitsandbytes checkpoint exposes GPT-OSS experts as per-expert Linear4bit modules
only after Unsloth patches Transformers.  The controlled variable is adapter
preparation/injection: this script uses PEFT directly instead of
FastLanguageModel.get_peft_model.
"""

from __future__ import annotations

import argparse
import gc
import importlib.metadata as importlib_metadata
import json
import math
import re
import shlex
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.environment import load_project_env  # noqa: E402

load_project_env(REPO_ROOT)

from aegislm.datasets import (  # noqa: E402
    load_source_records,
    records_sha256,
    select_source_train_canary,
    select_stratified_canary,
    validate_source_split_integrity,
)
from aegislm.training.source import (  # noqa: E402
    build_unsloth_moe_target_regex,
    load_persisted_source_tokenizer,
    supervised_token_count,
    tokenizer_contract_sha256,
    tokenize_source_training_record,
)
from aegislm.training.source_config import (  # noqa: E402
    artifact_directory_sha256,
    create_exclusive_artifact_directory,
    file_sha256,
    load_canary_gate_report,
    load_source_training_config,
    reserve_training_stage,
    source_protocol_sha256,
    source_train_selection_strategy,
    source_training_config_sha256,
    validate_canary_gate_report,
    validate_source_training_paths,
)
from aegislm.training.source_gate import (  # noqa: E402
    GenerationContract,
    GateRunSummary,
    canary_gate_evidence_fields,
    run_source_schema_gate,
)

RECIPE = "peft_split_control"
BASE_MODEL_ID = "openai/gpt-oss-20b"
RUNTIME_MODEL_ID = "unsloth/gpt-oss-20b-unsloth-bnb-4bit"
RUNTIME_REVISION = "093fba6992ef5a7152481afec0bdfca1ac486998"
TRAIN_PATH = "data/processed/phase-f-source-v5-r1/train.jsonl"
TRAIN_SHA256 = "0c7bf1802c014eb6a5fec4de23e855308ac8558d387e0a28e482c4ae45e428ff"
VALIDATION_PATH = "data/processed/phase-f-source-v5-r1/validation.jsonl"
VALIDATION_SHA256 = "52c92aeb8e0c6c896bbad4256d6cb42a1cec42f22d8a7d87062a6f367549b6fe"
ATTENTION_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]
EXPERT_TARGET_LAYERS = [7, 15, 23]
EXPECTED_HIDDEN_LAYERS = 24
EXPECTED_LOCAL_EXPERTS = 32
EXPECTED_TARGET_MODULES = 288
EXPECTED_TRAINABLE_PARAMETERS = 15_040_512
EXPECTED_ADAPTER_TENSORS = 576
EXPECTED_ATTENTION_TENSORS = 192
EXPECTED_EXPERT_TENSORS = 384
PAD_TOKEN_ID = 200_017
RETURN_TOKEN_ID = 200_002
END_OF_TEXT_TOKEN_ID = 199_999
REASONING_EFFORT: Literal["low"] = "low"
PROTOCOL = {
    "reasoning_effort": REASONING_EFFORT,
    "padding_side": "left",
    "pad_token_id": PAD_TOKEN_ID,
    "eos_token_ids": [RETURN_TOKEN_ID, END_OF_TEXT_TOKEN_ID],
    "do_sample": False,
}


def load_peft_control_config(path: Path) -> dict[str, Any]:
    """Load the common source-v2 contract plus the fixed control recipe."""
    config = load_source_training_config(path)
    if config.get("recipe") != RECIPE:
        raise ValueError(f"{path}: recipe must be {RECIPE}")
    validate_peft_control_contract(config)
    return config


def validate_peft_control_contract(config: dict[str, Any]) -> None:
    """Reject drift that would make this run incomparable to the frozen canary."""
    expected: tuple[tuple[str, str, Any], ...] = (
        ("model", "base_model_id", BASE_MODEL_ID),
        ("model", "runtime_model_id", RUNTIME_MODEL_ID),
        ("model", "revision", RUNTIME_REVISION),
        ("model", "cache_dir", "models/cache"),
        ("dataset", "train_path", TRAIN_PATH),
        ("dataset", "train_sha256", TRAIN_SHA256),
        ("dataset", "validation_path", VALIDATION_PATH),
        ("dataset", "validation_sha256", VALIDATION_SHA256),
        ("training", "max_seq_length", 2048),
        ("training", "batch_size", 2),
        ("training", "eval_batch_size", 2),
        ("training", "gradient_accumulation_steps", 4),
        ("training", "epochs", 1),
        ("training", "learning_rate", 0.0002),
        ("training", "warmup_ratio", 0.03),
        ("training", "lr_scheduler_type", "cosine"),
        ("training", "optimizer", "adamw_8bit"),
        ("training", "weight_decay", 0.01),
        ("training", "lora_r", 8),
        ("training", "lora_alpha", 16),
        ("training", "lora_dropout", 0.05),
        ("training", "attention_target_modules", ATTENTION_TARGETS),
        ("training", "expert_target_layers", EXPERT_TARGET_LAYERS),
        ("training", "eval_steps", 25),
        ("training", "save_steps", 25),
        ("training", "save_total_limit", 6),
        ("training", "seed", 3407),
        ("canary", "train_size", 1000),
        ("canary", "validation_size", 40),
        ("canary", "minimum_schema_pass_rate", 0.9),
        ("canary", "generation_batch_size", 1),
        ("canary", "max_new_tokens", 512),
    )
    drift = [
        f"{section}.{key}"
        for section, key, value in expected
        if config[section].get(key) != value
    ]
    if config.get("recipe") != RECIPE:
        drift.append("recipe")
    if config.get("protocol") != PROTOCOL:
        drift.append("protocol")
    strategy = source_train_selection_strategy(config)
    expected_paths = {
        "assessment_round_robin_v1": (
            "adapters/source-v2-peft-control",
            "checkpoints/source-v2-peft-control",
        ),
        "target_cwe_assessment_round_robin_v1": (
            "adapters/source-v2-peft-cwe-balanced",
            "checkpoints/source-v2-peft-cwe-balanced",
        ),
    }
    expected_output_dir, expected_checkpoint_dir = expected_paths[strategy]
    if config["training"].get("output_dir") != expected_output_dir:
        drift.append("training.output_dir")
    if config["training"].get("checkpoint_dir") != expected_checkpoint_dir:
        drift.append("training.checkpoint_dir")
    if drift:
        raise ValueError(
            "peft split control contract drifted: " + ", ".join(sorted(drift))
        )


def _load_runtime() -> SimpleNamespace:
    """Import Unsloth first; its split-expert monkey-patch is required."""
    from unsloth import (  # type: ignore[import-not-found,import-untyped]
        FastLanguageModel,
    )

    import torch
    from datasets import Dataset  # type: ignore[import-not-found,import-untyped]
    from peft import (  # type: ignore[import-not-found]
        LoraConfig,
        PeftModel,
        get_peft_model,
        prepare_model_for_kbit_training,
    )
    from transformers import (  # type: ignore[import-not-found]
        AutoTokenizer,
        DataCollatorForSeq2Seq,
        Trainer,
        TrainerCallback,
        TrainingArguments,
    )

    return SimpleNamespace(
        FastLanguageModel=FastLanguageModel,
        torch=torch,
        Dataset=Dataset,
        LoraConfig=LoraConfig,
        PeftModel=PeftModel,
        get_peft_model=get_peft_model,
        prepare_model_for_kbit_training=prepare_model_for_kbit_training,
        DataCollatorForSeq2Seq=DataCollatorForSeq2Seq,
        Trainer=Trainer,
        TrainerCallback=TrainerCallback,
        TrainingArguments=TrainingArguments,
        AutoTokenizer=AutoTokenizer,
    )


def _expected_target_names() -> set[str]:
    attention = {
        f"model.layers.{layer}.self_attn.{module}"
        for layer in range(EXPECTED_HIDDEN_LAYERS)
        for module in ATTENTION_TARGETS
    }
    experts = {
        f"model.layers.{layer}.mlp.experts.{projection}.{expert}"
        for layer in EXPERT_TARGET_LAYERS
        for projection in ("gate_up_projs", "down_projs")
        for expert in range(EXPECTED_LOCAL_EXPERTS)
    }
    return attention | experts


def validate_split_bnb_targets(model: Any, target_regex: str) -> list[str]:
    """Require the exact pinned split layout and quantized target modules."""
    if getattr(model.config, "num_hidden_layers", None) != EXPECTED_HIDDEN_LAYERS:
        raise RuntimeError("unexpected GPT-OSS hidden-layer count")
    if getattr(model.config, "num_local_experts", None) != EXPECTED_LOCAL_EXPERTS:
        raise RuntimeError("unexpected GPT-OSS local-expert count")
    modules = dict(model.named_modules())
    matched = sorted(name for name in modules if re.fullmatch(target_regex, name))
    expected = _expected_target_names()
    if set(matched) != expected or len(matched) != EXPECTED_TARGET_MODULES:
        missing = sorted(expected - set(matched))[:3]
        extra = sorted(set(matched) - expected)[:3]
        raise RuntimeError(
            "split target layout mismatch: "
            f"count={len(matched)} missing={missing} extra={extra}"
        )
    invalid = [
        name
        for name in matched
        if type(modules[name]).__name__ != "Linear4bit"
        or type(getattr(modules[name], "weight", None)).__name__ != "Params4bit"
    ]
    if invalid:
        raise RuntimeError(
            "claimed QLoRA target is not bitsandbytes 4-bit: " + invalid[0]
        )
    return matched


def validate_trainable_adapter(model: Any) -> int:
    """Allow exactly the expected LoRA trainables and no base parameters."""
    trainable = [
        (name, parameter)
        for name, parameter in model.named_parameters()
        if parameter.requires_grad
    ]
    unexpected = [name for name, _ in trainable if "lora_" not in name]
    count = sum(parameter.numel() for _, parameter in trainable)
    if unexpected:
        raise RuntimeError(f"non-LoRA parameter is trainable: {unexpected[0]}")
    if count != EXPECTED_TRAINABLE_PARAMETERS:
        raise RuntimeError(
            "unexpected trainable parameter count: "
            f"expected {EXPECTED_TRAINABLE_PARAMETERS}, got {count}"
        )
    return count


def inspect_saved_adapter(adapter_dir: Path) -> dict[str, int]:
    """Validate exact attention/expert tensor coverage in a saved adapter."""
    from safetensors import safe_open  # type: ignore[import-not-found]

    weights = adapter_dir / "adapter_model.safetensors"
    if not weights.is_file():
        raise RuntimeError(f"saved adapter weights are missing: {weights}")
    with safe_open(weights, framework="pt") as tensors:
        keys = list(tensors.keys())
    attention = [key for key in keys if ".self_attn." in key]
    experts = [key for key in keys if ".mlp.experts." in key]
    suffixes = {
        "model.layers." + key.split(".model.layers.", 1)[1]
        for key in keys
        if ".model.layers." in key
    }
    stats = {
        "total": len(keys),
        "attention": len(attention),
        "experts": len(experts),
    }
    if (
        stats
        != {
            "total": EXPECTED_ADAPTER_TENSORS,
            "attention": EXPECTED_ATTENTION_TENSORS,
            "experts": EXPECTED_EXPERT_TENSORS,
        }
        or suffixes != _expected_adapter_tensor_suffixes()
    ):
        raise RuntimeError(
            f"saved adapter target coverage mismatch: {stats}, "
            f"matched_suffixes={len(suffixes)}"
        )
    return stats


def _expected_adapter_tensor_suffixes() -> set[str]:
    attention = {
        f"model.layers.{layer}.self_attn.{module}.lora_{side}.weight"
        for layer in range(EXPECTED_HIDDEN_LAYERS)
        for module in ATTENTION_TARGETS
        for side in ("A", "B")
    }
    experts = {
        f"model.layers.{layer}.mlp.experts.{projection}.{expert}.lora_{side}.weight"
        for layer in EXPERT_TARGET_LAYERS
        for projection in ("gate_up_projs", "down_projs")
        for expert in range(EXPECTED_LOCAL_EXPERTS)
        for side in ("A", "B")
    }
    return attention | experts


def validate_tokenizer_contract(tokenizer: Any) -> str:
    """Bind the control to the tokenizer used by the Unsloth canary."""
    return tokenizer_contract_sha256(tokenizer, _generation_contract())


def _generation_contract() -> GenerationContract:
    return GenerationContract(
        reasoning_effort=REASONING_EFFORT,
        padding_side="left",
        pad_token_id=PAD_TOKEN_ID,
        eos_token_ids=(RETURN_TOKEN_ID, END_OF_TEXT_TOKEN_ID),
        do_sample=False,
        max_new_tokens=512,
    )


def _validate_runtime_identity(model: Any, config: dict[str, Any]) -> tuple[str, str]:
    resolved_id = str(getattr(model.config, "_name_or_path", ""))
    resolved_revision = getattr(model.config, "_commit_hash", None)
    expected = config["model"]
    if resolved_id != expected["runtime_model_id"]:
        raise RuntimeError(
            f"resolved model mismatch: expected {expected['runtime_model_id']}, got {resolved_id}"
        )
    if resolved_revision != expected["revision"]:
        raise RuntimeError(
            f"resolved revision mismatch: expected {expected['revision']}, got {resolved_revision}"
        )
    return resolved_id, resolved_revision


def _load_split_base(
    runtime: SimpleNamespace, config: dict[str, Any]
) -> tuple[Any, Any, str, str]:
    model_config = config["model"]
    training = config["training"]
    model, tokenizer = runtime.FastLanguageModel.from_pretrained(
        model_name=model_config["runtime_model_id"],
        revision=model_config["revision"],
        max_seq_length=int(training["max_seq_length"]),
        dtype=None,
        load_in_4bit=True,
        cache_dir=model_config["cache_dir"],
    )
    resolved_id, resolved_revision = _validate_runtime_identity(model, config)
    validate_tokenizer_contract(tokenizer)
    return model, tokenizer, resolved_id, resolved_revision


def _inject_direct_peft(
    runtime: SimpleNamespace, model: Any, config: dict[str, Any], target_regex: str
) -> tuple[Any, int]:
    """Prepare k-bit training and inject LoRA through PEFT's public API."""
    validate_split_bnb_targets(model, target_regex)
    model.config.use_cache = False
    model = runtime.prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    training = config["training"]
    peft_config = runtime.LoraConfig(
        r=int(training["lora_r"]),
        lora_alpha=int(training["lora_alpha"]),
        target_modules=target_regex,
        target_parameters=None,
        lora_dropout=float(training["lora_dropout"]),
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = runtime.get_peft_model(model, peft_config)
    for adapter_config in model.peft_config.values():
        adapter_config.revision = config["model"]["revision"]
    return model, validate_trainable_adapter(model)


def _tokenize_dataset(
    runtime: SimpleNamespace, records: list[Any], tokenizer: Any, max_length: int
) -> Any:
    rows = [
        tokenize_source_training_record(
            record,
            tokenizer,
            max_length=max_length,
            reasoning_effort=REASONING_EFFORT,
        )
        for record in records
    ]
    if not rows or any(supervised_token_count(row) <= 0 for row in rows):
        raise RuntimeError("every training record must contain supervised tokens")
    return runtime.Dataset.from_list(rows)


def _validate_adapter_base(adapter_dir: Path, config: dict[str, Any]) -> None:
    path = adapter_dir / "adapter_config.json"
    from aegislm.artifacts import load_bounded_json_object

    try:
        adapter_config, _digest = load_bounded_json_object(
            path, description="saved adapter config"
        )
    except ValueError as exc:
        raise ValueError(f"invalid adapter config: {path}") from exc
    if (
        adapter_config.get("base_model_name_or_path")
        != config["model"]["runtime_model_id"]
        or adapter_config.get("revision") != config["model"]["revision"]
    ):
        raise ValueError(
            "saved adapter base model or revision does not match the control config"
        )


def _run_reload_and_schema_gate(
    runtime: SimpleNamespace,
    *,
    adapter_output: Path,
    config: dict[str, Any],
    records: list[Any],
    prediction_path: Path,
) -> tuple[GateRunSummary, str]:
    """Fresh-load the split base, attach with PeftModel, and run the exact gate."""
    _validate_adapter_base(adapter_output, config)
    inspect_saved_adapter(adapter_output)
    artifact_digest_before = artifact_directory_sha256(adapter_output)
    base_model, base_tokenizer, _, _ = _load_split_base(runtime, config)
    tokenizer, _tokenizer_digest = load_persisted_source_tokenizer(
        runtime.AutoTokenizer,
        adapter_output,
        base_tokenizer,
        _generation_contract(),
    )
    model = runtime.PeftModel.from_pretrained(
        base_model, str(adapter_output), is_trainable=False
    )
    runtime.FastLanguageModel.for_inference(model)
    protocol = config["protocol"]
    summary = run_source_schema_gate(
        model=model,
        tokenizer=tokenizer,
        records=records,
        prediction_path=prediction_path,
        batch_size=int(config["canary"]["generation_batch_size"]),
        contract=GenerationContract(
            reasoning_effort=REASONING_EFFORT,
            padding_side="left",
            pad_token_id=int(protocol["pad_token_id"]),
            eos_token_ids=tuple(protocol["eos_token_ids"]),
            do_sample=False,
            max_new_tokens=int(config["canary"]["max_new_tokens"]),
        ),
    )
    del model, base_model
    gc.collect()
    runtime.torch.cuda.empty_cache()
    artifact_digest_after = artifact_directory_sha256(adapter_output)
    if artifact_digest_after != artifact_digest_before:
        raise RuntimeError("adapter artifact changed while running the promotion gate")
    return summary, artifact_digest_before


def _write_gate_report(
    output_dir: Path,
    adapter_dir: Path,
    config: dict[str, Any],
    train_records: list[Any],
    records: list[Any],
    summary: GateRunSummary,
    *,
    adapter_artifact_sha256: str,
    promotion_authority: bool,
    tracking: dict[str, Any] | None,
) -> dict[str, Any]:
    prediction_path = output_dir / "post_training_gate_predictions.jsonl"
    if artifact_directory_sha256(adapter_dir) != adapter_artifact_sha256:
        raise RuntimeError("adapter artifact changed before writing the gate report")
    report = {
        "recipe": RECIPE,
        "passed": summary.schema_pass_rate
        >= float(config["canary"]["minimum_schema_pass_rate"]),
        "adapter_reload": True,
        "adapter_sha256": file_sha256(adapter_dir / "adapter_model.safetensors"),
        **canary_gate_evidence_fields(
            summary=summary,
            predictions_sha256=file_sha256(prediction_path),
            adapter_artifact_sha256=adapter_artifact_sha256,
        ),
        "promotion_authority": promotion_authority,
        "record_count": len(records),
        "passed_count": summary.passed_count,
        "schema_pass_rate": summary.schema_pass_rate,
        "parsed_count": summary.parsed_count,
        "harmony_prefix_count": summary.harmony_prefix_count,
        "harmony_final_count": summary.harmony_final_count,
        "finish_reasons": summary.finish_reasons,
        "minimum_schema_pass_rate": config["canary"]["minimum_schema_pass_rate"],
        "generation_batch_size": config["canary"]["generation_batch_size"],
        "max_new_tokens": config["canary"]["max_new_tokens"],
        "config_sha256": source_training_config_sha256(config),
        "train_records_sha256": records_sha256(train_records),
        "validation_records_sha256": records_sha256(records),
        "runtime_model_id": config["model"]["runtime_model_id"],
        "runtime_model_revision": config["model"]["revision"],
        "protocol_sha256": source_protocol_sha256(config),
        "prediction_path": str(prediction_path),
        "tracking": tracking,
    }
    with (output_dir / "post_training_gate.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return report


def _require_schema_gate(rate: float, config: dict[str, Any]) -> None:
    if rate < float(config["canary"]["minimum_schema_pass_rate"]):
        raise RuntimeError(f"post-training gate failed: schema_pass_rate={rate:.3f}")


def _require_passing_canary(
    config: dict[str, Any], train_records: list[Any], validation_records: list[Any]
) -> None:
    report_path = (
        Path(config["training"]["output_dir"]) / "canary" / "post_training_gate.json"
    )
    if not report_path.is_file():
        raise FileNotFoundError(
            f"full stage requires a passing control canary report: {report_path}"
        )
    report = load_canary_gate_report(report_path)
    if not isinstance(report, dict) or report.get("recipe") != RECIPE:
        raise ValueError("full stage requires a peft_split_control canary report")
    validate_canary_gate_report(
        report,
        config,
        train_records_sha256=records_sha256(train_records),
        validation_records_sha256=records_sha256(validation_records),
        adapter_dir=Path(config["training"]["output_dir"]) / "canary" / "final",
        prediction_path=(
            Path(config["training"]["output_dir"])
            / "canary"
            / "post_training_gate_predictions.jsonl"
        ),
        validation_records=validation_records,
    )


def _gate_output_forbidden_roots(config: dict[str, Any]) -> tuple[Path, ...]:
    return (
        Path(config["training"]["output_dir"]),
        Path(config["training"]["checkpoint_dir"]),
        Path(config["model"]["cache_dir"]),
        Path(config["dataset"]["train_path"]).parent,
        Path(config["dataset"]["validation_path"]).parent,
        REPO_ROOT / "data",
        REPO_ROOT / "raw_datasets",
        REPO_ROOT / "models",
        REPO_ROOT / "adapters",
        REPO_ROOT / "checkpoints",
    )


def _package_versions() -> dict[str, str]:
    packages = (
        "accelerate",
        "bitsandbytes",
        "datasets",
        "peft",
        "torch",
        "transformers",
        "trl",
        "unsloth",
        "unsloth-zoo",
        "wandb",
    )
    return {name: importlib_metadata.version(name) for name in packages}


def _runtime_manifest(torch: Any) -> dict[str, Any]:
    properties = torch.cuda.get_device_properties(0)
    return {
        "python": sys.version.split()[0],
        "torch_cuda": torch.version.cuda,
        "gpu_name": properties.name,
        "gpu_total_vram_gb": round(properties.total_memory / 1024**3, 3),
        "gpu_compute_capability": list(torch.cuda.get_device_capability(0)),
    }


def _make_wandb_callback(runtime: SimpleNamespace, run: Any) -> Any:
    class SafeWandbTrainerCallback(
        runtime.TrainerCallback  # type: ignore[misc,name-defined]
    ):
        def on_log(
            self,
            args: Any,
            state: Any,
            control: Any,
            logs: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> Any:
            del args, kwargs
            if logs and state.is_world_process_zero:
                from aegislm.tracking import (
                    log_wandb_payload,
                    safe_training_log_payload,
                )

                payload = safe_training_log_payload(logs)
                if payload:
                    log_wandb_payload(run, payload, step=int(state.global_step))
            return control

    return SafeWandbTrainerCallback()


def main() -> None:
    from aegislm.artifacts import validate_artifact_output_location
    from aegislm.tracking import (
        build_tracking_receipt,
        finish_active_wandb,
        finish_with_tracking_receipt,
        git_reference,
        init_wandb_run,
        log_wandb_payload,
        mark_tracking_logging_started,
        prepare_tracking_receipt,
        require_wandb_api_key,
        source_training_wandb_config,
        tracking_payload_sha256,
        tracking_run_id,
        wandb_run_reference,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/source_v2_peft_control.json")
    )
    parser.add_argument("--stage", choices=("canary", "full"), default="canary")
    parser.add_argument("--resume-from-checkpoint", type=Path)
    parser.add_argument("--wandb", action="store_true")
    parser.add_argument("--wandb-reconcile", choices=("retry-logging", "finish-only"))
    parser.add_argument("--gate-only", action="store_true")
    parser.add_argument(
        "--gate-output-dir",
        type=Path,
        help="New output directory required for an immutable gate-only run.",
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Load the pinned 4-bit base and validate direct PEFT injection only.",
    )
    args = parser.parse_args()
    if args.wandb_reconcile and not args.wandb:
        parser.error("--wandb-reconcile requires --wandb")
    if args.gate_only and args.gate_output_dir is None:
        parser.error("--gate-only requires --gate-output-dir")
    if not args.gate_only and args.gate_output_dir is not None:
        parser.error("--gate-output-dir requires --gate-only")
    if sum((args.prepare_only, args.preflight_only, args.gate_only)) > 1:
        parser.error("choose only one of --prepare-only, --preflight-only, --gate-only")
    if args.resume_from_checkpoint is not None and (
        args.prepare_only or args.preflight_only or args.gate_only
    ):
        parser.error("--resume-from-checkpoint requires an actual training run")
    if args.prepare_only and args.wandb:
        parser.error("--wandb cannot be combined with --prepare-only")
    if args.preflight_only and args.wandb:
        parser.error("--wandb cannot be combined with --preflight-only")
    if args.wandb:
        require_wandb_api_key()

    config = load_peft_control_config(args.config)
    validate_source_training_paths(config)
    training = config["training"]
    seed = int(training["seed"])
    all_train_records = load_source_records(
        Path(config["dataset"]["train_path"]), require_assistant=True
    )
    all_validation_records = load_source_records(
        Path(config["dataset"]["validation_path"]), require_assistant=True
    )
    validate_source_split_integrity(all_train_records, all_validation_records)
    gate_records = select_stratified_canary(
        all_validation_records, int(config["canary"]["validation_size"]), seed=seed
    )
    train_selection_strategy = source_train_selection_strategy(config)
    canary_train_records = select_source_train_canary(
        all_train_records,
        int(config["canary"]["train_size"]),
        seed=seed,
        strategy=train_selection_strategy,
    )
    if args.stage == "canary":
        train_records, validation_records = canary_train_records, gate_records
    else:
        _require_passing_canary(config, canary_train_records, gate_records)
        train_records, validation_records = all_train_records, all_validation_records
    print(
        f"[DATA] recipe={RECIPE} stage={args.stage} train={len(train_records)} "
        f"validation={len(validation_records)} train_sha256={records_sha256(train_records)}"
    )
    if args.prepare_only:
        print(
            "[OK] PEFT control config, hashes, records, and split selection are valid"
        )
        return

    adapter_output = Path(training["output_dir"]) / args.stage
    checkpoint_output = Path(training["checkpoint_dir"]) / args.stage
    final_adapter_output = adapter_output / "final"
    gate_output: Path | None = None
    gate_adapter_identity: str | None = None
    if args.gate_only:
        if not (final_adapter_output / "adapter_config.json").is_file():
            raise FileNotFoundError(f"saved adapter not found: {final_adapter_output}")
        gate_adapter_identity = artifact_directory_sha256(final_adapter_output)
        _validate_adapter_base(final_adapter_output, config)
        assert args.gate_output_dir is not None
        gate_output = args.gate_output_dir
        validate_artifact_output_location(gate_output)

    wandb_run = None
    wandb_claim = None
    receipt_path: Path | None = None
    receipt_base: dict[str, Any] | None = None
    if args.wandb:
        receipt_path = (
            Path(training["output_dir"]) / f"{args.stage}.gate.wandb.json"
            if args.gate_only
            else Path(training["output_dir"]) / f"{args.stage}.wandb.json"
        )
        receipt_base = build_tracking_receipt(
            "gate" if args.gate_only else "training",
            tracking_payload_sha256(
                {
                    "recipe": RECIPE,
                    "stage": args.stage,
                    "gate_only": args.gate_only,
                    "config_sha256": source_training_config_sha256(config),
                    "train_records_sha256": records_sha256(train_records),
                    "validation_records_sha256": records_sha256(validation_records),
                    "adapter_artifact_sha256": gate_adapter_identity,
                }
            ),
        )
        wandb_claim = prepare_tracking_receipt(
            receipt_path,
            receipt_base,
            ambiguous_resolution=args.wandb_reconcile,
        )
        if wandb_claim is None:
            print("source-v2 PEFT W&B receipt is already complete")
            return
        if not wandb_claim.needs_logging:
            safe_config = source_training_wandb_config(
                config, args.stage, args.gate_only
            )
            strategy_slug = source_train_selection_strategy(config).replace(
                "_round_robin_v1", ""
            )
            wandb_run = init_wandb_run(
                job_type="evaluation" if args.gate_only else "training",
                name=(
                    f"source-v2-peft-control-{strategy_slug}-{args.stage}"
                    f"{'-gate' if args.gate_only else ''}"
                ),
                tags=("source-v2", "peft-split-control", strategy_slug, args.stage),
                config={
                    **safe_config,
                    "recipe": RECIPE,
                    "git": git_reference(REPO_ROOT),
                },
                run_id=tracking_run_id(receipt_base),
                resume=wandb_claim.resume,
            )
            reference = wandb_run_reference(wandb_run)
            if reference is None:
                raise RuntimeError("W&B recovery run has no local reference")
            finish_with_tracking_receipt(wandb_claim, reference, finish_active_wandb)
            print("source-v2 PEFT W&B finish recovery complete")
            return
    if args.gate_only:
        assert gate_output is not None
        create_exclusive_artifact_directory(
            gate_output,
            forbidden_roots=_gate_output_forbidden_roots(config),
        )
    elif not args.preflight_only:
        reserve_training_stage(
            adapter_stage=adapter_output,
            checkpoint_stage=checkpoint_output,
            resume_from_checkpoint=args.resume_from_checkpoint,
            config_sha256=source_training_config_sha256(config),
            stage=args.stage,
        )
    if args.wandb:
        assert receipt_base is not None
        assert wandb_claim is not None
        mark_tracking_logging_started(wandb_claim)
        safe_config = source_training_wandb_config(config, args.stage, args.gate_only)
        strategy_slug = source_train_selection_strategy(config).replace(
            "_round_robin_v1", ""
        )
        wandb_run = init_wandb_run(
            job_type="evaluation" if args.gate_only else "training",
            name=(
                f"source-v2-peft-control-{strategy_slug}-{args.stage}"
                f"{'-gate' if args.gate_only else ''}"
            ),
            tags=("source-v2", "peft-split-control", strategy_slug, args.stage),
            config={**safe_config, "recipe": RECIPE, "git": git_reference(REPO_ROOT)},
            run_id=tracking_run_id(receipt_base),
            resume=wandb_claim.resume,
        )

    runtime = _load_runtime()
    if not runtime.torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for source-v2 QLoRA training")
    if args.gate_only:
        assert gate_output is not None
        summary, gate_adapter_digest = _run_reload_and_schema_gate(
            runtime,
            adapter_output=final_adapter_output,
            config=config,
            records=gate_records,
            prediction_path=gate_output / "post_training_gate_predictions.jsonl",
        )
        _write_gate_report(
            gate_output,
            final_adapter_output,
            config,
            canary_train_records,
            gate_records,
            summary,
            adapter_artifact_sha256=gate_adapter_digest,
            promotion_authority=False,
            tracking=wandb_run_reference(wandb_run),
        )
        if wandb_run is not None:
            threshold = float(config["canary"]["minimum_schema_pass_rate"])
            log_wandb_payload(
                wandb_run,
                {
                    "gate/schema_pass_rate": summary.schema_pass_rate,
                    "gate/minimum_schema_pass_rate": threshold,
                    "gate/passed": summary.schema_pass_rate >= threshold,
                },
            )
        _require_schema_gate(summary.schema_pass_rate, config)
        if (
            wandb_run is not None
            and receipt_path is not None
            and receipt_base is not None
        ):
            reference = wandb_run_reference(wandb_run)
            if reference is None:
                raise RuntimeError("W&B gate run has no local reference")
            assert wandb_claim is not None
            finish_with_tracking_receipt(wandb_claim, reference, finish_active_wandb)
        return

    runtime.torch.cuda.empty_cache()
    runtime.torch.cuda.reset_peak_memory_stats()
    model, tokenizer, resolved_id, resolved_revision = _load_split_base(runtime, config)
    tokenizer_contract_sha256 = validate_tokenizer_contract(tokenizer)
    target_regex = build_unsloth_moe_target_regex(
        list(training["attention_target_modules"]),
        list(training["expert_target_layers"]),
    )
    model, trainable_parameters = _inject_direct_peft(
        runtime, model, config, target_regex
    )
    if args.preflight_only:
        peak_vram_gb = runtime.torch.cuda.max_memory_allocated() / 1024**3
        if peak_vram_gb > 42.0:
            raise RuntimeError(
                f"PEFT control preflight exceeds 42 GiB budget: {peak_vram_gb:.3f}"
            )
        print(
            f"[OK] PEFT control preflight targets={EXPECTED_TARGET_MODULES} "
            f"trainable={trainable_parameters} peak_vram={peak_vram_gb:.3f}GiB"
        )
        del model
        gc.collect()
        runtime.torch.cuda.empty_cache()
        return
    train_dataset = _tokenize_dataset(
        runtime, train_records, tokenizer, int(training["max_seq_length"])
    )
    validation_dataset = _tokenize_dataset(
        runtime, validation_records, tokenizer, int(training["max_seq_length"])
    )
    update_steps = max(
        1,
        math.ceil(
            len(train_records)
            / int(training["batch_size"])
            / int(training["gradient_accumulation_steps"])
        ),
    )
    interval_steps = min(
        int(training["eval_steps"]), int(training["save_steps"]), update_steps
    )
    callbacks = (
        [_make_wandb_callback(runtime, wandb_run)] if wandb_run is not None else None
    )
    trainer = runtime.Trainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        data_collator=runtime.DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            model=model,
            label_pad_token_id=-100,
            pad_to_multiple_of=8,
        ),
        args=runtime.TrainingArguments(
            output_dir=str(checkpoint_output),
            per_device_train_batch_size=int(training["batch_size"]),
            per_device_eval_batch_size=int(training["eval_batch_size"]),
            gradient_accumulation_steps=int(training["gradient_accumulation_steps"]),
            num_train_epochs=float(training["epochs"]),
            learning_rate=float(training["learning_rate"]),
            warmup_ratio=float(training["warmup_ratio"]),
            lr_scheduler_type=training["lr_scheduler_type"],
            optim=training["optimizer"],
            weight_decay=float(training["weight_decay"]),
            bf16=runtime.torch.cuda.is_bf16_supported(),
            fp16=not runtime.torch.cuda.is_bf16_supported(),
            logging_steps=1 if args.stage == "canary" else 10,
            eval_strategy="no",
            save_strategy="steps",
            save_steps=interval_steps,
            save_total_limit=int(training["save_total_limit"]),
            load_best_model_at_end=False,
            report_to="none",
            seed=seed,
            data_seed=seed,
            remove_unused_columns=False,
        ),
        callbacks=callbacks,
    )
    runtime.torch.cuda.empty_cache()
    runtime.torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    result = trainer.train(
        resume_from_checkpoint=(
            str(args.resume_from_checkpoint)
            if args.resume_from_checkpoint is not None
            else None
        )
    )
    elapsed = time.perf_counter() - started
    losses = [
        float(row["loss"])
        for row in trainer.state.log_history
        if isinstance(row.get("loss"), (int, float))
    ]
    if not losses or not all(math.isfinite(loss) for loss in losses):
        raise RuntimeError("canary gate failed: training loss is missing or non-finite")

    trainer.save_model(str(final_adapter_output))
    tokenizer.save_pretrained(str(final_adapter_output))
    adapter_tensors = inspect_saved_adapter(final_adapter_output)
    manifest = {
        "recipe": RECIPE,
        "loader": "unsloth.FastLanguageModel.from_pretrained",
        "unsloth_monkey_patch_required": True,
        "adapter_injection": "peft.prepare_model_for_kbit_training+get_peft_model",
        "stage": args.stage,
        "base_model_id": config["model"]["base_model_id"],
        "runtime_model_id": config["model"]["runtime_model_id"],
        "runtime_model_revision": config["model"]["revision"],
        "resolved_model_id": resolved_id,
        "resolved_model_revision": resolved_revision,
        "resolved_protocol_sha256": source_protocol_sha256(config),
        "config_sha256": source_training_config_sha256(config),
        "command": shlex.join([sys.executable, *sys.argv]),
        "packages": _package_versions(),
        "runtime": _runtime_manifest(runtime.torch),
        "lora_target_regex": target_regex,
        "target_module_count": EXPECTED_TARGET_MODULES,
        "trainable_parameter_count": trainable_parameters,
        "adapter_tensor_counts": adapter_tensors,
        "tokenizer_contract_sha256": tokenizer_contract_sha256,
        "resolved_protocol": config["protocol"],
        "train_record_count": len(train_records),
        "train_selection_strategy": train_selection_strategy,
        "validation_record_count": len(validation_records),
        "train_records_sha256": records_sha256(train_records),
        "validation_records_sha256": records_sha256(validation_records),
        "gate_records_sha256": records_sha256(gate_records),
        "dataset_files": {
            "train": config["dataset"]["train_sha256"],
            "validation": config["dataset"]["validation_sha256"],
        },
        "training_loss": result.training_loss,
        "elapsed_seconds": round(elapsed, 3),
        "peak_vram_gb": round(runtime.torch.cuda.max_memory_allocated() / 1024**3, 3),
        "expert_adapter_tensors_present": True,
        "adapter_sha256": file_sha256(
            final_adapter_output / "adapter_model.safetensors"
        ),
        "final_adapter_path": str(final_adapter_output),
        "checkpoint_selection": "not_performed_final_adapter_only",
        "trainer_eval_loss_disabled": (
            "The control retains the source-v2 deterministic persisted-adapter generation gate"
        ),
        "config": config,
        "tracking": wandb_run_reference(wandb_run),
    }
    (adapter_output / "aegislm_training_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    del trainer, model, train_dataset, validation_dataset
    gc.collect()
    runtime.torch.cuda.empty_cache()
    prediction_path = adapter_output / "post_training_gate_predictions.jsonl"
    if prediction_path.exists():
        raise FileExistsError(
            f"refusing to overwrite existing gate predictions: {prediction_path}"
        )
    summary, gate_adapter_digest = _run_reload_and_schema_gate(
        runtime,
        adapter_output=final_adapter_output,
        config=config,
        records=gate_records,
        prediction_path=prediction_path,
    )
    _write_gate_report(
        adapter_output,
        final_adapter_output,
        config,
        canary_train_records,
        gate_records,
        summary,
        adapter_artifact_sha256=gate_adapter_digest,
        promotion_authority=True,
        tracking=wandb_run_reference(wandb_run),
    )
    if wandb_run is not None:
        threshold = float(config["canary"]["minimum_schema_pass_rate"])
        log_wandb_payload(
            wandb_run,
            {
                "training/final_loss": result.training_loss,
                "training/elapsed_seconds": round(elapsed, 3),
                "training/peak_vram_gb": manifest["peak_vram_gb"],
                "gate/schema_pass_rate": summary.schema_pass_rate,
                "gate/minimum_schema_pass_rate": threshold,
                "gate/passed": summary.schema_pass_rate >= threshold,
            },
        )
    _require_schema_gate(summary.schema_pass_rate, config)
    if wandb_run is not None and receipt_path is not None and receipt_base is not None:
        reference = wandb_run_reference(wandb_run)
        if reference is None:
            raise RuntimeError("W&B training run has no local reference")
        assert wandb_claim is not None
        finish_with_tracking_receipt(wandb_claim, reference, finish_active_wandb)
    print(
        f"[OK] recipe={RECIPE} adapter={final_adapter_output} "
        f"loss={result.training_loss:.6f} "
        f"schema_pass_rate={summary.schema_pass_rate:.3f}"
    )


if __name__ == "__main__":
    from aegislm.tracking import finish_active_wandb, release_active_tracking_claims

    try:
        main()
    except BaseException:
        try:
            finish_active_wandb(1)
        finally:
            release_active_tracking_claims()
        raise
    else:
        try:
            finish_active_wandb(0)
        finally:
            release_active_tracking_claims()
