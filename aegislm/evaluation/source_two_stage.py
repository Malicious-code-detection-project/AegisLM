"""End-to-end evaluation for decision then evidence source assessment."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aegislm.evaluation.harness import Prediction
from aegislm.evaluation.source_decision import (
    SourceDecisionThresholds,
    evaluate_source_decisions,
)
from aegislm.evaluation.source_evidence_lines import (
    SourceEvidenceThresholds,
    evaluate_source_evidence_predictions,
)


@dataclass(frozen=True)
class SourceTwoStageThresholds:
    minimum_sample_count: int = 100
    minimum_precision: float = 0.90
    minimum_recall: float = 0.95
    maximum_false_positive_rate: float = 0.05
    maximum_abstention_rate: float = 0.05
    minimum_parse_success_rate: float = 0.99
    minimum_schema_pass_rate: float = 0.99
    minimum_evidence_precision: float = 0.50
    minimum_evidence_recall: float = 0.50
    minimum_renderer_pass_rate: float = 1.00


def evaluate_source_two_stage_predictions(
    decision_gold_rows: list[dict[str, Any]],
    decision_predictions: list[Prediction],
    evidence_challenge_rows: list[dict[str, Any]],
    evidence_gold_rows: list[dict[str, Any]],
    private_records: list[dict[str, Any]],
    evidence_predictions: list[Prediction],
    *,
    thresholds: SourceTwoStageThresholds | None = None,
    blind_test_used: bool = False,
) -> dict[str, Any]:
    """Apply absolute decision gates plus evidence and renderer gates."""
    active = thresholds or SourceTwoStageThresholds()
    decision = evaluate_source_decisions(
        decision_gold_rows,
        decision_predictions,
        thresholds=SourceDecisionThresholds(
            minimum_sample_count=active.minimum_sample_count,
            minimum_precision=active.minimum_precision,
            minimum_recall=active.minimum_recall,
            maximum_false_positive_rate=active.maximum_false_positive_rate,
            maximum_abstention_rate=active.maximum_abstention_rate,
            minimum_parse_success_rate=active.minimum_parse_success_rate,
            minimum_schema_pass_rate=active.minimum_schema_pass_rate,
        ),
        blind_test_used=blind_test_used,
    )
    evidence = evaluate_source_evidence_predictions(
        evidence_challenge_rows,
        evidence_gold_rows,
        private_records,
        evidence_predictions,
        thresholds=SourceEvidenceThresholds(
            minimum_sample_count=active.minimum_sample_count,
            minimum_parse_success_rate=active.minimum_parse_success_rate,
            minimum_schema_pass_rate=active.minimum_schema_pass_rate,
            minimum_evidence_precision=active.minimum_evidence_precision,
            minimum_evidence_recall=active.minimum_evidence_recall,
            minimum_renderer_pass_rate=active.minimum_renderer_pass_rate,
        ),
        blind_test_used=blind_test_used,
    )
    combined_latencies = _combined_latencies(
        decision["cases"],
        evidence["cases"],
    )
    gates = {
        "decision_absolute_gate": bool(decision["overall_pass"]),
        "evidence_gate": bool(evidence["overall_pass"]),
    }
    return {
        "evaluation_type": (
            "source_two_stage_blind_end_to_end"
            if blind_test_used
            else "diagnostic_source_two_stage_end_to_end"
        ),
        "diagnostic_only": not blind_test_used,
        "blind_test_used": blind_test_used,
        "overall_pass": all(gates.values()),
        "gates": gates,
        "decision": decision,
        "evidence": evidence,
        "pipeline_latency_p50_ms": _percentile(combined_latencies, 0.50),
        "pipeline_latency_p95_ms": _percentile(combined_latencies, 0.95),
    }


def write_source_two_stage_summary(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _combined_latencies(
    decision_cases: list[dict[str, Any]],
    evidence_cases: list[dict[str, Any]],
) -> list[float]:
    decision = {
        str(case["record_id"]): case.get("latency_ms") for case in decision_cases
    }
    evidence = {
        str(case["record_id"]): case.get("latency_ms") for case in evidence_cases
    }
    if set(decision) != set(evidence):
        raise ValueError("decision and evidence case ids differ")
    combined: list[float] = []
    for record_id, decision_latency in decision.items():
        evidence_latency = evidence[record_id]
        if decision_latency is None or evidence_latency is None:
            continue
        combined.append(float(decision_latency) + float(evidence_latency))
    return sorted(combined)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, int((len(values) - 1) * percentile)))
    return round(values[index], 4)
