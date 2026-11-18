"""Dependency-free project entrypoint with an explicit local-data exercise."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def inspect_training_example(dataset: Path, tokenizer_path: Path | None) -> None:
    """Inspect one local training record; load a tokenizer only when requested."""
    from aegislm.datasets.source import parse_source_record

    with dataset.open(encoding="utf-8") as stream:
        record = parse_source_record(json.loads(next(stream)), require_assistant=True)
    target = record.assistant_output
    assert target is not None
    print("대화 역할:", [message["role"] for message in record.messages])
    print("문제 메시지 수:", len(record.prompt_messages))
    print("정답 필드:", sorted(target))
    print("분석 범위:", target["scope"])
    print("정답 판단:", target["assessment"])
    if tokenizer_path is not None:
        from transformers import AutoTokenizer

        from aegislm.training.source import tokenize_source_training_record

        tokenizer = AutoTokenizer.from_pretrained(
            str(tokenizer_path), local_files_only=True
        )
        features = tokenize_source_training_record(
            record, tokenizer, max_length=2048, reasoning_effort="low"
        )
        print("전체 토큰 수:", len(features["input_ids"]))
        print("정답 토큰 수:", sum(label != -100 for label in features["labels"]))


def main(argv: list[str] | None = None) -> None:
    """Show project status by default; never implicitly load local ML assets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect-training-example", action="store_true")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/processed/phase-f-source-v5-r1/train.jsonl"),
    )
    parser.add_argument("--tokenizer", type=Path)
    args = parser.parse_args(argv)
    if args.tokenizer is not None and not args.inspect_training_example:
        parser.error("--tokenizer requires --inspect-training-example")
    if args.inspect_training_example:
        inspect_training_example(args.dataset, args.tokenizer)
    else:
        print(
            "AegisLM scaffold is ready. "
            "See README.md and docs/FINETUNING_EXPERIMENT_PLAN.md for the roadmap."
        )


if __name__ == "__main__":
    main()
