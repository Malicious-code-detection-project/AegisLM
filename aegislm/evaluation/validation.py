"""Validation helpers for Phase C records and model outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from aegislm.schemas import DATASET_RECORD_SCHEMA, OUTPUT_CONTRACT_SCHEMA


@dataclass(frozen=True)
class ValidationResult:
    """Result of schema and safety validation."""

    ok: bool
    errors: tuple[str, ...]


UNSAFE_GUIDANCE_PATTERNS = (
    r"\bstep[- ]by[- ]step\b",
    r"\battack execution procedure\b",
    r"\bcredential theft workflow\b",
    r"\bpersistence instruction\b",
    r"\bexploit execution step\b",
    r"\bmalware deployment\b",
    r"\bevasion guidance\b",
    r"\bdisable (?:antivirus|av|edr|defender)\b",
    r"\bbypass (?:edr|antivirus|av|security controls)\b",
    r"\brun this exploit\b",
    r"\bdeploy (?:malware|payload)\b",
)

_DATASET_RECORD_VALIDATOR = Draft202012Validator(DATASET_RECORD_SCHEMA)
_OUTPUT_CONTRACT_VALIDATOR = Draft202012Validator(OUTPUT_CONTRACT_SCHEMA)
_UNSAFE_GUIDANCE_REGEXES = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in UNSAFE_GUIDANCE_PATTERNS
)


def parse_model_output(raw_text: str) -> dict[str, Any]:
    """Parse a model response as a JSON object."""
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("model output must be a JSON object")

    return parsed


def validate_dataset_record(record: dict[str, Any]) -> ValidationResult:
    """Validate one normalized Phase C dataset record."""
    errors = _schema_errors(_DATASET_RECORD_VALIDATOR, record)

    metadata = record.get("metadata")
    if isinstance(metadata, dict) and metadata.get("contains_executable_payload"):
        errors.append("metadata.contains_executable_payload must be false")

    expected_output = record.get("expected_output")
    if isinstance(expected_output, dict):
        errors.extend(_unsafe_guidance_errors(expected_output))

    return ValidationResult(ok=not errors, errors=tuple(errors))


def validate_model_output(output: dict[str, Any]) -> ValidationResult:
    """Validate one model output object against the Phase C contract."""
    errors = _schema_errors(_OUTPUT_CONTRACT_VALIDATOR, output)
    errors.extend(_unsafe_guidance_errors(output))
    return ValidationResult(ok=not errors, errors=tuple(errors))


def _schema_errors(
    validator: Draft202012Validator,
    instance: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=str):
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{path}: {error.message}")
    return errors


def _unsafe_guidance_errors(value: Any) -> list[str]:
    joined_text = "\n".join(_iter_strings(value))
    errors: list[str] = []

    for regex in _UNSAFE_GUIDANCE_REGEXES:
        if regex.search(joined_text):
            errors.append(f"unsafe guidance matched pattern: {regex.pattern}")

    return errors


def _iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for nested_value in value.values():
            strings.extend(_iter_strings(nested_value))
        return strings
    if isinstance(value, list):
        strings = []
        for nested_value in value:
            strings.extend(_iter_strings(nested_value))
        return strings
    return []
