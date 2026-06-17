import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aegislm.evaluation import load_predictions
from aegislm.inference import make_static_response_generator, run_baseline_inference
from aegislm.prompts import PromptMessage

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


class BaselineInferenceTest(unittest.TestCase):
    def test_writes_prediction_jsonl_with_raw_output_preserved(self) -> None:
        raw_output = '{"summary":"raw model text"}'

        with tempfile.TemporaryDirectory() as tmp_dir:
            predictions_path = Path(tmp_dir) / "baseline_predictions.jsonl"
            count = run_baseline_inference(
                dataset_path=FIXTURE_PATH,
                predictions_path=predictions_path,
                model_id="unit-test-model",
                run_id="unit-test-run",
                generate_response=make_static_response_generator(raw_output),
                generation_metadata={"backend": "unit-test"},
            )

            self.assertEqual(count, 5)
            predictions = load_predictions(predictions_path)

        self.assertEqual(len(predictions), 5)
        self.assertEqual(predictions[0].record_id, "fixture-kev-deserialization-001")
        self.assertEqual(predictions[0].model_id, "unit-test-model")
        self.assertEqual(predictions[0].run_id, "unit-test-run")
        self.assertEqual(predictions[0].raw_output, raw_output)
        self.assertIsNotNone(predictions[0].latency_ms)
        self.assertIsNotNone(predictions[0].generated_at)
        self.assertEqual(
            predictions[0].metadata,
            {"prompt_message_count": 2, "backend": "unit-test"},
        )

    def test_generator_receives_formatted_prompt_messages(self) -> None:
        observed_messages: list[list[PromptMessage]] = []

        def generate_response(messages: list[PromptMessage]) -> str:
            observed_messages.append(messages)
            return '{"summary":"ok"}'

        with tempfile.TemporaryDirectory() as tmp_dir:
            predictions_path = Path(tmp_dir) / "baseline_predictions.jsonl"
            run_baseline_inference(
                dataset_path=FIXTURE_PATH,
                predictions_path=predictions_path,
                model_id="unit-test-model",
                run_id="unit-test-run",
                generate_response=generate_response,
            )

        self.assertEqual(len(observed_messages), 5)
        self.assertEqual(observed_messages[0][0]["role"], "system")
        self.assertEqual(observed_messages[0][1]["role"], "user")
        self.assertIn(
            "Record ID: fixture-kev-deserialization-001",
            observed_messages[0][1]["content"],
        )

    def test_cli_mock_backend_writes_prediction_contract(self) -> None:
        raw_output = '{"summary":"cli raw output"}'

        with tempfile.TemporaryDirectory() as tmp_dir:
            predictions_path = Path(tmp_dir) / "cli_predictions.jsonl"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_baseline_inference.py",
                    "--dataset",
                    str(FIXTURE_PATH),
                    "--predictions",
                    str(predictions_path),
                    "--model-id",
                    "unit-test-model",
                    "--run-id",
                    "unit-test-run",
                    "--backend",
                    "mock",
                    "--mock-raw-output",
                    raw_output,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            lines = predictions_path.read_text(encoding="utf-8").splitlines()

        self.assertIn("records=5", result.stdout)
        self.assertEqual(len(lines), 5)
        first_prediction = json.loads(lines[0])
        self.assertEqual(first_prediction["raw_output"], raw_output)
        self.assertEqual(first_prediction["metadata"]["backend"], "mock")


if __name__ == "__main__":
    unittest.main()
