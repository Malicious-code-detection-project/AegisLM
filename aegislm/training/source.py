"""Harmony formatting and assistant-only labels for source-v2 SFT."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal, Protocol

from aegislm.datasets.source import SourceAssessmentRecord


class ChatTokenizer(Protocol):
    """Tokenizer surface required by the source training formatter."""

    def apply_chat_template(
        self,
        conversation: list[dict[str, Any]],
        *,
        tokenize: bool,
        add_generation_prompt: bool = False,
        return_dict: bool = False,
        reasoning_effort: str = "medium",
    ) -> Any: ...


ReasoningEffort = Literal["low", "medium", "high"]


def tokenizer_contract_sha256(tokenizer: Any, contract: Any) -> str:
    """Validate and fingerprint every tokenizer field used by source-v2.

    The fingerprint deliberately includes the complete serialized backend and
    chat template, not only token IDs. This lets a persisted adapter tokenizer
    be compared with the pinned base tokenizer before it is allowed to score a
    promotion gate.
    """
    expected = {"padding_side": contract.padding_side}
    # ``None`` means inherited runtime semantics, not a demand that the
    # tokenizer's concrete ID be ``None``. The concrete value remains in the
    # fingerprint below so inherited defaults cannot drift unnoticed.
    if contract.pad_token_id is not None:
        expected["pad_token_id"] = contract.pad_token_id
    actual = {key: getattr(tokenizer, key, None) for key in expected}
    if actual != expected:
        raise RuntimeError(
            f"source tokenizer contract mismatch: expected {expected}, got {actual}"
        )
    eos_token_ids = contract.eos_token_ids
    if eos_token_ids is not None:
        if not eos_token_ids:
            raise RuntimeError("source tokenizer contract requires a non-empty EOS set")
        if getattr(tokenizer, "eos_token_id", None) != eos_token_ids[0]:
            raise RuntimeError(
                "source tokenizer eos_token_id does not match the canonical first EOS"
            )

    chat_template = getattr(tokenizer, "chat_template", None)
    backend = getattr(tokenizer, "backend_tokenizer", None)
    backend_to_str = getattr(backend, "to_str", None)
    special_tokens_map = getattr(tokenizer, "special_tokens_map", None)
    if not isinstance(chat_template, str) or not chat_template:
        raise RuntimeError("source tokenizer requires a non-empty chat_template")
    if not callable(backend_to_str):
        raise RuntimeError("source tokenizer requires a serializable backend_tokenizer")
    if not isinstance(special_tokens_map, Mapping):
        raise RuntimeError("source tokenizer requires a special_tokens_map mapping")
    backend_json = backend_to_str()
    if not isinstance(backend_json, str) or not backend_json:
        raise RuntimeError("source tokenizer backend serialization is empty")
    try:
        parsed_backend = json.loads(backend_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "source tokenizer backend serialization is invalid JSON"
        ) from exc

    payload = {
        "backend_tokenizer": parsed_backend,
        "chat_template": chat_template,
        "clean_up_tokenization_spaces": getattr(
            tokenizer, "clean_up_tokenization_spaces", None
        ),
        "eos_token_id": getattr(tokenizer, "eos_token_id", None),
        "model_max_length": getattr(tokenizer, "model_max_length", None),
        "pad_token_id": getattr(tokenizer, "pad_token_id", None),
        "padding_side": getattr(tokenizer, "padding_side", None),
        "special_tokens_map": _json_safe_token_map(special_tokens_map),
        "split_special_tokens": getattr(tokenizer, "split_special_tokens", None),
        "truncation_side": getattr(tokenizer, "truncation_side", None),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def load_persisted_source_tokenizer(
    tokenizer_loader: Any,
    adapter_dir: Path,
    base_tokenizer: Any,
    contract: Any,
) -> tuple[Any, str]:
    """Load the saved tokenizer locally and require exact base-contract parity."""
    expected_digest = tokenizer_contract_sha256(base_tokenizer, contract)
    try:
        persisted_tokenizer = tokenizer_loader.from_pretrained(
            str(adapter_dir), local_files_only=True
        )
    except Exception as exc:
        raise RuntimeError(
            f"failed to load persisted tokenizer from adapter directory: {adapter_dir}"
        ) from exc
    actual_digest = tokenizer_contract_sha256(persisted_tokenizer, contract)
    if actual_digest != expected_digest:
        raise RuntimeError(
            "persisted tokenizer contract does not match the pinned base tokenizer"
        )
    return persisted_tokenizer, actual_digest


def _json_safe_token_map(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe_token_map(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe_token_map(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_unsloth_moe_target_regex(
    attention_modules: list[str], expert_layers: list[int]
) -> str:
    """Build the module regex for Unsloth's split GPT-OSS expert layout."""
    if not attention_modules:
        raise ValueError("at least one attention target module is required")
    if not expert_layers:
        raise ValueError("at least one expert target layer is required")
    attention = "|".join(re.escape(name) for name in attention_modules)
    layers = "|".join(str(layer) for layer in expert_layers)
    return (
        rf"(?:.*self_attn\.(?:{attention})|"
        rf".*model\.layers\.(?:{layers})\.mlp\.experts\."
        rf"(?:gate_up_projs|down_projs)\.\d+)$"
    )


