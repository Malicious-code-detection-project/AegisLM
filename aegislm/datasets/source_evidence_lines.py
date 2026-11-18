"""Assessment-conditioned evidence line selection and exact-span resolution."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from jsonschema import Draft202012Validator

from aegislm.datasets.source_compact import (
    render_source_assessment,
    validate_compact_evidence_output,
)
from aegislm.schemas import SOURCE_EVIDENCE_LINES_OUTPUT_SCHEMA

SourceContractError = ValueError
SourcePromptMessage = dict[str, str]

SOURCE_EVIDENCE_LINES_SYSTEM_PROMPT = """You are AegisLM, a defensive source-code evidence selector.

The scoped assessment has already been decided. Do not change or repeat it.
Return exactly one JSON object and no Markdown with:
- schema_version="aegislm.source-evidence-lines.v1"
- evidence_ranges: 1 to 8 objects with integer start_line and end_line
- confidence: low, medium, or high

Select the smallest sufficient line ranges that support the supplied assessment
for the requested CWE. Use only line numbers visible in numbered_source_code.
Do not copy source text. Do not add explanations, labels, provenance, record IDs,
paths, exploit steps, payloads, or any other field."""

_VALIDATOR = Draft202012Validator(SOURCE_EVIDENCE_LINES_OUTPUT_SCHEMA)
_ASSESSMENTS = frozenset({"present", "not_observed"})


def validate_evidence_lines_output(
    output: Mapping[str, Any],
    *,
    line_count: int,
) -> list[str]:
    """Validate schema, range bounds, ordering, and overlap."""
    errors = [
        _format_schema_error(error)
        for error in sorted(
            _VALIDATOR.iter_errors(dict(output)),
            key=lambda item: list(item.absolute_path),
        )
    ]
    if errors:
        return errors
    previous_end = 0
    for index, item in enumerate(
        cast(Sequence[Mapping[str, Any]], output["evidence_ranges"])
    ):
        start = int(item["start_line"])
        end = int(item["end_line"])
        if start > end:
            errors.append(f"evidence_ranges.{index}.start_line exceeds end_line")
        if end > line_count:
            errors.append(f"evidence_ranges.{index}.end_line exceeds source line count")
        if start <= previous_end:
            errors.append(
                f"evidence_ranges.{index} overlaps or is not strictly ordered"
            )
        previous_end = max(previous_end, end)
    return errors


def format_evidence_lines_payload(
    *,
    target_cwe: str,
    source_code: str,
    assessment: Literal["present", "not_observed"],
) -> list[SourcePromptMessage]:
    """Format the evidence task from an already validated visible payload."""
    if assessment not in _ASSESSMENTS:
        raise SourceContractError(f"unsupported evidence assessment: {assessment}")
    visible = {
        "scope": {
            "target_cwe": target_cwe,
            "boundary": "supplied_function",
        },
        "assessment": assessment,
        "numbered_source_code": number_source_code(source_code),
    }
    return [
        {"role": "system", "content": SOURCE_EVIDENCE_LINES_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "\n\n".join(
                [
                    "Select code evidence for the supplied scoped assessment.",
                    json.dumps(visible, ensure_ascii=False, indent=2, sort_keys=True),
                    "Return only the source evidence line-range JSON.",
                ]
            ),
        },
    ]


def number_source_code(source_code: str) -> str:
    """Add stable one-based line numbers without changing the private source."""
    lines = source_code.splitlines()
    width = max(4, len(str(len(lines))))
    return "\n".join(
        f"{index:0{width}d}|{line}" for index, line in enumerate(lines, start=1)
    )


def project_compact_to_evidence_lines(
    compact: Mapping[str, Any],
    *,
    source_code: str,
) -> dict[str, Any]:
    """Project exact compact spans to sorted, merged source line ranges."""
    errors = validate_compact_evidence_output(compact, source_code=source_code)
    if errors:
        raise SourceContractError("; ".join(errors))
    assessment = str(compact["assessment"])
    if assessment not in _ASSESSMENTS:
        raise SourceContractError("evidence-only training requires a binary assessment")
    ranges = [
        _span_line_range(source_code, str(span))
        for span in cast(Sequence[Any], compact["evidence_spans"])
    ]
    merged = _merge_ranges(ranges)
    target = {
        "schema_version": "aegislm.source-evidence-lines.v1",
        "evidence_ranges": [
            {"start_line": start, "end_line": end} for start, end in merged
        ],
        "confidence": compact["confidence"],
    }
    target_errors = validate_evidence_lines_output(
        target,
        line_count=len(source_code.splitlines()),
    )
    if target_errors:
        raise SourceContractError("; ".join(target_errors))
    return target


def resolve_evidence_ranges(
    output: Mapping[str, Any],
    *,
    source_code: str,
) -> list[str]:
    """Resolve validated one-based line ranges to exact source substrings."""
    errors = validate_evidence_lines_output(
        output,
        line_count=len(source_code.splitlines()),
    )
    if errors:
        raise SourceContractError("; ".join(errors))
    lines = source_code.splitlines(keepends=True)
    spans: list[str] = []
    for item in cast(Sequence[Mapping[str, Any]], output["evidence_ranges"]):
        start = int(item["start_line"]) - 1
        end = int(item["end_line"])
        span = "".join(lines[start:end]).rstrip("\r\n")
        if not span.strip():
            continue
        if span not in source_code:
            raise SourceContractError("resolved evidence is not an exact substring")
        if span not in spans:
            spans.append(span)
    if not spans:
        raise SourceContractError("resolved evidence contains only blank lines")
    return spans


def render_assessment_from_evidence_lines(
    output: Mapping[str, Any],
    *,
    assessment: Literal["present", "not_observed"],
    target_cwe: str,
    source_code: str,
) -> dict[str, Any]:
    """Resolve evidence and render the stable source assessment v2 contract."""
    spans = resolve_evidence_ranges(output, source_code=source_code)
    compact = {
        "schema_version": "aegislm.source-compact-evidence.v1",
        "assessment": assessment,
        "evidence_spans": spans,
        "confidence": output["confidence"],
    }
    return render_source_assessment(
        compact,
        target_cwe=target_cwe,
        source_code=source_code,
    )


def _span_line_range(source_code: str, span: str) -> tuple[int, int]:
    start = source_code.find(span)
    if start < 0:
        raise SourceContractError("compact evidence span is not in source")
    end_offset = start + len(span) - 1
    return (
        source_code.count("\n", 0, start) + 1,
        source_code.count("\n", 0, end_offset) + 1,
    )


def _merge_ranges(ranges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(set(ranges)):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    if len(merged) > 8:
        raise SourceContractError("projected evidence requires more than 8 ranges")
    return merged


def _format_schema_error(error: Any) -> str:
    path = ".".join(str(item) for item in error.absolute_path)
    return f"{path}: {error.message}" if path else error.message
