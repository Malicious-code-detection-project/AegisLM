"""One-shot GPT-OSS pilot: reviewed data, frozen split, baseline/train/reload.

This diagnostic run never promotes the parent dataset or schedules another run.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time
import uuid
from typing import Any

SYSTEM = (
    "You are a defensive source-code vulnerability classifier. Use only the "
    "supplied function and requested CWE. Return exactly one JSON object with "
    'one key, assessment: "present", "not_observed", or "uncertain". '
    "Do not provide exploit instructions. not_observed is scoped to this "
    "function and CWE, not a claim that the whole program is safe."
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def verify_runtime(config: dict[str, Any]) -> None:
    for name, version in config["expected_versions"].items():
        if importlib.metadata.version(name) != version:
            raise RuntimeError(f"runtime mismatch: {name}")


def verify_snapshot(config: dict[str, Any], *, weights: bool = False) -> None:
    root = Path(config["model_root"])
    path = root / "pilot_snapshot_attestation.json"
    if digest(path) != config["model_attestation_sha256"]:
        raise RuntimeError("snapshot attestation changed")
    attestation = json.loads(path.read_text())
    if (
        attestation["repo_id"] != config["model_id"]
        or attestation["revision"] != config["model_revision"]
    ):
        raise RuntimeError("snapshot revision mismatch")
    for name, identity in attestation["files"].items():
        if Path(name).name != name:
            raise RuntimeError("unsafe snapshot filename")
        file = root / name
        if file.stat().st_size != identity["size"]:
            raise RuntimeError(f"snapshot size mismatch: {name}")
        if (weights or not name.endswith(".safetensors")) and digest(file) != identity[
            "sha256"
        ]:
            raise RuntimeError(f"snapshot hash mismatch: {name}")


def review_composition(reviews: list[dict[str, Any]]) -> dict[str, int]:
    methods = collections.Counter(r["review_method"] for r in reviews)
    expected = {
        "AI-assisted structured source review": 88,
        "AI-assisted structured review of CWE-191/194/195 causal evidence; not expert sign-off": 12,
    }
    if dict(methods) != expected:
        raise ValueError("review composition is not the frozen 88/12 cohort")
    return dict(methods)


def verify_review_cwes(reviews: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    for review in reviews:
        if review["review_method"].startswith("AI-assisted structured review of CWE-"):
            if metadata[review["id"]]["cwe"] not in {"CWE-191", "CWE-194", "CWE-195"}:
                raise ValueError("re-audited review ID has an unexpected CWE")


def pilot_tokenizer(config: dict[str, Any]) -> Any:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        config["model_root"], local_files_only=True, trust_remote_code=False
    )
    expression = 'strftime_now("%Y-%m-%d")'
    if expression not in tokenizer.chat_template:
        raise ValueError("unrecognized GPT-OSS template date expression")
    tokenizer.chat_template = tokenizer.chat_template.replace(
        expression, json.dumps(config["template_date"])
    )
    tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def validate_run(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    run = Path(config["run_root"])
    manifest = json.loads((run / "manifest.json").read_text())
    if (
        digest(config_path) != manifest["input_config_sha256"]
        or digest(Path(__file__)) != manifest["script_sha256"]
    ):
        raise RuntimeError("config or script changed after preflight")
    if (
        config["training_runs_allowed"] != 1
        or config["full_training_approved"]
        or config["nurilab_deployment_approved"]
    ):
        raise RuntimeError("pilot authorization boundary changed")
    for name, expected in manifest["artifact_hashes"].items():
        if digest(run / name) != expected:
            raise RuntimeError(f"artifact changed: {name}")
    verify_runtime(config)
    verify_snapshot(config)
    return manifest


def authorize_child(config: dict[str, Any], phase: str) -> None:
    run = Path(config["run_root"])
    try:
        parent = json.loads((run / "RUN_STARTED").read_text())
        state = json.loads((run / "status.json").read_text())
    except FileNotFoundError as error:
        raise RuntimeError("direct phases are forbidden; use guarded run") from error
    if (
        parent["pid"] != os.getppid()
        or parent["nonce"] != os.environ.get("AEGISLM_PILOT_NONCE")
        or state != {"status": "running", "phase": phase, "training_runs_allowed": 1}
    ):
        raise RuntimeError("phase is not authorized by the active orchestrator")
    if phase == "train":
        with (run / "TRAIN_STARTED").open("x") as handle:
            handle.write(parent["nonce"])


def split_reviewed(
    rows: list[dict[str, Any]], seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Choose 10 per label, excluding multi-record groups from validation."""
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("duplicate record IDs")
    groups = collections.Counter(r["group_id"] for r in rows)
    rng = random.Random(seed)
    chosen: set[str] = set()
    for label in ("present", "not_observed"):
        pools: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for row in sorted(rows, key=lambda r: r["id"]):
            if row["label"] == label and groups[row["group_id"]] == 1:
                pools[row["cwe"]].append(row)
        # Leave at least one example of each selected CWE/label in train.
        for pool in pools.values():
            rng.shuffle(pool)
        count = 0
        while count < 10:
            progressed = False
            for cwe in sorted(pools):
                if len(pools[cwe]) > 1 and count < 10:
                    chosen.add(pools[cwe].pop()["id"])
                    count += 1
                    progressed = True
            if not progressed:
                raise ValueError("insufficient reviewed stratified validation supply")
    train = [r for r in rows if r["id"] not in chosen]
    validation = [r for r in rows if r["id"] in chosen]
    if {r["group_id"] for r in train} & {r["group_id"] for r in validation}:
        raise ValueError("group leakage")
    if {r["code_sha256"] for r in train} & {r["code_sha256"] for r in validation}:
        raise ValueError("code leakage")
    rng.shuffle(train)
    return train, validation


