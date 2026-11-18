"""Compare equivalent source-v2 base and adapter evaluation summaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.environment import load_project_env  # noqa: E402

load_project_env(REPO_ROOT)


def main() -> None:
    from aegislm.artifacts import (
        load_bounded_json_object,
        validate_artifact_path_plan,
        write_text_artifact,
    )
    from aegislm.evaluation import (
        bind_source_comparison_inputs,
        compare_source_summaries,
    )
    from aegislm.tracking import (
        build_tracking_receipt,
        finish_active_wandb,
        finish_with_tracking_receipt,
        git_reference,
        init_wandb_run,
        log_source_comparison,
        mark_tracking_logging_started,
        prepare_tracking_receipt,
        require_wandb_api_key,
        source_comparison_wandb_payload,
        source_evaluation_wandb_config,
        wandb_run_reference,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-summary", type=Path, required=True)
    parser.add_argument("--adapter-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--wandb",
        action="store_true",
        help="Log validated aggregate comparison metrics to W&B.",
    )
    parser.add_argument(
        "--wandb-receipt",
        type=Path,
        help="Optional local receipt path; defaults beside --output.",
    )
    parser.add_argument("--wandb-reconcile", choices=("retry-logging", "finish-only"))
    args = parser.parse_args()
    if args.wandb_reconcile and not args.wandb:
        parser.error("--wandb-reconcile requires --wandb")
    receipt_path = args.wandb_receipt or args.output.with_suffix(
        args.output.suffix + ".wandb.json"
    )
    planned_outputs = [args.output]
    if args.wandb:
        planned_outputs.append(receipt_path)
    validate_artifact_path_plan(
        inputs=(args.base_summary, args.adapter_summary),
        outputs=planned_outputs,
        protected_roots=(
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
    base, base_sha256 = load_bounded_json_object(
        args.base_summary, description="base summary"
    )
    adapter, adapter_sha256 = load_bounded_json_object(
        args.adapter_summary, description="adapter summary"
    )
    comparison = bind_source_comparison_inputs(
        compare_source_summaries(base, adapter),
        base_summary_sha256=base_sha256,
        adapter_summary_sha256=adapter_sha256,
    )
    write_text_artifact(
        args.output,
        json.dumps(comparison, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        idempotent=True,
    )
    if args.wandb:
        safe_base = source_evaluation_wandb_config(base)
        safe_adapter = source_evaluation_wandb_config(adapter)
        source_comparison_wandb_payload(comparison)
        comparison_sha256 = hashlib.sha256(args.output.read_bytes()).hexdigest()
        receipt_base = build_tracking_receipt("comparison", comparison_sha256)
        receipt_claim = prepare_tracking_receipt(
            receipt_path,
            receipt_base,
            ambiguous_resolution=args.wandb_reconcile,
        )
        if receipt_claim is None:
            print("source-v2 comparison W&B receipt is already complete")
            print(f"source-v2 comparison complete: outcome={comparison['outcome']}")
            return
        if receipt_claim.needs_logging:
            mark_tracking_logging_started(receipt_claim)
        run = init_wandb_run(
            job_type="comparison",
            name=f"source-v2-{comparison['comparison_mode']}-comparison",
            tags=("source-v2", "comparison", comparison["comparison_mode"]),
            run_id=f"source-v2-comparison-{receipt_base['identity']}",
            resume=receipt_claim.resume,
            config={
                "base_model_id": safe_base["model_id"],
                "adapter_model_id": safe_adapter["model_id"],
                "comparison_mode": comparison["comparison_mode"],
                "base_summary_sha256": base_sha256,
                "adapter_summary_sha256": adapter_sha256,
                "base_case_set_sha256": safe_base["case_set_sha256"],
                "adapter_case_set_sha256": safe_adapter["case_set_sha256"],
                "gold_sha256": safe_base["gold_sha256"],
                "adapter_artifact_sha256": safe_adapter["provenance"][
                    "adapter_artifact_sha256"
                ],
                "adapter_sha256": safe_adapter["provenance"]["adapter_sha256"],
                "git": git_reference(REPO_ROOT),
            },
        )
        if receipt_claim.needs_logging:
            log_source_comparison(run, comparison)
        reference = wandb_run_reference(run)
        if reference is None:
            raise RuntimeError("W&B comparison run has no local reference")
        finish_with_tracking_receipt(receipt_claim, reference, finish_active_wandb)
    print(f"source-v2 comparison complete: outcome={comparison['outcome']}")


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
