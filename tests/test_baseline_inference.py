import json
import subprocess
import sys
from pathlib import Path

from aegislm.evaluation import load_predictions
from aegislm.inference import make_static_response_generator, run_baseline_inference
from aegislm.prompts import PromptMessage

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def test_writes_prediction_jsonl_with_raw_output_preserved(tmp_path: Path) -> None:
    raw_output = '{"summary":"raw model text"}'
    predictions_path = tmp_path / "baseline_predictions.jsonl"

    count = run_baseline_inference(
        dataset_path=FIXTURE_PATH,
        predictions_path=predictions_path,
        model_id="unit-test-model",
        run_id="unit-test-run",
        generate_response=make_static_response_generator(raw_output),
        generation_metadata={"backend": "unit-test"},
    )
    predictions = load_predictions(predictions_path)

    assert count == 5
    assert len(predictions) == 5
    assert predictions[0].record_id == "fixture-kev-deserialization-001"
    assert predictions[0].model_id == "unit-test-model"
    assert predictions[0].run_id == "unit-test-run"
    assert predictions[0].raw_output == raw_output
    assert predictions[0].latency_ms is not None
    assert predictions[0].generated_at is not None
    assert predictions[0].metadata == {
        "prompt_message_count": 2,
        "backend": "unit-test",
    }


def test_generator_receives_formatted_prompt_messages(tmp_path: Path) -> None:
    observed_messages: list[list[PromptMessage]] = []

    def generate_response(messages: list[PromptMessage]) -> str:
        observed_messages.append(messages)
        return '{"summary":"ok"}'

    predictions_path = tmp_path / "baseline_predictions.jsonl"
    run_baseline_inference(
        dataset_path=FIXTURE_PATH,
        predictions_path=predictions_path,
        model_id="unit-test-model",
        run_id="unit-test-run",
        generate_response=generate_response,
    )

    assert len(observed_messages) == 5
    assert observed_messages[0][0]["role"] == "system"
    assert observed_messages[0][1]["role"] == "user"
    assert (
        "Record ID: fixture-kev-deserialization-001"
        in observed_messages[0][1]["content"]
    )


def test_cli_mock_backend_writes_prediction_contract(tmp_path: Path) -> None:
    raw_output = '{"summary":"cli raw output"}'
    predictions_path = tmp_path / "cli_predictions.jsonl"

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

    assert "records=5" in result.stdout
    assert len(lines) == 5
    first_prediction = json.loads(lines[0])
    assert first_prediction["raw_output"] == raw_output
    assert first_prediction["metadata"]["backend"] == "mock"
