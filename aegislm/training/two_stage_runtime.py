"""Lazy GPU workers for the fixed two-stage experiment."""

from __future__ import annotations

from dataclasses import asdict
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import time
from typing import Any

from aegislm.evaluation.harness import Prediction
from aegislm.inference.source import extract_harmony_final
from aegislm.training.fresh import (
    resolve_fresh_tokenizer_snapshot,
    validate_fresh_model_identity,
)
from aegislm.training.source import build_unsloth_moe_target_regex
from aegislm.training.source_config import artifact_directory_sha256
from aegislm.training.two_stage import freeze_tokenizer, tokenize_rows, write_json


def preserve_mask_signatures(masking_utils: Any) -> None:
    """Restore introspection lost by pinned Unsloth mask wrappers before GPT patching."""
    if getattr(masking_utils, "__patched_causal_mask__", False):
        raise ValueError("mask signatures must be preserved before GPT-OSS patching")
    for name in ("create_causal_mask", "create_sliding_window_causal_mask"):
        if hasattr(masking_utils, "_old_" + name):
            raise ValueError("unexpected prior GPT-OSS mask alias")
        original = getattr(masking_utils, "_unsloth_original_" + name, None)
        if original is None:
            raise ValueError("pinned Unsloth original mask factory missing")
        signature = inspect.signature(original)
        if not {
            "config",
            "inputs_embeds",
            "attention_mask",
            "past_key_values",
        }.issubset(signature.parameters):
            raise ValueError("unexpected original mask factory signature")
        wrapped = getattr(masking_utils, name)
        wrapped.__signature__ = signature


def load_model(
    config: dict[str, Any],
    date: str,
    adapter: Path | None = None,
    *,
    provenance: dict[str, Any] | None = None,
) -> tuple[Any, Any]:
    """Load only cached pinned weights and, optionally, a digest-checked adapter."""
    os.environ["UNSLOTH_RETURN_LOGITS"] = "1"
    unsloth = importlib.import_module("unsloth")
    if provenance is not None:
        preserve_mask_signatures(importlib.import_module("transformers.masking_utils"))
    snapshot = resolve_fresh_tokenizer_snapshot(config)
    settings = config["model"]
    model, tokenizer = unsloth.FastLanguageModel.from_pretrained(
        model_name=settings["runtime_model_id"],
        tokenizer_name=str(snapshot),
        revision=settings["revision"],
        cache_dir=settings["cache_dir"],
        local_files_only=True,
        max_seq_length=config["training"]["max_seq_length"],
        dtype=None,
        load_in_4bit=True,
    )
    validate_fresh_model_identity(model, config)
    if adapter is not None:
        manifest = json.loads((adapter.parent / "training.json").read_text())
        if provenance is not None and manifest.get("provenance") != provenance:
            raise ValueError("adapter preparation/config/data provenance mismatch")
        if artifact_directory_sha256(adapter) != manifest["adapter_sha256"]:
            raise ValueError("saved adapter digest mismatch")
        peft = importlib.import_module("peft")
        model = peft.PeftModel.from_pretrained(model, str(adapter), is_trainable=False)
        transformers = importlib.import_module("transformers")
        tokenizer = transformers.AutoTokenizer.from_pretrained(
            str(adapter), local_files_only=True
        )
        if not model.active_adapters:
            raise RuntimeError("adapter was not activated")
    freeze_tokenizer(tokenizer, date, training=False)
    if provenance is not None:
        from aegislm.training.cc_decision import tokenizer_fingerprint

        if tokenizer_fingerprint(tokenizer) != provenance["tokenizer_sha256"]:
            raise ValueError("loaded tokenizer differs from prepared contract")
    return model, tokenizer


