"""Run the GPT-OSS Q1R10/Q1R11 comparison with isolated GPU subprocesses."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aegislm.datasets.source_evidence_lines import format_evidence_lines_payload  # noqa: E402
from aegislm.evaluation.harness import load_jsonl, load_predictions  # noqa: E402
from aegislm.evaluation.source_decision import (  # noqa: E402
    evaluate_source_decisions,
    SourceDecisionThresholds,
)  # noqa: E402
from aegislm.evaluation.source_evidence_lines import (  # noqa: E402
    evaluate_source_evidence_predictions,
)  # noqa: E402
from aegislm.training.fresh import resolve_fresh_tokenizer_snapshot  # noqa: E402
from aegislm.training.two_stage import (  # noqa: E402
    data_root,
    development,
    digest,
    freeze_tokenizer,
    load_config,
    rows_for,
    split_overlap,
    tokenize_rows,
    verify_inputs,
    write_json,
)  # noqa: E402


def decision_score(gold: list[dict[str, Any]], predictions: Any) -> dict[str, Any]:
    return evaluate_source_decisions(
        gold,
        predictions,
        thresholds=SourceDecisionThresholds(
            minimum_sample_count=100,
            minimum_precision=0.9,
            minimum_recall=0.95,
            maximum_false_positive_rate=0.05,
            maximum_abstention_rate=0.05,
        ),
    )


def prepare(config: dict[str, Any], path: Path) -> None:
    output = Path(config["output_dir"])
    if output.exists():
        raise ValueError("experiment output already exists; choose new paths")
    inputs = verify_inputs(Path(config["dataset_dir"]))
    transformers = importlib.import_module("transformers")
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        str(resolve_fresh_tokenizer_snapshot(config)), local_files_only=True
    )
    date = datetime.now(timezone.utc).date().isoformat()
    freeze_tokenizer(tokenizer, date, training=True)
    audit = {}
    for objective in ("decision", "evidence"):
        identifiers = {}
        for split in ("train", "validation"):
            rows = rows_for(config, objective, split)
            identifiers[split] = {r["id"] for r in rows}
            features = tokenize_rows(rows, tokenizer, 4096)
            audit[f"{objective}/{split}"] = {
                "count": len(rows),
                "max_tokens": max(len(r["input_ids"]) for r in features),
                "min_supervised": min(
                    sum(v != -100 for v in r["labels"]) for r in features
                ),
            }
        if identifiers["train"] & identifiers["validation"]:
            raise ValueError("train/validation overlap")
    # Original frozen source manifests bind code/group split integrity as well.
    source_manifest = json.loads(
        (data_root(config, "benchmark") / "dataset_manifest.json").read_text()
    )
    dev = development(config)
    benchmark_ids = {
        r["id"] for r in load_jsonl(data_root(config, "benchmark") / "challenge.jsonl")
    }
    benchmark = load_jsonl(data_root(config, "benchmark") / "challenge.jsonl")
    overlaps = {
        "train_vs_validation": split_overlap(
            rows_for(config, "decision", "train"),
            rows_for(config, "decision", "validation"),
        ),
        "train_vs_benchmark": split_overlap(
            rows_for(config, "decision", "train"), benchmark
        ),
        "validation_vs_benchmark": split_overlap(
            rows_for(config, "decision", "validation"), benchmark
        ),
    }
    failed = len(benchmark_ids) != 500 or any(
        result["id_overlap_count"] or result["code_overlap_count"]
        for result in overlaps.values()
    )
    write_json(
        output / "preparation-audit.json",
        {
            "pass": not failed,
            "config_sha256": digest(path),
            "inputs": inputs,
            "token_audit": audit,
            "split_overlap": overlaps,
            "benchmark_count": len(benchmark_ids),
            "date": date,
            "reason": "split-overlap" if failed else "passed",
        },
    )
    if failed:
        raise ValueError(
            "split isolation failed; see preparation-audit.json; training blocked"
        )
    packages = {
        k: importlib.metadata.version(k)
        for k in (
            "torch",
            "transformers",
            "unsloth",
            "unsloth-zoo",
            "peft",
            "trl",
            "wandb",
        )
    }
    sources = sorted(set(ROOT.glob("aegislm/**/*.py")) | set(ROOT.glob("scripts/*.py")))
    write_json(
        output / "manifest.json",
        {
            "config": config,
            "config_sha256": digest(path),
            "date": date,
            "inputs": inputs,
            "token_audit": audit,
            "development_ids": [r["id"] for r in dev["decision"]],
            "benchmark_manifest": source_manifest,
            "packages": packages,
            "git_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            "source_hashes": {str(p.relative_to(ROOT)): digest(p) for p in sources},
        },
    )
    print(json.dumps(audit), flush=True)


def context(config: dict[str, Any], path: Path) -> dict[str, Any]:
    manifest = json.loads((Path(config["output_dir"]) / "manifest.json").read_text())
    if manifest["config_sha256"] != digest(path):
        raise ValueError("config changed since preparation")
    for name, expected in manifest["source_hashes"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"source changed since preparation: {name}")
    verify_inputs(Path(config["dataset_dir"]))
    return manifest


def evaluation_set(config: dict[str, Any], split: str) -> dict[str, Any]:
    if split == "development":
        return development(config)
    if split == "benchmark":
        contracts = data_root(config, "contracts")
        return {
            "decision": load_jsonl(contracts / "decision/challenge.jsonl"),
            "decision_gold": load_jsonl(contracts / "decision/gold.jsonl"),
            "evidence_gold": load_jsonl(contracts / "evidence/gold.jsonl"),
            "private": load_jsonl(
                data_root(config, "benchmark") / "private/records.jsonl"
            ),
        }
    decision = rows_for(config, "decision", "validation")
    evidence = rows_for(config, "evidence", "validation")
    evidence_ids = {r["id"] for r in evidence}
    private = load_jsonl(
        Path(config["dataset_dir"]) / "phase-f-source-v5-r1/private/records.jsonl"
    )
    return {
        "decision": [{"id": r["id"], "messages": r["messages"][:2]} for r in decision],
        "decision_gold": [
            {"id": r["id"], "expected_output": json.loads(r["messages"][-1]["content"])}
            for r in decision
        ],
        "evidence": [{"id": r["id"], "messages": r["messages"][:2]} for r in evidence],
        "evidence_gold": [
            {"id": r["id"], "expected_output": json.loads(r["messages"][-1]["content"])}
            for r in evidence
        ],
        "private": [r for r in private if r["id"] in evidence_ids],
    }


def predicted_evidence(data: dict[str, Any], predictions: Any) -> list[dict[str, Any]]:
    """No gold fallback: an invalid/uncertain decision fails the pipeline."""
    indexed = {p.record_id: p for p in predictions}
    rows = []
    for record in data["private"]:
        output = json.loads(indexed[record["id"]].raw_output)
        if set(output) != {"assessment"} or output["assessment"] not in {
            "present",
            "not_observed",
        }:
            raise ValueError("pipeline decision is invalid or uncertain")
        rows.append(
            {
                "id": record["id"],
                "messages": format_evidence_lines_payload(
                    target_cwe=record["task"]["target_cwe"],
                    source_code=record["code"]["text"],
                    assessment=output["assessment"],
                ),
            }
        )
    return rows


def publish_evaluation(
    config: dict[str, Any], objective: str, report: dict[str, Any], label: str
) -> None:
    from aegislm.environment import load_project_env
    from aegislm.tracking import validate_wandb_payload

    load_project_env(ROOT)
    receipt = json.loads(
        (Path(config["output_dir"]) / objective / "wandb.json").read_text()
    )
    payload = {
        f"{label}/{k}": v
        for k, v in report["metrics"].items()
        if isinstance(v, (int, float))
    }
    payload[f"{label}/pass"] = bool(report["overall_pass"])
    validate_wandb_payload(payload)
    run = importlib.import_module("wandb").Api().run(receipt["path"])
    run.summary.update(payload)


def worker(
    config: dict[str, Any], path: Path, name: str, objective: str, split: str
) -> None:
    from aegislm.training.two_stage_runtime import (
        generate,
        load_model,
        preflight,
        train,
    )

    manifest = context(config, path)
    output = Path(config["output_dir"])
    date = manifest["date"]
    if name == "preflight":
        model, tokenizer = load_model(config, date)
        rows = (
            rows_for(config, "decision", "train")[:16]
            + rows_for(config, "evidence", "train")[:16]
        )
        preflight(model, tokenizer, rows, config, output / "preflight")
    elif name == "baseline":
        model, tokenizer = load_model(config, date)
        data = development(config)
        for target in ("decision", "evidence"):
            predictions = generate(
                model,
                tokenizer,
                data[target],
                output / "baseline" / f"{target}.jsonl",
                target,
                "base",
            )
            report = (
                decision_score(data["decision_gold"], predictions)
                if target == "decision"
                else evaluate_source_evidence_predictions(
                    data["evidence"],
                    data["evidence_gold"],
                    data["private"],
                    predictions,
                )
            )
            write_json(output / "baseline" / f"{target}.json", report)
    elif name == "train":
        train(
            config,
            date,
            objective,
            rows_for(config, objective, "train"),
            output / objective,
        )
    else:
        data = evaluation_set(config, split)
        folder = output / split
        if objective == "decision":
            prompts = data["decision"]
        else:
            decision = load_predictions(folder / "decision.jsonl")
            try:
                prompts = predicted_evidence(data, decision)
            except (ValueError, KeyError):
                write_json(
                    folder / "pipeline-failure.json",
                    {
                        "overall_pass": False,
                        "reason": "invalid-or-uncertain-decision",
                        "expected_evidence_count": len(data["private"]),
                    },
                )
                raise RuntimeError(
                    "invalid decision prevents evidence; no gold fallback"
                ) from None
        model, tokenizer = load_model(
            config, date, Path(config["adapter_dir"]) / objective / "final"
        )
        if objective == "evidence" and split == "development":
            oracle = generate(
                model,
                tokenizer,
                data["evidence"],
                folder / "evidence-gold-conditioned.jsonl",
                "evidence",
                "evidence-oracle",
            )
            oracle_report = evaluate_source_evidence_predictions(
                data["evidence"], data["evidence_gold"], data["private"], oracle
            )
            write_json(folder / "evidence-gold-conditioned.json", oracle_report)
        predictions = generate(
            model,
            tokenizer,
            prompts,
            folder / f"{objective}.jsonl",
            objective,
            objective,
        )
        report = (
            decision_score(data["decision_gold"], predictions)
            if objective == "decision"
            else evaluate_source_evidence_predictions(
                prompts, data["evidence_gold"], data["private"], predictions
            )
        )
        if objective == "evidence" and split == "development":
            report["gold_conditioned_gate_pass"] = oracle_report["overall_pass"]
            report["overall_pass"] = (
                report["overall_pass"] and oracle_report["overall_pass"]
            )
        report["adapter_reloaded"] = True
        report["evaluation_set"] = split
        report["reused_qwen_benchmark"] = split == "benchmark"
        write_json(folder / f"{objective}.json", report)
        publish_evaluation(config, objective, report, split)
        print(
            json.dumps(
                {
                    "objective": objective,
                    "split": split,
                    "overall_pass": report["overall_pass"],
                    "metrics": report["metrics"],
                }
            ),
            flush=True,
        )
        if split == "development" and not report["overall_pass"]:
            raise RuntimeError(
                f"{objective} development gate failed; no automatic continuation"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/source_two_stage.json")
    )
    parser.add_argument(
        "--stage",
        choices=("prepare", "decision", "evidence", "evaluate", "all"),
        default="all",
    )
    parser.add_argument(
        "--worker",
        choices=("preflight", "baseline", "train", "reload"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--objective",
        choices=("decision", "evidence"),
        default="decision",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--split",
        choices=("development", "validation", "benchmark"),
        default="development",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    config = load_config(args.config)
    if args.worker:
        worker(config, args.config, args.worker, args.objective, args.split)
        return
    output = Path(config["output_dir"])

    def launch(
        name: str, objective: str = "decision", split: str = "development"
    ) -> None:
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--config",
                str(args.config),
                "--worker",
                name,
                "--objective",
                objective,
                "--split",
                split,
            ],
            check=True,
            cwd=ROOT,
        )

    def require_gate(objective: str) -> None:
        report = json.loads((output / "development" / f"{objective}.json").read_text())
        if not report["overall_pass"] or not report["adapter_reloaded"]:
            raise RuntimeError(f"{objective} gate required")

    if args.stage in ("prepare", "all"):
        prepare(config, args.config)
        if args.stage == "prepare":
            return
    context(config, args.config)
    if args.stage in ("decision", "all"):
        if not (output / "preflight/gpu-preflight.json").exists():
            launch("preflight")
        if not json.loads((output / "preflight/gpu-preflight.json").read_text())[
            "pass"
        ]:
            raise RuntimeError("preflight failed")
        if not (output / "baseline/evidence.json").exists():
            launch("baseline")
        launch("train", "decision")
        launch("reload", "decision")
    if args.stage in ("evidence", "all"):
        require_gate("decision")
        launch("train", "evidence")
        launch("reload", "evidence")
    if args.stage in ("evaluate", "all"):
        require_gate("decision")
        require_gate("evidence")
        for split in ("validation", "benchmark"):
            for objective in ("decision", "evidence"):
                launch("reload", objective, split)
        reports = {
            s: {
                o: json.loads((output / s / f"{o}.json").read_text())
                for o in ("decision", "evidence")
            }
            for s in ("validation", "benchmark")
        }
        write_json(
            output / "comparison.json",
            {
                "overall_pass": all(
                    r["overall_pass"] for r in reports["benchmark"].values()
                ),
                "results": reports,
                "qwen_hf_reference": {
                    "decision_precision": 0.9881,
                    "decision_recall": 1.0,
                    "evidence_f1": 0.9114,
                },
                "not_framework_only_comparison": True,
            },
        )


if __name__ == "__main__":
    main()
