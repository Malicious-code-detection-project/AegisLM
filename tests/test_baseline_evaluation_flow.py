import json
import subprocess
import sys
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def test_cli_generates_predictions_and_evaluation_artifacts(tmp_path: Path) -> None:
    predictions_path = tmp_path / "baseline_predictions.jsonl"
    summary_path = tmp_path / "evaluation_summary.json"
    report_path = tmp_path / "evaluation_report.html"

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

    assert "records=5" in inference_result.stdout
    assert "AegisLM evaluation complete" in evaluation_result.stdout
    assert predictions_path.exists()
    assert summary_path.exists()
    assert report_path.exists()
    assert summary["run_id"] == "unit-test-baseline-smoke"
    assert summary["model_id"] == "unit-test-mock-baseline"
    assert summary["metrics"]["total_count"] == 5
    assert summary["metrics"]["json_parse_success_rate"] == 1.0
    assert summary["metrics"]["schema_validation_pass_rate"] == 0.0
    assert summary["metrics"]["hard_gate_pass_rate"] == 0.0
    assert len(summary["cases"][0]["errors"]) > 0
    assert "AegisLM Evaluation Report" in report_path.read_text()
