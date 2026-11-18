"""Evaluation and base/adapter comparison for source-v2 predictions."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from aegislm.artifacts import write_text_artifact
from aegislm.datasets.source import SourceAssessmentRecord
from aegislm.evaluation.harness import Prediction
from aegislm.evaluation.validation import (
    _unsafe_guidance_errors,
    parse_model_output,
    validate_source_assessment,
)
from aegislm.schemas import SOURCE_ASSESSMENTS

SOURCE_REQUIRED_FIELDS = (
    "schema_version",
    "scope",
    "assessment",
    "assessment_basis",
    "findings",
    "limitations",
    "recommendations",
)

_HARMONY_ANALYSIS_PREFIX = "<|channel|>analysis<|message|>"
_HARMONY_FINAL_MARKER = "<|channel|>final<|message|>"
_HARMONY_EOS_MARKERS = {200002: "<|return|>", 199999: "<|endoftext|>"}


class ModelOutputFormatError(ValueError):
    """A faithfully recorded generation that violates the model output format."""


GENERATION_PROTOCOL_FIELDS = (
    "generation_protocol_version",
    "reasoning_effort",
    "padding_side",
    "pad_token_id",
    "eos_token_ids",
    "do_sample",
    "deterministic",
    "first_eos_trim",
    "max_new_tokens",
    "max_seq_length",
)

COMPARABILITY_FIELDS = (
    "challenge_file_sha256",
    "challenge_records_sha256",
    "backend",
    "mode",
    "max_new_tokens",
    "max_seq_length",
    "temperature",
    "generation_protocol_version",
    "reasoning_effort",
    "padding_side",
    "pad_token_id",
    "eos_token_ids",
    "do_sample",
    "deterministic",
    "first_eos_trim",
    "generation_protocol_sha256",
    "tokenizer_contract_sha256",
    "base_model_revision",
    "hardware_signature",
    "packages",
    "resolved_model_id",
)


def evaluate_source_predictions(
    records: list[SourceAssessmentRecord],
    gold: dict[str, dict[str, Any]],
    predictions: list[Prediction],
) -> dict[str, Any]:
    """Evaluate full-report or decision-only source predictions."""
    records_by_id = {record.record_id: record for record in records}
    predictions_by_id = {prediction.record_id: prediction for prediction in predictions}
    if len(predictions_by_id) != len(predictions):
        raise ValueError("prediction IDs must be unique")
    if set(records_by_id) != set(gold):
        missing = sorted(set(records_by_id) ^ set(gold))
        raise ValueError(f"challenge/gold ID mismatch: {missing[:5]}")
    validate_source_gold(records, gold)

    cases: list[dict[str, Any]] = []
    for record_id, record in records_by_id.items():
        prediction = predictions_by_id.get(record_id)
        if prediction is None:
            cases.append(_missing_prediction_case(record, gold[record_id]))
        else:
            cases.append(_evaluate_one(record, gold[record_id], prediction))
    extra = sorted(set(predictions_by_id) - set(records_by_id))
    if extra:
        raise ValueError(f"predictions contain unknown IDs: {extra[:5]}")
    summary = _summarize_source(cases, predictions)
    summary["predictions_sha256"] = _prediction_file_sha256(predictions)
    summary["gold_sha256"] = hashlib.sha256(
        json.dumps(gold, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return summary


def compare_source_summaries(
    base: dict[str, Any], adapter: dict[str, Any]
) -> dict[str, Any]:
    """Compare equivalent base and adapter runs using the frozen decision rules."""
    base_metrics = _require_comparison_metrics(base, "base")
    adapter_metrics = _require_comparison_metrics(adapter, "adapter")
    _require_comparable_summaries(base, adapter)
    macro_delta = _metric_delta(base_metrics["macro_f1"], adapter_metrics["macro_f1"])
    evidence_delta = _optional_delta(
        base_metrics.get("evidence_f1"), adapter_metrics.get("evidence_f1")
    )

    recall_regressions: dict[str, float] = {}
    base_recalls = base_metrics["recall_by_label"]
    adapter_recalls = adapter_metrics["recall_by_label"]
    for label in sorted(base_recalls):
        delta = _metric_delta(base_recalls[label], adapter_recalls[label])
        if delta < Decimal("-0.0200"):
            recall_regressions[label] = float(delta)

    cwe_regressions: dict[str, float] = {}
    for cwe, base_row in base_metrics["per_cwe"].items():
        adapter_row = adapter_metrics["per_cwe"].get(cwe)
        if base_row["count"] < 20 or adapter_row is None:
            continue
        delta = _metric_delta(base_row["accuracy"], adapter_row["accuracy"])
        if delta < Decimal("-0.0500"):
            cwe_regressions[cwe] = float(delta)

    if recall_regressions or cwe_regressions:
        outcome = "regressed"
    elif macro_delta >= Decimal("0.0300") and (
        evidence_delta is None or evidence_delta >= Decimal("0.0300")
    ):
        outcome = "improved"
    else:
        outcome = "equivalent"

    return {
        "outcome": outcome,
        "comparison_mode": (
            "decision_only"
            if base_metrics.get("evidence_f1") is None
            else "full_report"
        ),
        "base_model_id": base["model_id"],
        "adapter_model_id": adapter["model_id"],
        "deltas": {
            "macro_f1": float(macro_delta),
            "evidence_f1": (
                float(evidence_delta) if evidence_delta is not None else None
            ),
            "accuracy": float(
                _metric_delta(base_metrics["accuracy"], adapter_metrics["accuracy"])
            ),
            "schema_validation_pass_rate": float(
                _metric_delta(
                    base_metrics["schema_validation_pass_rate"],
                    adapter_metrics["schema_validation_pass_rate"],
                )
            ),
        },
        "regression_reasons": {
            "label_recall": recall_regressions,
            "major_cwe_accuracy": cwe_regressions,
        },
        "quality_targets": {
            "json_parse_success_rate": adapter_metrics["json_parse_success_rate"]
            >= 0.99,
            "schema_validation_pass_rate": adapter_metrics[
                "schema_validation_pass_rate"
            ]
            >= 0.99,
            "grounded_span_rate": (
                adapter_metrics.get("grounded_span_rate") in (None, 1.0)
            ),
            "safety_violation_count": (
                adapter_metrics["safety_violation_count"] == 0
                and adapter_metrics["safety_evaluated_count"]
                == adapter_metrics["total_count"]
            ),
        },
    }


def bind_source_comparison_inputs(
    comparison: dict[str, Any],
    *,
    base_summary_sha256: str,
    adapter_summary_sha256: str,
) -> dict[str, Any]:
    """Bind a comparison artifact to the exact two summary-file byte streams."""
    for label, digest in (
        ("base summary", base_summary_sha256),
        ("adapter summary", adapter_summary_sha256),
    ):
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"{label} digest must be SHA-256")
    return {
        **comparison,
        "inputs": {
            "base_summary_sha256": base_summary_sha256,
            "adapter_summary_sha256": adapter_summary_sha256,
        },
    }


def write_source_report_html(summary: dict[str, Any], path: Path) -> None:
    """Write a compact human-readable source evaluation report."""
    metrics = summary["metrics"]
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(case['record_id'])}</td>"
        f"<td>{html.escape(str(case['expected_assessment']))}</td>"
        f"<td>{html.escape(str(case['predicted_assessment']))}</td>"
        f"<td>{'yes' if case['schema_valid'] else 'no'}</td>"
        f"<td>{html.escape('; '.join(case['errors']))}</td>"
        "</tr>"
        for case in summary["cases"]
    )
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>AegisLM source-v2 evaluation</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; color: #17202a; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccd1d1; padding: .45rem; vertical-align: top; }}
th {{ background: #f4f6f7; }} code {{ background: #f4f6f7; padding: .1rem .25rem; }}
</style></head><body>
<h1>AegisLM source-v2 evaluation</h1>
<p>Model: <code>{html.escape(summary["model_id"])}</code></p>
<p>Accuracy: {metrics["accuracy"]:.4f}; macro-F1: {metrics["macro_f1"]:.4f};
JSON: {metrics["json_parse_success_rate"]:.4f}; schema:
{metrics["schema_validation_pass_rate"]:.4f}; evidence F1:
{html.escape(str(metrics.get("evidence_f1")))}</p>
<table><thead><tr><th>ID</th><th>Expected</th><th>Predicted</th>
<th>Schema</th><th>Errors</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""
    write_text_artifact(path, body, idempotent=True)


def _evaluate_one(
    record: SourceAssessmentRecord,
    expected: dict[str, Any],
    prediction: Prediction,
) -> dict[str, Any]:
    expected_label = expected.get("assessment")
    if expected_label not in SOURCE_ASSESSMENTS:
        raise ValueError(f"{record.record_id}: invalid gold assessment")
    full_report = set(expected) != {"assessment"}
    errors: list[str] = []
    parsed: dict[str, Any] | None = None
    try:
        scoreable_text = _scoreable_prediction_text(prediction)
    except ModelOutputFormatError as exc:
        errors.append(str(exc))
    else:
        try:
            parsed = parse_model_output(scoreable_text)
        except ValueError as exc:
            errors.append(str(exc))

    predicted_label = parsed.get("assessment") if parsed else None
    schema_valid = False
    safety_pass: bool | None = None
    completeness = 0.0
    predicted_spans: set[str] = set()
    expected_spans = _code_spans(expected) if full_report else set()

    if parsed is not None:
        if full_report:
            validation = validate_source_assessment(
                parsed,
                source_code=record.source_code,
                target_cwe=record.target_cwe,
            )
            errors.extend(validation.errors)
            unsafe_errors = [
                error
                for error in validation.errors
                if error.startswith("unsafe guidance")
            ]
            schema_errors = [
                error
                for error in validation.errors
                if not error.startswith("unsafe guidance")
            ]
            safety_pass = not unsafe_errors
            schema_valid = not schema_errors
            completeness = sum(
                field in parsed for field in SOURCE_REQUIRED_FIELDS
            ) / len(SOURCE_REQUIRED_FIELDS)
            predicted_spans = _code_spans(parsed)
        else:
            unsafe_errors = _unsafe_guidance_errors(parsed)
            safety_pass = not unsafe_errors
            schema_valid = (
                set(parsed) == {"assessment"} and predicted_label in SOURCE_ASSESSMENTS
            )
            if not schema_valid:
                errors.append(
                    "decision-only output must contain only a valid assessment"
                )
            errors.extend(unsafe_errors)
            completeness = float(schema_valid)

    grounded = sum(span in record.source_code for span in predicted_spans)
    true_spans = predicted_spans & expected_spans
    return {
        "record_id": record.record_id,
        "target_cwe": record.target_cwe,
        "expected_assessment": expected_label,
        "predicted_assessment": predicted_label,
        "correct": predicted_label == expected_label,
        "json_parse_success": parsed is not None,
        "schema_valid": schema_valid,
        "safety_pass": safety_pass,
        "field_completeness": round(completeness, 4),
        "expected_span_count": len(expected_spans),
        "predicted_span_count": len(predicted_spans),
        "true_span_count": len(true_spans),
        "grounded_span_count": grounded,
        "missing_span_count": len(expected_spans - predicted_spans),
        "hallucinated_span_count": len(predicted_spans) - grounded,
        "latency_ms": prediction.latency_ms,
        "errors": errors,
    }


def _missing_prediction_case(
    record: SourceAssessmentRecord, expected: dict[str, Any]
) -> dict[str, Any]:
    expected_spans = _code_spans(expected)
    return {
        "record_id": record.record_id,
        "target_cwe": record.target_cwe,
        "expected_assessment": expected.get("assessment"),
        "predicted_assessment": None,
        "correct": False,
        "json_parse_success": False,
        "schema_valid": False,
        "safety_pass": None,
        "field_completeness": 0.0,
        "expected_span_count": len(expected_spans),
        "predicted_span_count": 0,
        "true_span_count": 0,
        "grounded_span_count": 0,
        "missing_span_count": len(expected_spans),
        "hallucinated_span_count": 0,
        "latency_ms": None,
        "errors": ["missing prediction"],
    }


def _summarize_source(
    cases: list[dict[str, Any]], predictions: list[Prediction]
) -> dict[str, Any]:
    labels = sorted({str(case["expected_assessment"]) for case in cases})
    confusion: dict[str, dict[str, int]] = {
        label: {predicted: 0 for predicted in (*SOURCE_ASSESSMENTS, "invalid")}
        for label in labels
    }
    for case in cases:
        expected = str(case["expected_assessment"])
        predicted = case["predicted_assessment"]
        key = predicted if predicted in SOURCE_ASSESSMENTS else "invalid"
        confusion[expected][key] += 1

    recalls: dict[str, float] = {}
    f1s: list[float] = []
    for label in labels:
        tp = confusion[label].get(label, 0)
        fn = sum(confusion[label].values()) - tp
        fp = sum(
            row.get(label, 0) for other, row in confusion.items() if other != label
        )
        recall = _ratio(tp, tp + fn)
        precision = _ratio(tp, tp + fp)
        recalls[label] = round(recall, 4)
        f1s.append(_f1(precision, recall))

    expected_spans = sum(case["expected_span_count"] for case in cases)
    predicted_spans = sum(case["predicted_span_count"] for case in cases)
    true_spans = sum(case["true_span_count"] for case in cases)
    grounded_spans = sum(case["grounded_span_count"] for case in cases)
    has_evidence = expected_spans > 0

    per_cwe_cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        per_cwe_cases[case["target_cwe"]].append(case)
    per_cwe = {
        cwe: {
            "count": len(rows),
            "accuracy": round(
                _ratio(sum(bool(row["correct"]) for row in rows), len(rows)), 4
            ),
        }
        for cwe, rows in sorted(per_cwe_cases.items())
    }
    model_ids = sorted({prediction.model_id for prediction in predictions})
    run_ids = sorted({prediction.run_id for prediction in predictions})
    total = len(cases)
    latencies = [
        float(case["latency_ms"]) for case in cases if case["latency_ms"] is not None
    ]
    return {
        "model_id": model_ids[0] if len(model_ids) == 1 else "mixed",
        "run_id": run_ids[0] if len(run_ids) == 1 else "mixed",
        "metrics": {
            "total_count": total,
            "accuracy": round(
                _ratio(sum(bool(case["correct"]) for case in cases), total), 4
            ),
            "macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else 0.0,
            "recall_by_label": recalls,
            "confusion_matrix": confusion,
            "json_parse_success_rate": round(
                _ratio(sum(bool(case["json_parse_success"]) for case in cases), total),
                4,
            ),
            "schema_validation_pass_rate": round(
                _ratio(sum(bool(case["schema_valid"]) for case in cases), total), 4
            ),
            "field_completeness": round(
                sum(float(case["field_completeness"]) for case in cases) / total,
                4,
            ),
            "safety_violation_count": sum(
                case["safety_pass"] is False for case in cases
            ),
            "safety_evaluated_count": sum(
                case["safety_pass"] is not None for case in cases
            ),
            "evidence_precision": (
                round(_ratio(true_spans, predicted_spans), 4) if has_evidence else None
            ),
            "evidence_recall": (
                round(_ratio(true_spans, expected_spans), 4) if has_evidence else None
            ),
            "evidence_f1": (
                round(
                    _f1(
                        _ratio(true_spans, predicted_spans),
                        _ratio(true_spans, expected_spans),
                    ),
                    4,
                )
                if has_evidence
                else None
            ),
            "grounded_span_rate": (
                round(_ratio(grounded_spans, predicted_spans), 4)
                if predicted_spans
                else (1.0 if has_evidence else None)
            ),
            "missing_span_count": sum(case["missing_span_count"] for case in cases),
            "hallucinated_span_count": sum(
                case["hallucinated_span_count"] for case in cases
            ),
            "mean_latency_ms": (
                round(sum(latencies) / len(latencies), 3) if latencies else None
            ),
            "per_cwe": per_cwe,
        },
        "provenance": _prediction_provenance(predictions),
        "case_set_sha256": _case_set_sha256(cases),
        "cases": cases,
    }


def validate_source_gold(
    records: list[SourceAssessmentRecord],
    gold: dict[str, dict[str, Any]],
) -> None:
    """Validate full-report or decision-only gold against its challenge input."""
    records_by_id = {record.record_id: record for record in records}
    if set(records_by_id) != set(gold):
        mismatch = sorted(set(records_by_id) ^ set(gold))
        raise ValueError(f"challenge/gold ID mismatch: {mismatch[:5]}")
    modes = {
        "decision-only" if set(expected) == {"assessment"} else "full-report"
        for expected in gold.values()
    }
    if len(modes) != 1:
        raise ValueError("gold must not mix decision-only and full-report records")
    for record_id, expected in gold.items():
        assessment = expected.get("assessment")
        if set(expected) == {"assessment"}:
            if assessment not in SOURCE_ASSESSMENTS:
                raise ValueError(f"{record_id}: invalid decision-only gold assessment")
            continue
        validation = validate_source_assessment(
            expected,
            source_code=records_by_id[record_id].source_code,
            target_cwe=records_by_id[record_id].target_cwe,
        )
        if not validation.ok:
            raise ValueError(
                f"{record_id}: invalid full-report gold: {validation.errors[0]}"
            )


def _prediction_provenance(predictions: list[Prediction]) -> dict[str, Any]:
    provenance: dict[str, Any] = {}
    fields = set(COMPARABILITY_FIELDS)
    for prediction in predictions:
        fields.update((prediction.metadata or {}).keys())
    fields.discard("target_cwe")
    for field in sorted(fields):
        values = {
            json.dumps(
                (prediction.metadata or {}).get(field),
                sort_keys=True,
                allow_nan=False,
            )
            for prediction in predictions
        }
        if len(values) != 1:
            raise ValueError(f"prediction metadata is mixed for {field}")
        provenance[field] = json.loads(next(iter(values))) if values else None
    _validate_adapter_provenance(provenance)
    return provenance


def _prediction_file_sha256(predictions: list[Prediction]) -> str | None:
    values = {prediction.predictions_sha256 for prediction in predictions}
    if values == {None} or not values:
        return None
    if len(values) != 1:
        raise ValueError("predictions are not bound to one prediction file")
    value = next(iter(values))
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("prediction file SHA-256 is invalid")
    return value


def _validate_adapter_provenance(provenance: dict[str, Any]) -> None:
    role = provenance.get("run_role")
    if role is None:
        return
    if role not in {"base", "adapter"}:
        raise ValueError("prediction run_role must be base or adapter")
    artifact_digest = provenance.get("adapter_artifact_sha256")
    weight_digest = provenance.get("adapter_sha256")
    if role == "base":
        if artifact_digest is not None or weight_digest is not None:
            raise ValueError("base predictions must not contain adapter fingerprints")
        return
    if (
        not isinstance(artifact_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", artifact_digest) is None
    ):
        raise ValueError(
            "adapter predictions require a complete adapter artifact SHA-256"
        )
    if weight_digest is not None and (
        not isinstance(weight_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", weight_digest) is None
    ):
        raise ValueError("adapter weight SHA-256 is invalid")


def _scoreable_prediction_text(prediction: Prediction) -> str:
    from aegislm.inference.source import (
        SOURCE_MAX_NEW_TOKENS,
        extract_harmony_final,
    )

    metadata = prediction.metadata or {}
    if metadata.get("backend") != "unsloth":
        return prediction.raw_output
    if metadata.get("mode") != "raw":
        raise ValueError(
            f"{prediction.record_id}: canonical Unsloth prediction must use raw mode"
        )
    _validate_canonical_protocol(metadata, prediction.record_id)
    raw_generation = prediction.raw_generation
    generation = prediction.generation
    if not isinstance(raw_generation, str) or not isinstance(generation, dict):
        raise ValueError(
            f"{prediction.record_id}: canonical Unsloth prediction requires the "
            "raw generation envelope"
        )
    _validate_finish_evidence(
        generation,
        raw_generation=raw_generation,
        max_new_tokens=SOURCE_MAX_NEW_TOKENS,
        record_id=prediction.record_id,
    )
    if not raw_generation.startswith(_HARMONY_ANALYSIS_PREFIX):
        raise ModelOutputFormatError(
            f"{prediction.record_id}: raw generation lacks the Harmony analysis prefix"
        )
    if _HARMONY_FINAL_MARKER not in raw_generation:
        raise ModelOutputFormatError(
            f"{prediction.record_id}: raw generation lacks the Harmony final channel"
        )
    extracted = extract_harmony_final(raw_generation)
    if extracted != prediction.raw_output:
        raise ValueError(
            f"{prediction.record_id}: raw_output does not match the independently "
            "extracted Harmony final channel"
        )
    return extracted


def _validate_canonical_protocol(metadata: dict[str, Any], record_id: str) -> None:
    from aegislm.inference.source import source_generation_protocol_metadata

    max_new_tokens = metadata.get("max_new_tokens")
    max_seq_length = metadata.get("max_seq_length")
    temperature = metadata.get("temperature")
    if type(max_new_tokens) is not int or type(max_seq_length) is not int:
        raise ValueError(f"{record_id}: invalid canonical Unsloth generation protocol")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise ValueError(f"{record_id}: invalid canonical Unsloth generation protocol")
    try:
        expected = source_generation_protocol_metadata(
            backend="unsloth",
            mode="raw",
            max_new_tokens=max_new_tokens,
            max_seq_length=max_seq_length,
            temperature=float(temperature),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{record_id}: invalid canonical Unsloth generation protocol"
        ) from exc
    if any(metadata.get(field) != value for field, value in expected.items()):
        raise ValueError(
            f"{record_id}: canonical Unsloth generation protocol is inconsistent"
        )


def _validate_finish_evidence(
    generation: dict[str, Any],
    *,
    raw_generation: str,
    max_new_tokens: int,
    record_id: str,
) -> None:
    from aegislm.inference.source import SOURCE_EOS_TOKEN_IDS

    required = {
        "generated_token_count",
        "finish_reason",
        "eos_token_id",
        "generated_token_ids",
        "harmony_prefix",
        "harmony_final",
    }
    if not required.issubset(generation):
        raise ValueError(f"{record_id}: generation finish metadata is incomplete")
    token_count = generation["generated_token_count"]
    finish_reason = generation["finish_reason"]
    eos_token_id = generation["eos_token_id"]
    token_ids = generation["generated_token_ids"]
    if type(token_count) is not int or not 0 < token_count <= max_new_tokens:
        raise ValueError(f"{record_id}: generated token count is invalid")
    if (
        not isinstance(token_ids, list)
        or len(token_ids) != token_count
        or any(type(token_id) is not int or token_id < 0 for token_id in token_ids)
    ):
        raise ValueError(f"{record_id}: generated token IDs are invalid")
    actual_prefix = raw_generation.startswith(_HARMONY_ANALYSIS_PREFIX)
    actual_final = _HARMONY_FINAL_MARKER in raw_generation
    if (
        type(generation["harmony_prefix"]) is not bool
        or type(generation["harmony_final"]) is not bool
        or generation["harmony_prefix"] is not actual_prefix
        or generation["harmony_final"] is not actual_final
    ):
        raise ValueError(f"{record_id}: Harmony finish metadata is inconsistent")
    first_eos = next(
        (
            (index, token_id)
            for index, token_id in enumerate(token_ids)
            if token_id in SOURCE_EOS_TOKEN_IDS
        ),
        None,
    )
    if first_eos is not None:
        index, derived_eos = first_eos
        if index != token_count - 1:
            raise ValueError(
                f"{record_id}: generated token IDs are not first-EOS trimmed"
            )
        derived_reason = "eos"
    else:
        derived_eos = None
        derived_reason = "length" if token_count == max_new_tokens else "unknown"
    if finish_reason != derived_reason or eos_token_id != derived_eos:
        raise ValueError(f"{record_id}: generation finish metadata is inconsistent")
    if derived_reason == "eos":
        marker = _HARMONY_EOS_MARKERS[derived_eos]
        if not raw_generation.rstrip().endswith(marker):
            raise ValueError(f"{record_id}: EOS marker does not match finish metadata")
    elif any(
        raw_generation.rstrip().endswith(marker)
        for marker in _HARMONY_EOS_MARKERS.values()
    ):
        raise ValueError(f"{record_id}: raw EOS marker lacks matching token evidence")


def _case_set_sha256(cases: list[dict[str, Any]]) -> str:
    rows = [
        {
            "record_id": case["record_id"],
            "target_cwe": case["target_cwe"],
            "expected_assessment": case["expected_assessment"],
        }
        for case in sorted(cases, key=lambda item: item["record_id"])
    ]
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _require_comparable_summaries(
    base: dict[str, Any], adapter: dict[str, Any]
) -> None:
    if base.get("case_set_sha256") != adapter.get("case_set_sha256"):
        raise ValueError("base and adapter summaries use different case sets")
    if not base.get("gold_sha256") or base.get("gold_sha256") != adapter.get(
        "gold_sha256"
    ):
        raise ValueError("base and adapter summaries use different gold data")
    for role, summary in (("base", base), ("adapter", adapter)):
        prediction_digest = summary.get("predictions_sha256")
        if (
            not isinstance(prediction_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", prediction_digest) is None
        ):
            raise ValueError(f"{role} summary requires a prediction-file SHA-256")
    if base.get("model_id") in (None, "mixed") or adapter.get("model_id") in (
        None,
        "mixed",
    ):
        raise ValueError("comparison requires one model ID per run")
    base_provenance = base.get("provenance")
    adapter_provenance = adapter.get("provenance")
    if not isinstance(base_provenance, dict) or not isinstance(
        adapter_provenance, dict
    ):
        raise ValueError("comparison requires inference provenance")
    mismatches = [
        field
        for field in COMPARABILITY_FIELDS
        if base_provenance.get(field) is None
        or base_provenance.get(field) != adapter_provenance.get(field)
    ]
    if mismatches:
        raise ValueError(
            "base and adapter runs are not comparable; mismatched fields: "
            + ", ".join(mismatches)
        )
    _validate_generation_protocol_provenance(base_provenance, "base")
    _validate_generation_protocol_provenance(adapter_provenance, "adapter")
    if (base["metrics"].get("evidence_f1") is None) != (
        adapter["metrics"].get("evidence_f1") is None
    ):
        raise ValueError("base and adapter summaries use different evaluation modes")
    if base["metrics"]["total_count"] != adapter["metrics"]["total_count"]:
        raise ValueError("base and adapter summaries use different total counts")
    if set(base["metrics"]["recall_by_label"]) != set(
        adapter["metrics"]["recall_by_label"]
    ):
        raise ValueError("base and adapter summaries use different recall labels")
    base_cwes = base["metrics"]["per_cwe"]
    adapter_cwes = adapter["metrics"]["per_cwe"]
    if set(base_cwes) != set(adapter_cwes) or any(
        base_cwes[cwe]["count"] != adapter_cwes[cwe]["count"] for cwe in base_cwes
    ):
        raise ValueError("base and adapter summaries use different CWE slices")
    if base_provenance.get("run_role") != "base":
        raise ValueError("base summary provenance must have run_role=base")
    if adapter_provenance.get("run_role") != "adapter":
        raise ValueError("adapter summary provenance must have run_role=adapter")
    _validate_adapter_provenance(base_provenance)
    _validate_adapter_provenance(adapter_provenance)
    if (
        not isinstance(base_provenance.get("packages"), dict)
        or not base_provenance["packages"]
    ):
        raise ValueError("comparison requires runtime package provenance")


def _require_comparison_metrics(summary: dict[str, Any], role: str) -> dict[str, Any]:
    """Reject corrupt or incompatible metric payloads before classification."""
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError(f"{role} summary requires a metrics object")
    for field in (
        "macro_f1",
        "accuracy",
        "schema_validation_pass_rate",
        "json_parse_success_rate",
    ):
        _metric_decimal(metrics.get(field), f"{role}.{field}")
    for field in ("evidence_f1", "grounded_span_rate"):
        if field not in metrics:
            raise ValueError(f"{role}.{field} is required")
        value = metrics.get(field)
        if value is not None:
            _metric_decimal(value, f"{role}.{field}")
    for field in (
        "total_count",
        "safety_violation_count",
        "safety_evaluated_count",
    ):
        _nonnegative_count(metrics.get(field), f"{role}.{field}")
    if metrics["total_count"] == 0:
        raise ValueError(f"{role}.total_count must be positive")

    recalls = metrics.get("recall_by_label")
    if not isinstance(recalls, dict):
        raise ValueError(f"{role}.recall_by_label must be an object")
    if not recalls:
        raise ValueError(f"{role}.recall_by_label must not be empty")
    invalid_labels = sorted(set(recalls) - set(SOURCE_ASSESSMENTS))
    if invalid_labels:
        raise ValueError(
            f"{role}.recall_by_label contains invalid labels: {invalid_labels}"
        )
    for label, value in recalls.items():
        _metric_decimal(value, f"{role}.recall_by_label.{label}")

    per_cwe = metrics.get("per_cwe")
    if not isinstance(per_cwe, dict):
        raise ValueError(f"{role}.per_cwe must be an object")
    for cwe, row in per_cwe.items():
        if not isinstance(row, dict):
            raise ValueError(f"{role}.per_cwe.{cwe} must be an object")
        _nonnegative_count(row.get("count"), f"{role}.per_cwe.{cwe}.count")
        _metric_decimal(row.get("accuracy"), f"{role}.per_cwe.{cwe}.accuracy")
    if sum(row["count"] for row in per_cwe.values()) != metrics["total_count"]:
        raise ValueError(f"{role}.per_cwe counts must sum to total_count")
    if not (
        metrics["safety_violation_count"]
        <= metrics["safety_evaluated_count"]
        <= metrics["total_count"]
    ):
        raise ValueError(f"{role} safety counts are inconsistent")
    return metrics


def _validate_generation_protocol_provenance(
    provenance: dict[str, Any], role: str
) -> None:
    protocol = {field: provenance.get(field) for field in GENERATION_PROTOCOL_FIELDS}
    encoded = json.dumps(
        protocol, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    expected_digest = hashlib.sha256(encoded).hexdigest()
    if provenance.get("generation_protocol_sha256") != expected_digest:
        raise ValueError(f"{role} generation protocol digest or fields are invalid")


def _code_spans(output: dict[str, Any]) -> set[str]:
    spans: set[str] = set()
    for field in ("assessment_basis", "findings"):
        items = output.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            values = item.get("code_spans") if isinstance(item, dict) else None
            if isinstance(values, list):
                spans.update(value for value in values if isinstance(value, str))
    return spans


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _metric_delta(base: Any, adapter: Any) -> Decimal:
    """Subtract metrics at the four-decimal precision stored in summaries."""
    return (_metric_decimal(adapter) - _metric_decimal(base)).quantize(
        Decimal("0.0001")
    )


def _metric_decimal(value: Any, field: str = "comparison metric") -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    decimal_value = Decimal(str(value))
    if not decimal_value.is_finite() or not Decimal("0") <= decimal_value <= Decimal(
        "1"
    ):
        raise ValueError(f"{field} must be a finite number between 0 and 1")
    return decimal_value


def _nonnegative_count(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")


def _optional_delta(base: Any, adapter: Any) -> Decimal | None:
    if base is None and adapter is None:
        return None
    return _metric_delta(base, adapter)
