"""Baseline prompt formatting for Phase D inference."""

from __future__ import annotations

import json
from typing import Any, Literal, Mapping, TypedDict, cast


class PromptMessage(TypedDict):
    """Chat-style prompt message consumed by inference helpers."""

    role: Literal["system", "user"]
    content: str


BASELINE_SYSTEM_PROMPT = """You are AegisLM, a defensive security analysis assistant.

Return exactly one JSON object and no other text. Do not use Markdown or code fences.

The JSON object must include these required fields:
- summary: string
- behavior_explanation: string
- risk_level: one of low, medium, high, critical, unknown
- malware_like_behaviors: array of objects with behavior, evidence, confidence
- attack_mapping: array of objects with tactic, technique_id, technique_name, evidence
- recommendations: array of strings
- limitations: array of strings

Use only the provided evidence. Do not invent ATT&CK mappings. If evidence is
insufficient for a technique, leave attack_mapping empty or explain the
uncertainty in limitations.

Do not provide exploit execution steps, malware deployment guidance, evasion
guidance, credential theft workflows, persistence instructions, or other
actionable offensive instructions.

AegisLM is not the final security decision maker. Deterministic analyzer
signals, curated evidence, and human review remain the decision basis."""


def format_baseline_prompt(record: Mapping[str, Any]) -> list[PromptMessage]:
    """Format one Phase C dataset record as baseline system/user messages."""
    input_section = cast(Mapping[str, Any], record["input"])

    user_prompt = "\n\n".join(
        [
            "Analyze the following normalized AegisLM dataset record.",
            f"Record ID: {record['id']}",
            f"Task: {input_section['task']}",
            "Context:",
            str(input_section["context"]),
            "Signals JSON:",
            _to_pretty_json(input_section["signals"]),
            "Source JSON:",
            _to_pretty_json(record["source"]),
            "Metadata JSON:",
            _to_pretty_json(record["metadata"]),
            (
                "Produce only the JSON output object matching the required "
                "AegisLM output contract."
            ),
        ]
    )

    return [
        {"role": "system", "content": BASELINE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _to_pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