def parse_final(raw: str) -> tuple[str | None, str]:
    """Accept JSON from the Harmony final channel, never from analysis."""
    finals = []
    for index, segment in enumerate(raw.split("<|start|>")):
        if index:
            if not segment.startswith("assistant"):
                continue
            segment = segment[len("assistant") :]
        header, separator, body = segment.partition("<|message|>")
        if separator and re.fullmatch(
            r"\s*<\|channel\|>final(?:\s*<\|constrain\|>(?i:json))?\s*", header
        ):
            finals.append(body)
    if len(finals) != 1:
        return None, "missing_final_channel"
    final = finals[0].strip()
    for end in ("<|fim_suffix|>", "<|return|>"):
        if final.endswith(end):
            final = final[: -len(end)].strip()
    try:
        value = json.loads(final)
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(value, dict) or set(value) != {"assessment"}:
        return None, "invalid_schema"
    assessment = value["assessment"]
    if assessment not in ("present", "not_observed", "uncertain"):
        return None, "invalid_assessment"
    return assessment, "valid"


def encode_record(
    tokenizer: Any, row: dict[str, Any], max_length: int
) -> dict[str, Any]:
    messages = row["messages"]
    prompt = tokenizer.apply_chat_template(
        messages[:-1],
        tokenize=True,
        return_dict=False,
        add_generation_prompt=True,
        reasoning_effort="low",
    )
    full = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        return_dict=False,
        add_generation_prompt=False,
        reasoning_effort="low",
    )
    if not isinstance(full, list) or full[: len(prompt)] != prompt:
        raise ValueError("Harmony prompt is not a token prefix of training record")
    if len(full) > max_length:
        raise ValueError("sequence exceeds budget; truncation is forbidden")
    if len(full) <= len(prompt):
        raise ValueError("no supervised assistant tokens")
    return {
        "input_ids": full,
        "attention_mask": [1] * len(full),
        "labels": [-100] * len(prompt) + full[len(prompt) :],
    }


