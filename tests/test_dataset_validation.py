"""Unit tests for dataset record validation and contamination checking."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aegislm.datasets.validation import (
    ContaminationError,
    DatasetValidationError,
    SafetyPolicyViolationError,
    check_contamination,
    validate_record,
    validate_safety_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TINY_DATASET_PATH = REPO_ROOT / "tests" / "fixtures" / "tiny_phase_c_records.jsonl"
HELDOUT_DATASET_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "heldout_evaluation_records.jsonl"
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                records.append(json.loads(line_str))
    return records


def test_tiny_dataset_validation() -> None:
    """Verify that all records in tiny_phase_c_records.jsonl are valid and safe."""
    records = _load_jsonl(TINY_DATASET_PATH)
    assert len(records) > 0

    for r in records:
        # Must pass JSON schema validation
        validate_record(r)
        # Must pass safety policy validation
        validate_safety_policy(r)


def test_heldout_dataset_validation() -> None:
    """Verify that all records in heldout_evaluation_records.jsonl are valid and safe."""
    records = _load_jsonl(HELDOUT_DATASET_PATH)
    assert len(records) > 0

    for r in records:
        # Must pass JSON schema validation
        validate_record(r)
        # Must pass safety policy validation
        validate_safety_policy(r)


def test_contamination_check_passes() -> None:
    """Verify that train and eval datasets do not overlap."""
    train_records = _load_jsonl(TINY_DATASET_PATH)
    eval_records = _load_jsonl(HELDOUT_DATASET_PATH)

    # Should complete without raising any ContaminationError
    check_contamination(train_records, eval_records)


def test_validation_failure_bad_schema() -> None:
    """Test schema validation fails when required keys are missing."""
    invalid_record = {
        "id": "bad-schema-record",
        "source": {
            "type": "nurilab_synthetic",
            "name": "Invalid Source",
            "url": None,
            "license_or_terms": None,
            "retrieved_at": "2026-06-29",
        },
        # Missing 'input', 'expected_output', and 'metadata'
    }

    with pytest.raises(DatasetValidationError) as exc_info:
        validate_record(invalid_record)
    assert "Schema validation failed" in str(exc_info.value)


def test_safety_violation_payload() -> None:
    """Test safety check fails if contains_executable_payload is true."""
    unsafe_record = {
        "id": "unsafe-payload-record",
        "source": {
            "type": "nurilab_synthetic",
            "name": "Unsafe Source",
            "url": None,
            "license_or_terms": None,
            "retrieved_at": "2026-06-29",
        },
        "input": {
            "task": "summarize benign script",
            "context": "Benign local operation description",
            "signals": {},
        },
        "expected_output": {
            "summary": "Benign utility",
            "behavior_explanation": "Explanation",
            "risk_level": "low",
            "malware_like_behaviors": [],
            "attack_mapping": [],
            "recommendations": ["No escalation"],
            "limitations": ["None"],
        },
        "metadata": {
            "split": "train",
            "safety_level": "synthetic",
            "contains_executable_payload": True,  # Violation!
            "notes": [],
        },
    }

    with pytest.raises(SafetyPolicyViolationError) as exc_info:
        validate_safety_policy(unsafe_record)
    assert "contains an executable payload" in str(exc_info.value)


def test_safety_violation_secret() -> None:
    """Test safety check fails if credentials are leaked in context."""
    secret_record = {
        "id": "secret-leak-record",
        "source": {
            "type": "nurilab_synthetic",
            "name": "Secret Source",
            "url": None,
            "license_or_terms": None,
            "retrieved_at": "2026-06-29",
        },
        "input": {
            "task": "summarize",
            "context": "Code snippet: api_key=1234abcdsecretkey",  # Violation!
            "signals": {},
        },
        "expected_output": {
            "summary": "Utility",
            "behavior_explanation": "Explanation",
            "risk_level": "low",
            "malware_like_behaviors": [],
            "attack_mapping": [],
            "recommendations": ["No escalation"],
            "limitations": ["None"],
        },
        "metadata": {
            "split": "train",
            "safety_level": "synthetic",
            "contains_executable_payload": False,
            "notes": [],
        },
    }

    with pytest.raises(SafetyPolicyViolationError) as exc_info:
        validate_safety_policy(secret_record)
    assert "may contain sensitive credential secrets" in str(exc_info.value)


def test_contamination_overlap_id() -> None:
    """Test contamination check fails if same record ID is in both datasets."""
    r1 = {
        "id": "duplicate-id-123",
        "input": {"signals": {}},
    }
    r2 = {
        "id": "duplicate-id-123",
        "input": {"signals": {}},
    }

    with pytest.raises(ContaminationError) as exc_info:
        check_contamination([r1], [r2])
    assert "Overlapping Record ID(s)" in str(exc_info.value)


def test_contamination_overlap_scenario() -> None:
    """Test contamination check fails if same scenario_id is in both datasets."""
    r1 = {
        "id": "train-rec-1",
        "input": {"signals": {"scenario_id": "overlap-scenario"}},
    }
    r2 = {
        "id": "eval-rec-1",
        "input": {"signals": {"scenario_id": "overlap-scenario"}},
    }

    with pytest.raises(ContaminationError) as exc_info:
        check_contamination([r1], [r2])
    assert "Overlapping CVE or Scenario identifier(s)" in str(exc_info.value)


def test_contamination_overlap_cve() -> None:
    """Test contamination check fails if same CVE ID is in both datasets."""
    r1 = {
        "id": "train-rec-1",
        "input": {"signals": {"cve_id": "cve-2026-99999"}},
    }
    r2 = {
        "id": "eval-rec-1",
        "input": {"signals": {"cve_id": "CVE-2026-99999"}},  # Checks case insensitivity
    }

    with pytest.raises(ContaminationError) as exc_info:
        check_contamination([r1], [r2])
    assert "Overlapping CVE or Scenario identifier(s)" in str(exc_info.value)
