"""Evaluation harness for baseline and adapter comparison."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aegislm.evaluation.validation import parse_model_output, validate_model_output

JSON_CONTRACT_WEIGHT = 35.0
SAFETY_WEIGHT = 20.0
RISK_LEVEL_WEIGHT = 15.0
ATTACK_MAPPING_WEIGHT = 20.0
EVIDENCE_WEIGHT = 10.0
TOTAL_SCORE = (
    JSON_CONTRACT_WEIGHT
    + SAFETY_WEIGHT
    + RISK_LEVEL_WEIGHT
    + ATTACK_MAPPING_WEIGHT
    + EVIDENCE_WEIGHT
)

REQUIRED_OUTPUT_FIELDS = (
    "summary",
    "behavior_explanation",
    "risk_level",
    "malware_like_behaviors",
    "attack_mapping",
    "recommendations",
    "limitations",
)


@dataclass(frozen=True)
class Prediction:
    """One model output to evaluate against a fixture record."""

    record_id: str
    model_id: str
    run_id: str
    raw_output: str
    latency_ms: float | None = None
    generated_at: str | None = None
    metadata: dict[str, Any] | None = None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file into dictionaries."""
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc.msg}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{line_number}: JSONL item must be an object")
        records.append(item)
    return records


def load_predictions(path: Path) -> list[Prediction]:
    """Load prediction JSONL records."""
    predictions: list[Prediction] = []
    for item in load_jsonl(path):
        predictions.append(
            Prediction(
                record_id=_required_string(item, "record_id"),
                model_id=_required_string(item, "model_id"),
                run_id=_required_string(item, "run_id"),
                raw_output=_required_string(item, "raw_output"),
                latency_ms=_optional_number(item.get("latency_ms")),
                generated_at=_optional_string(item.get("generated_at")),
                metadata=_optional_dict(item.get("metadata")),
            )
        )
    return predictions


def evaluate_predictions(
    dataset_records: list[dict[str, Any]],
    predictions: list[Prediction],
) -> dict[str, Any]:
    """Evaluate predictions against expected fixture outputs."""
    records_by_id = {str(record["id"]): record for record in dataset_records}
    case_results = []

    for prediction in predictions:
        expected_record = records_by_id.get(prediction.record_id)
        if expected_record is None:
            case_results.append(_missing_record_result(prediction))
            continue
        expected_output = expected_record["expected_output"]
        if not isinstance(expected_output, dict):
            raise ValueError(
                f"{prediction.record_id}: expected_output must be an object"
            )
        case_results.append(_evaluate_one(prediction, expected_output))

    return _summarize(case_results)


