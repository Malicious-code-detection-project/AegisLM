"""JSON contracts for Phase C dataset records and model outputs."""

from __future__ import annotations

RISK_LEVELS = ("low", "medium", "high", "critical", "unknown")
CONFIDENCE_LEVELS = ("low", "medium", "high")
SOURCE_TYPES = (
    "nvd",
    "cisa_kev",
    "mitre_attack",
    "public_cti",
    "nurilab_synthetic",
    "nurilab_analysis",
)
SPLITS = ("train", "validation", "test", "fixture")
SAFETY_LEVELS = ("metadata_only", "synthetic", "redacted", "restricted")

OUTPUT_CONTRACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "AegisLM Phase C Output Contract",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "summary",
        "behavior_explanation",
        "risk_level",
        "malware_like_behaviors",
        "attack_mapping",
        "recommendations",
        "limitations",
    ],
    "properties": {
        "summary": {"type": "string", "minLength": 1},
        "behavior_explanation": {"type": "string", "minLength": 1},
        "risk_level": {"type": "string", "enum": list(RISK_LEVELS)},
        "malware_like_behaviors": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["behavior", "evidence", "confidence"],
                "properties": {
                    "behavior": {"type": "string", "minLength": 1},
                    "evidence": {"type": "string", "minLength": 1},
                    "confidence": {"type": "string", "enum": list(CONFIDENCE_LEVELS)},
                },
            },
        },
        "attack_mapping": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tactic", "technique_id", "technique_name", "evidence"],
                "properties": {
                    "tactic": {"type": "string", "minLength": 1},
                    "technique_id": {"type": "string", "minLength": 1},
                    "technique_name": {"type": "string", "minLength": 1},
                    "evidence": {"type": "string", "minLength": 1},
                },
            },
        },
        "recommendations": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "limitations": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
}

DATASET_RECORD_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "AegisLM Phase C Dataset Record",
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "source", "input", "expected_output", "metadata"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "source": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "name", "url", "license_or_terms", "retrieved_at"],
            "properties": {
                "type": {"type": "string", "enum": list(SOURCE_TYPES)},
                "name": {"type": "string", "minLength": 1},
                "url": {"type": ["string", "null"]},
                "license_or_terms": {"type": ["string", "null"]},
                "retrieved_at": {
                    "type": ["string", "null"],
                    "pattern": r"^\d{4}-\d{2}-\d{2}$",
                },
            },
        },
        "input": {
            "type": "object",
            "additionalProperties": False,
            "required": ["task", "context", "signals"],
            "properties": {
                "task": {"type": "string", "minLength": 1},
                "context": {"type": "string", "minLength": 1},
                "signals": {"type": "object"},
            },
        },
        "expected_output": OUTPUT_CONTRACT_SCHEMA,
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "split",
                "safety_level",
                "contains_executable_payload",
                "notes",
            ],
            "properties": {
                "split": {"type": "string", "enum": list(SPLITS)},
                "safety_level": {"type": "string", "enum": list(SAFETY_LEVELS)},
                "contains_executable_payload": {"type": "boolean"},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}
