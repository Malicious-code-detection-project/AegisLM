"""Evaluation for the diagnostic source decision-only contract."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from aegislm.evaluation.harness import Prediction

_ALLOWED = frozenset({"present", "not_observed", "uncertain"})


@dataclass(frozen=True)
class SourceDecisionThresholds:
    minimum_sample_count: int = 20
    minimum_precision: float = 0.75
    minimum_recall: float = 0.75
    maximum_false_positive_rate: float = 0.20
    maximum_abstention_rate: float = 0.10
    minimum_parse_success_rate: float = 0.99
    minimum_schema_pass_rate: float = 0.99


def evaluate_source_decisions(
    gold_rows: list[dict[str, Any]],
    predictions: list[Prediction],
    *,
    thresholds: SourceDecisionThresholds | None = None,
    blind_test_used: bool = False,
) -> dict[str, Any]:
    active = thresholds or SourceDecisionThresholds()
    gold = {str(row["id"]): _gold_assessment(row) for row in gold_rows}
    predicted = _index_predictions(predictions)
    cases = [
        _case(record_id, label, predicted.get(record_id))
        for record_id, label in gold.items()
    ]
    positives = sum(case["gold"] == "present" for case in cases)
    negatives = sum(case["gold"] == "not_observed" for case in cases)
    tp = sum(
        case["gold"] == "present" and case["assessment"] == "present" for case in cases
    )
    fp = sum(
        case["gold"] == "not_observed" and case["assessment"] == "present"
        for case in cases
    )
    tn = sum(
        case["gold"] == "not_observed" and case["assessment"] == "not_observed"
        for case in cases
    )
    fn = positives - tp
    abstentions = sum(
        case["assessment"] not in {"present", "not_observed"} for case in cases
    )
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, positives)
    fpr = _ratio(fp, negatives)
    metrics = {
        "total_count": len(cases),
        "true_positive_count": tp,
        "false_positive_count": fp,
        "true_negative_count": tn,
        "false_negative_count": fn,
        "missing_prediction_count": sum(case["missing"] for case in cases),
        "extra_prediction_count": len(set(predicted) - set(gold)),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "false_positive_rate": round(fpr, 4),
        "abstention_rate": round(_ratio(abstentions, len(cases)), 4),
        "parse_success_rate": _rate(cases, "parse_success"),
        "schema_pass_rate": _rate(cases, "schema_valid"),
        "latency_p50_ms": _latency(cases, 0.50),
        "latency_p95_ms": _latency(cases, 0.95),
    }
    gates = {
        "minimum_sample_count": len(cases) >= active.minimum_sample_count,
        "complete_prediction_set": (
            metrics["missing_prediction_count"] == 0
            and metrics["extra_prediction_count"] == 0
        ),
        "both_binary_labels_present": tp + fp > 0 and tn + fn > 0,
        "minimum_precision": precision >= active.minimum_precision,
        "minimum_recall": recall >= active.minimum_recall,
        "maximum_false_positive_rate": fpr <= active.maximum_false_positive_rate,
        "maximum_abstention_rate": (
            metrics["abstention_rate"] <= active.maximum_abstention_rate
        ),
        "minimum_parse_success_rate": (
            metrics["parse_success_rate"] >= active.minimum_parse_success_rate
        ),
        "minimum_schema_pass_rate": (
            metrics["schema_pass_rate"] >= active.minimum_schema_pass_rate
        ),
    }
    model_ids = sorted({item.model_id for item in predictions})
    run_ids = sorted({item.run_id for item in predictions})
    return {
        "evaluation_type": (
            "source_decision_blind_challenge"
            if blind_test_used
            else "diagnostic_source_decision_challenge"
        ),
        "diagnostic_only": not blind_test_used,
        "blind_test_used": blind_test_used,
        "overall_pass": all(gates.values()),
        "model_id": model_ids[0] if len(model_ids) == 1 else "mixed",
        "run_id": run_ids[0] if len(run_ids) == 1 else "mixed",
        "thresholds": asdict(active),
        "gates": gates,
        "metrics": metrics,
        "cases": cases,
    }


def write_source_decision_summary(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _gold_assessment(row: dict[str, Any]) -> str:
    expected = row.get("expected_output")
    if not isinstance(expected, dict) or expected.get("assessment") not in {
        "present",
        "not_observed",
    }:
        raise ValueError(f"{row.get('id')}: invalid decision gold")
    return str(expected["assessment"])


def _index_predictions(predictions: list[Prediction]) -> dict[str, Prediction]:
    indexed: dict[str, Prediction] = {}
    for prediction in predictions:
        if prediction.record_id in indexed:
            raise ValueError(f"duplicate prediction record_id: {prediction.record_id}")
        indexed[prediction.record_id] = prediction
    return indexed


def _case(
    record_id: str,
    gold: str,
    prediction: Prediction | None,
) -> dict[str, Any]:
    case: dict[str, Any] = {
        "record_id": record_id,
        "gold": gold,
        "assessment": None,
        "missing": prediction is None,
        "parse_success": False,
        "schema_valid": False,
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
    if set(output) != {"assessment"} or output.get("assessment") not in _ALLOWED:
        case["errors"].append("output must contain only one valid assessment")
        return case
    case["schema_valid"] = True
    case["assessment"] = output["assessment"]
    return case


def _ratio(numerator: int, denominator: int) -> float:
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
