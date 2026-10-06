"""Opt-in online W&B tracking of saved native generation evaluation snapshots.

This CPU sidecar never changes generation, weights, prompts or runtime defaults.
It sends only explicit safe projections, using the existing tracking lifecycle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from aegislm.tracking.receipt import (  # noqa: E402
    build_tracking_receipt,
    finish_with_tracking_receipt,
    mark_tracking_logging_started,
    prepare_tracking_receipt,
    tracking_run_id,
)
from aegislm.tracking.wandb import (  # noqa: E402
    finish_active_wandb,
    init_wandb_run,
    log_wandb_payload,
    update_wandb_summary,
    validate_wandb_payload,
    wandb_run_reference,
)

LABELS = ["present", "not_observed", "uncertain", "invalid"]
CASE_COLUMNS: list[str | int] = [
    "model",
    "generation_budget",
    "record_id",
    "expected_assessment",
    "semantic_assessment",
    "strict_assessment",
    "json_valid",
    "schema_valid",
    "generated_tokens",
    "stop_reason",
]


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def save(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def safe_config(config: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    """Bind the run to immutable local inputs without transmitting paths."""
    result = {
        "experiment_id": config["experiment_id"],
        "training_steps": 100,
        "training_max_seq_length": 1024,
        "samples_per_condition": 100,
        "positive_samples": 50,
        "negative_samples": 50,
        "budgets": config["budgets"],
        "models": config["models"],
        "runtime_context": config["runtime_context"],
        "generation_mode": "official-native-defaults",
        "reasoning_effort": "medium",
        "external_timeout": None,
        "recording_mode": "saved-evaluation-backfill-and-live-snapshots",
        "labels_reviewed": False,
        "test_used": False,
        "train_sha256": audit["train_sha256"],
        "validation_sha256": audit["validation_sha256"],
        "selection_sha256": audit["selection_sha256"],
        "frozen_input_sha256": audit["frozen_input_sha256"],
        "adapter_sha256": audit["adapter_sha256"],
    }
    # Preserve the historical v1 identity; new runs explicitly bind isolation policy.
    if "execution_protocol" in config:
        result["execution_protocol"] = config["execution_protocol"]
    validate_wandb_payload(result)
    return result


def assessment(row: dict[str, Any], *, strict: bool) -> str:
    if strict:
        label = row.get("assessment") if row["schema_valid"] else None
    else:
        parsed = row.get("parsed")
        label = (
            parsed.get("assessment")
            if isinstance(parsed, dict)
            and row["json_valid"]
            and row["final_channel_present"]
            else None
        )
    return label if label in LABELS[:3] else "invalid"


def project_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    """Keep pending, invalid and uncertain separate; never project raw outputs."""
    metrics: dict[str, Any] = {}
    groups = []
    for group in report["groups"]:
        model, budget = group["model"], str(group["budget"])
        if model not in {"base", "adapter"} or budget not in {
            "128",
            "512",
            "2048",
            "65536",
            "130000",
            "context-minus-input",
        }:
            raise ValueError("Unexpected model or generation budget")
        prefix = f"evaluation/{model}/max_new_tokens_{budget}"
        completed, planned = group["completed"], group["planned"]
        if (
            planned != 100
            or not 0 <= completed <= 100
            or group["pending"] != 100 - completed
        ):
            raise ValueError("Unexpected evaluation counts")
        metrics.update(
            {
                f"{prefix}/completed": completed,
                f"{prefix}/pending": group["pending"],
                f"{prefix}/complete": completed == 100,
            }
        )
        for policy in ("semantic", "strict"):
            matrix = group[f"{policy}_matrix"]
            if (
                len(matrix) != 2
                or any(len(row) != 4 for row in matrix)
                or sum(map(sum, matrix)) != completed
            ):
                raise ValueError("Confusion matrix does not match completed count")
            values = {
                "TP": matrix[0][0],
                "FN": matrix[0][1],
                "FP": matrix[1][0],
                "TN": matrix[1][1],
                "uncertain": matrix[0][2] + matrix[1][2],
                "invalid": matrix[0][3] + matrix[1][3],
                "completed_positive": sum(matrix[0]),
                "completed_negative": sum(matrix[1]),
            }
            metrics.update(
                {f"{prefix}/{policy}/{key}": value for key, value in values.items()}
            )
            if completed:
                metrics[f"{prefix}/{policy}/label_match_over_completed"] = (
                    values["TP"] + values["TN"]
                ) / completed
        cases = [
            [
                model,
                budget,
                row["id"],
                row["source_label"],
                assessment(row, strict=False),
                assessment(row, strict=True),
                row["json_valid"],
                row["schema_valid"],
                row["generated_tokens"],
                row["stop_reason"],
            ]
            for row in group["rows"]
        ]
        if len(cases) != completed:
            raise ValueError("Case count differs from completed count")
        groups.append(
            {
                "prefix": prefix,
                "model": model,
                "budget": budget,
                "completed": completed,
                "cases": cases,
            }
        )
    if len(groups) != 12 or len({g["prefix"] for g in groups}) != 12:
        raise ValueError("Expected 12 unique model/budget groups")
    metrics["evaluation/completed"] = sum(g["completed"] for g in groups)
    metrics["evaluation/planned"] = 1200
    metrics["evaluation/complete"] = metrics["evaluation/completed"] == 1200
    projected = {"metrics": metrics, "groups": groups, "case_columns": CASE_COLUMNS}
    validate_wandb_payload(projected)
    return projected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO / "configs/cc_native_step100_validation100_fresh_process_v2.json",
    )
    parser.add_argument("--wandb", action="store_true", required=True)
    parser.add_argument("--wandb-reconcile", choices=["retry-logging", "finish-only"])
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env", override=False)
    config = read(args.config)
    root = REPO / config["output_dir"]
    project_snapshot(read(root / "confusion-matrices.json"))
    outbound_config = safe_config(config, read(root / "prepared.json"))
    payload = json.dumps(outbound_config, sort_keys=True, separators=(",", ":"))
    base = build_tracking_receipt(
        "evaluation", hashlib.sha256(payload.encode()).hexdigest()
    )
    claim = prepare_tracking_receipt(
        root / "evaluation.wandb.json", base, ambiguous_resolution=args.wandb_reconcile
    )
    if claim is None:
        print("Tracking receipt is already complete", flush=True)
        return
    run = None
    try:
        if claim.needs_logging:
            mark_tracking_logging_started(claim)
        run = init_wandb_run(
            job_type="evaluation",
            name=config["experiment_id"],
            config=outbound_config,
            tags=[
                "native-tutorial",
                "step100",
                "validation100",
                "generation-token-caps",
                "backfill",
            ],
            run_id=tracking_run_id(base),
            resume=claim.resume,
        )
        reference = wandb_run_reference(run)
        assert reference is not None
        save(root / "wandb-link.json", reference)
        if not claim.needs_logging:
            finish_with_tracking_receipt(claim, reference, finish_active_wandb)
            return
        import wandb

        last_digest = None
        charts_logged: set[str] = set()
        while True:
            text = (root / "confusion-matrices.json").read_text()
            digest = hashlib.sha256(text.encode()).hexdigest()
            if digest != last_digest:
                report = json.loads(text)
                projected = project_snapshot(report)
                completed = projected["metrics"]["evaluation/completed"]
                log_wandb_payload(run, projected["metrics"], step=completed)
                update_wandb_summary(run, projected["metrics"])
                charts: dict[str, Any] = {}
                for group in projected["groups"]:
                    prefix = group["prefix"]
                    if group["completed"] != 100 or prefix in charts_logged:
                        continue
                    cases = group["cases"]
                    charts[f"{prefix}/cases"] = wandb.Table(
                        columns=CASE_COLUMNS, data=cases
                    )
                    for policy, column in (("semantic", 4), ("strict", 5)):
                        charts[f"{prefix}/{policy}/confusion_matrix"] = (
                            wandb.plot.confusion_matrix(
                                probs=None,
                                y_true=[LABELS.index(row[3]) for row in cases],
                                preds=[LABELS.index(row[column]) for row in cases],
                                class_names=LABELS,
                                title=f"{group['model']}-{group['budget']}-{policy}",
                            )
                        )
                    charts_logged.add(prefix)
                if charts:
                    run.log(charts)
                save(
                    root / "wandb-progress.json",
                    {
                        "status": "online",
                        "scored_completed": completed,
                        "planned": 1200,
                        "snapshot_sha256": digest,
                        "charts_logged": sorted(charts_logged),
                        "tracking": reference,
                    },
                )
                print("UPLOADED", completed, "/1200", reference["run_url"], flush=True)
                last_digest = digest
                if report["complete"]:
                    finish_with_tracking_receipt(claim, reference, finish_active_wandb)
                    save(
                        root / "wandb-progress.json",
                        {
                            "status": "completed",
                            "scored_completed": 1200,
                            "tracking": reference,
                        },
                    )
                    return
            if (root / "error.json").exists():
                update_wandb_summary(run, {"evaluation/generation_failed": True})
                finish_with_tracking_receipt(claim, reference, finish_active_wandb)
                save(
                    root / "wandb-progress.json",
                    {"status": "generation-failed", "tracking": reference},
                )
                return
            time.sleep(10)
    except BaseException as error:
        save(
            root / "wandb-error.json",
            {
                "exception_type": type(error).__name__,
                "tracking_run_id": tracking_run_id(base),
            },
        )
        if run is not None:
            finish_active_wandb(1)
        raise
    finally:
        claim.close()


if __name__ == "__main__":
    main()
