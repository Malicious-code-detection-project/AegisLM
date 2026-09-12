import json
import re
from collections import UserDict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aegislm.datasets.source import parse_source_record
from aegislm.inference.source import extract_harmony_final
from aegislm.training.source import (
    build_unsloth_moe_target_regex,
    harmony_training_messages,
    load_persisted_source_tokenizer,
    supervised_token_count,
    tokenizer_contract_sha256,
    tokenize_source_training_record,
)


class FakeHarmonyTokenizer:
    def apply_chat_template(
        self,
        conversation: list[dict[str, Any]],
        *,
        tokenize: bool,
        add_generation_prompt: bool = False,
        return_dict: bool = False,
        reasoning_effort: str = "medium",
    ) -> dict[str, list[int]]:
        assert tokenize
        assert reasoning_effort in {"low", "medium", "high"}
        prefix = [10, 11, 12]
        if add_generation_prompt:
            return {"input_ids": prefix, "attention_mask": [1] * len(prefix)}
        assert conversation[-1]["role"] == "assistant"
        return {
            "input_ids": prefix + [20, 21],
            "attention_mask": [1, 1, 1, 1, 1],
        }


class BatchEncodingLikeTokenizer(FakeHarmonyTokenizer):
    def apply_chat_template(self, *args, **kwargs):
        return UserDict(super().apply_chat_template(*args, **kwargs))


def _record():
    output = {
        "schema_version": "aegislm.source-vulnerability-assessment.v2",
        "scope": {"boundary": "supplied_function", "target_cwe": "CWE-120"},
        "assessment": "not_observed",
        "assessment_basis": [
            {
                "code_spans": ["return 0;"],
                "relationship": "No copy occurs.",
                "conclusion": "Not observed.",
                "confidence": "high",
            }
        ],
        "findings": [],
        "limitations": ["Local only."],
        "recommendations": ["Review."],
    }
    return parse_source_record(
        {
            "id": "record",
            "messages": [
                {"role": "system", "content": "system"},
                {
                    "role": "user",
                    "content": (
                        '{"scope":{"target_cwe":"CWE-120"},"source_code":"return 0;"}'
                    ),
                },
                {"role": "assistant", "content": json.dumps(output)},
            ],
        },
        require_assistant=True,
    )


def test_harmony_messages_use_empty_thinking_and_final_content():
    messages = harmony_training_messages(_record())

    assert messages[-1]["thinking"] == ""
    assert json.loads(messages[-1]["content"])["assessment"] == "not_observed"


def test_assistant_only_mask_masks_exact_prompt_prefix():
    features = tokenize_source_training_record(
        _record(), FakeHarmonyTokenizer(), max_length=10
    )

    assert features["labels"] == [-100, -100, -100, 20, 21]
    assert supervised_token_count(features) == 2


def test_assistant_only_mask_accepts_mapping_tokenizer_outputs():
    features = tokenize_source_training_record(
        _record(), BatchEncodingLikeTokenizer(), max_length=10
    )

    assert features["labels"][-2:] == [20, 21]


def test_assistant_only_mask_forwards_explicit_reasoning_effort():
    class RecordingTokenizer(FakeHarmonyTokenizer):
        seen: list[str] = []

        def apply_chat_template(self, *args, reasoning_effort="medium", **kwargs):
            self.seen.append(reasoning_effort)
            return super().apply_chat_template(
                *args, reasoning_effort=reasoning_effort, **kwargs
            )

    tokenizer = RecordingTokenizer()
    tokenize_source_training_record(
        _record(), tokenizer, max_length=10, reasoning_effort="low"
    )

    assert tokenizer.seen == ["low", "low"]


def test_tokenizer_length_gate_rejects_overflow():
    with pytest.raises(ValueError, match="exceed max_length"):
        tokenize_source_training_record(_record(), FakeHarmonyTokenizer(), max_length=4)


def test_extract_harmony_final_drops_analysis_channel():
    raw = (
        "<|channel|>analysis<|message|>hidden"
        '<|channel|>final<|message|>{"assessment":"present"}<|return|>'
    )

    assert extract_harmony_final(raw) == '{"assessment":"present"}'


