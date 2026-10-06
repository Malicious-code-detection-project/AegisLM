"""Train adapted official SFTTrainer/final-only recipe and compare native EOS."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import importlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aegislm.artifacts import write_text_artifact  # noqa: E402
from aegislm.environment import load_project_env  # noqa: E402
from aegislm.evaluation.harness import Prediction, load_jsonl  # noqa: E402
from aegislm.evaluation.source_decision import evaluate_source_decisions  # noqa: E402
from aegislm.inference.source import extract_harmony_final  # noqa: E402
from aegislm.training.cc_decision import (  # noqa: E402
    context,
    development_rows,
    gpu_identity,
    load_config as load_source_config,
    load_data,
    tokenizer_fingerprint,
    wandb_readiness,
)
from aegislm.training.fresh import resolve_fresh_tokenizer_snapshot  # noqa: E402
from aegislm.training.source import build_unsloth_moe_target_regex  # noqa: E402
from aegislm.training.tutorial import (  # noqa: E402
    EOS,
    INSTRUCTION,
    RESPONSE,
    completion_metadata,
    cpu_mask_function,
    extended_rows,
    final_prefix_text,
    formatting_text,
    load_config,
    model_features,
    validate_final_labels,
)
from aegislm.training.two_stage import digest, freeze_tokenizer, write_json  # noqa: E402

FINAL = "<|channel|>final<|message|>"


def source_context(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Revalidate original immutable inputs without changing their recipe."""
    path = Path(config["source_config"])
    source = load_source_config(path)
    return source, context(source, path)


def implementation_paths() -> list[Path]:
    """Bind local entrypoints plus the actual installed trainer/mask sources."""
    site = Path(sys.prefix) / "lib/python3.12/site-packages"
    return [
        Path(__file__),
        ROOT / "aegislm/training/tutorial.py",
        site / "unsloth_zoo/dataset_utils.py",
        site / "trl/trainer/sft_trainer.py",
        site / "unsloth/models/rl.py",
        site / "unsloth/models/_utils.py",
        site / "unsloth_zoo/temporary_patches/gpt_oss.py",
        ROOT / "scripts/run_cc_max_new_tokens_65536.py",
    ]


def tokenized(row: dict[str, Any], tokenizer: Any) -> list[int]:
    """Encode rendered text exactly as the pre-training audit expects."""
    value: list[int] = tokenizer.encode(
        formatting_text(row, tokenizer), add_special_tokens=False
    )
    return value


def audit_rows(rows: list[dict[str, Any]], tokenizer: Any, mask: Any) -> dict[str, Any]:
    """Audit every record before creating a trainable model."""
    lengths, supervised = [], Counter()
    for row in rows:
        ids = tokenized(row, tokenizer)
        labels = mask({"input_ids": [ids]})["labels"][0]
        supervised[validate_final_labels(row, ids, labels, tokenizer, 4096)] += 1
        prefix = tokenizer.encode(
            final_prefix_text(
                {"id": row["id"], "messages": row["messages"][:2]}, tokenizer
            ),
            add_special_tokens=False,
        )
        if ids[: len(prefix)] != prefix or labels[: len(prefix)] != [-100] * len(
            prefix
        ):
            raise ValueError(
                "gold-free final prefix does not match supervised boundary"
            )
        lengths.append(len(ids))
    return {
        "count": len(rows),
        "min_tokens": min(lengths),
        "max_tokens": max(lengths),
        "supervised_count_histogram": dict(supervised),
        "extreme_ids": [
            rows[lengths.index(min(lengths))]["id"],
            rows[lengths.index(max(lengths))]["id"],
        ],
        "exact_final_tail": True,
        "gold_free_prefix_matches": True,
    }


