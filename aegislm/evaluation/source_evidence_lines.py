"""Evaluation for assessment-conditioned source evidence line selection."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from aegislm.datasets.source_evidence_lines import (
    render_assessment_from_evidence_lines,
    validate_evidence_lines_output,
)
from aegislm.evaluation.harness import Prediction


@dataclass(frozen=True)
class SourceEvidenceThresholds:
    minimum_sample_count: int = 100
    minimum_parse_success_rate: float = 0.99
    minimum_schema_pass_rate: float = 0.99
    minimum_evidence_precision: float = 0.50
    minimum_evidence_recall: float = 0.50
    minimum_renderer_pass_rate: float = 1.00


def evaluate_source_evidence_predictions(
    challenge_rows: list[dict[str, Any]],
    gold_rows: list[dict[str, Any]],
    private_records: list[dict[str, Any]],
    predictions: list[Prediction],
    *,
    thresholds: SourceEvidenceThresholds | None = None,
    blind_test_used: bool = False,
) -> dict[str, Any]:
    """Evaluate line-level evidence overlap and deterministic rendering."""
    active = thresholds or SourceEvidenceThresholds()
    challenge = _index_rows(challenge_rows, "challenge")
    gold = _index_rows(gold_rows, "gold")
    records = _index_rows(private_records, "private records")
    if set(challenge) != set(gold) or set(challenge) != set(records):
        raise ValueError("evidence challenge, gold, and private record ids differ")
    predicted = _index_predictions(predictions)
    cases = [
        _evaluate_case(
            record_id,
            challenge[record_id],
            gold[record_id],
            records[record_id],
            predicted.get(record_id),
        )
        for record_id in challenge
    ]
    evidence_tp = sum(case["evidence_true_positive_count"] for case in cases)
    evidence_predicted = sum(case["evidence_predicted_count"] for case in cases)
    evidence_gold = sum(case["evidence_gold_count"] for case in cases)
    evidence_precision = _ratio(evidence_tp, evidence_predicted)
    evidence_recall = _ratio(evidence_tp, evidence_gold)
    metrics = {
        "total_count": len(cases),
        "missing_prediction_count": sum(case["missing"] for case in cases),
        "extra_prediction_count": len(set(predicted) - set(gold)),
        "parse_success_rate": _rate(cases, "parse_success"),
        "schema_pass_rate": _rate(cases, "schema_valid"),
        "renderer_pass_rate": _rate(cases, "renderer_valid"),
        "evidence_precision": round(evidence_precision, 4),
        "evidence_recall": round(evidence_recall, 4),
        "evidence_f1": round(
            _ratio(
                2 * evidence_precision * evidence_recall,
                evidence_precision + evidence_recall,
            ),
            4,
        ),
        "latency_p50_ms": _latency(cases, 0.50),
        "latency_p95_ms": _latency(cases, 0.95),
    }
    gates = {
        "minimum_sample_count": len(cases) >= active.minimum_sample_count,
        "complete_prediction_set": (
            metrics["missing_prediction_count"] == 0
            and metrics["extra_prediction_count"] == 0
        ),
        "minimum_parse_success_rate": (
            metrics["parse_success_rate"] >= active.minimum_parse_success_rate
        ),
        "minimum_schema_pass_rate": (
            metrics["schema_pass_rate"] >= active.minimum_schema_pass_rate
        ),
        "minimum_evidence_precision": (
            evidence_precision >= active.minimum_evidence_precision
        ),
        "minimum_evidence_recall": evidence_recall >= active.minimum_evidence_recall,
        "minimum_renderer_pass_rate": (
            metrics["renderer_pass_rate"] >= active.minimum_renderer_pass_rate
        ),
    }
    model_ids = sorted({item.model_id for item in predictions})
    run_ids = sorted({item.run_id for item in predictions})
    return {
        "evaluation_type": (
            "source_evidence_lines_blind"
            if blind_test_used
            else "diagnostic_source_evidence_lines"
        ),
        "diagnostic_only": not blind_test_used,
        "blind_test_used": blind_test_used,
        "gold_assessment_conditioned": True,
        "overall_pass": all(gates.values()),
        "model_id": model_ids[0] if len(model_ids) == 1 else "mixed",
        "run_id": run_ids[0] if len(run_ids) == 1 else "mixed",
        "thresholds": asdict(active),
        "gates": gates,
        "metrics": metrics,
        "cases": cases,
    }


def write_source_evidence_summary(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _evaluate_case(
    record_id: str,
    challenge: dict[str, Any],
    gold: dict[str, Any],
    record: dict[str, Any],
    prediction: Prediction | None,
) -> dict[str, Any]:
    assessment, target_cwe, line_count = _prompt_condition(challenge)
    code = record.get("code")
    if not isinstance(code, dict) or not isinstance(code.get("text"), str):
        raise ValueError(f"{record_id}: private source code is invalid")
    source_code = str(code["text"])
    if len(source_code.splitlines()) != line_count:
        raise ValueError(f"{record_id}: numbered source and private code differ")
    expected = gold.get("expected_output")
    if not isinstance(expected, dict):
        raise ValueError(f"{record_id}: evidence gold is invalid")
    expected_errors = validate_evidence_lines_output(
        expected,
        line_count=line_count,
    )
    if expected_errors:
        raise ValueError(f"{record_id}: invalid evidence gold: {expected_errors}")
    gold_lines = _range_lines(expected)
    case: dict[str, Any] = {
        "record_id": record_id,
        "assessment_condition": assessment,
        "missing": prediction is None,
        "parse_success": False,
        "schema_valid": False,
        "renderer_valid": False,
        "evidence_true_positive_count": 0,
        "evidence_predicted_count": 0,
        "evidence_gold_count": len(gold_lines),
        "latency_ms": prediction.latency_ms if prediction is not None else None,
        "errors": [],
    }
    if prediction is None:
        case["errors"].append("prediction missing")
        return case
    try:
        output = json.loads(prediction.raw_output)
    except json.JSONDecodeError as exc:
        case["errors"].append(f"invalid JSON: {exc.msg}")
        return case
    if not isinstance(output, dict):
        case["errors"].append("output must be a JSON object")
        return case
    case["parse_success"] = True
    errors = validate_evidence_lines_output(output, line_count=line_count)
    if errors:
        case["errors"].extend(errors)
        return case
    case["schema_valid"] = True
    predicted_lines = _range_lines(output)
    case["evidence_true_positive_count"] = len(gold_lines & predicted_lines)
    case["evidence_predicted_count"] = len(predicted_lines)
    try:
        render_assessment_from_evidence_lines(
            output,
            assessment=assessment,
            target_cwe=target_cwe,
            source_code=source_code,
        )
    except ValueError as exc:
        case["errors"].append(f"renderer failed: {exc}")
        return case
    case["renderer_valid"] = True
    return case


def _prompt_condition(row: dict[str, Any]) -> tuple[Any, str, int]:
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) != 2:
        raise ValueError(f"{row.get('id')}: invalid evidence challenge")
    user = messages[1]
    if not isinstance(user, dict) or not isinstance(user.get("content"), str):
        raise ValueError(f"{row.get('id')}: invalid evidence user message")
    content = str(user["content"])
    start = content.find("{")
    if start < 0:
        raise ValueError(f"{row.get('id')}: evidence prompt JSON missing")
    payload, _ = json.JSONDecoder().raw_decode(content[start:])
    if not isinstance(payload, dict) or not isinstance(payload.get("scope"), dict):
        raise ValueError(f"{row.get('id')}: evidence prompt scope missing")
    assessment = payload.get("assessment")
    target_cwe = payload["scope"].get("target_cwe")
    numbered = payload.get("numbered_source_code")
    if (
        assessment not in {"present", "not_observed"}
        or not isinstance(target_cwe, str)
        or not isinstance(numbered, str)
    ):
        raise ValueError(f"{row.get('id')}: evidence condition is invalid")
    return assessment, target_cwe, len(numbered.splitlines())


def _range_lines(output: dict[str, Any]) -> set[int]:
    lines: set[int] = set()
    for item in output["evidence_ranges"]:
        lines.update(range(int(item["start_line"]), int(item["end_line"]) + 1))
    return lines


def _index_rows(
    rows: list[dict[str, Any]],
    name: str,
) -> dict[str, dict[str, Any]]:
    indexed = {str(row["id"]): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"evidence {name} contains duplicate ids")
    return indexed


def _index_predictions(predictions: list[Prediction]) -> dict[str, Prediction]:
    indexed: dict[str, Prediction] = {}
    for prediction in predictions:
        if prediction.record_id in indexed:
            raise ValueError(f"duplicate prediction record_id: {prediction.record_id}")
        indexed[prediction.record_id] = prediction
    return indexed


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _rate(cases: list[dict[str, Any]], key: str) -> float:
    return round(_ratio(sum(bool(case[key]) for case in cases), len(cases)), 4)


def _latency(cases: list[dict[str, Any]], percentile: float) -> float | None:
    values = sorted(
        float(case["latency_ms"]) for case in cases if case["latency_ms"] is not None
    )
    if not values:
        return None
    index = max(0, min(len(values) - 1, int((len(values) - 1) * percentile)))
    return round(values[index], 4)
