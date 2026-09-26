"""Manually run source-v2 Unsloth QLoRA: prepare, smoke, canary, then full.

Run from the repository root. Heavy imports occur only after argument parsing
and data validation. This script never starts another training stage by itself.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib
import importlib.metadata
import json
import math
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.datasets.source import records_sha256  # noqa: E402
from aegislm.training.fresh import (  # noqa: E402
    CHECKPOINT_EVIDENCE_FILE,
    CHECKPOINT_EVIDENCE_SCHEMA,
    FRESH_RECIPE,
    SMOKE_STEPS,
    FreshData,
    checkpoint_logged_loss,
    fresh_stage_exit_code,
    load_fresh_config,
    load_fresh_data,
    load_completed_checkpoint,
    prepare_fresh_tokens,
    reload_fresh_stage,
    resolve_fresh_tokenizer_snapshot,
    require_fresh_canary,
    select_fresh_stage,
    tokenize_fresh_records,
    validate_fresh_model_identity,
    write_fresh_json,
    write_training_traces,
)
from aegislm.training.source_config import (  # noqa: E402
    artifact_directory_sha256,
    file_sha256,
    reserve_training_stage,
    resolved_source_generation_contract,
    source_training_config_sha256,
)


def build_parser() -> argparse.ArgumentParser:
    """Expose a GPU-free help/argument surface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/source_v2_unsloth_fresh.json")
    )
    parser.add_argument("--stage", choices=("smoke", "canary", "full"), default="smoke")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Audit all data and the cached tokenizer without model loading.",
    )
    parser.add_argument("--resume-from-checkpoint", type=Path)
    parser.add_argument(
        "--wandb",
        action="store_true",
        help="Opt in to the existing source-free W&B tracking policy.",
    )
    parser.add_argument("--wandb-reconcile", choices=("retry-logging", "finish-only"))
    parser.add_argument("--reload-only", action="store_true", help=argparse.SUPPRESS)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Reject incompatible modes before loading data, credentials or libraries."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.prepare_only and (
        args.wandb or args.resume_from_checkpoint or args.reload_only
    ):
        parser.error("--prepare-only cannot train, resume, reload, or use W&B")
    if args.reload_only and (args.wandb or args.resume_from_checkpoint):
        parser.error("reload subprocess cannot train or use W&B")
    if args.wandb_reconcile and not args.wandb:
        parser.error("--wandb-reconcile requires --wandb")
    return args


def trainable_fingerprint(model: Any, torch: Any) -> str:
    """Hash finite trainable LoRA tensors to verify an actual optimizer update."""
    digest = hashlib.sha256()
    count = 0
    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            continue
        if "lora_" not in name:
            raise RuntimeError(f"unexpected trainable base parameter: {name}")
        tensor = parameter.detach().cpu().contiguous()
        if not torch.isfinite(tensor).all().item():
            raise RuntimeError("trainable adapter contains non-finite weights")
        digest.update(name.encode())
        digest.update(tensor.view(torch.uint8).numpy().tobytes())
        count += tensor.numel()
    if count == 0:
        raise RuntimeError("model has no trainable LoRA parameters")
    return digest.hexdigest()