def preflight(
    model: Any,
    tokenizer: Any,
    rows: list[dict[str, Any]],
    config: dict[str, Any],
    output: Path,
) -> None:
    """Check actual forward predictions at supervised positions with padding."""
    torch = importlib.import_module("torch")
    transformers = importlib.import_module("transformers")
    features = tokenize_rows(rows, tokenizer, config["training"]["max_seq_length"])
    chosen = [
        min(features, key=lambda r: len(r["input_ids"])),
        max(features, key=lambda r: len(r["input_ids"])),
    ]
    model.eval()
    model.config.use_cache = False
    checks = []
    for side in ("right", "left"):
        tokenizer.padding_side = side
        collator = transformers.DataCollatorForSeq2Seq(
            tokenizer, label_pad_token_id=-100, pad_to_multiple_of=8
        )
        packed = collator([{k: list(v) for k, v in row.items()} for row in chosen])
        # Explicitly retain the collated batch for diagnosis before moving to GPU.
        write_json(
            output / f"batch-{side}.json", {k: v.tolist() for k, v in packed.items()}
        )
        for index, row in enumerate(chosen):
            mask = packed["attention_mask"][index].bool()
            if (
                packed["labels"][index][mask].tolist() != row["labels"]
                or not (packed["labels"][index][~mask] == -100).all()
            ):
                raise RuntimeError("collator corrupted supervised labels")

        def selected(
            batch: Any, index: int, row: dict[str, list[int]]
        ) -> tuple[Any, float]:
            live = batch["attention_mask"][index].nonzero().flatten()
            positions = [i for i, x in enumerate(row["labels"]) if x != -100]
            with torch.inference_mode():
                result = model(
                    input_ids=batch["input_ids"].to("cuda"),
                    attention_mask=batch["attention_mask"].to("cuda"),
                    position_ids=(batch["attention_mask"].long().cumsum(-1) - 1)
                    .masked_fill(batch["attention_mask"] == 0, 0)
                    .to("cuda"),
                    use_cache=False,
                )
                if not hasattr(result.logits, "shape") or result.logits.ndim != 3:
                    raise RuntimeError("preflight requires real logits")
                logits = (
                    result.logits[index, live[torch.tensor(positions)] - 1]
                    .float()
                    .cpu()
                )
            targets = torch.tensor([row["labels"][i] for i in positions])
            loss = float(torch.nn.functional.cross_entropy(logits, targets))
            return logits, loss

        for index, row in enumerate(chosen):
            solo = collator([{k: list(v) for k, v in row.items()}])
            single, single_loss = selected(solo, 0, row)
            batched, batch_loss = selected(packed, index, row)
            maximum = float((single - batched).abs().max())
            passed = (
                bool(torch.isfinite(batched).all())
                and torch.allclose(single, batched, atol=0.5, rtol=0.02)
                and abs(single_loss - batch_loss) <= max(0.05, abs(single_loss) * 0.02)
            )
            checks.append(
                {
                    "padding_side": side,
                    "row": index,
                    "supervised_positions": sum(x != -100 for x in row["labels"]),
                    "max_logit_difference": maximum,
                    "single_loss": single_loss,
                    "batch_loss": batch_loss,
                    "pass": bool(passed),
                }
            )
    write_json(
        output / "gpu-preflight.json",
        {
            "checks": checks,
            "pass": all(r["pass"] for r in checks),
            "logit_atol": 0.5,
            "logit_rtol": 0.02,
            "position_ids": "live-token-cumulative-from-attention-mask",
        },
    )
    if not all(r["pass"] for r in checks):
        raise RuntimeError("GPU padding/forward parity failed; training blocked")


def generate(
    model: Any,
    tokenizer: Any,
    rows: list[dict[str, Any]],
    path: Path,
    objective: str,
    run_id: str,
) -> list[Prediction]:
    """Generate without gold or constrained decoding and persist raw token IDs."""
    torch = importlib.import_module("torch")
    unsloth = importlib.import_module("unsloth")
    unsloth.FastLanguageModel.for_inference(model)
    tokenizer.padding_side = "left"
    maximum = 128 if objective == "decision" else 512
    result = []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        for index, row in enumerate(rows):
            messages = row["messages"]
            if [m["role"] for m in messages] != ["system", "user"]:
                raise ValueError("generation must not receive assistant gold")
            inputs = tokenizer.apply_chat_template(
                [messages],
                tokenize=True,
                add_generation_prompt=True,
                padding=True,
                return_tensors="pt",
                return_dict=True,
                reasoning_effort="low",
            ).to("cuda")
            started = time.monotonic()
            with torch.inference_mode():
                tokens = model.generate(
                    **inputs,
                    max_new_tokens=maximum,
                    do_sample=False,
                    use_cache=True,
                    pad_token_id=200017,
                    eos_token_id=[200002, 199999],
                )
            ids = tokens[0, inputs["input_ids"].shape[1] :].tolist()
            for i, token in enumerate(ids):
                if token in (200002, 199999):
                    ids = ids[: i + 1]
                    break
            raw = tokenizer.decode(ids, skip_special_tokens=False)
            final = (
                extract_harmony_final(raw)
                if "<|channel|>final<|message|>" in raw
                else ""
            )
            prediction = Prediction(
                record_id=row["id"],
                model_id="openai/gpt-oss-20b",
                run_id=run_id,
                raw_output=final,
                raw_generation=raw,
                latency_ms=(time.monotonic() - started) * 1000,
                generation={
                    "input_ids": inputs["input_ids"][0].tolist(),
                    "generated_ids": ids,
                    "max_new_tokens": maximum,
                },
            )
            stream.write(json.dumps(asdict(prediction), ensure_ascii=False) + "\n")
            stream.flush()
            result.append(prediction)
            if (index + 1) % 10 == 0:
                print(f"{objective}: generated {index + 1}/{len(rows)}", flush=True)
    return result


