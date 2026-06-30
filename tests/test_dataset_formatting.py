"""Unit tests for SFT dataset formatting and eligibility helpers."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from aegislm.prompts import BASELINE_SYSTEM_PROMPT
from aegislm.datasets.formatting import (
    SFTSafetyLevelError,
    SFTSplitError,
    SFTValidationError,
    check_sft_eligibility,
    format_sft_dataset,
    format_sft_record,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line]


def test_fixture_records_are_ineligible_due_to_split() -> None:
    """Verify that raw fixture records cannot be formatted because of split='fixture'."""
    records = load_records()
    assert len(records) > 0

    for r in records:
        assert r["metadata"]["split"] == "fixture"
        with pytest.raises(SFTSplitError) as exc_info:
            check_sft_eligibility(r)
        assert "belongs to a held-out split 'fixture'" in str(exc_info.value)

        with pytest.raises(SFTSplitError):
            format_sft_record(r)


def test_valid_record_formatting_success() -> None:
    """Verify formatting succeeds when split is changed to 'train' or 'validation'."""
    record = deepcopy(load_records()[0])
    record["metadata"]["split"] = "train"

    # Verify eligibility passes
    check_sft_eligibility(record)

    # Format the record
    result = format_sft_record(record)

    # Assert shape of the output
    assert "messages" in result
    messages = result["messages"]
    assert len(messages) == 3

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == BASELINE_SYSTEM_PROMPT

    assert messages[1]["role"] == "user"
    assert f"Record ID: {record['id']}" in messages[1]["content"]

    assert messages[2]["role"] == "assistant"
    # Assistant content must be pretty-printed JSON matching expected_output
    raw_assistant_json = messages[2]["content"]
    parsed_assistant = json.loads(raw_assistant_json)
    assert parsed_assistant == record["expected_output"]

    # Verify formatting output is pretty-printed (contains indentation)
    assert "\n  " in raw_assistant_json


def test_split_eligibility() -> None:
    """Verify SFT training only allows 'train' and 'validation' splits."""
    record = deepcopy(load_records()[0])

    # Allow train and validation
    for allowed_split in ("train", "validation"):
        record["metadata"]["split"] = allowed_split
        check_sft_eligibility(record)  # Should not raise

    # Disallow test and fixture
    for blocked_split in ("test", "fixture"):
        record["metadata"]["split"] = blocked_split
        with pytest.raises(SFTSplitError) as exc_info:
            check_sft_eligibility(record)
        assert f"belongs to a held-out split '{blocked_split}'" in str(exc_info.value)

    # Disallow invalid splits
    record["metadata"]["split"] = "invalid_split_name"
    with pytest.raises(SFTValidationError) as val_exc_info:
        check_sft_eligibility(record)
    assert "failed schema validation" in str(val_exc_info.value)


def test_restricted_safety_level_rejection() -> None:
    """Verify that safety_level='restricted' is rejected."""
    record = deepcopy(load_records()[0])
    record["metadata"]["split"] = "train"
    record["metadata"]["safety_level"] = "restricted"

    with pytest.raises(SFTSafetyLevelError) as exc_info:
        check_sft_eligibility(record)
    assert "safety level is 'restricted'" in str(exc_info.value)


def test_executable_payload_rejection() -> None:
    """Verify that metadata.contains_executable_payload=True is rejected."""
    record = deepcopy(load_records()[0])
    record["metadata"]["split"] = "train"
    record["metadata"]["contains_executable_payload"] = True

    with pytest.raises(SFTValidationError) as exc_info:
        check_sft_eligibility(record)
    assert "contains an executable payload" in str(exc_info.value)


def test_unsafe_guidance_rejection() -> None:
    """Verify that expected_output containing unsafe guidance is rejected."""
    record = deepcopy(load_records()[0])
    record["metadata"]["split"] = "train"
    # Inject unsafe guidance phrase in summary
    record["expected_output"]["summary"] = (
        "We offer a step-by-step attack execution procedure."
    )

    with pytest.raises(SFTValidationError) as exc_info:
        check_sft_eligibility(record)
    assert "failed evaluation/safety validation" in str(exc_info.value)
    assert "unsafe guidance matched pattern" in str(exc_info.value)


def test_batch_formatting_with_and_without_ignore_errors() -> None:
    """Verify format_sft_dataset behaves correctly with ignore_errors parameter."""
    records = load_records()
    assert len(records) >= 3

    # Create a mix of valid and invalid records
    mixed_records = []
    for i, r in enumerate(records):
        rec_copy = deepcopy(r)
        if i == 0:
            rec_copy["metadata"]["split"] = "train"  # Valid
        elif i == 1:
            rec_copy["metadata"]["split"] = "fixture"  # Invalid split
        else:
            rec_copy["metadata"]["split"] = "validation"
            rec_copy["metadata"]["safety_level"] = "restricted"  # Invalid safety level
        mixed_records.append(rec_copy)

    # Without ignore_errors, it should raise immediately
    with pytest.raises(SFTSplitError):
        format_sft_dataset(mixed_records, ignore_errors=False)

    # With ignore_errors, it should silently skip invalid ones and return only valid ones
    formatted = format_sft_dataset(mixed_records, ignore_errors=True)
    assert len(formatted) == 1
    assert formatted[0]["messages"][2]["role"] == "assistant"
