"""Validation utilities for AegisLM dataset records and contamination checks."""

from __future__ import annotations

from typing import Any
import jsonschema
from aegislm.schemas import DATASET_RECORD_SCHEMA


class DatasetValidationError(Exception):
    """Exception raised when a dataset record fails validation."""

    pass


class SafetyPolicyViolationError(Exception):
    """Exception raised when a record violates the safety and exclusion policy."""

    pass


class ContaminationError(Exception):
    """Exception raised when contamination (overlap) is detected between splits."""

    pass


def validate_record(record: dict[str, Any]) -> None:
    """Validate a dataset record against the JSON schema contract.

    Args:
        record: The dataset record to validate.

    Raises:
        DatasetValidationError: If schema validation fails.
    """
    try:
        jsonschema.validate(instance=record, schema=DATASET_RECORD_SCHEMA)
    except jsonschema.exceptions.ValidationError as e:
        raise DatasetValidationError(f"Schema validation failed: {e.message}") from e


def validate_safety_policy(record: dict[str, Any]) -> None:
    """Verify that the record does not violate the safety policy.

    Args:
        record: The dataset record to verify.

    Raises:
        SafetyPolicyViolationError: If safety rules are violated.
    """
    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        return

    # 1. Executable payloads are strictly forbidden
    if metadata.get("contains_executable_payload") is True:
        raise SafetyPolicyViolationError(
            f"Record {record.get('id')} contains an executable payload, which is forbidden."
        )

    # 2. Basic secrets/credentials check in context or expected output
    context = record.get("input", {}).get("context", "")
    expected = str(record.get("expected_output", ""))

    forbidden_patterns = ["password=", "api_key=", "client_secret="]
    for pattern in forbidden_patterns:
        if pattern in context.lower() or pattern in expected.lower():
            raise SafetyPolicyViolationError(
                f"Record {record.get('id')} may contain sensitive credential secrets."
            )


def check_contamination(
    train_records: list[dict[str, Any]], eval_records: list[dict[str, Any]]
) -> None:
    """Ensure no overlap (contamination) between training and evaluation dataset splits.

    Checks overlap of ID, CVE ID, and Scenario ID.

    Args:
        train_records: A list of training dataset records.
        eval_records: A list of evaluation dataset records.

    Raises:
        ContaminationError: If duplicate identifiers or scenarios are detected across splits.
    """
    train_ids = {r.get("id") for r in train_records if r.get("id")}
    eval_ids = {r.get("id") for r in eval_records if r.get("id")}

    id_overlap = train_ids.intersection(eval_ids)
    if id_overlap:
        raise ContaminationError(
            f"Contamination detected: Overlapping Record ID(s): {id_overlap}"
        )

    # Extract scenario and CVE identifiers from signals
    def get_identifiers(record: dict[str, Any]) -> set[str]:
        idents: set[str] = set()
        signals = record.get("input", {}).get("signals", {})
        if not isinstance(signals, dict):
            return idents
        cve_id = signals.get("cve_id")
        if cve_id:
            idents.add(str(cve_id).upper())
        scenario_id = signals.get("scenario_id")
        if scenario_id:
            idents.add(str(scenario_id))
        return idents

    train_scenarios: set[str] = set()
    for r in train_records:
        train_scenarios.update(get_identifiers(r))

    eval_scenarios: set[str] = set()
    for r in eval_records:
        eval_scenarios.update(get_identifiers(r))

    scenario_overlap = train_scenarios.intersection(eval_scenarios)
    if scenario_overlap:
        raise ContaminationError(
            f"Contamination detected: Overlapping CVE or Scenario identifier(s): {scenario_overlap}"
        )