def test_extract_harmony_final_preserves_marker_text_inside_json_value():
    marker = "<|channel|>final<|message|>"
    raw = f'{marker}{{"note":"literal {marker} value"}}<|return|>'

    assert extract_harmony_final(raw) == f'{{"note":"literal {marker} value"}}'


def test_unsloth_moe_target_regex_selects_attention_and_selected_experts():
    pattern = build_unsloth_moe_target_regex(["q_proj", "o_proj"], [7, 15, 23])

    assert re.fullmatch(pattern, "model.layers.0.self_attn.q_proj")
    assert re.fullmatch(pattern, "model.layers.15.mlp.experts.gate_up_projs.31")
    assert re.fullmatch(pattern, "model.layers.23.mlp.experts.down_projs.0")
    assert not re.fullmatch(pattern, "model.layers.14.mlp.experts.down_projs.0")
    assert not re.fullmatch(pattern, "model.layers.15.mlp.experts.router")


class _BackendTokenizer:
    def __init__(self, marker: str = "same"):
        self.marker = marker

    def to_str(self) -> str:
        return json.dumps({"model": {"type": "test", "marker": self.marker}})


class _PersistedTokenizer:
    padding_side = "left"
    pad_token_id = 200017
    eos_token_id = 200002
    chat_template = "{{ messages }}"
    special_tokens_map = {"eos_token": "<|return|>", "pad_token": "<|pad|>"}
    model_max_length = 2048
    truncation_side = "right"
    clean_up_tokenization_spaces = False
    split_special_tokens = False

    def __init__(self, marker: str = "same"):
        self.backend_tokenizer = _BackendTokenizer(marker)


def _generation_contract():
    return SimpleNamespace(
        padding_side="left",
        pad_token_id=200017,
        eos_token_ids=(200002, 199999),
    )


def test_persisted_tokenizer_is_loaded_locally_and_matches_base_contract():
    calls = []

    class Loader:
        @staticmethod
        def from_pretrained(path, **kwargs):
            calls.append((path, kwargs))
            return _PersistedTokenizer()

    tokenizer, digest = load_persisted_source_tokenizer(
        Loader,
        Path("/external/adapter/final"),
        _PersistedTokenizer(),
        _generation_contract(),
    )

    assert isinstance(tokenizer, _PersistedTokenizer)
    assert digest == tokenizer_contract_sha256(tokenizer, _generation_contract())
    assert calls == [("/external/adapter/final", {"local_files_only": True})]


def test_persisted_tokenizer_rejects_saved_backend_drift():
    class DriftedLoader:
        @staticmethod
        def from_pretrained(path, **kwargs):
            del path, kwargs
            return _PersistedTokenizer("drifted")

    with pytest.raises(RuntimeError, match="does not match the pinned base"):
        load_persisted_source_tokenizer(
            DriftedLoader,
            Path("/external/adapter/final"),
            _PersistedTokenizer(),
            _generation_contract(),
        )


def test_tokenizer_contract_rejects_noncanonical_primary_eos():
    tokenizer = _PersistedTokenizer()
    tokenizer.eos_token_id = 199999

    with pytest.raises(RuntimeError, match="canonical first EOS"):
        tokenizer_contract_sha256(tokenizer, _generation_contract())


def test_persisted_tokenizer_rejects_missing_or_invalid_saved_assets():
    class InvalidLoader:
        @staticmethod
        def from_pretrained(path, **kwargs):
            del path, kwargs
            raise ValueError("invalid tokenizer_config.json")

    with pytest.raises(RuntimeError, match="failed to load persisted tokenizer"):
        load_persisted_source_tokenizer(
            InvalidLoader,
            Path("/external/adapter/final"),
            _PersistedTokenizer(),
            _generation_contract(),
        )


def test_unsloth_tracking_receipt_precedes_stage_reservation_and_network():
    source = Path("scripts/train_source_unsloth.py").read_text(encoding="utf-8")

    receipt = source.index("wandb_claim = prepare_tracking_receipt(")
    reservation = source.index("reserve_training_stage(")
    initialization = source.index("wandb_run = init_wandb_run(", reservation)
    assert receipt < reservation < initialization
    recovery = source.index("if not wandb_claim.needs_logging:")
    assert receipt < recovery < reservation