def prepare(config: dict[str, Any], path: Path) -> None:
    """Freeze source, data, tutorial and EOS table before any GPU work."""
    out = Path(config["output_dir"])
    if out.exists():
        raise FileExistsError("preparation already exists")
    source, original = source_context(config)
    reference = Path(config["reference_dir"])
    receipt = json.loads(Path(config["tutorial_receipt"]).read_text())
    if receipt["git_commit"] != config["tutorial_commit"] or any(
        digest(ROOT / item["local_path"]) != item["sha256"] for item in receipt["files"]
    ):
        raise ValueError("pinned official source changed")
    data = load_data(source)
    dev = development_rows(data["exports"]["validation"])
    prompts = json.loads((reference / "prompts.json").read_text())
    gold = json.loads((reference / "gold.json").read_text())
    selected = {row["id"]: row for row in dev}
    if len(prompts) != 2 or [row["id"] for row in prompts] != [
        row["id"] for row in gold
    ]:
        raise ValueError("reference prompt set changed")
    for row, answer in zip(prompts, gold, strict=True):
        if row["messages"] != selected[row["id"]]["messages"][:2] or answer[
            "expected_output"
        ] != json.loads(selected[row["id"]]["messages"][-1]["content"]):
            raise ValueError("reference is not the same gold-free validation pair")
    tokenizer = importlib.import_module("transformers").AutoTokenizer.from_pretrained(
        str(resolve_fresh_tokenizer_snapshot(source)), local_files_only=True
    )
    freeze_tokenizer(tokenizer, original["date"], training=True)
    if tokenizer_fingerprint(tokenizer) != original["tokenizer_sha256"]:
        raise ValueError("prepared tokenizer differs from original")
    mask = cpu_mask_function(tokenizer, implementation_paths()[2])
    token_audit = {
        "train": audit_rows(data["exports"]["train"], tokenizer, mask),
        "development": audit_rows(dev, tokenizer, mask),
    }
    ready = wandb_readiness()
    if not ready["pass"]:
        raise RuntimeError(f"W&B readiness failed: {ready.get('reason', 'unknown')}")
    packages = dict(original["packages"], trl=version("trl"))
    manifest = {
        "config_sha256": digest(path),
        "source_preparation_sha256": digest(
            Path(source["output_dir"]) / "manifest.json"
        ),
        "source_hashes": {str(p): digest(p) for p in implementation_paths()},
        "tutorial_receipt_sha256": digest(Path(config["tutorial_receipt"])),
        "reference_comparison_sha256": digest(reference / "comparison.json"),
        "reference_prompts_sha256": digest(reference / "prompts.json"),
        "reference_gold_sha256": digest(reference / "gold.json"),
        "reference_base_predictions_sha256": digest(
            reference / "base/65536/predictions.jsonl"
        ),
        "date": original["date"],
        "tokenizer_sha256": original["tokenizer_sha256"],
        "packages": packages,
        "gpu": gpu_identity(),
        "token_audit": token_audit,
        "development_ids": [row["id"] for row in dev],
        "comparison_ids": [row["id"] for row in prompts],
        "train_count": 10000,
        "sample_presentations": 3200,
        "test_used": False,
        "source_label_unreviewed": True,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "literal_tutorial_reproduction": False,
    }
    write_json(out / "manifest.json", manifest)
    write_json(out / "config.json", config)
    write_json(out / "wandb-readiness.json", ready)
    write_json(out / "prompts.json", prompts)
    write_json(out / "gold.json", gold)
    write_json(
        out / "historical-comparison.json",
        json.loads((reference / "comparison.json").read_text()),
    )
    write_text_artifact(out / "execution-source.py", Path(__file__).read_text())
    write_text_artifact(
        out / "training-helper-source.py",
        (ROOT / "aegislm/training/tutorial.py").read_text(),
    )
    write_text_artifact(
        out / "plan.md",
        render_table(
            config,
            json.loads((reference / "comparison.json").read_text())["rows"],
            pending=True,
        ),
    )
    print(
        json.dumps({"prepared": True, "token_audit": token_audit, "test_used": False}),
        flush=True,
    )


