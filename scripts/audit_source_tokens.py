"""Audit Harmony token lengths and assistant-only labels without loading a model."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.environment import load_project_env  # noqa: E402

load_project_env(REPO_ROOT)


def main() -> None:
    from aegislm.artifacts import validate_artifact_path_plan, write_text_artifact
    from aegislm.datasets import load_source_records
    from aegislm.training import (
        supervised_token_count,
        tokenize_source_training_record,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high"),
        default="medium",
        help="Harmony reasoning level; new source-v2 recipes use low.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.max_length <= 0:
        parser.error("--max-length must be positive")
    if args.output is not None:
        validate_artifact_path_plan(
            inputs=(args.train, args.validation),
            outputs=(args.output,),
            protected_roots=(args.train.parent, args.validation.parent),
            require_new=True,
        )
    # The output plan is validated before initializing a tokenizer, which can
    # otherwise download or initialize a substantial model artifact.
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer)

    report: dict[str, Any] = {
        "tokenizer": args.tokenizer,
        "max_length": args.max_length,
        "reasoning_effort": args.reasoning_effort,
        "splits": {},
    }
    for name, path in (("train", args.train), ("validation", args.validation)):
        records = load_source_records(path, require_assistant=True)
        lengths: list[int] = []
        supervised: list[int] = []
        overflow: list[str] = []
        for record in records:
            try:
                features = tokenize_source_training_record(
                    record,
                    tokenizer,
                    max_length=args.max_length,
                    reasoning_effort=args.reasoning_effort,
                )
            except ValueError as exc:
                if "exceed max_length" in str(exc):
                    overflow.append(record.record_id)
                    continue
                raise
            lengths.append(len(features["input_ids"]))
            supervised.append(supervised_token_count(features))
        report["splits"][name] = {
            "count": len(records),
            "min_tokens": min(lengths),
            "p50_tokens": statistics.median(lengths),
            "p95_tokens": sorted(lengths)[int(len(lengths) * 0.95) - 1],
            "max_tokens": max(lengths),
            "min_supervised_tokens": min(supervised),
            "overflow_count": len(overflow),
            "overflow_ids": overflow[:20],
        }

    text = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        write_text_artifact(args.output, text + "\n")
    print(text)
    if any(split["overflow_count"] for split in report["splits"].values()):
        raise SystemExit("token length gate failed")


if __name__ == "__main__":
    main()
