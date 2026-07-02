"""Unsloth adapter inference helpers for Phase E/F verification and evaluation."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, cast

from aegislm.prompts import PromptMessage
from aegislm.inference.baseline import GenerateResponse


def make_unsloth_response_generator(
    *,
    adapter_path: str | Path,
    max_seq_length: int = 1024,
    max_new_tokens: int = 1024,
    temperature: float = 0.0,
    cache_dir: str | Path | None = "models/cache",
) -> GenerateResponse:
    """Build an Unsloth adapter response generator for fast inference."""
    unsloth = importlib.import_module("unsloth")
    FastLanguageModel = unsloth.FastLanguageModel

    print(f"[INFO] Loading Unsloth model and adapter from: {adapter_path}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(adapter_path),
        max_seq_length=max_seq_length,
        dtype=None,  # Auto-detection
        load_in_4bit=True,
        cache_dir=str(cache_dir) if cache_dir else None,
    )

    # Enable native 2x faster inference
    FastLanguageModel.for_inference(model)

    def generate_response(messages: list[PromptMessage]) -> str:
        # Format using chat template
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
        )
        # Move inputs to cuda
        inputs = inputs.to("cuda")

        generation_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "use_cache": True,
            "do_sample": temperature > 0.0,
        }
        if temperature > 0.0:
            generation_kwargs["temperature"] = temperature

        output_ids = model.generate(input_ids=inputs, **generation_kwargs)
        input_length = inputs.shape[-1]
        generated_ids = output_ids[0][input_length:]
        decoded = tokenizer.decode(generated_ids, skip_special_tokens=True)
        return cast(str, decoded)

    return generate_response