def make_training_callback(
    transformers: Any,
    torch: Any,
    run: Any,
    checkpoint_context: dict[str, Any] | None = None,
) -> Any:
    """Check real gradients and forward only approved scalar logs to W&B."""
    from aegislm.tracking import log_wandb_payload, safe_training_log_payload

    class TrainingChecks(transformers.TrainerCallback):
        def __init__(self) -> None:
            self.initial_fingerprint: str | None = None
            self.gradients_checked = False
            self.losses: list[float] = []

        def on_train_begin(
            self, args: Any, state: Any, control: Any, model: Any, **kwargs: Any
        ) -> None:
            self.initial_fingerprint = trainable_fingerprint(model, torch)

        def on_pre_optimizer_step(
            self, args: Any, state: Any, control: Any, model: Any, **kwargs: Any
        ) -> None:
            if self.gradients_checked:
                return
            nonzero = False
            for parameter in model.parameters():
                if parameter.requires_grad and parameter.grad is not None:
                    grad = parameter.grad.detach()
                    if not torch.isfinite(grad).all().item():
                        raise RuntimeError("non-finite adapter gradient")
                    nonzero |= bool(torch.count_nonzero(grad).item())
            if not nonzero:
                raise RuntimeError("all adapter gradients are missing or zero")
            self.gradients_checked = True

        def on_log(
            self,
            args: Any,
            state: Any,
            control: Any,
            logs: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> None:
            if not logs:
                return
            for key in ("loss", "grad_norm"):
                if key in logs and not math.isfinite(float(logs[key])):
                    raise RuntimeError(f"non-finite training {key}")
            if "loss" in logs:
                self.losses.append(float(logs["loss"]))
            if run is not None and state.is_world_process_zero:
                payload = safe_training_log_payload(logs)
                if payload:
                    log_wandb_payload(run, payload, step=int(state.global_step))

        def on_save(
            self, args: Any, state: Any, control: Any, model: Any, **kwargs: Any
        ) -> None:
            if (
                checkpoint_context is None
                or not state.is_world_process_zero
                or state.global_step != state.max_steps
            ):
                return
            from aegislm.artifacts import load_bounded_json_object

            after = trainable_fingerprint(model, torch)
            if (
                not self.losses
                or not self.gradients_checked
                or self.initial_fingerprint is None
                or self.initial_fingerprint == after
            ):
                raise RuntimeError(
                    "completed checkpoint has no verified adapter update"
                )
            checkpoint = Path(args.output_dir) / f"checkpoint-{state.global_step}"
            saved_state, state_digest = load_bounded_json_object(
                checkpoint / "trainer_state.json", description="saved checkpoint state"
            )
            if (
                saved_state.get("global_step") != state.global_step
                or saved_state.get("max_steps") != state.max_steps
            ):
                raise RuntimeError("saved checkpoint step does not match Trainer state")
            checkpoint_logged_loss(saved_state)
            write_fresh_json(
                checkpoint / CHECKPOINT_EVIDENCE_FILE,
                {
                    **checkpoint_context,
                    "schema_version": CHECKPOINT_EVIDENCE_SCHEMA,
                    "global_step": state.global_step,
                    "max_steps": state.max_steps,
                    "gradients_checked": True,
                    "trainable_before_sha256": self.initial_fingerprint,
                    "trainable_after_sha256": after,
                    "trainer_state_sha256": state_digest,
                    "adapter_sha256": file_sha256(
                        checkpoint / "adapter_model.safetensors"
                    ),
                    "adapter_config_sha256": file_sha256(
                        checkpoint / "adapter_config.json"
                    ),
                },
            )

    return TrainingChecks()


def train_stage(
    config: dict[str, Any], data: FreshData, args: argparse.Namespace, run: Any
) -> None:
    """Load, tokenize, train, save; the caller then starts a fresh reload process."""
    selected, gate_records = select_fresh_stage(data, args.stage)
    completed = load_completed_checkpoint(
        args.resume_from_checkpoint,
        config=config,
        stage=args.stage,
        train_records_digest=records_sha256(selected),
    )
    tokenizer_snapshot = resolve_fresh_tokenizer_snapshot(config)
    # Unsloth must patch the runtime before any direct torch/Transformers import.
    unsloth = importlib.import_module("unsloth")
    torch = importlib.import_module("torch")
    transformers = importlib.import_module("transformers")
    datasets = importlib.import_module("datasets")
    from aegislm.training.source import (
        build_unsloth_moe_target_regex,
        tokenizer_contract_sha256,
    )
    from aegislm.tracking import wandb_run_reference

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for Unsloth QLoRA training")
    training = config["training"]
    model_config = config["model"]
    output = Path(training["output_dir"]) / args.stage
    checkpoint = Path(training["checkpoint_dir"]) / args.stage
    model, tokenizer = unsloth.FastLanguageModel.from_pretrained(
        model_name=model_config["runtime_model_id"],
        tokenizer_name=str(tokenizer_snapshot),
        revision=model_config["revision"],
        cache_dir=model_config["cache_dir"],
        local_files_only=True,
        max_seq_length=training["max_seq_length"],
        dtype=None,
        load_in_4bit=True,
    )
    validate_fresh_model_identity(model, config)
    tokenizer.padding_side = "left"
    tokenizer_digest = tokenizer_contract_sha256(
        tokenizer,
        resolved_source_generation_contract(config),
    )
    # Audit ALL supervised records with the actual training tokenizer, even for smoke.
    train_tokens = tokenize_fresh_records(data.train, tokenizer, config)
    validation_tokens = tokenize_fresh_records(data.validation, tokenizer, config)
    del validation_tokens
    indexed = {
        record.record_id: row
        for record, row in zip(data.train, train_tokens, strict=True)
    }
    selected_features = [indexed[record.record_id] for record in selected]

    trace_path = output.parent / (f"{args.stage}.training-trace-{uuid4().hex}.jsonl")
    write_training_traces(
        trace_path,
        selected,
        selected_features,
        tokenizer,
    )
    trace_sha256 = file_sha256(trace_path)

    dataset = datasets.Dataset.from_list(selected_features)
    del indexed, train_tokens, selected_features

    targets = build_unsloth_moe_target_regex(
        training["attention_target_modules"],
        training["expert_target_layers"],
    )
    model = unsloth.FastLanguageModel.get_peft_model(
        model,
        r=training["lora_r"],
        lora_alpha=training["lora_alpha"],
        lora_dropout=training["lora_dropout"],
        target_modules=targets,
        target_parameters=None,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=training["seed"],
        max_seq_length=training["max_seq_length"],
    )
    for peft_config in model.peft_config.values():
        peft_config.revision = model_config["revision"]
    checks = make_training_callback(
        transformers,
        torch,
        run,
        {
            "config_sha256": source_training_config_sha256(config),
            "stage": args.stage,
            "train_records_sha256": records_sha256(selected),
            "tokenizer_contract_sha256": tokenizer_digest,
        },
    )
    trainer = transformers.Trainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        data_collator=transformers.DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            label_pad_token_id=-100,
            pad_to_multiple_of=8,
        ),
        args=transformers.TrainingArguments(
            output_dir=str(checkpoint),
            per_device_train_batch_size=training["batch_size"],
            gradient_accumulation_steps=training["gradient_accumulation_steps"],
            num_train_epochs=training["epochs"],
            max_steps=SMOKE_STEPS if args.stage == "smoke" else -1,
            learning_rate=training["learning_rate"],
            warmup_ratio=training["warmup_ratio"],
            lr_scheduler_type=training["lr_scheduler_type"],
            optim=training["optimizer"],
            weight_decay=training["weight_decay"],
            bf16=torch.cuda.is_bf16_supported(),
            fp16=not torch.cuda.is_bf16_supported(),
            logging_steps=1,
            logging_nan_inf_filter=False,
            eval_strategy="no",
            save_strategy="steps",
            save_steps=SMOKE_STEPS if args.stage == "smoke" else training["save_steps"],
            save_total_limit=training["save_total_limit"],
            load_best_model_at_end=False,
            report_to="none",
            seed=training["seed"],
            data_seed=training["seed"],
            remove_unused_columns=False,
        ),
        callbacks=[checks],
    )
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    if completed is not None:
        # Do not call train(): a terminal smoke checkpoint may otherwise take an
        # extra optimizer step when max_steps ends partway through an epoch.
        recover_completed_checkpoint(
            trainer,
            model,
            checks,
            torch,
            transformers,
            args.resume_from_checkpoint,
            completed,
            tokenizer_digest,
        )
        training_loss = float(completed["training_loss"])
    else:
        result = trainer.train(
            resume_from_checkpoint=(
                str(args.resume_from_checkpoint)
                if args.resume_from_checkpoint
                else None
            )
        )
        training_loss = float(result.training_loss)
    elapsed = time.monotonic() - started
    final_fingerprint = trainable_fingerprint(model, torch)
    if (
        not checks.losses
        or not checks.gradients_checked
        or checks.initial_fingerprint == final_fingerprint
        or not math.isfinite(training_loss)
    ):
        raise RuntimeError(
            "training did not produce finite loss and a verified adapter update"
        )
    # Save only adapter/tokenizer; a partial final directory deliberately blocks resume.
    final = output / "final"
    final.mkdir()
    trainer.save_model(str(final))
    tokenizer.save_pretrained(str(final))
    safe_open = importlib.import_module("safetensors").safe_open
    with safe_open(final / "adapter_model.safetensors", framework="pt") as tensors:
        keys = list(tensors.keys())
        if not keys or not any("experts" in key for key in keys):
            raise RuntimeError("saved adapter has no expert tensors")
        if not all(
            torch.isfinite(tensors.get_tensor(key)).all().item() for key in keys
        ):
            raise RuntimeError("saved adapter contains non-finite tensors")
    manifest = {
        "recipe": FRESH_RECIPE,
        "stage": args.stage,
        "config": config,
        "config_sha256": source_training_config_sha256(config),
        "base_model_id": model_config["base_model_id"],
        "runtime_model_id": model_config["runtime_model_id"],
        "runtime_model_revision": model_config["revision"],
        "tokenizer_contract_sha256": tokenizer_digest,
        "train_records_sha256": records_sha256(selected),
        "gate_records_sha256": records_sha256(gate_records),
        "train_record_count": len(selected),
        "validation_record_count": len(gate_records),
        "max_steps": SMOKE_STEPS if args.stage == "smoke" else None,
        "global_step": trainer.state.global_step,
        "trainable_before_sha256": checks.initial_fingerprint,
        "trainable_after_sha256": final_fingerprint,
        "gradients_checked": checks.gradients_checked,
        "training_loss": training_loss,
        "training_loss_source": (
            "checkpoint_log_history_mean" if completed else "trainer_result"
        ),
        "resume_mode": (
            "finalize_completed_checkpoint"
            if completed
            else "continue_training"
            if args.resume_from_checkpoint
            else "new_training"
        ),
        "gradient_verification_source": "checkpoint_evidence"
        if completed
        else "current_run",
        "checkpoint_evidence_sha256": completed["evidence_sha256"]
        if completed
        else None,
        "elapsed_seconds": elapsed,
        "peak_vram_gb": torch.cuda.max_memory_allocated() / 1024**3,
        "adapter_artifact_sha256": artifact_directory_sha256(final),
        "adapter_sha256": file_sha256(final / "adapter_model.safetensors"),
        "adapter_tensor_count": len(keys),
        "checkpoint_selection": "not_performed_final_adapter_only",
        "trainer_eval_loss": "disabled_due_to_pinned_runtime_mask_incompatibility",
        "command": shlex.join([sys.executable, *sys.argv]),
        "packages": {
            name: importlib.metadata.version(name)
            for name in (
                "unsloth",
                "unsloth-zoo",
                "torch",
                "transformers",
                "peft",
                "trl",
                "datasets",
                "accelerate",
                "bitsandbytes",
                "safetensors",
                "wandb",
            )
        },
        "runtime": {
            "python": sys.version,
            "gpu": torch.cuda.get_device_name(0),
            "cuda": torch.version.cuda,
        },
        "tracking": wandb_run_reference(run),
        "training_trace": {
            "path": str(trace_path),
            "sha256": trace_sha256,
            "record_count": len(selected),
            "capture_point": "before_data_collator",
        },
    }
    write_fresh_json(output / "aegislm_training_manifest.json", manifest)
    write_fresh_json(
        output / "training_log.json", {"log_history": trainer.state.log_history}
    )
    del trainer, model, dataset
    gc.collect()
    torch.cuda.empty_cache()