def wandb_run_path(run: Any) -> str:
    """Handle SDK string paths and public-API component paths without splitting characters."""
    value = run.path
    path = value if isinstance(value, str) else "/".join(value)
    parts = path.split("/")
    if len(parts) != 3 or any(not part for part in parts) or parts[1] != "aegislm":
        raise ValueError("unexpected W&B entity/project/run path")
    return path


def start_tracking(config: dict[str, Any], objective: str, output: Path) -> Any:
    """Require a remote readiness receipt before any optimizer update."""
    from aegislm.environment import load_project_env
    from aegislm.tracking import init_wandb_run, log_wandb_payload, update_wandb_summary

    load_project_env(Path.cwd())
    run = init_wandb_run(
        job_type="training",
        name=f"{Path(config['output_dir']).name}-{objective}",
        tags=(config["recipe"], objective),
        config={
            "recipe": config["recipe"],
            "objective": objective,
            "base_model_id": config["model"]["base_model_id"],
            "model_revision": config["model"]["revision"],
            "label_status": "source_label_unreviewed"
            if config["recipe"] in {"cc_decision_v1", "cc_unsloth_smoke_v1"}
            else "frozen_reference",
            **config["training"],
        },
    )
    try:
        path = wandb_run_path(run)
        log_wandb_payload(run, {"preflight/ready": 1}, step=0)
        update_wandb_summary(run, {"preflight_ready": 1})
        wandb = importlib.import_module("wandb")
        deadline = time.monotonic() + 60
        while True:
            remote = wandb.Api().run(path)
            if remote.summary.get("preflight_ready") == 1:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "W&B readiness not visible remotely; training blocked"
                )
            time.sleep(3)
        write_json(
            output / "wandb.json",
            {
                "id": run.id,
                "path": path,
                "url": run.url,
                "remote_readiness_confirmed": True,
            },
        )
    except BaseException:
        run.finish(exit_code=1)
        raise
    return run


def verify_adapter_update(
    before: str, after: str, optimizer_lr: float, gradients_checked: bool
) -> None:
    """Require finite gradients; zero-LR warmup legitimately leaves weights unchanged."""
    if not math.isfinite(optimizer_lr) or optimizer_lr < 0 or not gradients_checked:
        raise RuntimeError("invalid optimizer learning rate or unverified gradients")
    if optimizer_lr > 0 and before == after:
        raise RuntimeError("positive-LR optimizer did not update adapter weights")