def prepare(config: dict[str, Any], config_path: Path) -> None:
    import pyarrow.parquet as pq

    source, run = Path(config["source_root"]), Path(config["run_root"])
    if run.exists() and any(run.iterdir()):
        raise ValueError("refusing to overwrite an existing prepared run")
    parent = json.loads((source / "dataset_manifest.json").read_text())
    if parent["profile"] != "phase-f-sard-grounded-v3" or not all(
        parent["quality_gates"].values()
    ):
        raise ValueError("parent automatic quality checks failed")
    reviews = read_rows(source / "manual_review_decisions_100.ai-assisted.jsonl")
    composition = review_composition(reviews)
    reviewed = {
        r["id"]
        for r in reviews
        if r["review_status"] == "pass"
        and not r["operator_label_error"]
        and not r["operator_evidence_error"]
        and all(r["checks"].values())
    }
    if len(reviewed) != 100:
        raise ValueError("expected exactly 100 reviewed records")
    metadata_rows = pq.read_table(source / "eligible_manifest.parquet").to_pylist()
    metadata = {r["record_id"]: r for r in metadata_rows}
    if len(metadata) != len(metadata_rows):
        raise ValueError("duplicate manifest IDs")
    verify_review_cwes(reviews, metadata)
    projected = []
    for original in read_rows(source / "train.jsonl"):
        if original["id"] not in reviewed:
            continue
        meta = metadata[original["id"]]
        user = original["messages"][1]["content"]
        payload = json.loads(user[user.index("{") : user.rindex("}") + 1])
        target = json.loads(original["messages"][-1]["content"])
        if (
            target["assessment"] != meta["label"]
            or payload["scope"]["target_cwe"] != meta["cwe"]
        ):
            raise ValueError("label/CWE mismatch")
        projected.append(
            {
                "id": original["id"],
                "group_id": meta["group_id"],
                "cwe": meta["cwe"],
                "label": meta["label"],
                "code_sha256": meta["code_sha256"],
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {"assessment": meta["label"]}, separators=(",", ":")
                        ),
                    },
                ],
            }
        )
    if len(projected) != 100:
        raise ValueError("review/materialized join incomplete")
    train, validation = split_reviewed(projected, config["seed"])
    verify_runtime(config)
    verify_snapshot(config, weights=True)
    tokenizer = pilot_tokenizer(config)
    lengths = []
    for row in train + validation:
        lengths.append(
            len(encode_record(tokenizer, row, config["max_length"])["input_ids"])
        )
    run.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("validation", validation)):
        (run / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )
    write_json(run / "config.json", config)
    model_root = Path(config["model_root"])
    manifest = {
        "profile": "gpt-oss-reviewed-decision-pilot-v1",
        "purpose": "diagnostic_pilot_only",
        "parent_training_approved": parent["approved_for_training"],
        "parent_status": parent["status"],
        "pilot_authorization": "2026-09-18 user: GPT-OSS-20B, AegisLM, first pilot only",
        "full_training_approved": False,
        "nurilab_deployment_approved": False,
        "expert_signoff": False,
        "review_provenance": "AI-assisted; 88 carried exact matches, 12 re-audited; not independent expert gold",
        "review_composition": composition,
        "template_date": config["template_date"],
        "split": {
            "train": len(train),
            "validation": len(validation),
            "group_overlap": 0,
            "code_overlap": 0,
        },
        "validation_use": "diagnostic development set; not a fresh blind test or generalization claim",
        "label_counts": {
            name: dict(collections.Counter(r["label"] for r in rows))
            for name, rows in (("train", train), ("validation", validation))
        },
        "max_observed_tokens": max(lengths),
        "seed": config["seed"],
        "model_revision": config["model_revision"],
        "source_hashes": {
            name: digest(source / name)
            for name in (
                "dataset_manifest.json",
                "train.jsonl",
                "eligible_manifest.parquet",
                "manual_review_decisions_100.ai-assisted.jsonl",
            )
        },
        "artifact_hashes": {
            name: digest(run / name)
            for name in ("train.jsonl", "validation.jsonl", "config.json")
        },
        "model_metadata_hashes": {
            name: digest(model_root / name)
            for name in (
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "chat_template.jinja",
                "model.safetensors.index.json",
            )
        },
        "versions": {
            n: importlib.metadata.version(n)
            for n in ("torch", "transformers", "peft", "datasets", "accelerate")
        },
        "script_sha256": digest(Path(__file__)),
        "input_config_sha256": digest(config_path),
    }
    write_json(run / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2), flush=True)


def load_model(config: dict[str, Any], adapter: Path | None = None) -> tuple[Any, Any]:
    import torch
    from transformers import AutoModelForCausalLM, Mxfp4Config

    tokenizer = pilot_tokenizer(config)
    model = AutoModelForCausalLM.from_pretrained(
        config["model_root"],
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.bfloat16,
        device_map={"": 0},
        quantization_config=Mxfp4Config(dequantize=True),
        attn_implementation="eager",
    )
    if adapter is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter, is_trainable=False)
    return model, tokenizer


