"""Export AegisLM JSONL records into a LLaMA-Factory dataset file."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegislm.training.llamafactory import (  # noqa: E402
    export_llamafactory_records,
    load_jsonl_records,
    write_dataset_info_entry,
    write_llamafactory_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export AegisLM SFT JSONL records for LLaMA-Factory."
    )
    parser.add_argument("--input", required=True, help="AegisLM JSONL input path.")
    parser.add_argument(
        "--output",
        required=True,
        help="Output dataset path, usually LLaMA-Factory data/aegislm_security_sft.json.",
    )
    parser.add_argument(
        "--dataset-name",
        default="aegislm_security_sft",
        help="Dataset key to use in LLaMA-Factory dataset_info.json.",
    )
    parser.add_argument(
        "--dataset-info-output",
        help="Optional path for a dataset_info.json fragment.",
    )
    parser.add_argument(
        "--ignore-errors",
        action="store_true",
        help="Skip records that fail AegisLM SFT safety or split eligibility checks.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = Path(args.input)
    destination = Path(args.output)

    records = load_jsonl_records(source)
    exported = export_llamafactory_records(records, ignore_errors=args.ignore_errors)
    write_llamafactory_dataset(exported, destination)

    if args.dataset_info_output:
        write_dataset_info_entry(
            dataset_name=args.dataset_name,
            dataset_file_name=destination.name,
            output_path=args.dataset_info_output,
        )

    print(
        f"Exported {len(exported)} / {len(records)} records "
        f"to {destination} for dataset '{args.dataset_name}'."
    )


if __name__ == "__main__":
    main()
