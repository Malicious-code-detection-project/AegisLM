"""Evaluate source-v2 predictions after inference has completed."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.environment import load_project_env  # noqa: E402

load_project_env(REPO_ROOT)


def main() -> None:
    from aegislm.artifacts import validate_artifact_path_plan
    from aegislm.datasets import load_source_gold, load_source_records
    from aegislm.evaluation import (
        evaluate_source_predictions,
        load_predictions,
        write_source_report_html,
        write_summary_json,
    )
    from aegislm.tracking import (
        build_tracking_receipt,
        finish_active_wandb,
        finish_with_tracking_receipt,
        git_reference,
        init_wandb_run,
        log_source_evaluation,
        mark_tracking_logging_started,
        prepare_tracking_receipt,
        require_wandb_api_key,
        source_evaluation_wandb_config,
        source_evaluation_wandb_payload,
        wandb_run_reference,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--report-html", type=Path, required=True)
    parser.add_argument(
        "--wandb",
        action="store_true",
        help="Log aggregate metrics and a source-free case table to W&B.",
    )
    parser.add_argument(
        "--wandb-receipt",
        type=Path,
        help="Optional local receipt path; defaults beside --summary-json.",
    )
    parser.add_argument("--wandb-reconcile", choices=("retry-logging", "finish-only"))
    args = parser.parse_args()
    if args.wandb_reconcile and not args.wandb:
        parser.error("--wandb-reconcile requires --wandb")
    receipt_path = args.wandb_receipt or args.summary_json.with_suffix(
        args.summary_json.suffix + ".wandb.json"
    )
    planned_outputs = [args.summary_json, args.report_html]
    if args.wandb:
        planned_outputs.append(receipt_path)
    validate_artifact_path_plan(
        inputs=(args.challenge, args.gold, args.predictions),
        outputs=planned_outputs,
        protected_roots=(
            args.challenge.parent,
            args.gold.parent,
            REPO_ROOT / "data",
            REPO_ROOT / "raw_datasets",
            REPO_ROOT / "models",
            REPO_ROOT / "adapters",
            REPO_ROOT / "checkpoints",
        ),
        require_new=False,
    )
    if args.wandb:
        require_wandb_api_key()

    summary = evaluate_source_predictions(
        load_source_records(args.challenge, require_assistant=False),
        load_source_gold(args.gold),
        load_predictions(args.predictions),
    )
    write_summary_json(summary, args.summary_json)
    write_source_report_html(summary, args.report_html)
    if args.wandb:
        provenance = summary["provenance"]
        safe_config = source_evaluation_wandb_config(summary)
        source_evaluation_wandb_payload(summary)
        summary_sha256 = hashlib.sha256(args.summary_json.read_bytes()).hexdigest()
        receipt_base = build_tracking_receipt("evaluation", summary_sha256)
        receipt_claim = prepare_tracking_receipt(
            receipt_path,
            receipt_base,
            ambiguous_resolution=args.wandb_reconcile,
        )
        if receipt_claim is None:
            print("source-v2 evaluation W&B receipt is already complete")
            metrics = summary["metrics"]
            print(
                "source-v2 evaluation complete: "
                f"accuracy={metrics['accuracy']:.4f}, "
                f"macro_f1={metrics['macro_f1']:.4f}"
            )
            return
        if receipt_claim.needs_logging:
            mark_tracking_logging_started(receipt_claim)
        run = init_wandb_run(
            job_type="evaluation",
            name=(
                f"source-v2-{provenance.get('run_role', 'unknown')}-"
                f"{provenance.get('mode', 'unknown')}-evaluation"
            ),
            run_id=f"source-v2-evaluation-{receipt_base['identity']}",
            resume=receipt_claim.resume,
            tags=(
                "source-v2",
                "evaluation",
                str(provenance.get("run_role", "unknown")),
                "decision-only"
                if summary["metrics"].get("evidence_f1") is None
                else "full-report",
            ),
            config={
                **safe_config,
                "git": git_reference(REPO_ROOT),
            },
        )
        if receipt_claim.needs_logging:
            log_source_evaluation(run, summary)
        reference = wandb_run_reference(run)
        if reference is None:
            raise RuntimeError("W&B evaluation run has no local reference")
        finish_with_tracking_receipt(receipt_claim, reference, finish_active_wandb)
    metrics = summary["metrics"]
    print(
        "source-v2 evaluation complete: "
        f"accuracy={metrics['accuracy']:.4f}, macro_f1={metrics['macro_f1']:.4f}"
    )


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
