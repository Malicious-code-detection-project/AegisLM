"""max-new-tokens-65536: compare output caps within a 131072-token context."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aegislm.artifacts import (  # noqa: E402
    validate_artifact_output_location,
    write_text_artifact,
)
from aegislm.evaluation.harness import Prediction, load_jsonl  # noqa: E402
from aegislm.evaluation.source_decision import evaluate_source_decisions  # noqa: E402
from aegislm.inference.source import extract_harmony_final  # noqa: E402
from aegislm.training.cc_decision import (  # noqa: E402
    context,
    development_rows,
    gpu_identity,
    load_config as load_source_config,
)
from aegislm.training.fresh import resolve_fresh_tokenizer_snapshot  # noqa: E402
from aegislm.training.two_stage import digest, write_json  # noqa: E402
from scripts.train_cc_decision import provenance  # noqa: E402

FINAL = "<|channel|>final<|message|>"
EOS = (200002, 199999)


def load_config(path: Path) -> dict[str, Any]:
    """Keep this diagnostic separate from the immutable training recipe."""
    config: dict[str, Any] = json.loads(path.read_text())
    budgets = config["budgets"]
    if (
        config["recipe"] != "cc_max_new_tokens_65536_v1"
        or config["changed_parameter"] != "max_new_tokens"
        or config["reference_value"] != 128
        or config["target_value"] != 65536
        or not isinstance(budgets, list)
        or not budgets
        or any(type(v) is not int or not 1 <= v <= 65536 for v in budgets)
        or budgets != sorted(set(budgets))
        or config["model_kinds"] != ["base", "adapter"]
        or type(config["sample_count"]) is not int
        or not 2 <= config["sample_count"] <= 100
        or config["sample_count"] % 2
        or config["runtime_context_length"] != 131072
        or type(config["max_time_seconds"]) is not int
        or not 1 <= config["max_time_seconds"] <= 300
    ):
        raise ValueError("unsupported generation budget diagnostic settings")
    if digest(Path(config["source_config"])) != config["source_config_sha256"]:
        raise ValueError("source training config changed")
    validate_artifact_output_location(Path(config["output_dir"]))
    return config


def select_rows(
    validation: list[dict[str, Any]], count: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select balanced development rows once; remove gold from all generation inputs."""
    if count < 2 or count > 100 or count % 2:
        raise ValueError("sample count must be even and between 2 and 100")
    development = development_rows(validation)
    selected = []
    for label in ("present", "not_observed"):
        selected.extend(
            [
                r
                for r in development
                if json.loads(r["messages"][-1]["content"])["assessment"] == label
            ][: count // 2]
        )
    identifiers = {r["id"] for r in selected}
    selected = [r for r in development if r["id"] in identifiers]
    if len(selected) != count or len(identifiers) != count:
        raise ValueError("invalid selected validation IDs")
    prompts = [{"id": r["id"], "messages": r["messages"][:2]} for r in selected]
    gold = [
        {"id": r["id"], "expected_output": json.loads(r["messages"][-1]["content"])}
        for r in selected
    ]
    return prompts, gold


def source_context(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Require the completed training candidate's original bindings unchanged."""
    path = Path(config["source_config"])
    source = load_source_config(path)
    manifest = context(source, path)
    training = json.loads(
        (Path(source["output_dir"]) / "decision/training.json").read_text()
    )
    if training["steps"] != 100 or not training["gradients_checked"]:
        raise ValueError("completed final adapter required")
    if training["provenance"] != provenance(source, manifest):
        raise ValueError("training provenance mismatch")
    return source, manifest


def prepare(config: dict[str, Any], path: Path) -> None:
    """Freeze the table, prompts and provenance before initializing a model."""
    output = Path(config["output_dir"])
    if output.exists():
        raise FileExistsError("diagnostic output exists; choose a new output directory")
    source, manifest = source_context(config)
    validation = load_jsonl(
        Path(source["dataset"]["root"]) / "decision-candidates/validation.jsonl"
    )
    prompts, gold = select_rows(validation, config["sample_count"])
    if not {r["id"] for r in prompts}.issubset(manifest["development_ids"]):
        raise ValueError("selected IDs outside frozen development subset")
    snapshot = resolve_fresh_tokenizer_snapshot(source)
    model_config = json.loads((snapshot / "config.json").read_text())
    if config["runtime_context_length"] > model_config["max_position_embeddings"]:
        raise ValueError("runtime context exceeds cached model limit")
    write_json(output / "config.json", config)
    write_json(output / "prompts.json", prompts)
    write_json(output / "gold.json", gold)
    write_json(
        output / "manifest.json",
        {
            "config_sha256": digest(path),
            "experiment_id": config["experiment_id"],
            "title": config["title"],
            "changed_parameter": config["changed_parameter"],
            "reference_value": config["reference_value"],
            "target_value": config["target_value"],
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "script_sha256": digest(Path(__file__)),
            "source_preparation_sha256": digest(
                Path(source["output_dir"]) / "manifest.json"
            ),
            "training_manifest_sha256": digest(
                Path(source["output_dir"]) / "decision/training.json"
            ),
            "prompts_sha256": digest(output / "prompts.json"),
            "gold_sha256": digest(output / "gold.json"),
            "input_ids": [r["id"] for r in prompts],
            "source_model_config_sha256": digest(snapshot / "config.json"),
            "model_context_length": model_config["max_position_embeddings"],
            "packages": manifest["packages"],
            "gpu": gpu_identity(),
            "optimizer_steps": 0,
            "test_used": False,
            "diagnostic_only": True,
            "label_status": "source_label_unreviewed",
            "git_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
        },
    )
    table = f"# {config['title']}\n\n"
    table += "| Model | max_new_tokens | Cases | State |\n| --- | ---: | ---: | --- |\n"
    for kind in config["model_kinds"]:
        for budget in config["budgets"]:
            table += f"| {kind} | {budget:,} | {len(prompts)} | pending |\n"
    write_text_artifact(output / "plan.md", table)
    write_text_artifact(output / "execution-source.py", Path(__file__).read_text())


def stop_reason(ids: list[int], maximum: int, elapsed: float, max_time: int) -> str:
    """Distinguish normal completion, token exhaustion and the time guard."""
    if ids and ids[-1] in EOS:
        return "eos"
    if len(ids) >= maximum:
        return "token_limit"
    if elapsed >= max_time:
        return "time_limit"
    return "other"


def generate_one(
    model: Any,
    tokenizer: Any,
    row: dict[str, Any],
    kind: str,
    budget: int,
    context_length: int,
    max_time: int,
) -> Prediction:
    """Apply the requested new-token cap to reasoning and final tokens together."""
    if [m["role"] for m in row["messages"]] != ["system", "user"]:
        raise ValueError("gold or unexpected roles in generation input")
    torch = importlib.import_module("torch")
    inputs = tokenizer.apply_chat_template(
        [row["messages"]],
        tokenize=True,
        add_generation_prompt=True,
        padding=True,
        return_tensors="pt",
        return_dict=True,
        reasoning_effort="low",
    ).to("cuda")
    input_length = inputs["input_ids"].shape[1]
    if input_length + budget > context_length:
        raise ValueError("prompt plus requested output exceeds runtime context")
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    with torch.inference_mode():
        tokens = model.generate(
            **inputs,
            max_new_tokens=budget,
            max_time=max_time,
            do_sample=False,
            use_cache=True,
            pad_token_id=200017,
            eos_token_id=list(EOS),
        )
    torch.cuda.synchronize()
    elapsed = time.monotonic() - started
    ids = tokens[0, input_length:].tolist()
    raw = tokenizer.decode(ids, skip_special_tokens=False)
    return Prediction(
        record_id=row["id"],
        model_id="openai/gpt-oss-20b",
        run_id=f"{kind}-{budget}",
        raw_output=extract_harmony_final(raw) if FINAL in raw else "",
        raw_generation=raw,
        latency_ms=elapsed * 1000,
        generation={
            "input_ids": inputs["input_ids"][0].tolist(),
            "generated_ids": ids,
            "max_new_tokens": budget,
            "max_time_seconds": max_time,
            "generated_tokens": len(ids),
            "stop_reason": stop_reason(ids, budget, elapsed, max_time),
            "final_channel_present": FINAL in raw,
            "peak_allocated_mib": torch.cuda.max_memory_allocated() / 1024**2,
            "peak_reserved_mib": torch.cuda.max_memory_reserved() / 1024**2,
        },
    )


def worker(config: dict[str, Any], path: Path, kind: str) -> None:
    """Run all table rows for one model in an isolated inference-only process."""
    from aegislm.training.two_stage_runtime import load_model

    output = Path(config["output_dir"])
    frozen = json.loads((output / "manifest.json").read_text())
    bindings = {
        "config_sha256": path,
        "script_sha256": Path(__file__),
        "prompts_sha256": output / "prompts.json",
        "gold_sha256": output / "gold.json",
    }
    if any(digest(p) != frozen[k] for k, p in bindings.items()):
        raise ValueError("generation diagnostic changed after preparation")
    source, manifest = source_context(config)
    if (
        digest(Path(source["output_dir"]) / "manifest.json")
        != frozen["source_preparation_sha256"]
        or digest(Path(source["output_dir"]) / "decision/training.json")
        != frozen["training_manifest_sha256"]
        or gpu_identity() != frozen["gpu"]
    ):
        raise ValueError("source training or GPU binding changed")
    prompts = json.loads((output / "prompts.json").read_text())
    gold = json.loads((output / "gold.json").read_text())
    if [r["id"] for r in prompts] != frozen["input_ids"]:
        raise ValueError("diagnostic IDs changed")
    runtime = deepcopy(source)
    runtime["training"]["max_seq_length"] = config["runtime_context_length"]
    adapter = (
        Path(source["adapter_dir"]) / "decision/final" if kind == "adapter" else None
    )
    model, tokenizer = load_model(
        runtime, manifest["date"], adapter, provenance=provenance(source, manifest)
    )
    if model.config.max_position_embeddings < config["runtime_context_length"]:
        raise ValueError("loaded model context smaller than requested")
    importlib.import_module("unsloth").FastLanguageModel.for_inference(model)
    tokenizer.padding_side = "left"
    write_json(
        output / kind / "runtime.json",
        {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "requested_context_length": config["runtime_context_length"],
            "loaded_max_position_embeddings": model.config.max_position_embeddings,
            "loaded_max_seq_length": getattr(model, "max_seq_length", None),
            "budgets": config["budgets"],
            "max_time_seconds": config["max_time_seconds"],
            "source_provenance": provenance(source, manifest),
            "adapter_loaded": kind == "adapter",
            "optimizer_steps": 0,
        },
    )
    for budget in config["budgets"]:
        folder = output / kind / str(budget)
        predictions = []
        validate_artifact_output_location(folder / "predictions.jsonl")
        folder.mkdir(parents=True, exist_ok=False)
        with (folder / "predictions.jsonl").open("x") as stream:
            for row in prompts:
                prediction = generate_one(
                    model,
                    tokenizer,
                    row,
                    kind,
                    budget,
                    config["runtime_context_length"],
                    config["max_time_seconds"],
                )
                predictions.append(prediction)
                stream.write(json.dumps(asdict(prediction), ensure_ascii=False) + "\n")
                stream.flush()
                assert prediction.generation is not None
                print(
                    json.dumps(
                        {
                            "model": kind,
                            "budget": budget,
                            "case": len(predictions),
                            **{
                                k: prediction.generation[k]
                                for k in (
                                    "generated_tokens",
                                    "stop_reason",
                                    "final_channel_present",
                                )
                            },
                        }
                    ),
                    flush=True,
                )
        report = evaluate_source_decisions(gold, predictions)
        report.update(
            diagnostic_only=True,
            test_used=False,
            input_ids=frozen["input_ids"],
            optimizer_steps=0,
        )
        write_json(folder / "evaluation.json", report)
        write_json(folder / "generation.json", [p.generation for p in predictions])


def summarize(config: dict[str, Any]) -> None:
    """Write one table of observed completion and JSON validity, including timeouts."""
    output = Path(config["output_dir"])
    table = f"# {config['title']}\n\n"
    table += "| Model | max_new_tokens | Cases | Final | Valid JSON | Schema | EOS | Token limit | Time limit | Actual tokens |\n"
    table += "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n"
    rows = []
    for kind in config["model_kinds"]:
        for budget in config["budgets"]:
            folder = output / kind / str(budget)
            report = json.loads((folder / "evaluation.json").read_text())
            generation = json.loads((folder / "generation.json").read_text())
            if (
                report["input_ids"]
                != json.loads((output / "manifest.json").read_text())["input_ids"]
            ):
                raise ValueError("table contains different validation IDs")
            n = len(generation)
            row = {
                "model": kind,
                "max_new_tokens": budget,
                "cases": n,
                "final": sum(g["final_channel_present"] for g in generation),
                "parse": sum(c["parse_success"] for c in report["cases"]),
                "schema": sum(c["schema_valid"] for c in report["cases"]),
                **{
                    r: sum(g["stop_reason"] == r for g in generation)
                    for r in ("eos", "token_limit", "time_limit")
                },
                "min_tokens": min(g["generated_tokens"] for g in generation),
                "max_tokens": max(g["generated_tokens"] for g in generation),
            }
            rows.append(row)
            table += f"| {kind} | {budget:,} | {n} | {row['final']} | {row['parse']} | {row['schema']} | {row['eos']} | {row['token_limit']} | {row['time_limit']} | {row['min_tokens']}–{row['max_tokens']} |\n"
    write_json(
        output / "comparison.json",
        {
            "rows": rows,
            "diagnostic_only": True,
            "test_used": False,
            "optimizer_steps": 0,
        },
    )
    write_text_artifact(output / "max-new-tokens-65536-comparison.md", table)
    print(table, flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/cc_max_new_tokens_65536_v1.json")
    )
    parser.add_argument("--stage", choices=("prepare", "run"), required=True)
    parser.add_argument("--worker", choices=("base", "adapter"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.worker:
        if args.stage != "run":
            raise ValueError("worker is inference-only")
        worker(config, args.config, args.worker)
    elif args.stage == "prepare":
        prepare(config, args.config)
        print("Generation budget diagnostic prepared; optimizer steps=0", flush=True)
    else:
        for kind in config["model_kinds"]:
            with (Path(config["output_dir"]) / f"{kind}.log").open("x") as log:
                subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__)),
                        "--config",
                        str(args.config),
                        "--stage",
                        "run",
                        "--worker",
                        kind,
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                    timeout=config["sample_count"]
                    * len(config["budgets"])
                    * (config["max_time_seconds"] + 30)
                    + 600,
                )
        summarize(config)


if __name__ == "__main__":
    main()
