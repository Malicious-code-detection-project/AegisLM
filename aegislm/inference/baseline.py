"""Baseline inference helpers for Phase D prediction generation."""

from __future__ import annotations

import importlib
import json
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from aegislm.prompts import PromptMessage, format_baseline_prompt

GenerateResponse = Callable[[list[PromptMessage]], str]


def run_baseline_inference(
    *,
    dataset_path: Path,
    predictions_path: Path,
    model_id: str,
    run_id: str,
    generate_response: GenerateResponse,
    generation_metadata: Mapping[str, Any] | None = None,
) -> int:
    """Generate prediction JSONL records for one dataset file."""
    dataset_records = _load_jsonl(dataset_path)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)

    with predictions_path.open("w", encoding="utf-8") as output_file:
        for record in dataset_records:
            prompt_messages = format_baseline_prompt(record)
            started_at = time.perf_counter()
            raw_output = generate_response(prompt_messages)
            latency_ms = (time.perf_counter() - started_at) * 1000.0

            output_file.write(
                json.dumps(
                    {
                        "record_id": str(record["id"]),
                        "model_id": model_id,
                        "run_id": run_id,
                        "raw_output": raw_output,
                        "latency_ms": round(latency_ms, 4),
                        "generated_at": _utc_now_iso(),
                        "metadata": {
                            "prompt_message_count": len(prompt_messages),
                            **dict(generation_metadata or {}),
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    return len(dataset_records)


def make_static_response_generator(raw_output: str) -> GenerateResponse:
    """Return a deterministic generator for smoke tests and dry runs."""

    def generate_response(_messages: list[PromptMessage]) -> str:
        return raw_output

    return generate_response


def make_transformers_response_generator(
    *,
    model_id: str,
    max_new_tokens: int,
    temperature: float,
) -> GenerateResponse:
    """Build an optional Hugging Face Transformers response generator."""
    transformers = importlib.import_module("transformers")
    tokenizer = transformers.AutoTokenizer.from_pretrained(model_id)
    model = transformers.AutoModelForCausalLM.from_pretrained(
        model_id,
        device_map="auto",
    )

    def generate_response(messages: list[PromptMessage]) -> str:
        encoded = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        model_device = getattr(model, "device", None)
        if model_device is not None:
            encoded = {
                key: value.to(model_device) if hasattr(value, "to") else value
                for key, value in encoded.items()
            }

        generation_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "do_sample": temperature > 0.0,
        }
        if temperature > 0.0:
            generation_kwargs["temperature"] = temperature

        output_ids = model.generate(**encoded, **generation_kwargs)
        input_length = encoded["input_ids"].shape[-1]
        generated_ids = output_ids[0][input_length:]
        decoded = tokenizer.decode(generated_ids, skip_special_tokens=True)
        return cast(str, decoded)

    return generate_response


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc.msg}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{line_number}: JSONL item must be an object")
        records.append(item)
    return records


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
