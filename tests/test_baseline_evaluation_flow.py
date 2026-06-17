import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


class BaselineEvaluationFlowTest(unittest.TestCase):
    def test_cli_generates_predictions_and_evaluation_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            predictions_path = output_dir / "baseline_predictions.jsonl"
            summary_path = output_dir / "evaluation_summary.json"
            report_path = output_dir / "evaluation_report.html"

            inference_result = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_baseline_inference.py",
                    "--dataset",
                    str(FIXTURE_PATH),
                    "--predictions",
                    str(predictions_path),
                    "--model-id",
                    "unit-test-mock-baseline",
                    "--run-id",
                    "unit-test-baseline-smoke",
                    "--backend",
                    "mock",
                    "--mock-raw-output",
                    '{"summary":"mock raw output"}',
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            evaluation_result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluate_predictions.py",
                    "--dataset",
                    str(FIXTURE_PATH),
                    "--predictions",
                    str(predictions_path),
                    "--summary-json",
                    str(summary_path),
                    "--report-html",
                    str(report_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))

            self.assertIn("records=5", inference_result.stdout)
            self.assertIn("AegisLM evaluation complete", evaluation_result.stdout)
            self.assertTrue(predictions_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertTrue(report_path.exists())
            self.assertEqual(summary["run_id"], "unit-test-baseline-smoke")
            self.assertEqual(summary["model_id"], "unit-test-mock-baseline")
            self.assertEqual(summary["metrics"]["total_count"], 5)
            self.assertEqual(summary["metrics"]["json_parse_success_rate"], 1.0)
            self.assertEqual(summary["metrics"]["schema_validation_pass_rate"], 0.0)
            self.assertEqual(summary["metrics"]["hard_gate_pass_rate"], 0.0)
            self.assertGreater(len(summary["cases"][0]["errors"]), 0)
            self.assertIn("AegisLM Evaluation Report", report_path.read_text())


if __name__ == "__main__":
    unittest.main()