def harmony_training_messages(
    record: SourceAssessmentRecord,
) -> list[dict[str, Any]]:
    """Map frozen assistant JSON to GPT-OSS empty-analysis/final channels."""
    if record.assistant_output is None:
        raise ValueError(f"{record.record_id}: training record has no assistant output")
    messages: list[dict[str, Any]] = [
        dict(message) for message in record.prompt_messages
    ]
    messages.append(
        {
            "role": "assistant",
            "thinking": "",
            "content": record.messages[-1]["content"],
        }
    )
    return messages


def tokenize_source_training_record(
    record: SourceAssessmentRecord,
    tokenizer: ChatTokenizer,
    *,
    max_length: int,
    reasoning_effort: ReasoningEffort = "medium",
) -> dict[str, list[int]]:
    """Tokenize one record and mask every prompt token from the loss.

    ``medium`` remains the compatibility default for the preserved legacy
    canary. New experiments pass an explicit value from their protocol config
    so training and generation cannot silently use different template defaults.
    """
    prompt = tokenizer.apply_chat_template(
        [dict(message) for message in record.prompt_messages],
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        reasoning_effort=reasoning_effort,
    )
    full = tokenizer.apply_chat_template(
        harmony_training_messages(record),
        tokenize=True,
        add_generation_prompt=False,
        return_dict=True,
        reasoning_effort=reasoning_effort,
    )
    prompt_ids = _one_sequence(prompt, "input_ids")
    input_ids = _one_sequence(full, "input_ids")
    attention_mask = _one_sequence(full, "attention_mask", default=[1] * len(input_ids))
    if len(input_ids) > max_length:
        raise ValueError(
            f"{record.record_id}: {len(input_ids)} tokens exceed "
            f"max_length={max_length}"
        )
    if input_ids[: len(prompt_ids)] != prompt_ids:
        raise ValueError(
            f"{record.record_id}: generation prompt is not a full-sequence prefix"
        )
    labels = [-100] * len(prompt_ids) + input_ids[len(prompt_ids) :]
    if not any(label != -100 for label in labels):
        raise ValueError(
            f"{record.record_id}: assistant-only mask has no supervised tokens"
        )
    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels,
    }


def supervised_token_count(features: dict[str, list[int]]) -> int:
    """Count tokens contributing to the SFT loss."""
    return sum(label != -100 for label in features["labels"])


def _one_sequence(
    value: Any, key: str, *, default: list[int] | None = None
) -> list[int]:
    raw = value.get(key, default) if isinstance(value, Mapping) else value
    if raw is None:
        raise ValueError(f"tokenizer output has no {key}")
    if raw and isinstance(raw[0], list):
        if len(raw) != 1:
            raise ValueError(f"tokenizer returned more than one {key} sequence")
        raw = raw[0]
    if not isinstance(raw, list) or not all(isinstance(item, int) for item in raw):
        raise ValueError(f"tokenizer {key} must be a list of integers")
    return raw