def recover_completed_checkpoint(
    trainer: Any,
    model: Any,
    checks: Any,
    torch: Any,
    transformers: Any,
    checkpoint: Path,
    evidence: dict[str, Any],
    tokenizer_digest: str,
) -> None:
    """Restore a verified terminal adapter without another optimizer step."""
    expected_steps = trainer.set_initial_training_values(
        trainer.args, trainer.get_train_dataloader()
    )[-1]
    if expected_steps != evidence["max_steps"]:
        raise ValueError(
            "completed checkpoint does not match the current training schedule"
        )
    if tokenizer_digest != evidence["tokenizer_contract_sha256"]:
        raise ValueError("completed checkpoint tokenizer contract mismatch")
    if list(model.peft_config) != ["default"]:
        raise ValueError("completed checkpoint recovery requires the default adapter")
    peft = importlib.import_module("peft")
    weights = peft.load_peft_weights(
        str(checkpoint), device="cpu", local_files_only=True
    )
    peft.set_peft_model_state_dict(model, weights, adapter_name="default")
    if trainable_fingerprint(model, torch) != evidence["trainable_after_sha256"]:
        raise ValueError("restored checkpoint trainable weights do not match evidence")
    trainer.state = transformers.TrainerState.load_from_json(
        str(checkpoint / "trainer_state.json")
    )
    checks.initial_fingerprint = evidence["trainable_before_sha256"]
    checks.gradients_checked = True
    checks.losses = [evidence["training_loss"]]
    print(f"[RECOVERY] Finalizing completed checkpoint without training: {checkpoint}")


