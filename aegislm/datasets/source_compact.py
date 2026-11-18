"""Minimal renderer ported from AegisLM-B200 a070726; no dataset rebuilding."""

from __future__ import annotations
from collections.abc import Mapping, Sequence
from typing import Any, cast
from jsonschema import Draft202012Validator
from aegislm.schemas import SOURCE_COMPACT_EVIDENCE_OUTPUT_SCHEMA
from aegislm.evaluation.validation import validate_source_assessment

SourceContractError = ValueError
_VALIDATOR = Draft202012Validator(SOURCE_COMPACT_EVIDENCE_OUTPUT_SCHEMA)


def validate_compact_evidence_output(
    output: Mapping[str, Any],
    *,
    source_code: str | None = None,
) -> list[str]:
    """Validate the compact schema and exact source-substring evidence."""
    errors = [
        _format_schema_error(error)
        for error in sorted(
            _VALIDATOR.iter_errors(dict(output)),
            key=lambda item: list(item.absolute_path),
        )
    ]
    if errors or source_code is None:
        return errors
    for index, span in enumerate(cast(Sequence[Any], output["evidence_spans"])):
        if str(span) not in source_code:
            errors.append(f"evidence_spans.{index} is not an exact source substring")
    return errors


def render_source_assessment(
    compact: Mapping[str, Any],
    *,
    target_cwe: str,
    source_code: str,
) -> dict[str, Any]:
    """Render a stable v2 report without asking the model for boilerplate prose."""
    errors = validate_compact_evidence_output(compact, source_code=source_code)
    if errors:
        raise SourceContractError("; ".join(errors))
    assessment = str(compact["assessment"])
    spans = list(cast(Sequence[str], compact["evidence_spans"]))
    confidence = str(compact["confidence"])
    if assessment == "present":
        relationship = (
            "The selected exact spans are the model-identified code-visible "
            "basis for the scoped CWE."
        )
        conclusion = (
            f"The supplied function contains code-visible evidence assessed as "
            f"{target_cwe}."
        )
    elif assessment == "not_observed":
        relationship = (
            "The selected exact spans are the model-identified defensive or "
            "non-triggering basis for the scoped CWE."
        )
        conclusion = (
            f"The scoped {target_cwe} condition was not observed in the supplied "
            "function."
        )
    else:
        relationship = "The supplied function did not provide sufficient evidence."
        conclusion = (
            f"The scoped {target_cwe} assessment is uncertain for the supplied "
            "function."
        )
    basis_spans = spans or [_first_nonempty_line(source_code)]
    basis = [
        {
            "code_spans": basis_spans,
            "relationship": relationship,
            "conclusion": conclusion,
            "confidence": confidence,
        }
    ]
    findings = (
        [
            {
                "code_spans": spans,
                "operation": (
                    "Code-visible operations selected for the scoped CWE assessment."
                ),
                "evidence": relationship,
                "confidence": confidence,
            }
        ]
        if assessment == "present"
        else []
    )
    report = {
        "schema_version": "aegislm.source-vulnerability-assessment.v2",
        "scope": {
            "target_cwe": target_cwe,
            "boundary": "supplied_function",
        },
        "assessment": assessment,
        "assessment_basis": basis,
        "findings": findings,
        "limitations": [
            "This assessment is limited to the requested CWE and supplied function.",
            "This result does not establish whole-program safety or exploitability.",
        ],
        "recommendations": [
            "Confirm the scoped result with deterministic analysis and human review."
        ],
    }
    report_errors = validate_source_assessment(
        report, source_code=source_code, target_cwe=target_cwe
    ).errors
    if report_errors:
        raise SourceContractError("; ".join(report_errors))
    return report


def _first_nonempty_line(source_code: str) -> str:
    for line in source_code.splitlines():
        value = line.strip()
        if value:
            return value
    raise SourceContractError("source code has no non-empty line")


def _format_schema_error(error: Any) -> str:
    path = ".".join(str(item) for item in error.absolute_path)
    return f"{path}: {error.message}" if path else error.message
