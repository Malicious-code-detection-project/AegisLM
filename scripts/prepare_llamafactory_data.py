"""Register exported AegisLM datasets in LLaMA-Factory dataset_info.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge AegisLM dataset entries into LLaMA-Factory dataset_info.json."
    )
    parser.add_argument("--llamafactory-dir", default="LLaMA-Factory")
    parser.add_argument(
        "--train-file",
        default="aegislm_security_sft_train.json",
        help="Dataset file name under LLaMA-Factory/data for training.",
    )
    parser.add_argument(
        "--validation-file",
        default="aegislm_security_sft_validation.json",
        help="Dataset file name under LLaMA-Factory/data for validation.",
    )
    parser.add_argument("--train-name", default="aegislm_security_sft_train")
    parser.add_argument("--validation-name", default="aegislm_security_sft_validation")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_info_path = Path(args.llamafactory_dir) / "data" / "dataset_info.json"
    dataset_info = _read_dataset_info(dataset_info_path)

    dataset_info[args.train_name] = _dataset_entry(args.train_file)
    dataset_info[args.validation_name] = _dataset_entry(args.validation_file)

    with dataset_info_path.open("w", encoding="utf-8") as f:
        json.dump(dataset_info, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    print(
        "Registered datasets in "
        f"{dataset_info_path}: {args.train_name}, {args.validation_name}"
    )


def _read_dataset_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"LLaMA-Factory dataset_info.json not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return data


def _dataset_entry(file_name: str) -> dict[str, Any]:
    return {
        "file_name": file_name,
        "columns": {
            "prompt": "instruction",
            "query": "input",
            "response": "output",
            "system": "system",
        },
    }


if __name__ == "__main__":
    main()
