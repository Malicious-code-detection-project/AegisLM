"""Train GPT-OSS source-v2 adapters with Unsloth QLoRA."""

from __future__ import annotations

import argparse
import gc
import importlib.metadata as importlib_metadata
import json
import math
import shlex
import sys
import time
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.environment import load_project_env  # noqa: E402

load_project_env(REPO_ROOT)

# Unsloth must patch torch/transformers before their direct imports.
from unsloth import (  # type: ignore[import-not-found,import-untyped] # noqa: E402
    FastLanguageModel,
)
import torch  # noqa: E402
from datasets import Dataset  # type: ignore[import-not-found,import-untyped] # noqa: E402
from transformers import (  # type: ignore[import-not-found] # noqa: E402
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainerCallback,
    TrainingArguments,
)

from aegislm.datasets import (  # noqa: E402
    load_source_records,
    records_sha256,
    select_source_train_canary,
    select_stratified_canary,
    validate_source_split_integrity,
)
from aegislm.training import (  # noqa: E402
    artifact_directory_sha256,
    canary_gate_evidence_fields,
    create_exclusive_artifact_directory,
    build_unsloth_moe_target_regex,
    file_sha256,
    load_persisted_source_tokenizer,
    load_canary_gate_report,
    load_source_training_config,
    source_training_config_sha256,
    source_protocol_config,
    source_protocol_sha256,
    source_train_selection_strategy,
    source_training_recipe,
    supervised_token_count,
    tokenizer_contract_sha256,
    tokenize_source_training_record,
    GenerationContract,
    GateRunSummary,
    run_source_schema_gate,
    reserve_training_stage,
    validate_source_training_paths,
    validate_canary_gate_report,
)


class SafeWandbTrainerCallback(TrainerCallback):
    """Forward only approved scalar curve fields to the active W&B run."""

    def __init__(self, run: Any):
        self.run = run

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
            from aegislm.tracking import log_wandb_payload, safe_training_log_payload

            payload = safe_training_log_payload(logs)
            if payload:
                log_wandb_payload(self.run, payload, step=int(state.global_step))
        return control


