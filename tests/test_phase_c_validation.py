import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from aegislm.evaluation import (
    parse_model_output,
    validate_dataset_record,
    validate_model_output,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line]


def test_tiny_phase_c_records_are_valid() -> None:
    records = load_records()

    assert len(records) == 5
    for record in records:
        result = validate_dataset_record(record)
        assert result.ok, (record["id"], result.errors)


def test_expected_outputs_are_valid_model_outputs() -> None:
    for record in load_records():
        output = record["expected_output"]
        assert isinstance(output, dict)
        result = validate_model_output(cast(dict[str, Any], output))
        assert result.ok, (record["id"], result.errors)


def test_parse_model_output_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_model_output('{"summary": "missing end"')


def test_parse_model_output_rejects_non_object_json() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_model_output('["not", "an", "object"]')


def test_missing_required_field_fails() -> None:
    record = deepcopy(load_records()[0])
    expected_output = cast(dict[str, Any], record["expected_output"])
    del expected_output["summary"]

    result = validate_dataset_record(record)

    assert not result.ok
    assert any("summary" in error for error in result.errors)


def test_invalid_enum_fails() -> None:
    record = deepcopy(load_records()[0])
    expected_output = cast(dict[str, Any], record["expected_output"])
    expected_output["risk_level"] = "severe"

    result = validate_dataset_record(record)

    assert not result.ok
    assert any("risk_level" in error for error in result.errors)


def test_unsafe_guidance_fails() -> None:
    record = deepcopy(load_records()[0])
    expected_output = cast(dict[str, Any], record["expected_output"])
    expected_output["recommendations"] = [
        "Follow this step-by-step malware deployment procedure."
    ]

    result = validate_dataset_record(record)

    assert not result.ok
    assert any("unsafe guidance" in error for error in result.errors)


def test_ambiguous_attack_mapping_can_be_empty_with_limitations() -> None:
    record = next(
        item for item in load_records() if item["id"] == "fixture-kev-ambiguous-001"
    )

    expected_output = cast(dict[str, Any], record["expected_output"])
    assert expected_output["attack_mapping"] == []
    assert len(expected_output["limitations"]) > 0
    assert validate_dataset_record(record).ok
