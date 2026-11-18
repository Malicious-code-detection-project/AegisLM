"""Check cgroup and model memory budget before B200 smoke training."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from aegislm.runtime.memory_budget import (  # noqa: E402
    MemoryBudgetReport,
    build_memory_budget_report,
    bytes_to_gib,
    snapshot_to_record,
    watch_memory,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check B200 cgroup/model memory budget before smoke training."
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("model/base/qwen3-coder-480b-a35b-instruct-fp8"),
        help="Local base model directory to inspect.",
    )
    parser.add_argument(
        "--nproc",
        type=int,
        default=4,
        help="Number of training ranks/processes expected for torchrun.",
    )
    parser.add_argument(
        "--known-risk-limit-gib",
        type=float,
        default=900.0,
        help="Fail 480B FP8 + 4-rank known-risk profiles at or below this limit.",
    )
    parser.add_argument(
        "--allow-known-risk",
        action="store_true",
        help="Return success for known-risk profiles after printing warnings.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously write memory telemetry logs instead of one-shot checking.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=5.0,
        help="Watch mode sampling interval.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        help="Optional watch mode duration. Omit to watch until interrupted.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("model/runs/memory"),
        help="Directory for watch mode JSONL/CSV logs.",
    )
    parser.add_argument(
        "--top-process-count",
        type=int,
        default=12,
        help="Number of top RSS processes to include in watch logs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.watch:
        watch_memory(
            output_dir=args.output_dir,
            model_dir=args.model_dir,
            nproc=args.nproc,
            interval_seconds=args.interval_seconds,
            duration_seconds=args.duration_seconds,
            process_count=args.top_process_count,
        )
        return

    report = build_memory_budget_report(
        model_dir=args.model_dir,
        nproc=args.nproc,
        known_risk_limit_gib=args.known_risk_limit_gib,
    )
    _print_report(report)
    if report.known_risk and not args.allow_known_risk:
        raise SystemExit(
            "Known-risk memory profile detected. Increase the container memory "
            "limit or rerun with --allow-known-risk for manual monitoring."
        )
    if report.missing_shards:
        raise SystemExit("Model shard check failed because shard files are missing.")


def _print_report(report: MemoryBudgetReport) -> None:
    record = snapshot_to_record(report)
    print("Memory budget report")
    print(f"- effective cgroup limit: {_fmt_gib(record['effective_limit_gib'])}")
    print(f"- effective cgroup path: {record['effective_limit_path']}")
    print(f"- host MemAvailable: {_fmt_gib(record['host_mem_available_gib'])}")
    print(f"- model size: {_fmt_gib(bytes_to_gib(report.model_total_bytes))}")
    print(f"- model shards: {report.model_shard_count}")
    print(f"- known risk: {report.known_risk}")
    for warning in report.warnings:
        print(f"WARN: {warning}")


def _fmt_gib(value: float | None) -> str:
    if value is None:
        return "unlimited/unknown"
    return f"{value:.1f} GiB"


if __name__ == "__main__":
    main()