def train(
    config: dict[str, Any],
    date: str,
    objective: str,
    rows: list[dict[str, Any]],
    output: Path,
    *,
    provenance: dict[str, Any] | None = None,
) -> None:
    """Train exactly 100 updates from base and retain checkpoints and provenance."""
    if provenance is not None:
        from aegislm.training.cc_decision import TRAINING

        if config["training"] != TRAINING or os.environ.get("WORLD_SIZE", "1") != "1":
            raise ValueError("unsupported fixed decision training runtime")
    checkpoint = Path(config["checkpoint_dir"]) / objective
    final = Path(config["adapter_dir"]) / objective / "final"
    if checkpoint.exists() or final.parent.exists() or (output / "wandb.json").exists():
        raise ValueError("training destination/receipt exists; refusing overwrite")
    model, tokenizer = load_model(config, date, provenance=provenance)
    unsloth = importlib.import_module("unsloth")
    transformers = importlib.import_module("transformers")
    torch = importlib.import_module("torch")
    datasets = importlib.import_module("datasets")
    if provenance is not None and torch.cuda.device_count() != 1:
        raise ValueError("fixed decision comparison requires one CUDA device")
    from scripts.train_source_unsloth_fresh import (
        make_training_callback,
        trainable_fingerprint,
    )
    from aegislm.tracking import (
        log_wandb_payload,
        safe_training_log_payload,
        update_wandb_summary,
    )

    freeze_tokenizer(tokenizer, date, training=True)
    settings = config["training"]
    features = tokenize_rows(rows, tokenizer, settings["max_seq_length"])
    model = unsloth.FastLanguageModel.get_peft_model(
        model,
        r=settings["lora_r"],
        lora_alpha=settings["lora_alpha"],
        lora_dropout=settings["lora_dropout"],
        target_modules=build_unsloth_moe_target_regex(
            ["q_proj", "k_proj", "v_proj", "o_proj"], [7, 15, 23]
        ),
        target_parameters=None,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=settings["seed"],
        max_seq_length=settings["max_seq_length"],
    )
    for adapter_config in model.peft_config.values():
        adapter_config.revision = config["model"]["revision"]
    checks = make_training_callback(transformers, torch, None)

    callback_base: Any = transformers.TrainerCallback

    class Journal(callback_base):
        update_lr: float | None = None

        def on_pre_optimizer_step(
            self, args: Any, state: Any, control: Any, optimizer: Any, **kwargs: Any
        ) -> None:
            self.update_lr = max(group["lr"] for group in optimizer.param_groups)

        def on_log(
            self, args: Any, state: Any, control: Any, logs: Any = None, **kwargs: Any
        ) -> None:
            payload = safe_training_log_payload(logs or {})
            if payload:
                with (output / "metrics.jsonl").open("a") as stream:
                    stream.write(
                        json.dumps({"step": int(state.global_step), **payload}) + "\n"
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
                log_wandb_payload(run, payload, step=int(state.global_step))

        def on_step_end(
            self, args: Any, state: Any, control: Any, model: Any, **kwargs: Any
        ) -> Any:
            if state.global_step in (1, 10):
                current = trainable_fingerprint(model, torch)
                if self.update_lr is None or checks.initial_fingerprint is None:
                    raise RuntimeError("optimizer progress was not observed")
                verify_adapter_update(
                    checks.initial_fingerprint,
                    current,
                    self.update_lr,
                    checks.gradients_checked,
                )
            control.should_save = state.global_step in (10, 25, 50, 100)
            return control

    trainer = transformers.Trainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=datasets.Dataset.from_list(features),
        data_collator=transformers.DataCollatorForSeq2Seq(
            tokenizer=tokenizer, label_pad_token_id=-100, pad_to_multiple_of=8
        ),
        args=transformers.TrainingArguments(
            output_dir=str(checkpoint),
            per_device_train_batch_size=1,
            gradient_accumulation_steps=32,
            max_steps=100,
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
            save_strategy="steps",
            save_steps=100,
            save_total_limit=4,
            report_to="none",
            remove_unused_columns=False,
        ),
        callbacks=[checks, Journal()],
    )
    run = start_tracking(config, objective, output)
    started = time.monotonic()
    try:
        result = trainer.train()
        if (
            trainer.state.global_step != 100
            or not checks.gradients_checked
            or not math.isfinite(result.training_loss)
        ):
            raise RuntimeError("incomplete or invalid training")
        final.mkdir(parents=True)
        trainer.save_model(str(final))
        tokenizer.save_pretrained(str(final))
        manifest = {
            "objective": objective,
            "provenance": provenance,
            "steps": 100,
            "loss": result.training_loss,
            "elapsed_seconds": time.monotonic() - started,
            "gradients_checked": checks.gradients_checked,
            "adapter_sha256": artifact_directory_sha256(final),
            "before_sha256": checks.initial_fingerprint,
            "after_sha256": trainable_fingerprint(model, torch),
            "date": date,
            "wandb_id": run.id,
        }
        write_json(final.parent / "training.json", manifest)
        write_json(output / "training.json", manifest)
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