def evaluate(
    model: Any, tokenizer: Any, config: dict[str, Any], phase: str
) -> dict[str, Any]:
    import torch

    run = Path(config["run_root"])
    rows = read_rows(run / "validation.jsonl")
    model.eval()
    model.config.use_cache = True
    predictions, total_loss, total_tokens = [], 0.0, 0
    start = time.monotonic()
    for row in rows:
        encoded = encode_record(tokenizer, row, config["max_length"])
        inputs = {k: torch.tensor([v], device="cuda:0") for k, v in encoded.items()}
        tokens = sum(v != -100 for v in encoded["labels"][1:])
        with torch.inference_mode():
            loss = float(model(**inputs, use_cache=False).loss)
        if not math.isfinite(loss):
            raise RuntimeError("nonfinite evaluation loss")
        total_loss += loss * tokens
        total_tokens += tokens
        prompt = tokenizer.apply_chat_template(
            row["messages"][:-1],
            tokenize=True,
            return_dict=False,
            add_generation_prompt=True,
            reasoning_effort="low",
        )
        ids = torch.tensor([prompt], device="cuda:0")
        tick = time.monotonic()
        with torch.inference_mode():
            generated = model.generate(
                input_ids=ids,
                attention_mask=torch.ones_like(ids),
                do_sample=False,
                max_new_tokens=config["max_new_tokens"],
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
                use_cache=True,
            )
        completion = generated[0, len(prompt) :].tolist()
        raw = tokenizer.decode(completion, skip_special_tokens=False)
        assessment, status = parse_final(raw)
        predictions.append(
            {
                "id": row["id"],
                "label": row["label"],
                "assessment": assessment,
                "schema": status,
                "generated_tokens": len(completion),
                "budget_exhausted": len(completion) >= config["max_new_tokens"],
                "latency_seconds": time.monotonic() - tick,
                "raw": raw,
            }
        )
        print(
            f"{phase} {len(predictions)}/{len(rows)} schema={status} assessment={assessment}",
            flush=True,
        )
    (run / f"{phase}_predictions.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in predictions), encoding="utf-8"
    )
    tp = sum(
        r["label"] == "present" and r["assessment"] == "present" for r in predictions
    )
    fp = sum(
        r["label"] == "not_observed" and r["assessment"] == "present"
        for r in predictions
    )
    negatives = sum(r["label"] == "not_observed" for r in predictions)
    positives = len(rows) - negatives
    summary = {
        "phase": phase,
        "count": len(rows),
        "loss": total_loss / total_tokens,
        "schema_rate": sum(r["schema"] == "valid" for r in predictions) / len(rows),
        "accuracy": sum(r["assessment"] == r["label"] for r in predictions) / len(rows),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / positives,
        "fpr": fp / negatives,
        "invalid_count": sum(r["assessment"] is None for r in predictions),
        "uncertain_count": sum(r["assessment"] == "uncertain" for r in predictions),
        "budget_exhausted_count": sum(r["budget_exhausted"] for r in predictions),
        "wall_seconds": time.monotonic() - start,
        "peak_allocated_gib": torch.cuda.max_memory_allocated() / 2**30,
        "peak_reserved_gib": torch.cuda.max_memory_reserved() / 2**30,
    }
    write_json(run / f"{phase}_metrics.json", summary)
    return summary


def train(config: dict[str, Any]) -> None:
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import Trainer, TrainerCallback, TrainingArguments, set_seed

    run = Path(config["run_root"])
    set_seed(config["seed"])
    model, tokenizer = load_model(config)
    model = get_peft_model(
        model,
        LoraConfig(
            r=config["lora_rank"],
            lora_alpha=config["lora_alpha"],
            lora_dropout=0.0,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
            bias="none",
            task_type="CAUSAL_LM",
        ),
    )
    model.print_trainable_parameters()
    model.config.use_cache = False
    trainable, total = model.get_nb_trainable_parameters()
    data = Dataset.from_list(
        [
            encode_record(tokenizer, r, config["max_length"])
            for r in read_rows(run / "train.jsonl")
        ]
    )

    def collate(features: list[dict[str, Any]]) -> dict[str, Any]:
        length = max(len(f["input_ids"]) for f in features)
        return {
            key: torch.tensor(
                [f[key] + [pad] * (length - len(f[key])) for f in features]
            )
            for key, pad in (
                ("input_ids", tokenizer.pad_token_id),
                ("attention_mask", 0),
                ("labels", -100),
            )
        }

    class FiniteMetrics(TrainerCallback):
        def on_log(
            self, args: Any, state: Any, control: Any, logs: Any = None, **kwargs: Any
        ) -> None:
            for key in ("loss", "grad_norm"):
                if logs and key in logs and not math.isfinite(float(logs[key])):
                    raise RuntimeError(f"nonfinite {key}")

    args = TrainingArguments(
        output_dir=str(run / "checkpoints"),
        max_steps=config["max_steps"],
        per_device_train_batch_size=1,
        gradient_accumulation_steps=config["gradient_accumulation_steps"],
        learning_rate=config["learning_rate"],
        bf16=True,
        tf32=True,
        optim="adamw_torch",
        lr_scheduler_type="constant",
        warmup_steps=0,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=1,
        logging_nan_inf_filter=False,
        save_strategy="no",
        report_to="none",
        seed=config["seed"],
        data_seed=config["seed"],
        dataloader_num_workers=0,
        max_grad_norm=1.0,
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=data,
        data_collator=collate,
        callbacks=[FiniteMetrics()],
    )
    started = time.monotonic()
    result = trainer.train()
    if trainer.state.global_step != config["max_steps"] or not math.isfinite(
        result.training_loss
    ):
        raise RuntimeError("training incomplete")
    model.save_pretrained(run / "adapter", safe_serialization=True)
    tokenizer.save_pretrained(run / "adapter")
    trainer.state.save_to_json(str(run / "trainer_state.json"))
    metrics = dict(
        result.metrics,
        global_step=trainer.state.global_step,
        trainable_parameters=trainable,
        total_parameters=total,
        wall_seconds=time.monotonic() - started,
        peak_allocated_gib=torch.cuda.max_memory_allocated() / 2**30,
        peak_reserved_gib=torch.cuda.max_memory_reserved() / 2**30,
    )
    write_json(run / "train_metrics.json", metrics)
    write_json(
        run / "adapter_hashes.json",
        {p.name: digest(p) for p in sorted((run / "adapter").iterdir()) if p.is_file()},
    )


