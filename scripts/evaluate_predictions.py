"""Evaluate AegisLM prediction JSONL files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    from aegislm.evaluation.harness import (
        evaluate_predictions,
        load_jsonl,
        load_predictions,
        write_report_html,
        write_summary_json,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to evaluation dataset JSONL records.",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="Path to model prediction JSONL records.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        required=True,
        help="Output path for machine-readable evaluation summary JSON.",
    )
    parser.add_argument(
        "--report-html",
        type=Path,
        required=True,
        help="Output path for static HTML evaluation report.",
    )
    args = parser.parse_args()

    summary = evaluate_predictions(
        dataset_records=load_jsonl(args.dataset),
        predictions=load_predictions(args.predictions),
    )
    write_summary_json(summary, args.summary_json)
    write_report_html(summary, args.report_html)

    metrics = summary["metrics"]
    print(
        "AegisLM evaluation complete: "
        f"score={metrics['composite_score']:.2f}, "
        f"hard_gate={metrics['hard_gate_pass_rate'] * 100:.1f}%"
    )


if __name__ == "__main__":
    main()
