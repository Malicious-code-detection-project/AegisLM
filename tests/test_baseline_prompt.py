import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from aegislm.prompts import BASELINE_SYSTEM_PROMPT, format_baseline_prompt

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line]


def test_formats_phase_c_record_as_system_and_user_messages() -> None:
    record = load_records()[0]

    messages = format_baseline_prompt(record)
    user_content = messages[1]["content"]

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == BASELINE_SYSTEM_PROMPT
    assert messages[1]["role"] == "user"
    assert "Record ID: fixture-kev-deserialization-001" in user_content
    assert str(record["input"]["task"]) in user_content
    assert str(record["input"]["context"]) in user_content
    assert '"candidate_attack_techniques": [' in user_content
    assert '"T1190"' in user_content


def test_system_prompt_contains_output_contract_and_safety_rules() -> None:
    for required_field in [
        "summary",
        "behavior_explanation",
        "risk_level",
        "malware_like_behaviors",
        "attack_mapping",
        "recommendations",
        "limitations",
    ]:
        assert required_field in BASELINE_SYSTEM_PROMPT

    assert "Return exactly one JSON object" in BASELINE_SYSTEM_PROMPT
    assert "low, medium, high, critical, unknown" in BASELINE_SYSTEM_PROMPT
    assert "Do not invent ATT&CK mappings" in BASELINE_SYSTEM_PROMPT
    assert "exploit execution steps" in BASELINE_SYSTEM_PROMPT
    assert "credential theft workflows" in BASELINE_SYSTEM_PROMPT
    assert "human review" in BASELINE_SYSTEM_PROMPT


def test_ambiguous_attack_mapping_instruction_is_preserved() -> None:
    record = next(
        item for item in load_records() if item["id"] == "fixture-kev-ambiguous-001"
    )

    messages = format_baseline_prompt(record)
    combined_prompt = "\n".join(message["content"] for message in messages)

    assert '"candidate_attack_techniques": []' in combined_prompt
    assert "If evidence is\ninsufficient" in combined_prompt
    assert "leave attack_mapping empty" in combined_prompt
    assert "limitations" in combined_prompt


def test_formatter_does_not_mutate_record() -> None:
    record = load_records()[1]
    original = deepcopy(record)

    format_baseline_prompt(record)

    assert record == original