def run_once(config: dict[str, Any], config_path: Path) -> None:
    run = Path(config["run_root"])
    validate_run(config, config_path)
    verify_snapshot(config, weights=True)
    nonce = uuid.uuid4().hex
    with (run / "RUN_STARTED").open("x") as f:
        json.dump(
            {
                "pid": os.getpid(),
                "nonce": nonce,
                "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            f,
        )
    env = dict(
        os.environ,
        CUDA_VISIBLE_DEVICES=str(config["gpu"]),
        TOKENIZERS_PARALLELISM="false",
        HF_HUB_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        WANDB_MODE="disabled",
        PYTHONUNBUFFERED="1",
        AEGISLM_PILOT_NONCE=nonce,
    )
    started = time.monotonic()
    try:
        for phase in ("baseline", "train", "reload"):
            remaining = config["max_wall_seconds"] - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("pilot wall budget exhausted")
            write_json(
                run / "status.json",
                {"status": "running", "phase": phase, "training_runs_allowed": 1},
            )
            with (run / f"{phase}.log").open("x") as log:
                subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        phase,
                        "--config",
                        str(config_path.resolve()),
                    ],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=remaining,
                    check=True,
                )
        before = json.loads((run / "baseline_metrics.json").read_text())
        after = json.loads((run / "reload_metrics.json").read_text())
        summary = {
            "status": "completed",
            "technical_lifecycle": "PASS",
            "training_runs_executed": 1,
            "baseline": before,
            "adapter": after,
            "loss_delta": after["loss"] - before["loss"],
            "diagnostic_quality_gate": after["schema_rate"] >= 0.95
            and after["accuracy"] >= before["accuracy"],
            "full_training_approved": False,
            "nurilab_deployment_approved": False,
            "wall_seconds": time.monotonic() - started,
            "next_run": "NOT_AUTHORIZED",
        }
        write_json(run / "summary.json", summary)
        write_json(
            run / "status.json", {"status": "completed", "next_run": "NOT_AUTHORIZED"}
        )
    except BaseException as error:
        write_json(
            run / "status.json",
            {"status": "failed", "error": str(error), "next_run": "STOPPED"},
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase", choices=("prepare", "run", "baseline", "train", "reload")
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if args.phase in ("baseline", "train", "reload"):
        validate_run(config, args.config)
        authorize_child(config, args.phase)
    if args.phase == "prepare":
        prepare(config, args.config)
    elif args.phase == "run":
        run_once(config, args.config)
    elif args.phase == "train":
        train(config)
    else:
        import torch
        from transformers import set_seed

        set_seed(config["seed"])
        model, tokenizer = load_model(
            config,
            Path(config["run_root"]) / "adapter" if args.phase == "reload" else None,
        )
        torch.cuda.reset_peak_memory_stats()
        print(json.dumps(evaluate(model, tokenizer, config, args.phase), indent=2))


if __name__ == "__main__":
    main()
