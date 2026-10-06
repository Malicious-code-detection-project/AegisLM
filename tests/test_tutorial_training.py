"""Regression checks for final-only supervision and native answer-end handling."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from aegislm.training.tutorial import (
    RESPONSE,
    completion_metadata,
    extended_rows,
    final_prefix_text,
    formatting_text,
    load_config,
    model_features,
    validate_final_labels,
)
from aegislm.training.two_stage import digest


class Tokenizer:
    def encode(self, value: str, **kwargs: Any) -> list[int]:
        assert value == '{"assessment":"present"}<|return|>'
        return [5, 6, 200002]

    def apply_chat_template(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        assert kwargs["reasoning_effort"] == "low"
        assert messages[-1]["thinking"] == ""
        return "prefix" + RESPONSE + messages[-1]["content"] + "<|return|>"


def record() -> dict[str, Any]:
    return {
        "id": "train-1",
        "messages": [
            {"role": "system", "content": "Return decision JSON."},
            {"role": "user", "content": "test source"},
            {"role": "assistant", "content": '{"assessment":"present"}'},
        ],
    }


def test_final_labels_reject_prompt_supervision_and_missing_end() -> None:
    row = record()
    ids = [8, 9, 5, 6, 200002]
    assert (
        validate_final_labels(row, ids, [-100, -100, 5, 6, 200002], Tokenizer(), 5) == 3
    )
    with pytest.raises(ValueError, match="unexpected prompt/header"):
        validate_final_labels(row, ids, [8, -100, 5, 6, 200002], Tokenizer(), 5)
    with pytest.raises(ValueError, match="differs from gold"):
        validate_final_labels(
            row, ids[:-1] + [200007], [-100, -100, 5, 6, 200007], Tokenizer(), 5
        )
    with pytest.raises(ValueError, match="overlength"):
        validate_final_labels(row, ids, [-100, -100, 5, 6, 200002], Tokenizer(), 4)
    with pytest.raises(ValueError, match="unexpected prompt/header"):
        validate_final_labels(row, ids, [-100] * 5, Tokenizer(), 5)


@pytest.mark.parametrize(
    ("ids", "elapsed", "reason"),
    [
        ([5, 200002], 1, "answer_end"),
        ([5, 199999], 1, "endoftext"),
        ([5, 200007], 1, "other"),
        ([5, 200012], 301, "time_limit"),
        ([5, 6, 7], 1, "token_limit"),
        ([], 1, "empty"),
    ],
)
def test_completion_distinguishes_answer_end_from_message_end(
    ids: list[int],
    elapsed: float,
    reason: str,
) -> None:
    actual = completion_metadata(ids, 3, elapsed, 300)
    assert actual["completion_reason"] == reason
    assert actual["answer_end_present"] == (reason == "answer_end")
    assert actual["forced_eos"] is False


def test_gold_free_final_prefix_matches_training_boundary() -> None:
    row = record()
    before = deepcopy(row)
    text = formatting_text(row, Tokenizer())
    prompt = {"id": row["id"], "messages": row["messages"][:2]}
    prefix = final_prefix_text(prompt, Tokenizer())
    assert text == prefix + row["messages"][-1]["content"] + "<|return|>"
    assert row == before
    with pytest.raises(ValueError, match="gold-free"):
        final_prefix_text(row, Tokenizer())


def test_extended_table_preserves_all_historical_results() -> None:
    historical = [{"model": f"old-{index}", "schema": index} for index in range(8)]
    new = [
        {"model": "tutorial_adapter", "start_protocol": "bare-assistant"},
        {"model": "tutorial_adapter", "start_protocol": "final-prefill"},
    ]
    before = deepcopy(historical)
    result = extended_rows(historical, new)
    assert len(result) == 10 and result[:8] == before
    result[0]["schema"] = 99
    assert historical == before


def test_metadata_is_removed_before_tensor_collation() -> None:
    row: dict[str, Any] = {
        "id": "train-one",
        "text": "source text stays out of tensor inputs",
        "input_ids": [1, 2, 200002],
        "attention_mask": [1, 1, 1],
        "labels": [-100, 2, 200002],
    }
    before = deepcopy(row)
    features = model_features(row)
    assert set(features) == {"input_ids", "attention_mask", "labels"}
    assert features["labels"] == [-100, 2, 200002]
    assert row == before


def test_config_rejects_silent_generation_changes(tmp_path: Path) -> None:
    config = json.loads(Path("configs/cc_tutorial_final_only_eos_v1.json").read_text())
    source = tmp_path / "source.json"
    source.write_text("{}\n")
    reference = tmp_path / "reference"
    reference.mkdir()
    comparison = reference / "comparison.json"
    comparison.write_text("{}\n")
    config.update(
        source_config=str(source),
        source_config_sha256=digest(source),
        reference_dir=str(reference),
        reference_comparison_sha256=digest(comparison),
    )
    for name in ("output_dir", "adapter_dir", "checkpoint_dir"):
        config[name] = str(tmp_path / name)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    assert load_config(path)["generation"]["max_new_tokens"] == 65536
    config["generation"]["force_eos"] = True
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="generation protocol"):
        load_config(path)