def main() -> None:
    from aegislm.artifacts import validate_artifact_output_location
    from aegislm.tracking import (
        build_tracking_receipt,
        finish_active_wandb,
        finish_with_tracking_receipt,
        git_reference,
        init_wandb_run,
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
        "--config", type=Path, default=Path("configs/source_v2_unsloth_v2.json")
    )
    parser.add_argument("--stage", choices=("canary", "full"), default="canary")
    parser.add_argument("--resume-from-checkpoint", type=Path)
    parser.add_argument(
        "--wandb",
        action="store_true",
        help="Track this experiment in the aegislm/source-v2 W&B project/group.",
    )
    parser.add_argument("--wandb-reconcile", choices=("retry-logging", "finish-only"))
    parser.add_argument(
        "--gate-only",
        action="store_true",
        help="Reload an existing final adapter and rerun the held-out canary gate.",
    )
    parser.add_argument(
        "--gate-output-dir",
        type=Path,
        help=(
            "New Git-ignored/external directory for a gate-only diagnostic run. "
            "Required with --gate-only so preserved gate evidence is never overwritten."
        ),
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help=(
            "Validate config, frozen file hashes, records, and split selection only; "
            "run audit_source_tokens.py for tokenizer preflight."
        ),
    )
    args = parser.parse_args()
    if args.wandb_reconcile and not args.wandb:
        parser.error("--wandb-reconcile requires --wandb")
    if args.gate_only and args.gate_output_dir is None:
        parser.error("--gate-only requires --gate-output-dir")
    if not args.gate_only and args.gate_output_dir is not None:
        parser.error("--gate-output-dir requires --gate-only")
    if args.prepare_only and args.gate_only:
        parser.error("choose only one of --prepare-only and --gate-only")
    if args.resume_from_checkpoint is not None and (
        args.gate_only or args.prepare_only
    ):
        parser.error("--resume-from-checkpoint requires an actual training run")
    if args.prepare_only and args.wandb:
        parser.error("--wandb cannot be combined with --prepare-only")
    if args.wandb:
        require_wandb_api_key()

    config = load_source_training_config(args.config)
    recipe = source_training_recipe(config)
    if recipe not in {"legacy_unsloth", "unsloth_v2"}:
        raise ValueError(f"train_source_unsloth.py does not support recipe={recipe}")
    if recipe == "legacy_unsloth" and args.stage == "full":
        raise ValueError("legacy Unsloth is diagnostic-only and cannot run full stage")
    validate_source_training_paths(config)
    training = config["training"]
    protocol = _generation_contract(config)
    seed = int(training["seed"])
    all_train_records = load_source_records(
        Path(config["dataset"]["train_path"]), require_assistant=True
    )
    all_validation_records = load_source_records(
        Path(config["dataset"]["validation_path"]), require_assistant=True
    )
    validate_source_split_integrity(all_train_records, all_validation_records)
    gate_records = select_stratified_canary(
        all_validation_records,
        int(config["canary"]["validation_size"]),
        seed=seed,
    )
    train_selection_strategy = source_train_selection_strategy(config)
    canary_train_records = select_source_train_canary(
        all_train_records,
        int(config["canary"]["train_size"]),
        seed=seed,
        strategy=train_selection_strategy,
    )
    if args.stage == "canary":
        train_records = canary_train_records
        validation_records = gate_records
    else:
        _require_passing_canary(config, canary_train_records, gate_records)
        train_records = all_train_records
        validation_records = all_validation_records
    print(
        f"[DATA] stage={args.stage} train={len(train_records)} "
        f"validation={len(validation_records)} train_sha256={records_sha256(train_records)}"
    )
    if args.prepare_only:
        print(
            "[OK] Configuration, frozen hashes, records, and split selection are "
            "valid. Tokenization was not run."
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
                    "recipe": recipe,
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
            print("source-v2 W&B receipt is already complete")
            return
        if not wandb_claim.needs_logging:
            wandb_run = init_wandb_run(
                job_type="evaluation" if args.gate_only else "training",
                name=f"source-v2-{args.stage}{'-gate' if args.gate_only else ''}",
                tags=(
                    "source-v2",
                    args.stage,
                    "gate-only" if args.gate_only else "sft",
                ),
                config={
                    **source_training_wandb_config(config, args.stage, args.gate_only),
                    "git": git_reference(REPO_ROOT),
                },
                run_id=tracking_run_id(receipt_base),
                resume=wandb_claim.resume,
            )
            reference = wandb_run_reference(wandb_run)
            if reference is None:
                raise RuntimeError("W&B recovery run has no local reference")
            finish_with_tracking_receipt(wandb_claim, reference, finish_active_wandb)
            print("source-v2 W&B finish recovery complete")
            return
    if args.gate_only:
        assert gate_output is not None
        create_exclusive_artifact_directory(
            gate_output,
            forbidden_roots=_gate_output_forbidden_roots(config),
        )
    else:
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
        wandb_run = init_wandb_run(
            job_type="evaluation" if args.gate_only else "training",
            name=f"source-v2-{args.stage}{'-gate' if args.gate_only else ''}",
            tags=("source-v2", args.stage, "gate-only" if args.gate_only else "sft"),
            config={
                **source_training_wandb_config(config, args.stage, args.gate_only),
                "git": git_reference(REPO_ROOT),
            },
            run_id=tracking_run_id(receipt_base),
            resume=wandb_claim.resume,
        )
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for source-v2 QLoRA training")

    model_config = config["model"]
    if args.gate_only:
        assert gate_output is not None
        gate_summary, gate_adapter_digest = _run_reload_and_schema_gate(
            adapter_output=final_adapter_output,
            records=gate_records,
            config=config,
            batch_size=int(config["canary"]["generation_batch_size"]),
            contract=protocol,
            prediction_path=gate_output / "post_training_gate_predictions.jsonl",
        )
        _write_gate_report(
            gate_output,
            final_adapter_output,
            config,
            canary_train_records,
            gate_records,
            gate_summary,
            adapter_artifact_sha256=gate_adapter_digest,
            promotion_authority=False,
            tracking=wandb_run_reference(wandb_run),
        )
        _log_wandb_gate(wandb_run, gate_summary.schema_pass_rate, config)
        _require_schema_gate(gate_summary.schema_pass_rate, config)
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
        print(
            f"[OK] adapter={final_adapter_output} "
            f"schema_pass_rate={gate_summary.schema_pass_rate:.3f}"
        )
        return
    print(
        f"[MODEL] Loading {model_config['runtime_model_id']}@"
        f"{model_config['revision']} in 4-bit "
        f"(canonical {model_config['base_model_id']})"
    )
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_config["runtime_model_id"],
        revision=model_config["revision"],
        max_seq_length=int(training["max_seq_length"]),
        dtype=None,
        load_in_4bit=True,
        cache_dir=model_config["cache_dir"],
    )
    resolved_model_id = str(getattr(model.config, "_name_or_path", ""))
    resolved_model_revision = getattr(model.config, "_commit_hash", None)
    if resolved_model_id != model_config["runtime_model_id"]:
        raise RuntimeError(
            f"resolved model mismatch: expected {model_config['runtime_model_id']}, "
            f"got {resolved_model_id}"
        )
    if resolved_model_revision != model_config["revision"]:
        raise RuntimeError(
            f"resolved revision mismatch: expected {model_config['revision']}, "
            f"got {resolved_model_revision}"
        )
    tokenizer_contract_digest = tokenizer_contract_sha256(tokenizer, protocol)
    target_regex = build_unsloth_moe_target_regex(
        list(training["attention_target_modules"]),
        list(training["expert_target_layers"]),
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=int(training["lora_r"]),
        target_modules=target_regex,
        target_parameters=None,
        lora_alpha=int(training["lora_alpha"]),
        lora_dropout=float(training["lora_dropout"]),
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=seed,
        max_seq_length=int(training["max_seq_length"]),
    )
    for peft_config in model.peft_config.values():
        peft_config.revision = resolved_model_revision
    train_dataset = _tokenize_dataset(
        train_records,
        tokenizer,
        int(training["max_seq_length"]),
        reasoning_effort=protocol.reasoning_effort,
    )
    validation_dataset = _tokenize_dataset(
        validation_records,
        tokenizer,
        int(training["max_seq_length"]),
        reasoning_effort=protocol.reasoning_effort,
    )

    stage_output = checkpoint_output
    update_steps = max(
        1,
        math.ceil(
            len(train_records)
            / int(training["batch_size"])
            / int(training["gradient_accumulation_steps"])
        ),
    )
    interval_steps = min(
        int(training["eval_steps"]),
        int(training["save_steps"]),
        update_steps,
    )
    trainer = Trainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            model=model,
            label_pad_token_id=-100,
            pad_to_multiple_of=8,
        ),
        args=TrainingArguments(
            output_dir=str(stage_output),
            per_device_train_batch_size=int(training["batch_size"]),
            per_device_eval_batch_size=int(training["eval_batch_size"]),
            gradient_accumulation_steps=int(training["gradient_accumulation_steps"]),
            num_train_epochs=float(training["epochs"]),
            learning_rate=float(training["learning_rate"]),
            warmup_ratio=float(training["warmup_ratio"]),
            lr_scheduler_type=training["lr_scheduler_type"],
            optim=training["optimizer"],
            weight_decay=float(training["weight_decay"]),
            bf16=torch.cuda.is_bf16_supported(),
            fp16=not torch.cuda.is_bf16_supported(),
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
        callbacks=(
            [SafeWandbTrainerCallback(wandb_run)] if wandb_run is not None else None
        ),
    )

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
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
    expert_tensors = _adapter_has_expert_tensors(final_adapter_output)
    if not expert_tensors:
        raise RuntimeError("canary gate failed: saved adapter has no expert tensors")

    manifest = {
        "recipe": source_training_recipe(config),
        "protocol": source_protocol_config(config),
        "protocol_sha256": source_protocol_sha256(config),
        "stage": args.stage,
        "base_model_id": model_config["base_model_id"],
        "runtime_model_id": model_config["runtime_model_id"],
        "runtime_model_revision": model_config["revision"],
        "resolved_model_id": resolved_model_id,
        "resolved_model_revision": resolved_model_revision,
        "tokenizer_contract_sha256": tokenizer_contract_digest,
        "config_sha256": source_training_config_sha256(config),
        "command": shlex.join([sys.executable, *sys.argv]),
        "packages": _package_versions(),
        "runtime": _runtime_manifest(),
        "lora_target_regex": target_regex,
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
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 3),
        "expert_adapter_tensors_present": expert_tensors,
        "adapter_sha256": file_sha256(
            final_adapter_output / "adapter_model.safetensors"
        ),
        "final_adapter_path": str(final_adapter_output),
        "checkpoint_selection": "not_performed_final_adapter_only",
        "trainer_eval_loss_disabled": (
            "Unsloth 2026.6.9 / unsloth-zoo 2026.6.7 / Transformers 5.5.0 "
            "eval forward is incompatible with create_causal_mask"
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
    torch.cuda.empty_cache()
    gate_prediction_path = adapter_output / "post_training_gate_predictions.jsonl"
    if gate_prediction_path.exists():
        raise FileExistsError(
            f"refusing to overwrite existing gate predictions: {gate_prediction_path}"
        )
    gate_summary, gate_adapter_digest = _run_reload_and_schema_gate(
        adapter_output=final_adapter_output,
        records=gate_records,
        config=config,
        batch_size=int(config["canary"]["generation_batch_size"]),
        contract=protocol,
        prediction_path=gate_prediction_path,
    )
    _write_gate_report(
        adapter_output,
        final_adapter_output,
        config,
        canary_train_records,
        gate_records,
        gate_summary,
        adapter_artifact_sha256=gate_adapter_digest,
        promotion_authority=recipe != "legacy_unsloth",
        tracking=wandb_run_reference(wandb_run),
    )
    if wandb_run is not None:
        from aegislm.tracking import log_wandb_payload

        log_wandb_payload(
            wandb_run,
            {
                "training/final_loss": result.training_loss,
                "training/elapsed_seconds": round(elapsed, 3),
                "training/peak_vram_gb": manifest["peak_vram_gb"],
            },
        )
    _log_wandb_gate(wandb_run, gate_summary.schema_pass_rate, config)
    _require_schema_gate(gate_summary.schema_pass_rate, config)
    if wandb_run is not None and receipt_path is not None and receipt_base is not None:
        reference = wandb_run_reference(wandb_run)
        if reference is None:
            raise RuntimeError("W&B training run has no local reference")
        assert wandb_claim is not None
        finish_with_tracking_receipt(wandb_claim, reference, finish_active_wandb)
    print(
        f"[OK] adapter={final_adapter_output} loss={result.training_loss:.6f} "
        f"elapsed={elapsed:.1f}s peak_vram={manifest['peak_vram_gb']}GiB "
        f"schema_pass_rate={gate_summary.schema_pass_rate:.3f}"
    )


def _tokenize_dataset(
    records: list[Any],
    tokenizer: Any,
    max_length: int,
    *,
    reasoning_effort: str,
) -> Dataset:
    rows = [
        tokenize_source_training_record(
            record,
            tokenizer,
            max_length=max_length,
            reasoning_effort=cast(Any, reasoning_effort),
        )
        for record in records
    ]
    if not rows or any(supervised_token_count(row) <= 0 for row in rows):
        raise RuntimeError("every training record must contain supervised tokens")
    return Dataset.from_list(rows)


def _adapter_has_expert_tensors(adapter_dir: Path) -> bool:
    from safetensors import safe_open  # type: ignore[import-not-found]

    weights = adapter_dir / "adapter_model.safetensors"
    if not weights.is_file():
        return False
    with safe_open(weights, framework="pt") as tensors:
        return any("experts" in key for key in tensors.keys())


def _run_reload_and_schema_gate(
    *,
    adapter_output: Path,
    records: list[Any],
    config: dict[str, Any],
    batch_size: int,
    contract: GenerationContract,
    prediction_path: Path,
) -> tuple[GateRunSummary, str]:
    """Reload the persisted adapter and validate deterministic held-out outputs."""
    _validate_adapter_base(adapter_output, config)
    artifact_digest_before = artifact_directory_sha256(adapter_output)
    model_config = config["model"]
    model, base_tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_config["runtime_model_id"],
        revision=model_config["revision"],
        max_seq_length=int(config["training"]["max_seq_length"]),
        dtype=None,
        load_in_4bit=True,
        cache_dir=model_config["cache_dir"],
    )
    _validate_resolved_model(model, config)
    tokenizer, _tokenizer_digest = load_persisted_source_tokenizer(
        AutoTokenizer,
        adapter_output,
        base_tokenizer,
        contract,
    )
    from peft import PeftModel  # type: ignore[import-not-found]

    model = PeftModel.from_pretrained(model, str(adapter_output), is_trainable=False)
    FastLanguageModel.for_inference(model)
    summary = run_source_schema_gate(
        model=model,
        tokenizer=tokenizer,
        records=records,
        prediction_path=prediction_path,
        batch_size=batch_size,
        contract=contract,
        require_harmony=source_training_recipe(config) != "legacy_unsloth",
    )
    del model
    gc.collect()
    torch.cuda.empty_cache()
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
    tracking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prediction_path = output_dir / "post_training_gate_predictions.jsonl"
    if artifact_directory_sha256(adapter_dir) != adapter_artifact_sha256:
        raise RuntimeError("adapter artifact changed before writing the gate report")
    gate_report = {
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
        "recipe": source_training_recipe(config),
        "protocol": source_protocol_config(config),
        "protocol_sha256": source_protocol_sha256(config),
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
        "prediction_path": str(prediction_path),
        "tracking": tracking,
    }
    report_path = output_dir / "post_training_gate.json"
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(gate_report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return gate_report


def _require_schema_gate(schema_pass_rate: float, config: dict[str, Any]) -> None:
    if schema_pass_rate < float(config["canary"]["minimum_schema_pass_rate"]):
        raise RuntimeError(
            f"post-training gate failed: schema_pass_rate={schema_pass_rate:.3f}"
        )


def _log_wandb_gate(
    run: Any | None, schema_pass_rate: float, config: dict[str, Any]
) -> None:
    if run is None:
        return
    from aegislm.tracking import log_wandb_payload

    threshold = float(config["canary"]["minimum_schema_pass_rate"])
    log_wandb_payload(
        run,
        {
            "gate/schema_pass_rate": schema_pass_rate,
            "gate/minimum_schema_pass_rate": threshold,
            "gate/passed": schema_pass_rate >= threshold,
        },
    )


def _require_passing_canary(
    config: dict[str, Any], train_records: list[Any], validation_records: list[Any]
) -> None:
    report_path = (
        Path(config["training"]["output_dir"]) / "canary" / "post_training_gate.json"
    )
    if not report_path.is_file():
        raise FileNotFoundError(
            f"full stage requires a passing canary report: {report_path}"
        )
    report = load_canary_gate_report(report_path)
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


def _generation_contract(config: dict[str, Any]) -> GenerationContract:
    protocol = source_protocol_config(config)
    eos = protocol["eos_token_ids"]
    return GenerationContract(
        reasoning_effort=cast(Any, protocol["reasoning_effort"]),
        padding_side="left",
        pad_token_id=protocol["pad_token_id"],
        eos_token_ids=tuple(eos) if eos is not None else None,
        do_sample=False,
        max_new_tokens=int(config["canary"]["max_new_tokens"]),
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


def _validate_resolved_model(model: Any, config: dict[str, Any]) -> None:
    resolved_model_id = str(getattr(model.config, "_name_or_path", ""))
    resolved_revision = getattr(model.config, "_commit_hash", None)
    if resolved_model_id != config["model"]["runtime_model_id"]:
        raise RuntimeError("fresh gate base model identity does not match the config")
    if resolved_revision != config["model"]["revision"]:
        raise RuntimeError("fresh gate base model revision does not match the config")


def _validate_adapter_base(adapter_dir: Path, config: dict[str, Any]) -> None:
    adapter_config_path = adapter_dir / "adapter_config.json"
    from aegislm.artifacts import load_bounded_json_object

    try:
        adapter_config, _digest = load_bounded_json_object(
            adapter_config_path, description="saved adapter config"
        )
    except ValueError as exc:
        raise ValueError(f"invalid adapter config: {adapter_config_path}") from exc
    expected_model = config["model"]["runtime_model_id"]
    expected_revision = config["model"]["revision"]
    if (
        adapter_config.get("base_model_name_or_path") != expected_model
        or adapter_config.get("revision") != expected_revision
    ):
        raise ValueError(
            "saved adapter base model or revision does not match the training config"
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


def _runtime_manifest() -> dict[str, Any]:
    properties = torch.cuda.get_device_properties(0)
    return {
        "python": sys.version.split()[0],
        "torch_cuda": torch.version.cuda,
        "gpu_name": properties.name,
        "gpu_total_vram_gb": round(properties.total_memory / 1024**3, 3),
        "gpu_compute_capability": list(torch.cuda.get_device_capability(0)),
    }


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
