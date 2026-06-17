import json
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from aegislm.evaluation import (
    parse_model_output,
    validate_dataset_record,
    validate_model_output,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line]


class PhaseCValidationTest(unittest.TestCase):
    def test_tiny_phase_c_records_are_valid(self) -> None:
        records = load_records()

        self.assertEqual(len(records), 5)
        for record in records:
            with self.subTest(record_id=record["id"]):
                result = validate_dataset_record(record)
                self.assertTrue(result.ok, result.errors)

    def test_expected_outputs_are_valid_model_outputs(self) -> None:
        for record in load_records():
            with self.subTest(record_id=record["id"]):
                output = record["expected_output"]
                self.assertIsInstance(output, dict)
                result = validate_model_output(cast(dict[str, Any], output))
                self.assertTrue(result.ok, result.errors)

    def test_parse_model_output_rejects_invalid_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            parse_model_output('{"summary": "missing end"')

    def test_parse_model_output_rejects_non_object_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON object"):
            parse_model_output('["not", "an", "object"]')

    def test_missing_required_field_fails(self) -> None:
        record = deepcopy(load_records()[0])
        expected_output = cast(dict[str, Any], record["expected_output"])
        del expected_output["summary"]

        result = validate_dataset_record(record)

        self.assertFalse(result.ok)
        self.assertTrue(any("summary" in error for error in result.errors))

    def test_invalid_enum_fails(self) -> None:
        record = deepcopy(load_records()[0])
        expected_output = cast(dict[str, Any], record["expected_output"])
        expected_output["risk_level"] = "severe"

        result = validate_dataset_record(record)

        self.assertFalse(result.ok)
        self.assertTrue(any("risk_level" in error for error in result.errors))

    def test_unsafe_guidance_fails(self) -> None:
        record = deepcopy(load_records()[0])
        expected_output = cast(dict[str, Any], record["expected_output"])
        expected_output["recommendations"] = [
            "Follow this step-by-step malware deployment procedure."
        ]

        result = validate_dataset_record(record)

        self.assertFalse(result.ok)
        self.assertTrue(any("unsafe guidance" in error for error in result.errors))

    def test_ambiguous_attack_mapping_can_be_empty_with_limitations(self) -> None:
        record = next(
            item for item in load_records() if item["id"] == "fixture-kev-ambiguous-001"
        )

        expected_output = cast(dict[str, Any], record["expected_output"])
        self.assertEqual(expected_output["attack_mapping"], [])
        self.assertGreater(len(expected_output["limitations"]), 0)
        self.assertTrue(validate_dataset_record(record).ok)


if __name__ == "__main__":
    unittest.main()
