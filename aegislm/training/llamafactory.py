"""LLaMA-Factory export helpers for AegisLM SFT records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from aegislm.datasets.formatting import SFTFormattingError, format_sft_record


class LlamaFactoryExportError(Exception):
    """Raised when AegisLM records cannot be exported for LLaMA-Factory."""

    pass


def load_jsonl_records(path: str | Path) -> list[dict[str, Any]]:
    """Load JSONL dataset records from disk."""
    source = Path(path)
    records: list[dict[str, Any]] = []

    with source.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LlamaFactoryExportError(
                    f"{source}:{line_number} is not valid JSON: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise LlamaFactoryExportError(
                    f"{source}:{line_number} must contain a JSON object."
                )
            records.append(record)

    return records


def to_llamafactory_alpaca_record(record: dict[str, Any]) -> dict[str, str]:
    """Convert one AegisLM record into LLaMA-Factory Alpaca-style columns.

    The AegisLM formatter remains the single source for prompt and safety
    validation. This adapter only reshapes the already validated chat messages
    into columns consumed by LLaMA-Factory's ``dataset_info.json`` mapping.
    """
    formatted = format_sft_record(record)
    messages = formatted["messages"]

    if len(messages) != 3:
        raise LlamaFactoryExportError(
            "AegisLM SFT records must contain system, user, and assistant messages."
        )

    system_message, user_message, assistant_message = messages
    expected_roles = ("system", "user", "assistant")
    actual_roles = tuple(message["role"] for message in messages)
    if actual_roles != expected_roles:
        raise LlamaFactoryExportError(
            f"Unexpected message roles {actual_roles}; expected {expected_roles}."
        )

    return {
        "system": system_message["content"],
        "instruction": user_message["content"],
        "input": "",
        "output": assistant_message["content"],
    }


def export_llamafactory_records(
    records: Iterable[dict[str, Any]],
    *,
    ignore_errors: bool = False,
) -> list[dict[str, str]]:
    """Convert a sequence of AegisLM records for LLaMA-Factory training."""
    exported: list[dict[str, str]] = []

    for record in records:
        try:
            exported.append(to_llamafactory_alpaca_record(record))
        except SFTFormattingError:
            if not ignore_errors:
                raise

    return exported


def write_llamafactory_dataset(
    records: list[dict[str, str]],
    output_path: str | Path,
) -> None:
    """Write exported records as JSON array or JSONL based on suffix."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.suffix == ".jsonl":
        with destination.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return

    with destination.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, sort_keys=True)


def build_dataset_info_entry(
    *,
    dataset_name: str,
    file_name: str,
) -> dict[str, Any]:
    """Build a LLaMA-Factory ``dataset_info.json`` entry."""
    return {
        dataset_name: {
            "file_name": file_name,
            "columns": {
                "prompt": "instruction",
                "query": "input",
                "response": "output",
                "system": "system",
            },
        }
    }


def write_dataset_info_entry(
    *,
    dataset_name: str,
    dataset_file_name: str,
    output_path: str | Path,
) -> None:
    """Write a standalone dataset_info.json fragment for LLaMA-Factory."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    entry = build_dataset_info_entry(
        dataset_name=dataset_name,
        file_name=dataset_file_name,
    )

    with destination.open("w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2, sort_keys=True)
