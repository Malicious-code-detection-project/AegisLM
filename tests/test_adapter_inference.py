import json
import subprocess
import sys
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def test_cli_mock_backend_writes_prediction_contract_for_adapter(
    tmp_path: Path,
) -> None:
    raw_output = '{"summary":"adapter cli raw output"}'
    predictions_path = tmp_path / "cli_adapter_predictions.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_adapter_inference.py",
            "--dataset",
            str(FIXTURE_PATH),
            "--predictions",
            str(predictions_path),
            "--adapter-path",
            "adapters/tiny-sft-poc",
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
    assert first_prediction["metadata"]["adapter_path"] == "adapters/tiny-sft-poc"
