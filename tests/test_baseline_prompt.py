import json
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any

from aegislm.prompts import BASELINE_SYSTEM_PROMPT, format_baseline_prompt

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line]


class BaselinePromptTest(unittest.TestCase):
    def test_formats_phase_c_record_as_system_and_user_messages(self) -> None:
        record = load_records()[0]

        messages = format_baseline_prompt(record)
        user_content = messages[1]["content"]

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], BASELINE_SYSTEM_PROMPT)
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("Record ID: fixture-kev-deserialization-001", user_content)
        self.assertIn(str(record["input"]["task"]), user_content)
        self.assertIn(str(record["input"]["context"]), user_content)
        self.assertIn('"candidate_attack_techniques": [', user_content)
        self.assertIn('"T1190"', user_content)

    def test_system_prompt_contains_output_contract_and_safety_rules(self) -> None:
        system_prompt = BASELINE_SYSTEM_PROMPT

        for required_field in [
            "summary",
            "behavior_explanation",
            "risk_level",
            "malware_like_behaviors",
            "attack_mapping",
            "recommendations",
            "limitations",
        ]:
            with self.subTest(required_field=required_field):
                self.assertIn(required_field, system_prompt)

        self.assertIn("Return exactly one JSON object", system_prompt)
        self.assertIn("low, medium, high, critical, unknown", system_prompt)
        self.assertIn("Do not invent ATT&CK mappings", system_prompt)
        self.assertIn("exploit execution steps", system_prompt)
        self.assertIn("credential theft workflows", system_prompt)
        self.assertIn("human review", system_prompt)

    def test_ambiguous_attack_mapping_instruction_is_preserved(self) -> None:
        record = next(
            item for item in load_records() if item["id"] == "fixture-kev-ambiguous-001"
        )

        messages = format_baseline_prompt(record)
        combined_prompt = "\n".join(message["content"] for message in messages)

        self.assertIn('"candidate_attack_techniques": []', combined_prompt)
        self.assertIn("If evidence is\ninsufficient", combined_prompt)
        self.assertIn("leave attack_mapping empty", combined_prompt)
        self.assertIn("limitations", combined_prompt)

    def test_formatter_does_not_mutate_record(self) -> None:
        record = load_records()[1]
        original = deepcopy(record)

        format_baseline_prompt(record)

        self.assertEqual(record, original)


if __name__ == "__main__":
    unittest.main()