def require_prepared(
    config: dict[str, Any], path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fail closed on changed implementations, reference data or runtime."""
    source, original = source_context(config)
    out = Path(config["output_dir"])
    manifest = json.loads((out / "manifest.json").read_text())
    pairs = {
        path: manifest["config_sha256"],
        Path(source["output_dir"]) / "manifest.json": manifest[
            "source_preparation_sha256"
        ],
        Path(config["tutorial_receipt"]): manifest["tutorial_receipt_sha256"],
        Path(config["reference_dir"]) / "comparison.json": manifest[
            "reference_comparison_sha256"
        ],
        Path(config["reference_dir"]) / "prompts.json": manifest[
            "reference_prompts_sha256"
        ],
        Path(config["reference_dir"]) / "gold.json": manifest["reference_gold_sha256"],
        out / "historical-comparison.json": manifest["reference_comparison_sha256"],
        Path(config["reference_dir"]) / "base/65536/predictions.jsonl": manifest[
            "reference_base_predictions_sha256"
        ],
        **{
            Path(name): expected for name, expected in manifest["source_hashes"].items()
        },
    }
    if any(digest(p) != expected for p, expected in pairs.items()):
        raise ValueError("prepared tutorial experiment changed")
    if (
        dict(original["packages"], trl=version("trl")) != manifest["packages"]
        or gpu_identity() != manifest["gpu"]
    ):
        raise ValueError("prepared runtime changed")
    for name, expected in (
        ("prompts.json", "reference_prompts_sha256"),
        ("gold.json", "reference_gold_sha256"),
    ):
        if digest(out / name) != manifest[expected]:
            raise ValueError("local comparison input changed")
    return source, manifest


def runtime_provenance(
    config: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Bind adapters to this recipe, not to the preserved original trainer."""
    return {
        key: manifest[key]
        for key in ("config_sha256", "source_hashes", "tokenizer_sha256", "packages")
    } | {"recipe": config["recipe"]}


def build_trainer(
    config: dict[str, Any], source: dict[str, Any], manifest: dict[str, Any]
) -> tuple[Any, Any, dict[str, Any]]:
    """Construct official SFTTrainer and verify the actual masked dataset/targets."""
    from aegislm.training.two_stage_runtime import load_model

    model, tokenizer = load_model(
        source, manifest["date"], provenance=runtime_provenance(config, manifest)
    )
    unsloth = importlib.import_module("unsloth")
    torch = importlib.import_module("torch")
    trl = importlib.import_module("trl")
    datasets = importlib.import_module("datasets")
    if torch.cuda.device_count() != 1:
        raise ValueError("tutorial adaptation requires one CUDA GPU")
    freeze_tokenizer(tokenizer, manifest["date"], training=True)
    layers = model.config.num_hidden_layers
    target = build_unsloth_moe_target_regex(
        ["q_proj", "k_proj", "v_proj", "o_proj"], list(range(layers))
    )
    names = [
        name
        for name, module in model.named_modules()
        if re.fullmatch(target, name) and hasattr(module, "weight")
    ]
    expected = layers * (4 + 2 * model.config.num_local_experts)
    if len(names) != expected or layers != 24:
        raise ValueError("unexpected linearized MoE module coverage")
    settings = config["training"]
    model = unsloth.FastLanguageModel.get_peft_model(
        model,
        r=settings["lora_r"],
        lora_alpha=settings["lora_alpha"],
        lora_dropout=0,
        target_modules=target,
        target_parameters=[],
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=settings["seed"],
        use_rslora=False,
        loftq_config=None,
    )
    injected = [
        name for name, module in model.named_modules() if hasattr(module, "lora_A")
    ]
    if len(injected) != expected or any(
        not any(actual.endswith(name) for actual in injected) for name in names
    ):
        raise ValueError("adapter injection differs from expected module set")
    trainable = {
        name: list(parameter.shape)
        for name, parameter in model.named_parameters()
        if parameter.requires_grad
    }
    if any("lora_" not in name for name in trainable):
        raise ValueError("unexpected trainable base parameter")
    for adapter_config in model.peft_config.values():
        adapter_config.revision = source["model"]["revision"]
    data = load_data(source)
    train_rows = data["exports"]["train"]
    dev_rows = development_rows(data["exports"]["validation"])

    def text_dataset(rows: list[dict[str, Any]]) -> Any:
        return datasets.Dataset.from_list(
            [{"id": row["id"], "text": formatting_text(row, tokenizer)} for row in rows]
        )

    trainer = trl.SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=text_dataset(train_rows),
        eval_dataset=text_dataset(dev_rows),
        args=trl.SFTConfig(
            output_dir=config["checkpoint_dir"],
            max_length=4096,
            dataset_num_proc=1,
            packing=False,
            padding_free=False,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=32,
            per_device_eval_batch_size=1,
            prediction_loss_only=True,
            max_steps=100,
            warmup_steps=5,
            learning_rate=2e-4,
            weight_decay=0.001,
            lr_scheduler_type="linear",
            optim="adamw_8bit",
            seed=3407,
            data_seed=3407,
            logging_steps=1,
            logging_nan_inf_filter=False,
            eval_strategy="steps",
            eval_steps=25,
            save_strategy="steps",
            save_steps=25,
            save_total_limit=4,
            report_to="none",
        ),
    )
    for attribute, rows in (("train_dataset", train_rows), ("eval_dataset", dev_rows)):
        actual = getattr(trainer, attribute)
        if len(actual) != len(rows):
            raise ValueError("SFTTrainer removed records before masking")
        for index, row in enumerate(rows):
            if actual[index]["input_ids"] != tokenized(row, tokenizer):
                raise ValueError("SFTTrainer changed tokens/order before masking")
            if "id" in actual.column_names and actual[index]["id"] != row["id"]:
                raise ValueError("SFTTrainer changed record IDs")
        if "id" not in actual.column_names:
            setattr(
                trainer, attribute, actual.add_column("id", [row["id"] for row in rows])
            )
    trainer = importlib.import_module("unsloth.chat_templates").train_on_responses_only(
        trainer,
        instruction_part=INSTRUCTION,
        response_part=RESPONSE,
        num_proc=1,
    )
    collator = trainer.data_collator

    def model_collator(features: list[dict[str, Any]]) -> Any:
        return collator([model_features(feature) for feature in features])

    trainer.data_collator = model_collator
    for split, actual, rows in (
        ("train", trainer.train_dataset, train_rows),
        ("development", trainer.eval_dataset, dev_rows),
    ):
        if len(actual) != len(rows) or len(rows) != (
            10000 if split == "train" else 100
        ):
            raise ValueError("SFTTrainer/helper removed records")
        for index, row in enumerate(rows):
            encoded = actual[index]
            if encoded["id"] != row["id"] or encoded["input_ids"] != tokenized(
                row, tokenizer
            ):
                raise ValueError(
                    "SFTTrainer changed IDs/order/tokens or truncated data"
                )
            validate_final_labels(
                row, encoded["input_ids"], encoded["labels"], tokenizer, 4096
            )
    coverage = {
        "module_count": len(injected),
        "attention_modules": layers * 4,
        "expert_modules": layers * model.config.num_local_experts * 2,
        "trainable_parameters": sum(
            p.numel() for p in model.parameters() if p.requires_grad
        ),
        "trainable_shapes": trainable,
        "injected_module_names": injected,
        "actual_train_count": len(trainer.train_dataset),
        "actual_eval_count": len(trainer.eval_dataset),
        "trainer_class": f"{type(trainer).__module__}.{type(trainer).__name__}",
        "bf16": trainer.args.bf16,
        "fp16": trainer.args.fp16,
        "force_float32": __import__("os").environ.get("UNSLOTH_FORCE_FLOAT32"),
        "dataset_preserved_and_exact_final_labels": True,
        "target_mapping_adaptation": "all_linearized_experts_target_parameters_empty",
    }
    return trainer, tokenizer, coverage