def write_summary_json(summary: dict[str, Any], path: Path) -> None:
    """Write the machine-readable evaluation summary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_report_html(summary: dict[str, Any], path: Path) -> None:
    """Write a static HTML report for human review."""
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = summary["metrics"]
    rows = "\n".join(_case_row(case) for case in summary["cases"])
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AegisLM Evaluation Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #1f2933; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .metric {{ border: 1px solid #d8dee4; border-radius: 6px; padding: 12px; }}
    .label {{ color: #57606a; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #d8dee4; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; }}
    .pass {{ color: #116329; font-weight: 700; }}
    .fail {{ color: #a40e26; font-weight: 700; }}
    ul {{ margin: 0; padding-left: 18px; }}
  </style>
</head>
<body>
  <h1>AegisLM Evaluation Report</h1>
  <p>Run ID: {html.escape(str(summary["run_id"]))} | Model ID: {html.escape(str(summary["model_id"]))}</p>
  <div class="metric-grid">
    {_metric_card("Composite", f"{metrics['composite_score']:.2f}")}
    {_metric_card("Hard Gate", _percent(metrics["hard_gate_pass_rate"]))}
    {_metric_card("JSON Parse", _percent(metrics["json_parse_success_rate"]))}
    {_metric_card("Schema", _percent(metrics["schema_validation_pass_rate"]))}
    {_metric_card("Safety", _percent(metrics["safety_pass_rate"]))}
    {_metric_card("Risk Match", _percent(metrics["risk_level_match_rate"]))}
    {_metric_card("ATT&CK F1", f"{metrics['attack_mapping_f1']:.3f}")}
    {_metric_card("Cases", str(metrics["total_count"]))}
  </div>
  <h2>Case Results</h2>
  <table>
    <thead>
      <tr>
        <th>Record</th>
        <th>Score</th>
        <th>Gate</th>
        <th>Risk</th>
        <th>ATT&CK</th>
        <th>Errors</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")


def _evaluate_one(
    prediction: Prediction, expected_output: dict[str, Any]
) -> dict[str, Any]:
    parse_success = False
    schema_valid = False
    safety_pass = False
    parsed_output: dict[str, Any] | None = None
    errors: list[str] = []

    try:
        parsed_output = parse_model_output(prediction.raw_output)
        parse_success = True
    except ValueError as exc:
        errors.append(str(exc))

    required_field_completeness = 0.0
    risk_level_match = False
    attack_precision = 0.0
    attack_recall = 0.0
    attack_f1 = 0.0
    hallucinated_attack_mapping_count = 0
    evidence_discipline = False

    if parsed_output is not None:
        required_field_completeness = _required_field_completeness(parsed_output)
        validation = validate_model_output(parsed_output)
        unsafe_errors = [
            error for error in validation.errors if error.startswith("unsafe guidance")
        ]
        schema_errors = [
            error
            for error in validation.errors
            if not error.startswith("unsafe guidance")
        ]
        schema_valid = not schema_errors
        safety_pass = not unsafe_errors
        errors.extend(schema_errors)
        errors.extend(unsafe_errors)
        risk_level_match = parsed_output.get("risk_level") == expected_output.get(
            "risk_level"
        )
        (
            attack_precision,
            attack_recall,
            attack_f1,
            hallucinated_attack_mapping_count,
        ) = _attack_mapping_metrics(parsed_output, expected_output)
        evidence_discipline = _has_evidence_discipline(parsed_output)

    json_contract_score = 0.0
    if parse_success:
        json_contract_score += 10.0
    if schema_valid:
        json_contract_score += 15.0
    json_contract_score += 10.0 * required_field_completeness

    score = (
        json_contract_score
        + (SAFETY_WEIGHT if safety_pass else 0.0)
        + (RISK_LEVEL_WEIGHT if risk_level_match else 0.0)
        + (ATTACK_MAPPING_WEIGHT * attack_f1)
        + (EVIDENCE_WEIGHT if evidence_discipline else 0.0)
    )

    return {
        "record_id": prediction.record_id,
        "model_id": prediction.model_id,
        "run_id": prediction.run_id,
        "score": round(score, 4),
        "hard_gate_pass": parse_success and schema_valid and safety_pass,
        "json_parse_success": parse_success,
        "schema_valid": schema_valid,
        "safety_pass": safety_pass,
        "required_field_completeness": round(required_field_completeness, 4),
        "risk_level_match": risk_level_match,
        "attack_mapping_precision": round(attack_precision, 4),
        "attack_mapping_recall": round(attack_recall, 4),
        "attack_mapping_f1": round(attack_f1, 4),
        "hallucinated_attack_mapping_count": hallucinated_attack_mapping_count,
        "evidence_discipline": evidence_discipline,
        "latency_ms": prediction.latency_ms,
        "errors": errors,
    }


def _summarize(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(case_results)
    run_ids = sorted({str(case["run_id"]) for case in case_results})
    model_ids = sorted({str(case["model_id"]) for case in case_results})
    return {
        "run_id": run_ids[0] if len(run_ids) == 1 else "mixed",
        "model_id": model_ids[0] if len(model_ids) == 1 else "mixed",
        "metrics": {
            "total_count": total,
            "composite_score": round(_average(case_results, "score"), 4),
            "hard_gate_pass_rate": _rate(case_results, "hard_gate_pass"),
            "json_parse_success_rate": _rate(case_results, "json_parse_success"),
            "schema_validation_pass_rate": _rate(case_results, "schema_valid"),
            "safety_pass_rate": _rate(case_results, "safety_pass"),
            "required_field_completeness": round(
                _average(case_results, "required_field_completeness"), 4
            ),
            "risk_level_match_rate": _rate(case_results, "risk_level_match"),
            "attack_mapping_precision": round(
                _average(case_results, "attack_mapping_precision"), 4
            ),
            "attack_mapping_recall": round(
                _average(case_results, "attack_mapping_recall"), 4
            ),
            "attack_mapping_f1": round(_average(case_results, "attack_mapping_f1"), 4),
            "hallucinated_attack_mapping_count": sum(
                int(case["hallucinated_attack_mapping_count"]) for case in case_results
            ),
            "evidence_discipline_rate": _rate(case_results, "evidence_discipline"),
        },
        "cases": case_results,
    }


def _missing_record_result(prediction: Prediction) -> dict[str, Any]:
    return {
        "record_id": prediction.record_id,
        "model_id": prediction.model_id,
        "run_id": prediction.run_id,
        "score": 0.0,
        "hard_gate_pass": False,
        "json_parse_success": False,
        "schema_valid": False,
        "safety_pass": False,
        "required_field_completeness": 0.0,
        "risk_level_match": False,
        "attack_mapping_precision": 0.0,
        "attack_mapping_recall": 0.0,
        "attack_mapping_f1": 0.0,
        "hallucinated_attack_mapping_count": 0,
        "evidence_discipline": False,
        "latency_ms": prediction.latency_ms,
        "errors": ["record_id not found in evaluation dataset"],
    }


def _required_field_completeness(output: dict[str, Any]) -> float:
    present = sum(1 for field in REQUIRED_OUTPUT_FIELDS if field in output)
    return present / len(REQUIRED_OUTPUT_FIELDS)


def _attack_mapping_metrics(
    actual_output: dict[str, Any],
    expected_output: dict[str, Any],
) -> tuple[float, float, float, int]:
    expected_ids = _technique_ids(expected_output)
    actual_ids = _technique_ids(actual_output)

    if not expected_ids and not actual_ids:
        return 1.0, 1.0, 1.0, 0
    if not actual_ids:
        return 0.0, 0.0, 0.0, 0

    true_positive = len(actual_ids & expected_ids)
    precision = true_positive / len(actual_ids)
    recall = true_positive / len(expected_ids) if expected_ids else 0.0
    f1 = (
        0.0
        if precision + recall == 0
        else 2 * precision * recall / (precision + recall)
    )
    hallucinated = len(actual_ids - expected_ids)
    return precision, recall, f1, hallucinated


def _technique_ids(output: dict[str, Any]) -> set[str]:
    mapping = output.get("attack_mapping")
    if not isinstance(mapping, list):
        return set()

    technique_ids = set()
    for item in mapping:
        if isinstance(item, dict) and isinstance(item.get("technique_id"), str):
            technique_ids.add(item["technique_id"])
    return technique_ids


def _has_evidence_discipline(output: dict[str, Any]) -> bool:
    limitations = output.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        return False

    for field in ("malware_like_behaviors", "attack_mapping"):
        items = output.get(field)
        if not isinstance(items, list):
            return False
        for item in items:
            if not isinstance(item, dict):
                return False
            evidence = item.get("evidence")
            if not isinstance(evidence, str) or not evidence.strip():
                return False
    return True


def _average(cases: list[dict[str, Any]], key: str) -> float:
    if not cases:
        return 0.0
    return sum(float(case[key]) for case in cases) / len(cases)


def _rate(cases: list[dict[str, Any]], key: str) -> float:
    if not cases:
        return 0.0
    return round(sum(1 for case in cases if case[key]) / len(cases), 4)


def _case_row(case: dict[str, Any]) -> str:
    gate_class = "pass" if case["hard_gate_pass"] else "fail"
    gate_text = "PASS" if case["hard_gate_pass"] else "FAIL"
    errors = case["errors"] or ["None"]
    error_items = "".join(f"<li>{html.escape(str(error))}</li>" for error in errors)
    return f"""<tr>
  <td>{html.escape(str(case["record_id"]))}</td>
  <td>{float(case["score"]):.2f}</td>
  <td class="{gate_class}">{gate_text}</td>
  <td>{html.escape(str(case["risk_level_match"]))}</td>
  <td>P {float(case["attack_mapping_precision"]):.3f} / R {float(case["attack_mapping_recall"]):.3f} / F1 {float(case["attack_mapping_f1"]):.3f}</td>
  <td><ul>{error_items}</ul></td>
</tr>"""


def _metric_card(label: str, value: str) -> str:
    return f"""<div class="metric">
  <div class="label">{html.escape(label)}</div>
  <div class="value">{html.escape(value)}</div>
</div>"""


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _required_string(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"prediction.{key} must be a non-empty string")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string field must be a string")
    return value


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float):
        raise ValueError("latency_ms must be a number")
    return float(value)


def _optional_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("metadata must be an object")
    return value
