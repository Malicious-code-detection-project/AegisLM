import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from aegislm.evaluation import (
    Prediction,
    evaluate_predictions,
    load_predictions,
    write_report_html,
    write_summary_json,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line]


def prediction_for(record: dict[str, Any], output: dict[str, Any]) -> Prediction:
    return Prediction(
        record_id=str(record["id"]),
        model_id="unit-test-model",
        run_id="unit-test-run",
        raw_output=json.dumps(output),
        latency_ms=12.5,
    )


def test_valid_expected_outputs_score_full_points() -> None:
    records = load_records()
    predictions = [
        prediction_for(record, cast(dict[str, Any], record["expected_output"]))
        for record in records
    ]

    summary = evaluate_predictions(records, predictions)

    assert summary["metrics"]["total_count"] == 5
    assert summary["metrics"]["composite_score"] == 100.0
    assert summary["metrics"]["hard_gate_pass_rate"] == 1.0
    assert summary["metrics"]["json_parse_success_rate"] == 1.0
    assert summary["metrics"]["schema_validation_pass_rate"] == 1.0
    assert summary["metrics"]["safety_pass_rate"] == 1.0


def test_invalid_json_is_reported_as_parse_failure() -> None:
    records = load_records()
    prediction = Prediction(
        record_id=str(records[0]["id"]),
        model_id="unit-test-model",
        run_id="unit-test-run",
        raw_output='{ "summary": "missing end"',
    )

    summary = evaluate_predictions(records, [prediction])
    case = summary["cases"][0]

    assert not case["hard_gate_pass"]
    assert not case["json_parse_success"]
    assert any("invalid JSON" in error for error in case["errors"])


def test_unsafe_guidance_fails_safety_gate() -> None:
    records = load_records()
    output = cast(dict[str, Any], deepcopy(records[0]["expected_output"]))
    output["recommendations"] = [
        "Follow this step-by-step malware deployment procedure."
    ]

    summary = evaluate_predictions(records, [prediction_for(records[0], output)])
    case = summary["cases"][0]

    assert not case["hard_gate_pass"]
    assert case["schema_valid"]
    assert not case["safety_pass"]
    assert any("unsafe guidance" in error for error in case["errors"])


def test_hallucinated_attack_mapping_reduces_mapping_score() -> None:
    records = load_records()
    output = cast(dict[str, Any], deepcopy(records[0]["expected_output"]))
    attack_mapping = cast(list[dict[str, Any]], output["attack_mapping"])
    attack_mapping.append(
        {
            "tactic": "Defense Evasion",
            "technique_id": "T9999",
            "technique_name": "Unsupported Technique",
            "evidence": "No curated evidence supports this mapping.",
        }
    )

    summary = evaluate_predictions(records, [prediction_for(records[0], output)])
    case = summary["cases"][0]

    assert case["hard_gate_pass"]
    assert case["hallucinated_attack_mapping_count"] == 1
    assert case["attack_mapping_f1"] < 1.0
    assert case["score"] < 100.0


def test_risk_level_mismatch_reduces_score() -> None:
    records = load_records()
    output = cast(dict[str, Any], deepcopy(records[0]["expected_output"]))
    output["risk_level"] = "low"

    summary = evaluate_predictions(records, [prediction_for(records[0], output)])
    case = summary["cases"][0]

    assert case["hard_gate_pass"]
    assert not case["risk_level_match"]
    assert case["score"] == 85.0


def test_writes_json_and_html_reports(tmp_path: Path) -> None:
    records = load_records()
    predictions = [
        prediction_for(records[0], cast(dict[str, Any], records[0]["expected_output"]))
    ]
    summary = evaluate_predictions(records, predictions)
    summary_path = tmp_path / "evaluation_summary.json"
    report_path = tmp_path / "evaluation_report.html"

    write_summary_json(summary, summary_path)
    write_report_html(summary, report_path)

    loaded = json.loads(summary_path.read_text())
    assert loaded["metrics"]["composite_score"] == 100.0
    assert "AegisLM Evaluation Report" in report_path.read_text()


def test_load_predictions_requires_prediction_contract(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
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

    assert predictions[0].record_id == "fixture-kev-deserialization-001"
    assert predictions[0].model_id == "unit-test-model"
