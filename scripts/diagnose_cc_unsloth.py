"""Run an isolated two-update batch-1 LoRA diagnostic on the pinned v5 train split."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aegislm.environment import load_project_env  # noqa: E402
from aegislm.artifacts import validate_artifact_output_location  # noqa: E402
from aegislm.training.cc_decision import (  # noqa: E402
    gpu_identity,
    load_config,
    load_data,
    package_versions,
    tokenizer_assets,
    verify_inputs,
    wandb_readiness,
)
from aegislm.training.source import build_unsloth_moe_target_regex  # noqa: E402
from aegislm.training.source_config import artifact_directory_sha256  # noqa: E402
from aegislm.training.two_stage import (  # noqa: E402
    digest,
    freeze_tokenizer,
    tokenize_rows,
    write_json,
)


def select_train(
    rows: list[dict[str, Any]], extremes: list[str]
) -> list[dict[str, Any]]:
    """Select 64 unique balanced train records, retaining both length extremes."""
    indexed = {r["id"]: r for r in rows}
    if (
        len(indexed) != len(rows)
        or len(set(extremes)) != 2
        or not set(extremes) <= set(indexed)
    ):
        raise ValueError("diagnostic extremes must be unique training records")
    selected = []
    for label in ("present", "not_observed"):
        ordered = sorted(
            (
                r
                for r in rows
                if json.loads(r["messages"][-1]["content"])["assessment"] == label
            ),
            key=lambda r: hashlib.sha256(f"3407:smoke:{r['id']}".encode()).hexdigest(),
        )
        preferred = [r for r in ordered if r["id"] in extremes]
        selected.extend(
            (preferred + [r for r in ordered if r["id"] not in extremes])[:32]
        )
    if len(selected) != 64 or not set(extremes) <= {r["id"] for r in selected}:
        raise ValueError("insufficient balanced train data for diagnostic")
    # Keep extremes at known manifest positions; Trainer shuffles all 64 with seed3407.
    return [indexed[i] for i in extremes] + [
        r for r in selected if r["id"] not in extremes
    ]


def lora_fingerprint(model: Any, torch: Any) -> str:
    """Compare finite LoRA values before/after updates and frozen reloads."""
    result = hashlib.sha256()
    count = 0
    for name, value in sorted(model.named_parameters()):
        if value.requires_grad and "lora_" not in name:
            raise RuntimeError("diagnostic would update a base parameter")
        if "lora_" not in name:
            continue
        tensor = value.detach().float().cpu().contiguous()
        if not torch.isfinite(tensor).all().item():
            raise RuntimeError("nonfinite saved/reloaded LoRA values")
        result.update(name.encode())
        result.update(tensor.view(torch.uint8).numpy().tobytes())
        count += tensor.numel()
    if not count:
        raise RuntimeError("no LoRA parameters")
    return result.hexdigest()


def validated_training_loss(logs: dict[str, Any]) -> float | None:
    """Read raw Trainer keys before the outbound journal adds training/ prefixes."""
    for key in ("loss", "grad_norm"):
        if key in logs and not math.isfinite(float(logs[key])):
            raise RuntimeError("nonfinite loss/gradient norm")
    return float(logs["loss"]) if "loss" in logs else None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/cc_source_decision_v5.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", choices=("train", "reload"), required=True)
    args = parser.parse_args(argv)
    load_project_env(ROOT)
    config = load_config(args.config)
    output = args.output.absolute()
    checkpoint = ROOT / "checkpoints" / output.name
    adapter = ROOT / "adapters" / output.name / "final"
    for directory in (output, checkpoint, adapter.parent):
        validate_artifact_output_location(directory)
    if not output.is_relative_to(ROOT / "outputs"):
        raise ValueError("diagnostic output must be below the repository outputs root")
    from aegislm.training.two_stage_runtime import (
        load_model,
        start_tracking,
        verify_adapter_update,
    )

    if args.stage == "reload":
        m = json.loads((output / "diagnostic.json").read_text())
        if (
            m["config_sha256"] != digest(args.config)
            or m["packages"] != package_versions()
        ):
            raise ValueError("diagnostic config/runtime changed")
        if m["dataset_hashes"] != verify_inputs(config) or m[
            "tokenizer_assets"
        ] != tokenizer_assets(config):
            raise ValueError("diagnostic data/tokenizer changed")
        for path, value in m["source_hashes"].items():
            if digest(ROOT / path) != value:
                raise ValueError("diagnostic code changed before reload")
        model, tokenizer = load_model(
            config,
            config["protocol"]["template_date"],
            adapter,
            provenance=m["provenance"],
        )
        torch = importlib.import_module("torch")
        after = lora_fingerprint(model, torch)
        if after != m["after_sha256"] or not model.active_adapters:
            raise RuntimeError("saved adapter values did not survive reload")
        from aegislm.tracking import validate_wandb_payload

        metrics = {
            "diagnostic/adapter_reload_pass": True,
            "diagnostic/optimizer_steps": 2,
        }
        validate_wandb_payload(metrics)
        receipt = json.loads((output / "wandb.json").read_text())
        if m["wandb"] != {key: receipt[key] for key in ("id", "path")}:
            raise ValueError("diagnostic W&B run changed before reload")
        importlib.import_module("wandb").Api().run(receipt["path"]).summary.update(
            metrics
        )
        write_json(
            output / "reload.json",
            {
                "pass": True,
                "after_sha256": after,
                "adapter_sha256": artifact_directory_sha256(adapter),
                "provenance": m["provenance"],
                "active_adapters": model.active_adapters,
                "optimizer_steps": 0,
                "wandb": m["wandb"],
            },
        )
        print("adapter reload: pass", flush=True)
        return
    if any(p.exists() for p in (output, checkpoint, adapter.parent)):
        raise ValueError("diagnostic destination exists; no implicit overwrite/retry")
    tracking = wandb_readiness()
    if not tracking["pass"]:
        raise RuntimeError("online W&B authentication/project check failed")
    data = load_data(config)
    prepared = json.loads((Path(config["output_dir"]) / "manifest.json").read_text())
    if prepared["config_sha256"] != digest(args.config) or prepared[
        "dataset_hashes"
    ] != verify_inputs(config):
        raise ValueError("original prepared inputs no longer match")
    rows = select_train(data["exports"]["train"], prepared["preflight_ids"])
    prov = {
        "recipe": "cc_unsloth_smoke_v1",
        "config_sha256": digest(args.config),
        "dataset_inventory_sha256": config["dataset"]["inventory_sha256"],
        "base_revision": config["model"]["revision"],
        "tokenizer_sha256": prepared["tokenizer_sha256"],
        "diagnostic_namespace": output.name,
    }
    smoke_config = deepcopy(config)
    smoke_config.update(recipe=prov["recipe"], output_dir=str(output))
    smoke_config["training"]["max_steps"] = 2
    input_manifest = {
        "provenance": prov,
        "config_sha256": digest(args.config),
        "config_snapshot": config,
        "dataset_hashes": verify_inputs(config),
        "packages": package_versions(),
        "tokenizer_assets": tokenizer_assets(config),
        "source_hashes": {
            str(p.relative_to(ROOT)): digest(p)
            for p in sorted(
                set(ROOT.glob("aegislm/**/*.py")) | set(ROOT.glob("scripts/*.py"))
            )
        },
        "train_ids": [r["id"] for r in rows],
        "training": smoke_config["training"],
        "gpu": gpu_identity(),
        "wandb_readiness": tracking,
        "test_or_validation_used_for_optimizer": False,
        "purpose": "functional-diagnostic-only",
    }
    write_json(output / "inputs.json", input_manifest)
    model, tokenizer = load_model(
        config, config["protocol"]["template_date"], provenance=prov
    )
    unsloth = importlib.import_module("unsloth")
    torch = importlib.import_module("torch")
    transformers = importlib.import_module("transformers")
    datasets = importlib.import_module("datasets")
    if torch.cuda.device_count() != 1:
        raise RuntimeError("diagnostic requires one CUDA device")
    freeze_tokenizer(tokenizer, config["protocol"]["template_date"], training=True)
    features = tokenize_rows(rows, tokenizer, 4096)
    model = unsloth.FastLanguageModel.get_peft_model(
        model,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=build_unsloth_moe_target_regex(
            ["q_proj", "k_proj", "v_proj", "o_proj"], [7, 15, 23]
        ),
        target_parameters=None,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
        max_seq_length=4096,
    )
    model.config.use_cache = False
    for peft_config in model.peft_config.values():
        peft_config.revision = config["model"]["revision"]
    if not any("experts" in n and "lora_" in n for n, _ in model.named_parameters()):
        raise RuntimeError("expert LoRA targets were not applied")
    from aegislm.tracking import (
        log_wandb_payload,
        safe_training_log_payload,
        update_wandb_summary,
    )

    callback_base: Any = transformers.TrainerCallback

    class Checks(callback_base):
        def __init__(self) -> None:
            self.before = ""
            self.previous = ""
            self.update_lr = 0.0
            self.gradient_checks = 0
            self.updates: list[dict[str, Any]] = []
            self.losses: list[float] = []

        def on_train_begin(
            self, args: Any, state: Any, control: Any, model: Any, **kwargs: Any
        ) -> None:
            self.before = lora_fingerprint(model, torch)
            self.previous = self.before

        def on_pre_optimizer_step(
            self,
            args: Any,
            state: Any,
            control: Any,
            model: Any,
            optimizer: Any,
            **kwargs: Any,
        ) -> None:
            live = [
                p.grad
                for p in model.parameters()
                if p.requires_grad and p.grad is not None
            ]
            if (
                not live
                or not all(torch.isfinite(g).all().item() for g in live)
                or not any(torch.count_nonzero(g).item() for g in live)
            ):
                raise RuntimeError("missing, zero or nonfinite LoRA gradients")
            self.gradient_checks += 1
            self.update_lr = max(group["lr"] for group in optimizer.param_groups)

        def on_step_end(
            self, args: Any, state: Any, control: Any, model: Any, **kwargs: Any
        ) -> Any:
            record: dict[str, Any] = {
                "step": int(state.global_step),
                "optimizer_lr": self.update_lr,
                "fingerprint": lora_fingerprint(model, torch),
            }
            verify_adapter_update(
                self.previous,
                record["fingerprint"],
                self.update_lr,
                self.gradient_checks > 0,
            )
            self.previous = record["fingerprint"]
            self.updates.append(record)
            print(
                json.dumps(
                    {
                        "optimizer_step": record["step"],
                        "optimizer_lr": self.update_lr,
                        "weights_changed_from_initial": record["fingerprint"]
                        != self.before,
                    }
                ),
                flush=True,
            )
            return control

        def on_log(
            self, args: Any, state: Any, control: Any, logs: Any = None, **kwargs: Any
        ) -> None:
            payload = safe_training_log_payload(logs or {})
            loss = validated_training_loss(logs or {})
            if loss is not None:
                self.losses.append(loss)
            if payload:
                with (output / "metrics.jsonl").open("a") as stream:
                    stream.write(
                        json.dumps({"step": int(state.global_step), **payload}) + "\n"
                    )
                log_wandb_payload(run, payload, step=int(state.global_step))

    checks = Checks()
    trainer = transformers.Trainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=datasets.Dataset.from_list(features),
        data_collator=transformers.DataCollatorForSeq2Seq(
            tokenizer, label_pad_token_id=-100, pad_to_multiple_of=8
        ),
        args=transformers.TrainingArguments(
            output_dir=str(checkpoint),
            per_device_train_batch_size=1,
            gradient_accumulation_steps=32,
            max_steps=2,
            learning_rate=1e-4,
            warmup_ratio=0.1,
            lr_scheduler_type="cosine",
            optim="adamw_8bit",
            weight_decay=0.01,
            bf16=True,
            fp16=False,
            seed=3407,
            data_seed=3407,
            logging_steps=1,
            logging_nan_inf_filter=False,
            eval_strategy="no",
            save_strategy="no",
            report_to="none",
            remove_unused_columns=False,
        ),
        callbacks=[checks],
    )
    run = start_tracking(smoke_config, "decision-runtime-smoke", output)
    torch.cuda.reset_peak_memory_stats()
    try:
        result = trainer.train()
        after = lora_fingerprint(model, torch)
        write_json(
            output / "observed-training.json",
            {
                "steps": int(trainer.state.global_step),
                "gradient_checks": checks.gradient_checks,
                "losses": checks.losses,
                "before_sha256": checks.before,
                "after_sha256": after,
                "updates": checks.updates,
            },
        )
        if (
            trainer.state.global_step != 2
            or checks.gradient_checks != 2
            or not checks.losses
            or not math.isfinite(result.training_loss)
            or checks.before == after
        ):
            raise RuntimeError("no complete finite diagnostic adapter update")
        adapter.mkdir(parents=True)
        trainer.save_model(str(adapter))
        tokenizer.save_pretrained(str(adapter))
        report = {
            **input_manifest,
            "pass": True,
            "optimizer_steps": 2,
            "gradient_checks": checks.gradient_checks,
            "loss": result.training_loss,
            "before_sha256": checks.before,
            "after_sha256": after,
            "updates": checks.updates,
            "adapter_sha256": artifact_directory_sha256(adapter),
            "peak_vram_bytes": torch.cuda.max_memory_allocated(),
            "elapsed_seconds": result.metrics.get("train_runtime"),
            "wandb": {
                key: json.loads((output / "wandb.json").read_text())[key]
                for key in ("id", "path")
            },
        }
        write_json(adapter.parent / "training.json", report)
        write_json(output / "diagnostic.json", report)
        update_wandb_summary(
            run,
            {
                "diagnostic/training_pass": True,
                "diagnostic/optimizer_steps": 2,
                "diagnostic/gradient_checks": checks.gradient_checks,
                "diagnostic/loss": float(result.training_loss),
            },
        )
        run.finish(exit_code=0)
        print("diagnostic training: pass", flush=True)
    except BaseException:
        run.finish(exit_code=1)
        raise


if __name__ == "__main__":
    main()
