import json
from pathlib import Path
from typing import Any, cast

from aegislm.evaluation import validate_dataset_record, validate_model_output

HELDOUT_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "heldout_evaluation_records.jsonl"
)
TINY_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def load_records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_heldout_evaluation_records_are_valid() -> None:
    records = load_records(HELDOUT_FIXTURE_PATH)

    assert len(records) == 5
    for record in records:
        result = validate_dataset_record(record)
        assert result.ok, (record["id"], result.errors)


def test_heldout_expected_outputs_are_valid_model_outputs() -> None:
    for record in load_records(HELDOUT_FIXTURE_PATH):
        output = record["expected_output"]
        assert isinstance(output, dict)
        result = validate_model_output(cast(dict[str, Any], output))
        assert result.ok, (record["id"], result.errors)


def test_heldout_records_are_excluded_from_training_split() -> None:
    for record in load_records(HELDOUT_FIXTURE_PATH):
        metadata = cast(dict[str, Any], record["metadata"])

        assert metadata["split"] == "test"
        assert metadata["contains_executable_payload"] is False
        assert metadata["safety_level"] in {"metadata_only", "synthetic"}
        assert "exclude from adapter training data" in metadata["notes"]


def test_heldout_records_do_not_overlap_with_phase_c_tiny_fixture() -> None:
    heldout_ids = {record["id"] for record in load_records(HELDOUT_FIXTURE_PATH)}
    tiny_ids = {record["id"] for record in load_records(TINY_FIXTURE_PATH)}

    assert heldout_ids.isdisjoint(tiny_ids)


def test_heldout_fixture_covers_required_evaluation_cases() -> None:
    records = load_records(HELDOUT_FIXTURE_PATH)

    assert any(_has_note(record, "benign case") for record in records)
    assert any(
        record["source"]["type"] == "cisa_kev"
        and record["input"]["signals"].get("is_known_exploited") is True
        for record in records
    )
    assert any(
        record["input"]["signals"].get("is_known_exploited") is False
        and record["input"]["signals"].get("cvss_severity") == "CRITICAL"
        for record in records
    )
    assert any(_is_ambiguous_mapping_case(record) for record in records)
    assert any(_is_safety_refusal_case(record) for record in records)


def _has_note(record: dict[str, Any], expected_note: str) -> bool:
    metadata = cast(dict[str, Any], record["metadata"])
    return expected_note in metadata["notes"]


def _is_ambiguous_mapping_case(record: dict[str, Any]) -> bool:
    expected_output = cast(dict[str, Any], record["expected_output"])
    signals = cast(dict[str, Any], record["input"])["signals"]
    return (
        _has_note(record, "ambiguous ATT&CK mapping case")
        and signals.get("candidate_attack_techniques") == []
        and expected_output["attack_mapping"] == []
        and len(expected_output["limitations"]) > 0
    )


def _is_safety_refusal_case(record: dict[str, Any]) -> bool:
    expected_output = cast(dict[str, Any], record["expected_output"])
    recommendations = " ".join(expected_output["recommendations"]).lower()
    return (
        _has_note(record, "safety refusal evaluation candidate")
        and "decline" in recommendations
        and "defensive" in recommendations
        and expected_output["attack_mapping"] == []
    )
