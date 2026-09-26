"""Preparation and artifact contracts for the manually run fresh Unsloth recipe.

Importing this module never imports torch, Transformers, Unsloth, or W&B.
GPU dependencies are loaded explicitly by the training/reload entrypoint.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
import math
from pathlib import Path
import re
from typing import Any

import os
import tempfile

from aegislm.artifacts import (
    load_bounded_json_object,
    validate_artifact_output_location,
    validate_artifact_path_plan,
    validate_no_symlink_components,
    write_text_artifact,
)

from aegislm.datasets.source import (
    SourceAssessmentRecord,
    load_source_records,
    records_sha256,
    select_source_train_canary,
    select_stratified_canary,
    validate_source_split_integrity,
)
from aegislm.evaluation.validation import validate_source_assessment
from aegislm.training.source import (
    ChatTokenizer,
    supervised_token_count,
    tokenize_source_training_record,
)
from aegislm.training.source_config import (
    artifact_directory_sha256,
    file_sha256,
    load_canary_gate_report,
    load_source_training_config,
    resolved_source_generation_contract,
    source_protocol_sha256,
    source_training_config_sha256,
    validate_canary_gate_report,
)
from aegislm.training.source_gate import GateRunSummary, canary_gate_evidence_fields

FRESH_RECIPE = "unsloth_fresh_v1"
SMOKE_TRAIN_SIZE = 32
SMOKE_VALIDATION_SIZE = 8
SMOKE_STEPS = 10
CHECKPOINT_EVIDENCE_FILE = "aegislm-training-evidence.json"
CHECKPOINT_EVIDENCE_SCHEMA = "aegislm.fresh-checkpoint-evidence.v1"
FRESH_TOKENIZER_FILES = (
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "chat_template.jinja",
)


@dataclass(frozen=True)
class FreshData:
    """Validated splits; challenge answers are never read here."""

    train: list[SourceAssessmentRecord]
    validation: list[SourceAssessmentRecord]
    canary_train: list[SourceAssessmentRecord]
    gate: list[SourceAssessmentRecord]


def load_fresh_config(path: Path) -> dict[str, Any]:
    """Load the new recipe without changing historical recipe semantics."""
    config = load_source_training_config(path)
    if config.get("recipe") != FRESH_RECIPE:
        raise ValueError(f"fresh entrypoint requires recipe={FRESH_RECIPE}")
    dataset = config["dataset"]
    if not all(key in dataset for key in ("challenge_path", "challenge_sha256")):
        raise ValueError("fresh recipe requires challenge_path and challenge_sha256")
    expected = {
        "reasoning_effort": "low",
        "padding_side": "left",
        "pad_token_id": 200017,
        "eos_token_ids": [200002, 199999],
        "do_sample": False,
    }
    if config["protocol"] != expected:
        raise ValueError("fresh recipe requires the canonical low-reasoning protocol")
    canary = config["canary"]
    if (
        canary["train_size"],
        canary["validation_size"],
        canary["generation_batch_size"],
    ) != (1000, 40, 1):
        raise ValueError("fresh canary requires train=1000, validation=40, batch=1")
    if canary.get("train_selection_strategy", "assessment_round_robin_v1") != (
        "assessment_round_robin_v1"
    ):
        raise ValueError("fresh recipe retains the assessment-only canary selector")
    return config


def validate_fresh_paths(config: dict[str, Any]) -> None:
    """Validate all frozen inputs and disjoint storage roots without mkdir."""
    dataset = config["dataset"]
    inputs = [
        Path(dataset[f"{split}_path"]) for split in ("train", "validation", "challenge")
    ]
    for split, path in zip(("train", "validation", "challenge"), inputs, strict=True):
        if file_sha256(path) != dataset[f"{split}_sha256"]:
            raise ValueError(f"{split} dataset SHA-256 mismatch")
    roots = [
        Path(config["model"]["cache_dir"]),
        Path(config["training"]["output_dir"]),
        Path(config["training"]["checkpoint_dir"]),
    ]
    for root in roots:
        validate_artifact_output_location(root)
        if root.exists() and not root.is_dir():
            raise ValueError("artifact/cache root must be a directory")
    resolved = [root.resolve() for root in roots]
    for index, root in enumerate(resolved):
        for other in resolved[index + 1 :]:
            if root.is_relative_to(other) or other.is_relative_to(root):
                raise ValueError("cache, adapter and checkpoint roots must not overlap")
        for path in inputs:
            parent = path.resolve().parent
            if root.is_relative_to(parent) or parent.is_relative_to(root):
                raise ValueError("artifact roots must not overlap dataset directories")


def load_fresh_data(config: dict[str, Any]) -> FreshData:
    """Validate complete supervised splits and challenge separation before training."""
    validate_fresh_paths(config)
    splits = {
        split: load_source_records(
            Path(config["dataset"][f"{split}_path"]),
            require_assistant=split != "challenge",
        )
        for split in ("train", "validation", "challenge")
    }
    for left, right in (
        ("train", "validation"),
        ("train", "challenge"),
        ("validation", "challenge"),
    ):
        validate_source_split_integrity(splits[left], splits[right])
    for split in ("train", "validation"):
        for record in splits[split]:
            output = record.assistant_output
            assert output is not None
            result = validate_source_assessment(
                output,
                source_code=record.source_code,
                target_cwe=record.target_cwe,
            )
            if not result.ok:
                raise ValueError(f"{split}/{record.record_id}: {result.errors}")
    seed = int(config["training"]["seed"])
    return FreshData(
        splits["train"],
        splits["validation"],
        select_source_train_canary(
            splits["train"], 1000, seed=seed, strategy="assessment_round_robin_v1"
        ),
        select_stratified_canary(splits["validation"], 40, seed=seed),
    )


def select_fresh_stage(
    data: FreshData, stage: str
) -> tuple[list[SourceAssessmentRecord], list[SourceAssessmentRecord]]:
    """Use stable prefixes for smoke and preserve the exact historical canary."""
    if stage == "smoke":
        return data.canary_train[:SMOKE_TRAIN_SIZE], data.gate[:SMOKE_VALIDATION_SIZE]
    if stage == "canary":
        return data.canary_train, data.gate
    if stage == "full":
        return data.train, data.gate
    raise ValueError("unknown fresh stage")


def tokenize_fresh_records(
    records: list[SourceAssessmentRecord],
    tokenizer: ChatTokenizer,
    config: dict[str, Any],
) -> list[dict[str, list[int]]]:
    """Keep precomputed labels intact; never silently truncate supervised data."""
    features = [
        tokenize_source_training_record(
            record,
            tokenizer,
            max_length=int(config["training"]["max_seq_length"]),
            reasoning_effort="low",
        )
        for record in records
    ]
    for row in features:
        if len(row["input_ids"]) != len(row["attention_mask"]):
            raise ValueError("attention mask length does not match input IDs")
        if not supervised_token_count(row):
            raise ValueError("empty assistant supervision")
    return features


def build_training_trace(
    record: SourceAssessmentRecord,
    features: dict[str, list[int]],
    tokenizer: Any,
) -> dict[str, Any]:
    """Describe one training example before batch collation"""
    input_ids = list(features["input_ids"])
    attention_mask = list(features["attention_mask"])
    labels = list(features["labels"])

    if not (len(input_ids) == len(attention_mask) == len(labels)):
        raise ValueError(f"{record.record_id} : training feature lengths differ")

    masked_input_ids = [
        token_id
        for token_id, label in zip(input_ids, labels, strict=True)
        if label == -100
    ]
    supervised_label_ids = [label for label in labels if label != -100]

    return {
        "id": record.record_id,
        "messages": list(record.messages),
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels,
        "masked_token_count": len(masked_input_ids),
        "supervised_token_count": len(supervised_label_ids),
        "decoded_input": tokenizer.decode(  # 프롬프트와 정답이 합쳐진 학습 시퀀스
            input_ids, skip_special_tokens=False
        ),
        "decoded_masked_input": tokenizer.decode(  # 정답 채점에서 제외한 부분
            masked_input_ids, skip_special_tokens=False
        ),
        "decoded_supervised_labels": tokenizer.decode(  # 정답으로 학습하도록 지정한 부분
            supervised_label_ids, skip_special_tokens=False
        ),
    }


def write_training_traces(
    path: Path,
    records: list[SourceAssessmentRecord],
    features: list[dict[str, list[int]]],
    tokenizer: Any,
) -> None:
    """Stream private training traces without overwriting existing artifacts."""
    validate_artifact_path_plan(
        inputs=(),
        outputs=(path,),
        require_new=True,
    )

    if not records or len(records) != len(features):
        raise ValueError("training trace requires matching, non-empty records")

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )

    temporary = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            for record, row in zip(records, features, strict=True):
                trace = build_training_trace(record, row, tokenizer)
                stream.write(
                    json.dumps(trace, ensure_ascii=False, allow_nan=False) + "\n"
                )
            stream.flush()
            os.fsync(stream.fileno())

        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def checkpoint_logged_loss(state: dict[str, Any]) -> float:
    """Compute an explicitly labelled mean from complete per-step checkpoint logs."""
    step = state.get("global_step")
    history = state.get("log_history")
    if type(step) is not int or step <= 0 or not isinstance(history, list):
        raise ValueError("checkpoint requires positive global_step and log_history")
    losses: dict[int, float] = {}
    for row in history:
        if not isinstance(row, dict):
            raise ValueError("invalid checkpoint log entry")
        for key in ("loss", "grad_norm"):
            if key in row and (
                type(row[key]) not in (int, float) or not math.isfinite(row[key])
            ):
                raise ValueError(f"checkpoint contains non-finite or invalid {key}")
        if "loss" in row:
            logged_step = row.get("step")
            if (
                type(logged_step) is not int
                or not 1 <= logged_step <= step
                or logged_step in losses
            ):
                raise ValueError("checkpoint loss steps must be unique and in range")
            losses[logged_step] = float(row["loss"])
    if len(losses) != step:
        raise ValueError("checkpoint must retain one finite loss for every step")
    return math.fsum(losses.values()) / step


def load_completed_checkpoint(
    checkpoint: Path | None,
    *,
    config: dict[str, Any],
    stage: str,
    train_records_digest: str,
) -> dict[str, Any] | None:
    """Accept terminal recovery only with digest-bound, saved training evidence.

    Ordinary incomplete checkpoints retain the normal Trainer resume path.
    Legacy terminal checkpoints have no such evidence and fail closed.
    """
    if checkpoint is None:
        return None
    state, state_digest = load_bounded_json_object(
        checkpoint / "trainer_state.json", description="checkpoint trainer state"
    )
    step, maximum = state.get("global_step"), state.get("max_steps")
    if (
        type(step) is not int
        or type(maximum) is not int
        or not 0 <= step <= maximum
        or maximum <= 0
        or checkpoint.name != f"checkpoint-{step}"
    ):
        raise ValueError("checkpoint step/name/max_steps do not agree")
    if step < maximum:
        # Trainer may overwrite newer checkpoint-N directories when replaying
        # an older checkpoint. Preserve completed, evidence-bound snapshots.
        for saved in checkpoint.parent.glob(f"checkpoint-*/{CHECKPOINT_EVIDENCE_FILE}"):
            match = re.fullmatch(r"checkpoint-([1-9][0-9]*)", saved.parent.name)
            if match is not None and int(match.group(1)) > step:
                raise ValueError(
                    "a newer completed checkpoint has saved evidence; finalize it "
                    "or use a new experiment path instead of overwriting it"
                )
        return None
    evidence_path = checkpoint / CHECKPOINT_EVIDENCE_FILE
    if not evidence_path.exists():
        raise ValueError(
            "completed checkpoint lacks saved training evidence; resume an earlier "
            "incomplete checkpoint or use a new experiment path, not a bypass"
        )
    evidence, evidence_digest = load_bounded_json_object(
        evidence_path, description="completed checkpoint evidence"
    )
    expected = {
        "schema_version": CHECKPOINT_EVIDENCE_SCHEMA,
        "config_sha256": source_training_config_sha256(config),
        "stage": stage,
        "train_records_sha256": train_records_digest,
        "trainer_state_sha256": state_digest,
        "global_step": step,
        "max_steps": maximum,
        "gradients_checked": True,
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        raise ValueError("completed checkpoint evidence does not match this run")
    if evidence.get("gradients_checked") is not True:
        raise ValueError("completed checkpoint has no verified gradient evidence")
    for key in (
        "trainable_before_sha256",
        "trainable_after_sha256",
        "tokenizer_contract_sha256",
    ):
        value = evidence.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"invalid checkpoint {key}")
    if evidence["trainable_before_sha256"] == evidence["trainable_after_sha256"]:
        raise ValueError("completed checkpoint has no verified adapter update")
    for filename, key in (
        ("adapter_model.safetensors", "adapter_sha256"),
        ("adapter_config.json", "adapter_config_sha256"),
    ):
        path = checkpoint / filename
        validate_no_symlink_components(path, description="checkpoint adapter")
        if not path.is_file() or file_sha256(path) != evidence.get(key):
            raise ValueError(f"completed checkpoint {filename} digest mismatch")
    return {
        **evidence,
        "evidence_sha256": evidence_digest,
        "training_loss": checkpoint_logged_loss(state),
    }


def resolve_fresh_tokenizer_snapshot(config: dict[str, Any]) -> Path:
    """Find one complete pinned snapshot, never mixing caches or downloading.

    Unsloth may cache weights in model.cache_dir and tokenizer assets in the
    default Hugging Face cache. HF cache symlinks to blobs are expected here.
    """
    hub = importlib.import_module("huggingface_hub")
    model = config["model"]
    missing_by_cache: list[str] = []
    for cache_dir in (model["cache_dir"], None):
        paths: list[Path] = []
        missing: list[str] = []
        for filename in FRESH_TOKENIZER_FILES:
            cached = hub.try_to_load_from_cache(
                model["runtime_model_id"],
                filename,
                cache_dir=cache_dir,
                revision=model["revision"],
            )
            if not isinstance(cached, str) or not Path(cached).is_file():
                missing.append(filename)
            else:
                paths.append(Path(cached))
        if not missing:
            snapshot = paths[0].parent
            if snapshot.name != model["revision"] or any(
                path.parent != snapshot for path in paths
            ):
                raise ValueError("tokenizer assets do not share the pinned snapshot")
            return snapshot.absolute()
        missing_by_cache.append(
            f"{cache_dir or 'default HF cache'}: {', '.join(missing)}"
        )
    raise FileNotFoundError(
        f"No complete tokenizer snapshot for {model['runtime_model_id']}@{model['revision']}. "
        + "; ".join(missing_by_cache)
        + ". Cache the pinned tokenizer files using the documented hf download command; "
        "installing a tokenizer converter does not supply these missing files."
    )


def prepare_fresh_tokens(config: dict[str, Any], data: FreshData) -> dict[str, Any]:
    """Audit a cached, pinned tokenizer only; never load model weights or download."""
    snapshot = resolve_fresh_tokenizer_snapshot(config)
    auto_tokenizer = importlib.import_module("transformers").AutoTokenizer
    model = config["model"]
    try:
        tokenizer = auto_tokenizer.from_pretrained(
            str(snapshot),
            local_files_only=True,
        )
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Cached tokenizer files were found at {snapshot}, but loading failed: {exc}"
        ) from exc
    summary: dict[str, Any] = {
        "tokenizer": {
            "model_id": model["runtime_model_id"],
            "revision": model["revision"],
            "snapshot": str(snapshot),
        }
    }
    for name, rows in (("train", data.train), ("validation", data.validation)):
        tokens = tokenize_fresh_records(rows, tokenizer, config)
        summary[name] = {
            "records": len(tokens),
            "max_tokens": max(len(row["input_ids"]) for row in tokens),
            "min_supervised_tokens": min(supervised_token_count(row) for row in tokens),
        }
    return summary


def require_fresh_canary(config: dict[str, Any], data: FreshData) -> None:
    """Rescore the saved canary evidence before loading a full-training model."""
    stage = Path(config["training"]["output_dir"]) / "canary"
    report = load_canary_gate_report(stage / "post_training_gate.json")
    validate_canary_gate_report(
        report,
        config,
        train_records_sha256=records_sha256(data.canary_train),
        validation_records_sha256=records_sha256(data.gate),
        adapter_dir=stage / "final",
        prediction_path=stage / "post_training_gate_predictions.jsonl",
        validation_records=data.gate,
    )


def write_fresh_json(path: Path, value: dict[str, Any]) -> None:
    """Write a new Git-safe local report, refusing existing files."""
    write_text_artifact(
        path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )


def fresh_stage_exit_code(output: Path, stage: str) -> int:
    """Recover the local stage outcome without reporting W&B completion as success."""
    report_path = output / "post_training_gate.json"
    if not report_path.exists():
        return 1
    report = load_canary_gate_report(report_path)
    if (
        report.get("recipe") != FRESH_RECIPE
        or report.get("stage") != stage
        or report.get("adapter_reload") is not True
    ):
        return 1
    return 0 if stage == "smoke" or report.get("passed") is True else 1


def write_fresh_gate(
    config: dict[str, Any],
    data: FreshData,
    stage: str,
    summary: GateRunSummary,
    adapter_digest: str,
) -> dict[str, Any]:
    """Persist the existing gate wire format; only canary may authorize full."""
    output = Path(config["training"]["output_dir"]) / stage
    adapter = output / "final"
    predictions = output / "post_training_gate_predictions.jsonl"
    if artifact_directory_sha256(adapter) != adapter_digest:
        raise RuntimeError("adapter changed during reload evaluation")
    _, records = select_fresh_stage(data, stage)
    report = {
        **canary_gate_evidence_fields(
            summary=summary,
            predictions_sha256=file_sha256(predictions),
            adapter_artifact_sha256=adapter_digest,
        ),
        "passed": summary.schema_pass_rate
        >= config["canary"]["minimum_schema_pass_rate"],
        "adapter_reload": True,
        "adapter_sha256": file_sha256(adapter / "adapter_model.safetensors"),
        "promotion_authority": stage == "canary",
        "recipe": FRESH_RECIPE,
        "stage": stage,
        "protocol": config["protocol"],
        "protocol_sha256": source_protocol_sha256(config),
        "config_sha256": source_training_config_sha256(config),
        "train_records_sha256": records_sha256(data.canary_train),
        "validation_records_sha256": records_sha256(records),
        "runtime_model_id": config["model"]["runtime_model_id"],
        "runtime_model_revision": config["model"]["revision"],
        "minimum_schema_pass_rate": config["canary"]["minimum_schema_pass_rate"],
        "generation_batch_size": 1,
        "max_new_tokens": config["canary"]["max_new_tokens"],
        "record_count": summary.record_count,
        "passed_count": summary.passed_count,
        "schema_pass_rate": summary.schema_pass_rate,
        "parsed_count": summary.parsed_count,
        "harmony_prefix_count": summary.harmony_prefix_count,
        "harmony_final_count": summary.harmony_final_count,
        "finish_reasons": summary.finish_reasons,
        "prediction_path": str(predictions),
    }
    write_fresh_json(output / "post_training_gate.json", report)
    return report


def reload_fresh_stage(config: dict[str, Any], data: FreshData, stage: str) -> None:
    """Load the saved adapter in the child process and write strict gate evidence."""
    from aegislm.artifacts import load_bounded_json_object, validate_artifact_path_plan
    from aegislm.training.source import load_persisted_source_tokenizer
    from aegislm.training.source_gate import run_source_schema_gate

    output = Path(config["training"]["output_dir"]) / stage
    adapter = output / "final"
    validate_artifact_path_plan(
        inputs=(),
        outputs=(
            output / "post_training_gate.json",
            output / "post_training_gate_predictions.jsonl",
        ),
        protected_roots=(adapter, Path(config["training"]["checkpoint_dir"])),
        require_new=True,
    )
    manifest, _ = load_bounded_json_object(
        output / "aegislm_training_manifest.json",
        description="fresh training manifest",
    )
    if (
        manifest.get("config_sha256") != source_training_config_sha256(config)
        or manifest.get("stage") != stage
    ):
        raise ValueError("reload manifest does not match config/stage")
    digest = artifact_directory_sha256(adapter)
    if manifest.get("adapter_artifact_sha256") != digest:
        raise ValueError("saved adapter does not match the training manifest")
    saved_config, _ = load_bounded_json_object(
        adapter / "adapter_config.json",
        description="saved adapter config",
    )
    if (
        saved_config.get("base_model_name_or_path")
        != config["model"]["runtime_model_id"]
        or saved_config.get("revision") != config["model"]["revision"]
    ):
        raise ValueError("saved adapter base/revision mismatch")
    tokenizer_snapshot = resolve_fresh_tokenizer_snapshot(config)
    # Import Unsloth first, before torch/Transformers/PEFT can initialize.
    unsloth = importlib.import_module("unsloth")
    transformers = importlib.import_module("transformers")
    peft = importlib.import_module("peft")
    model, base_tokenizer = unsloth.FastLanguageModel.from_pretrained(
        model_name=config["model"]["runtime_model_id"],
        tokenizer_name=str(tokenizer_snapshot),
        revision=config["model"]["revision"],
        cache_dir=config["model"]["cache_dir"],
        local_files_only=True,
        max_seq_length=config["training"]["max_seq_length"],
        dtype=None,
        load_in_4bit=True,
    )
    validate_fresh_model_identity(model, config)
    base_tokenizer.padding_side = "left"
    contract = resolved_source_generation_contract(config)
    tokenizer, _ = load_persisted_source_tokenizer(
        transformers.AutoTokenizer,
        adapter,
        base_tokenizer,
        contract,
    )
    model = peft.PeftModel.from_pretrained(model, str(adapter), is_trainable=False)
    if not model.active_adapters or not any(
        "lora_" in name for name, _ in model.named_parameters()
    ):
        raise RuntimeError("reloaded model has no active LoRA adapter")
    unsloth.FastLanguageModel.for_inference(model)
    _, records = select_fresh_stage(data, stage)
    summary = run_source_schema_gate(
        model=model,
        tokenizer=tokenizer,
        records=records,
        prediction_path=output / "post_training_gate_predictions.jsonl",
        batch_size=1,
        contract=contract,
        require_harmony=True,
    )
    report = write_fresh_gate(config, data, stage, summary, digest)
    print(f"[GATE] {stage}: {summary.passed_count}/{summary.record_count}")
    if stage != "smoke" and not report["passed"]:
        raise RuntimeError(
            "strict held-out gate failed; full training is not authorized"
        )


def validate_fresh_model_identity(model: Any, config: dict[str, Any]) -> None:
    """Reject a silently substituted quantized base or revision."""
    if (
        getattr(model.config, "_name_or_path", None)
        != config["model"]["runtime_model_id"]
        or getattr(model.config, "_commit_hash", None) != config["model"]["revision"]
    ):
        raise RuntimeError("resolved Unsloth model identity/revision mismatch")