def run_training(
    config: dict[str, Any], data: FreshData, args: argparse.Namespace
) -> None:
    """Reserve the stage, optionally track it, and independently reload its adapter."""
    from aegislm.tracking import (
        build_tracking_receipt,
        finish_active_wandb,
        finish_with_tracking_receipt,
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
    from aegislm.artifacts import load_bounded_json_object

    config_digest = source_training_config_sha256(config)
    selected, gate = select_fresh_stage(data, args.stage)
    output = Path(config["training"]["output_dir"]) / args.stage
    checkpoint = Path(config["training"]["checkpoint_dir"]) / args.stage
    # Missing tokenizer assets must not consume an immutable stage reservation.
    resolve_fresh_tokenizer_snapshot(config)
    claim = None
    run = None
    exit_code = 1
    try:
        if args.wandb:
            require_wandb_api_key()
            base = build_tracking_receipt(
                "training",
                tracking_payload_sha256(
                    {
                        "config_sha256": config_digest,
                        "stage": args.stage,
                        "train_records_sha256": records_sha256(selected),
                        "gate_records_sha256": records_sha256(gate),
                    }
                ),
            )
            claim = prepare_tracking_receipt(
                output.parent / f"{args.stage}.wandb.json",
                base,
                ambiguous_resolution=args.wandb_reconcile,
            )
            if claim is None:
                print(
                    "[TRACKING] Receipt already complete; inspect local stage results."
                )
                if fresh_stage_exit_code(output, args.stage):
                    raise RuntimeError(
                        "tracking is complete but the local stage did not pass"
                    )
                exit_code = 0
                return
        if claim is None or claim.needs_logging:
            reserve_training_stage(
                adapter_stage=output,
                checkpoint_stage=checkpoint,
                resume_from_checkpoint=args.resume_from_checkpoint,
                config_sha256=config_digest,
                stage=args.stage,
            )
        if claim is not None:
            if claim.needs_logging:
                mark_tracking_logging_started(claim)
            run = init_wandb_run(
                job_type="training",
                name=f"source-v2-fresh-{args.stage}",
                config={
                    **source_training_wandb_config(config, args.stage, False),
                    "train_record_count": len(selected),
                    "max_steps": SMOKE_STEPS if args.stage == "smoke" else None,
                },
                tags=("source-v2", "fresh", args.stage),
                run_id=tracking_run_id(claim.base),
                resume=claim.resume,
            )
            if not claim.needs_logging:
                reference = wandb_run_reference(run)
                assert reference is not None
                exit_code = fresh_stage_exit_code(output, args.stage)
                finish_with_tracking_receipt(
                    claim,
                    reference,
                    lambda _code: finish_active_wandb(exit_code),
                )
                if exit_code:
                    raise RuntimeError(
                        "W&B finish recovered; local stage is incomplete or failed"
                    )
                return
        print(f"[TRAIN] {args.stage}: {len(selected)} records; output={output}")
        train_stage(config, data, args, run)
        if run is not None:
            manifest, _ = load_bounded_json_object(
                output / "aegislm_training_manifest.json",
                description="fresh manifest",
            )
            log_wandb_payload(
                run,
                {
                    "training/final_loss": manifest["training_loss"],
                    "training/elapsed_seconds": manifest["elapsed_seconds"],
                    "training/peak_vram_gb": manifest["peak_vram_gb"],
                },
            )
        # No inherited model or Trainer objects in the reload process.
        child = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--config",
                str(args.config.resolve()),
                "--stage",
                args.stage,
                "--reload-only",
            ],
            cwd=REPO_ROOT,
            check=False,
        )
        report_path = output / "post_training_gate.json"
        if report_path.is_file() and run is not None:
            report, _ = load_bounded_json_object(
                report_path, description="fresh gate report"
            )
            log_wandb_payload(
                run,
                {
                    "gate/schema_pass_rate": report["schema_pass_rate"],
                    "gate/passed": report["passed"],
                    "gate/minimum_schema_pass_rate": report["minimum_schema_pass_rate"],
                },
            )
        exit_code = 0 if child.returncode == 0 else 1
        if claim is not None:
            reference = wandb_run_reference(run)
            assert reference is not None
            finish_with_tracking_receipt(
                claim,
                reference,
                lambda _code: finish_active_wandb(exit_code),
            )
        if child.returncode:
            raise RuntimeError(
                f"reload/gate failed; inspect {output}; do not start full"
            )
        print(f"[DONE] {args.stage}: {report_path}")
    finally:
        try:
            finish_active_wandb(exit_code)
        finally:
            if claim is not None:
                claim.close()


def main(argv: list[str] | None = None) -> None:
    """Run only the stage explicitly selected by the user."""
    args = parse_args(argv)
    if Path.cwd().resolve() != REPO_ROOT:
        raise ValueError(f"Run from repository root: {REPO_ROOT}")
    config = load_fresh_config(args.config)
    data = load_fresh_data(config)
    if args.prepare_only:
        print(json.dumps(prepare_fresh_tokens(config, data), indent=2))
        print("[READY] Data/token checks passed; no model weights loaded.")
        return
    if args.reload_only:
        reload_fresh_stage(config, data, args.stage)
        return
    if args.stage == "full":
        require_fresh_canary(config, data)
    from aegislm.environment import load_project_env

    load_project_env(REPO_ROOT)
    run_training(config, data, args)


if __name__ == "__main__":
    main()