def preflight(
    config: dict[str, Any], source: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """Use an isolated model process for finite forward/backward, with no update."""
    trainer, _, coverage = build_trainer(config, source, manifest)
    torch = importlib.import_module("torch")
    # compute_loss bypasses SFTTrainer.train()'s training-mode wrapper.
    trainer.model.for_training(
        use_gradient_checkpointing=trainer.args.gradient_checkpointing
    )
    trainer.model.train()
    ids = manifest["token_audit"]["train"]["extreme_ids"]
    features = {row["id"]: row for row in trainer.train_dataset if row["id"] in ids}
    checks = []
    for identifier in ids:
        trainer.model.zero_grad(set_to_none=True)
        batch = trainer._prepare_inputs(trainer.data_collator([features[identifier]]))
        with trainer.compute_loss_context_manager():
            loss = trainer.compute_loss(trainer.model, batch)
        trainer.accelerator.backward(loss)
        gradients = [
            p.grad
            for p in trainer.model.parameters()
            if p.requires_grad and p.grad is not None
        ]
        if (
            not torch.isfinite(loss).item()
            or not gradients
            or not all(torch.isfinite(g).all().item() for g in gradients)
            or not any(torch.count_nonzero(g).item() for g in gradients)
        ):
            raise RuntimeError("nonfinite/zero tutorial backward")
        checks.append(
            {
                "id": identifier,
                "loss": float(loss.detach()),
                "finite_nonzero_gradients": True,
                "training_mode": trainer.model.training,
            }
        )
    trainer.model.zero_grad(set_to_none=True)
    write_json(
        Path(config["output_dir"]) / "preflight.json",
        {
            "pass": True,
            "config_sha256": manifest["config_sha256"],
            "coverage": coverage,
            "checks": checks,
            "optimizer_steps": 0,
            "peak_allocated_mib": torch.cuda.max_memory_allocated() / 1024**2,
            "peak_reserved_mib": torch.cuda.max_memory_reserved() / 1024**2,
        },
    )


def tracking_run(config: dict[str, Any], out: Path) -> Any:
    """Confirm authorized W&B run readiness before optimizer progress."""
    from aegislm.tracking import init_wandb_run, log_wandb_payload, update_wandb_summary
    from aegislm.training.two_stage_runtime import wandb_run_path

    run = init_wandb_run(
        job_type="training",
        name=config["experiment_id"],
        tags=(config["recipe"], "decision"),
        config={
            "recipe": config["recipe"],
            "label_status": "source_label_unreviewed",
            "tutorial_commit": config["tutorial_commit"],
            **config["training"],
        },
    )
    try:
        log_wandb_payload(run, {"preflight/ready": 1}, step=0)
        update_wandb_summary(run, {"preflight_ready": 1})
        api = importlib.import_module("wandb").Api(timeout=20)
        deadline = time.monotonic() + 60
        while api.run(wandb_run_path(run)).summary.get("preflight_ready") != 1:
            if time.monotonic() >= deadline:
                raise RuntimeError("W&B remote readiness timeout")
            time.sleep(3)
        write_json(
            out / "wandb.json",
            {
                "id": run.id,
                "path": wandb_run_path(run),
                "url": run.url,
                "remote_readiness_confirmed": True,
            },
        )
        return run
    except BaseException:
        run.finish(exit_code=1)
        raise


def train(
    config: dict[str, Any], source: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """Train the fixed100 updates after the separate preflight passes."""
    from aegislm.tracking import (
        log_wandb_payload,
        safe_training_log_payload,
        update_wandb_summary,
    )
    from aegislm.training.two_stage_runtime import verify_adapter_update
    from scripts.train_source_unsloth_fresh import (
        make_training_callback,
        trainable_fingerprint,
    )
    from aegislm.training.source_config import artifact_directory_sha256

    out = Path(config["output_dir"])
    pre = json.loads((out / "preflight.json").read_text())
    if (
        not pre["pass"]
        or pre["optimizer_steps"] != 0
        or pre["config_sha256"] != manifest["config_sha256"]
    ):
        raise ValueError("bound tutorial GPU preflight required")
    final = Path(config["adapter_dir"]) / "final"
    if (out / "training-intent.json").exists() or final.parent.exists():
        raise FileExistsError("training attempt exists; no implicit retry")
    write_json(
        out / "training-intent.json",
        {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "steps": 100,
            "test_used": False,
        },
    )
    trainer, tokenizer, coverage = build_trainer(config, source, manifest)
    if coverage != pre["coverage"]:
        raise ValueError("training coverage differs from preflight")
    write_json(out / "training-runtime.json", coverage)
    run = tracking_run(config, out)
    torch = importlib.import_module("torch")
    transformers = importlib.import_module("transformers")
    checks = make_training_callback(transformers, torch, None)
    callback_base: Any = transformers.TrainerCallback

    class Journal(callback_base):
        lr: float | None = None
        pending_step: int | None = None
        pending: dict[str, float]

        def __init__(self) -> None:
            self.pending = {}

        def flush(self) -> None:
            if self.pending_step is not None and self.pending:
                log_wandb_payload(run, self.pending, step=self.pending_step)
                self.pending = {}

        def on_pre_optimizer_step(
            self, args: Any, state: Any, control: Any, optimizer: Any, **kwargs: Any
        ) -> None:
            self.lr = max(group["lr"] for group in optimizer.param_groups)

        def on_step_end(
            self, args: Any, state: Any, control: Any, model: Any, **kwargs: Any
        ) -> None:
            if state.global_step == 10:
                if checks.initial_fingerprint is None or self.lr is None:
                    raise RuntimeError("optimizer progress not observed")
                verify_adapter_update(
                    checks.initial_fingerprint,
                    trainable_fingerprint(model, torch),
                    self.lr,
                    checks.gradients_checked,
                )

        def on_log(
            self, args: Any, state: Any, control: Any, logs: Any = None, **kwargs: Any
        ) -> None:
            payload = safe_training_log_payload(logs or {})
            if logs and "eval_loss" in logs:
                value = float(logs["eval_loss"])
                if not math.isfinite(value):
                    raise RuntimeError("non-finite validation loss")
                payload["validation/loss"] = value
            if payload:
                with (out / "metrics.jsonl").open("a") as stream:
                    stream.write(
                        json.dumps({"step": int(state.global_step), **payload}) + "\n"
                    )
                step = int(state.global_step)
                if self.pending_step != step:
                    self.flush()
                    self.pending_step = step
                self.pending.update(payload)

        def on_train_end(
            self, args: Any, state: Any, control: Any, **kwargs: Any
        ) -> None:
            self.flush()

    trainer.add_callback(checks)
    trainer.add_callback(Journal())
    started = time.monotonic()
    try:
        result = trainer.train()
        if (
            trainer.state.global_step != 100
            or not checks.gradients_checked
            or not math.isfinite(result.training_loss)
        ):
            raise RuntimeError("training incomplete")
        trainer.save_model(str(final))
        tokenizer.save_pretrained(str(final))
        training = {
            "steps": 100,
            "epoch": trainer.state.epoch,
            "loss": float(result.training_loss),
            "elapsed_seconds": time.monotonic() - started,
            "gradients_checked": True,
            "provenance": runtime_provenance(config, manifest),
            "adapter_sha256": artifact_directory_sha256(final),
            "before_sha256": checks.initial_fingerprint,
            "after_sha256": trainable_fingerprint(trainer.model, torch),
            "test_used": False,
        }
        if training["before_sha256"] == training["after_sha256"]:
            raise RuntimeError("adapter did not update")
        write_json(final.parent / "training.json", training)
        write_json(out / "training.json", training)
        update_wandb_summary(
            run,
            {
                "training_complete": True,
                "optimizer_steps": 100,
                "train_loss": float(result.training_loss),
            },
        )
        run.finish(exit_code=0)
    except BaseException:
        run.finish(exit_code=1)
        raise


def evaluate(
    config: dict[str, Any], source: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """Fresh reload; evaluate equal caps with both bare and final-prefilled starts."""
    from aegislm.training.two_stage_runtime import load_model
    from scripts.run_cc_max_new_tokens_65536 import generate_one

    runtime = deepcopy(source)
    runtime["training"]["max_seq_length"] = config["generation"][
        "runtime_context_length"
    ]
    model, tokenizer = load_model(
        runtime,
        manifest["date"],
        Path(config["adapter_dir"]) / "final",
        provenance=runtime_provenance(config, manifest),
    )
    importlib.import_module("unsloth").FastLanguageModel.for_inference(model)
    model.generation_config.forced_eos_token_id = None
    model.generation_config.min_new_tokens = 0
    model.generation_config.min_length = 0
    torch = importlib.import_module("torch")
    out = Path(config["output_dir"])
    prompts = json.loads((out / "prompts.json").read_text())
    gold = json.loads((out / "gold.json").read_text())
    generation = config["generation"]
    new_rows = []
    reference_predictions = {
        item["record_id"]: item
        for item in load_jsonl(
            Path(config["reference_dir"]) / "base/65536/predictions.jsonl"
        )
    }
    for protocol in generation["start_protocols"]:
        predictions = []
        folder = out / "evaluation" / protocol
        for row in prompts:
            if protocol == "bare-assistant":
                prediction = generate_one(
                    model, tokenizer, row, "tutorial_adapter", 65536, 131072, 300
                )
            else:
                inputs = tokenizer(
                    final_prefix_text(row, tokenizer),
                    add_special_tokens=False,
                    return_tensors="pt",
                    return_attention_mask=True,
                ).to("cuda")
                n = inputs["input_ids"].shape[1]
                if n + 65536 > 131072:
                    raise ValueError("final prefix plus generation exceeds context")
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                started = time.monotonic()
                with torch.inference_mode():
                    result = model.generate(
                        **inputs,
                        max_new_tokens=65536,
                        max_time=300,
                        do_sample=False,
                        use_cache=True,
                        pad_token_id=200017,
                        eos_token_id=list(EOS),
                        forced_eos_token_id=None,
                        min_new_tokens=0,
                    )
                torch.cuda.synchronize()
                elapsed = time.monotonic() - started
                ids = result[0, n:].tolist()
                raw = tokenizer.decode(ids, skip_special_tokens=False)
                prediction = Prediction(
                    record_id=row["id"],
                    model_id="openai/gpt-oss-20b",
                    run_id="tutorial_adapter-final-prefill",
                    raw_output=extract_harmony_final(FINAL + raw),
                    raw_generation=raw,
                    latency_ms=elapsed * 1000,
                    generation={
                        "input_ids": inputs["input_ids"][0].tolist(),
                        "generated_ids": ids,
                        "max_new_tokens": 65536,
                        "max_time_seconds": 300,
                        "peak_allocated_mib": torch.cuda.max_memory_allocated()
                        / 1024**2,
                        "peak_reserved_mib": torch.cuda.max_memory_reserved() / 1024**2,
                    },
                )
            assert prediction.generation is not None
            if protocol == "bare-assistant":
                if (
                    prediction.generation["input_ids"]
                    != reference_predictions[row["id"]]["generation"]["input_ids"]
                ):
                    raise ValueError(
                        "bare-assistant input tokens differ from historical reference"
                    )
                prediction.generation["historical_input_ids_match"] = True
            prediction.generation.update(
                completion_metadata(
                    prediction.generation["generated_ids"],
                    65536,
                    prediction.latency_ms / 1000,
                    300,
                )
            )
            prediction.generation.update(
                start_protocol=protocol,
                final_in_prompt=protocol == "final-prefill",
                final_in_generation=FINAL in prediction.raw_generation,
            )
            predictions.append(prediction)
            print(
                json.dumps(
                    {
                        "protocol": protocol,
                        "case": len(predictions),
                        "tokens": prediction.generation["token_count"],
                        "reason": prediction.generation["completion_reason"],
                    }
                ),
                flush=True,
            )
        write_text_artifact(
            folder / "predictions.jsonl",
            "".join(
                json.dumps(asdict(p), ensure_ascii=False) + "\n" for p in predictions
            ),
        )
        report = evaluate_source_decisions(gold, predictions)
        report.update(
            test_used=False,
            diagnostic_only=True,
            start_protocol=protocol,
            same_validation_ids=manifest["comparison_ids"],
        )
        write_json(folder / "evaluation.json", report)
        gs = [p.generation for p in predictions if p.generation is not None]
        new_rows.append(
            {
                "model": "tutorial_adapter",
                "start_protocol": protocol,
                "max_new_tokens": 65536,
                "cases": 2,
                "final": sum(g["final_in_generation"] for g in gs),
                "prompt_final": sum(g["final_in_prompt"] for g in gs),
                "parse": sum(c["parse_success"] for c in report["cases"]),
                "schema": sum(c["schema_valid"] for c in report["cases"]),
                "eos": sum(g["engine_eos_present"] for g in gs),
                "answer_end": sum(g["answer_end_present"] for g in gs),
                "token_limit": sum(g["completion_reason"] == "token_limit" for g in gs),
                "time_limit": sum(g["completion_reason"] == "time_limit" for g in gs),
                "min_tokens": min(g["token_count"] for g in gs),
                "max_tokens": max(g["token_count"] for g in gs),
            }
        )
    historical = json.loads((out / "historical-comparison.json").read_text())["rows"]
    rows = extended_rows(historical, new_rows)
    write_json(
        out / "comparison.json",
        {
            "rows": rows,
            "historical_rows_preserved": True,
            "test_used": False,
            "diagnostic_only": True,
            "same_validation_ids": manifest["comparison_ids"],
        },
    )
    write_text_artifact(
        out / "sfttrainer-final-only-mask-eos-return-comparison.md",
        render_table(config, rows),
    )
    write_json(
        out / "reload.json",
        {
            "adapter_reloaded": True,
            "context": model.config.max_position_embeddings,
            "max_seq_length": model.max_seq_length,
            "provenance": runtime_provenance(config, manifest),
        },
    )


def render_table(
    config: dict[str, Any], rows: list[dict[str, Any]], *, pending: bool = False
) -> str:
    """Expose start protocol separately from generated final markers."""
    text = f"# {config['title']}\n\n"
    text += "Historical8rows retained. New training changes Trainer/mask/targets/hyperparameters; not a mask-only causal ablation. Same2validation IDs, test unused.\n\n"
    text += "| Model | Start protocol | Cap | Cases | Generated final | Prompt final | JSON | Schema | EOS | Return | Token limit | Time limit | Actual tokens |\n"
    text += "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n"
    for row in rows:
        text += f"| {row['model']} | {row.get('start_protocol', 'bare-assistant')} | {row['max_new_tokens']:,} | {row['cases']} | {row['final']} | {row.get('prompt_final', 0)} | {row['parse']} | {row['schema']} | {row['eos']} | {row.get('answer_end', 'unrecorded')} | {row['token_limit']} | {row['time_limit']} | {row['min_tokens']}–{row['max_tokens']} |\n"
    if pending:
        for protocol in config["generation"]["start_protocols"]:
            text += f"| tutorial_adapter | {protocol} | 65,536 | 2 | pending | pending | pending | pending | pending | pending | pending | pending | pending |\n"
    return text


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/cc_tutorial_final_only_eos_v1.json"),
    )
    parser.add_argument(
        "--stage",
        choices=("prepare", "preflight", "train", "evaluate", "run"),
        required=True,
    )
    args = parser.parse_args(argv)
    load_project_env(ROOT)
    config = load_config(args.config)
    if args.stage == "prepare":
        prepare(config, args.config)
        return
    source, manifest = require_prepared(config, args.config)
    if args.stage == "run":
        for stage in ("preflight", "train", "evaluate"):
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__)),
                    "--config",
                    str(args.config.resolve()),
                    "--stage",
                    stage,
                ],
                cwd=ROOT,
                check=True,
            )
        write_json(
            Path(config["output_dir"]) / "execution-result.json",
            {
                "returncode": 0,
                "steps": 100,
                "table_rows": 10,
                "test_used": False,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    elif args.stage == "preflight":
        preflight(config, source, manifest)
    elif args.stage == "train":
        train(config, source, manifest)
    else:
        evaluate(config, source, manifest)


if __name__ == "__main__":
    main()
