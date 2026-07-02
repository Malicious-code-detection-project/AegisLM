"""Run AegisLM adapter inference and write prediction JSONL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    from aegislm.inference import (
        make_static_response_generator,
        make_unsloth_response_generator,
        run_baseline_inference,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to input dataset JSONL records.",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="Output path for prediction JSONL records.",
    )
    parser.add_argument(
        "--adapter-path",
        type=Path,
        default=Path("adapters/tiny-sft-poc"),
        help="Path to the fine-tuned adapter directory.",
    )
    parser.add_argument(
        "--model-id",
        default="openai/gpt-oss-20b",
        help="Model id recorded in prediction JSONL.",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run identifier recorded in prediction JSONL.",
    )
    parser.add_argument(
        "--backend",
        choices=("unsloth", "mock"),
        default="unsloth",
        help="Inference backend. Use mock only for smoke tests.",
    )
    parser.add_argument(
        "--mock-raw-output",
        help="Raw output to write for every record when --backend mock is used.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=1024,
        help="Maximum generated tokens for the inference backend.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for the inference backend. 0 disables sampling.",
    )
    args = parser.parse_args()

    if args.backend == "mock":
        if args.mock_raw_output is None:
            parser.error("--mock-raw-output is required when --backend mock is used")
        generate_response = make_static_response_generator(args.mock_raw_output)
    else:
        generate_response = make_unsloth_response_generator(
            adapter_path=args.adapter_path,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
        )

    count = run_baseline_inference(
        dataset_path=args.dataset,
        predictions_path=args.predictions,
        model_id=args.model_id,
        run_id=args.run_id,
        generate_response=generate_response,
        generation_metadata={
            "backend": args.backend,
            "adapter_path": str(args.adapter_path),
            "max_new_tokens": args.max_new_tokens,
            "temperature": args.temperature,
        },
    )
    print(
        "AegisLM adapter inference complete: "
        f"records={count}, predictions={args.predictions}"
    )


if __name__ == "__main__":
    main()
