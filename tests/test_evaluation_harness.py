import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from aegislm.evaluation import (
    Prediction,
    evaluate_predictions,
    load_predictions,
    write_report_html,
    write_summary_json,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def load_records() -> list[dict[str, object]]:
    return [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line]


def prediction_for(record: dict[str, object], output: dict[str, object]) -> Prediction:
    return Prediction(
        record_id=str(record["id"]),
        model_id="unit-test-model",
        run_id="unit-test-run",
        raw_output=json.dumps(output),
        latency_ms=12.5,
    )


class EvaluationHarnessTest(unittest.TestCase):
    def test_valid_expected_outputs_score_full_points(self) -> None:
        records = load_records()
        predictions = [
            prediction_for(record, record["expected_output"]) for record in records
        ]

        summary = evaluate_predictions(records, predictions)

        self.assertEqual(summary["metrics"]["total_count"], 5)
        self.assertEqual(summary["metrics"]["composite_score"], 100.0)
        self.assertEqual(summary["metrics"]["hard_gate_pass_rate"], 1.0)
        self.assertEqual(summary["metrics"]["json_parse_success_rate"], 1.0)
        self.assertEqual(summary["metrics"]["schema_validation_pass_rate"], 1.0)
        self.assertEqual(summary["metrics"]["safety_pass_rate"], 1.0)

    def test_invalid_json_is_reported_as_parse_failure(self) -> None:
        records = load_records()
        prediction = Prediction(
            record_id=str(records[0]["id"]),
            model_id="unit-test-model",
            run_id="unit-test-run",
            raw_output='{ "summary": "missing end"',
        )

        summary = evaluate_predictions(records, [prediction])
        case = summary["cases"][0]

        self.assertFalse(case["hard_gate_pass"])
        self.assertFalse(case["json_parse_success"])
        self.assertTrue(any("invalid JSON" in error for error in case["errors"]))

    def test_unsafe_guidance_fails_safety_gate(self) -> None:
        records = load_records()
        output = deepcopy(records[0]["expected_output"])
        output["recommendations"] = [
            "Follow this step-by-step malware deployment procedure."
        ]

        summary = evaluate_predictions(records, [prediction_for(records[0], output)])
        case = summary["cases"][0]

        self.assertFalse(case["hard_gate_pass"])
        self.assertTrue(case["schema_valid"])
        self.assertFalse(case["safety_pass"])
        self.assertTrue(any("unsafe guidance" in error for error in case["errors"]))

    def test_hallucinated_attack_mapping_reduces_mapping_score(self) -> None:
        records = load_records()
        output = deepcopy(records[0]["expected_output"])
        output["attack_mapping"].append(
            {
                "tactic": "Defense Evasion",
                "technique_id": "T9999",
                "technique_name": "Unsupported Technique",
                "evidence": "No curated evidence supports this mapping.",
            }
        )

        summary = evaluate_predictions(records, [prediction_for(records[0], output)])
        case = summary["cases"][0]

        self.assertTrue(case["hard_gate_pass"])
        self.assertEqual(case["hallucinated_attack_mapping_count"], 1)
        self.assertLess(case["attack_mapping_f1"], 1.0)
        self.assertLess(case["score"], 100.0)

    def test_risk_level_mismatch_reduces_score(self) -> None:
        records = load_records()
        output = deepcopy(records[0]["expected_output"])
        output["risk_level"] = "low"

        summary = evaluate_predictions(records, [prediction_for(records[0], output)])
        case = summary["cases"][0]

        self.assertTrue(case["hard_gate_pass"])
        self.assertFalse(case["risk_level_match"])
        self.assertEqual(case["score"], 85.0)

    def test_writes_json_and_html_reports(self) -> None:
        records = load_records()
        predictions = [prediction_for(records[0], records[0]["expected_output"])]
        summary = evaluate_predictions(records, predictions)

        with tempfile.TemporaryDirectory() as tmp_dir:
            summary_path = Path(tmp_dir) / "evaluation_summary.json"
            report_path = Path(tmp_dir) / "evaluation_report.html"

            write_summary_json(summary, summary_path)
            write_report_html(summary, report_path)

            loaded = json.loads(summary_path.read_text())
            self.assertEqual(loaded["metrics"]["composite_score"], 100.0)
            self.assertIn("AegisLM Evaluation Report", report_path.read_text())

    def test_load_predictions_requires_prediction_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "predictions.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "record_id": "fixture-kev-deserialization-001",
                        "model_id": "unit-test-model",
                        "run_id": "unit-test-run",
                        "raw_output": "{}",
                    }
                )
                + "\n"
            )

            predictions = load_predictions(path)

        self.assertEqual(predictions[0].record_id, "fixture-kev-deserialization-001")
        self.assertEqual(predictions[0].model_id, "unit-test-model")


if __name__ == "__main__":
    unittest.main()
