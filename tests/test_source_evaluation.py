import hashlib
import json
from copy import deepcopy

import pytest

from aegislm.datasets.source import parse_source_record
from aegislm.evaluation.harness import Prediction
from aegislm.evaluation.source import (
    bind_source_comparison_inputs,
    compare_source_summaries,
    evaluate_source_predictions,
    validate_source_gold,
)
from aegislm.evaluation.validation import validate_source_assessment
from aegislm.inference.source import source_generation_protocol_metadata
from aegislm.tracking import build_tracking_receipt


def _expected() -> dict:
    return {
        "schema_version": "aegislm.source-vulnerability-assessment.v2",
        "scope": {"boundary": "supplied_function", "target_cwe": "CWE-120"},
        "assessment": "present",
        "assessment_basis": [
            {
                "code_spans": ["copy(dst, src);"],
                "relationship": "The copy is not bounded.",
                "conclusion": "CWE-120 is present.",
                "confidence": "high",
            }
        ],
        "findings": [
            {
                "code_spans": ["copy(dst, src);"],
                "operation": "Unbounded copy.",
                "evidence": "The destination size is not checked.",
                "confidence": "high",
            }
        ],
        "limitations": ["Function-local assessment only."],
        "recommendations": ["Use a size-checked operation."],
    }


def _challenge():
    return parse_source_record(
        {
            "id": "case-1",
            "messages": [
                {"role": "system", "content": "Return JSON."},
                {
                    "role": "user",
                    "content": (
                        '{"scope":{"boundary":"supplied_function",'
                        '"target_cwe":"CWE-120"},'
                        '"source_code":"copy(dst, src);"}'
                    ),
                },
            ],
        },
        require_assistant=False,
    )


def test_source_validation_requires_grounded_exact_spans():
    output = _expected()
    output["findings"][0]["code_spans"] = ["not in source"]

    result = validate_source_assessment(
        output, source_code="copy(dst, src);", target_cwe="CWE-120"
    )

    assert not result.ok
    assert any("exact substring" in error for error in result.errors)


def test_safety_failure_is_not_counted_as_schema_failure():
    expected = _expected()
    unsafe = _expected()
    unsafe["recommendations"] = ["Run this exploit."]
    summary = evaluate_source_predictions(
        [_challenge()],
        {"case-1": expected},
        [
            Prediction(
                record_id="case-1",
                model_id="adapter",
                run_id="run",
                raw_output=json.dumps(unsafe),
            )
        ],
    )

    assert summary["metrics"]["schema_validation_pass_rate"] == 1.0
    assert summary["metrics"]["safety_violation_count"] == 1


def test_invalid_json_is_not_reported_as_an_unsafe_guidance_match():
    summary = evaluate_source_predictions(
        [_challenge()],
        {"case-1": _expected()},
        [
            Prediction(
                record_id="case-1",
                model_id="adapter",
                run_id="run",
                raw_output="not-json",
            )
        ],
    )

    assert summary["metrics"]["safety_violation_count"] == 0
    assert summary["metrics"]["safety_evaluated_count"] == 0


def test_gold_validation_rejects_ungrounded_full_report():
    expected = _expected()
    expected["assessment_basis"][0]["code_spans"] = ["not in source"]

    with pytest.raises(ValueError, match="invalid full-report gold"):
        validate_source_gold([_challenge()], {"case-1": expected})


def test_full_report_evaluation_scores_labels_and_evidence():
    expected = _expected()
    summary = evaluate_source_predictions(
        [_challenge()],
        {"case-1": expected},
        [
            Prediction(
                record_id="case-1",
                model_id="adapter",
                run_id="run",
                raw_output=json.dumps(expected),
            )
        ],
    )

    metrics = summary["metrics"]
    assert metrics["accuracy"] == 1.0
    assert metrics["macro_f1"] == 1.0
    assert metrics["evidence_f1"] == 1.0
    assert metrics["grounded_span_rate"] == 1.0
    assert metrics["schema_validation_pass_rate"] == 1.0


def test_decision_only_gold_accepts_compact_prediction():
    summary = evaluate_source_predictions(
        [_challenge()],
        {"case-1": {"assessment": "present"}},
        [
            Prediction(
                record_id="case-1",
                model_id="base",
                run_id="blind",
                raw_output='{"assessment":"present"}',
            )
        ],
    )

    assert summary["metrics"]["macro_f1"] == 1.0
    assert summary["metrics"]["evidence_f1"] is None


def _canonical_unsloth_prediction(**overrides):
    raw_output = '{"assessment":"present"}'
    values = {
        "record_id": "case-1",
        "model_id": "adapter",
        "run_id": "run",
        "raw_output": raw_output,
        "raw_generation": (
            "<|channel|>analysis<|message|>reason"
            f"<|channel|>final<|message|>{raw_output}<|return|>"
        ),
        "generation": {
            "generated_token_count": 12,
            "finish_reason": "eos",
            "eos_token_id": 200002,
            "generated_token_ids": [10] * 11 + [200002],
            "harmony_prefix": True,
            "harmony_final": True,
        },
        "metadata": {
            "backend": "unsloth",
            "mode": "raw",
            "temperature": 0.0,
            **source_generation_protocol_metadata(
                backend="unsloth",
                mode="raw",
                max_new_tokens=512,
                max_seq_length=2048,
                temperature=0.0,
            ),
        },
    }
    values.update(overrides)
    return Prediction(**values)


def test_canonical_unsloth_evaluation_independently_validates_envelope():
    summary = evaluate_source_predictions(
        [_challenge()],
        {"case-1": {"assessment": "present"}},
        [_canonical_unsloth_prediction()],
    )

    assert summary["metrics"]["json_parse_success_rate"] == 1.0
    assert summary["metrics"]["accuracy"] == 1.0


def test_canonical_unsloth_evaluation_rejects_missing_or_tampered_envelope():
    missing = _canonical_unsloth_prediction(raw_generation=None)
    with pytest.raises(ValueError, match="requires the raw generation envelope"):
        evaluate_source_predictions(
            [_challenge()], {"case-1": {"assessment": "present"}}, [missing]
        )

    tampered = _canonical_unsloth_prediction(raw_output='{"assessment":"not_observed"}')
    with pytest.raises(ValueError, match="independently extracted"):
        evaluate_source_predictions(
            [_challenge()], {"case-1": {"assessment": "present"}}, [tampered]
        )


def test_canonical_unsloth_evaluation_rejects_tampered_finish_metadata():
    generation = dict(_canonical_unsloth_prediction().generation or {})
    generation["eos_token_id"] = 199999
    generation["generated_token_ids"] = [10] * 11 + [199999]
    prediction = _canonical_unsloth_prediction(generation=generation)

    with pytest.raises(ValueError, match="EOS marker does not match"):
        evaluate_source_predictions(
            [_challenge()], {"case-1": {"assessment": "present"}}, [prediction]
        )


def test_canonical_unsloth_malformed_output_is_counted_as_a_case_failure():
    generation = dict(_canonical_unsloth_prediction().generation or {})
    generation["harmony_final"] = False
    prediction = _canonical_unsloth_prediction(
        raw_output="not-json",
        raw_generation=(
            "<|channel|>analysis<|message|>honest malformed output<|return|>"
        ),
        generation=generation,
    )

    summary = evaluate_source_predictions(
        [_challenge()], {"case-1": {"assessment": "present"}}, [prediction]
    )

    assert summary["metrics"]["json_parse_success_rate"] == 0.0
    assert summary["metrics"]["schema_validation_pass_rate"] == 0.0
    assert "lacks the Harmony final channel" in summary["cases"][0]["errors"][0]


def test_canonical_unsloth_rejects_false_harmony_or_token_evidence():
    generation = dict(_canonical_unsloth_prediction().generation or {})
    generation["harmony_final"] = False
    with pytest.raises(ValueError, match="Harmony finish metadata"):
        evaluate_source_predictions(
            [_challenge()],
            {"case-1": {"assessment": "present"}},
            [_canonical_unsloth_prediction(generation=generation)],
        )

    generation = dict(_canonical_unsloth_prediction().generation or {})
    generation["generated_token_ids"] = [10, 200002, 10] + [10] * 9
    with pytest.raises(ValueError, match="first-EOS trimmed|finish metadata"):
        evaluate_source_predictions(
            [_challenge()],
            {"case-1": {"assessment": "present"}},
            [_canonical_unsloth_prediction(generation=generation)],
        )


def test_comparison_classifies_improvement_and_regression():
    common_provenance = {
        "challenge_file_sha256": "challenge",
        "challenge_records_sha256": "records",
        "backend": "unsloth",
        "mode": "raw",
        "max_new_tokens": 512,
        "max_seq_length": 2048,
        "temperature": 0.0,
        **source_generation_protocol_metadata(
            backend="unsloth",
            mode="raw",
            max_new_tokens=512,
            max_seq_length=2048,
            temperature=0.0,
        ),
        "tokenizer_contract_sha256": "tokenizer",
        "base_model_revision": "revision",
        "hardware_signature": "hardware",
        "packages": {"transformers": "5.5.0"},
        "resolved_model_id": "runtime/model",
    }
    base_provenance = {
        **common_provenance,
        "run_role": "base",
        "adapter_artifact_sha256": None,
        "adapter_sha256": None,
    }
    adapter_provenance = {
        **common_provenance,
        "run_role": "adapter",
        "adapter_artifact_sha256": "b" * 64,
        "adapter_sha256": "a" * 64,
    }
    base = {
        "model_id": "base",
        "case_set_sha256": "same-cases",
        "gold_sha256": "same-gold",
        "predictions_sha256": "c" * 64,
        "provenance": base_provenance,
        "metrics": {
            "total_count": 20,
            "macro_f1": 0.7,
            "evidence_f1": 0.5,
            "accuracy": 0.7,
            "schema_validation_pass_rate": 1.0,
            "json_parse_success_rate": 1.0,
            "grounded_span_rate": 1.0,
            "safety_violation_count": 0,
            "safety_evaluated_count": 20,
            "recall_by_label": {"present": 0.7},
            "per_cwe": {"CWE-120": {"count": 20, "accuracy": 0.7}},
        },
    }
    adapter = {
        "model_id": "adapter",
        "case_set_sha256": "same-cases",
        "gold_sha256": "same-gold",
        "predictions_sha256": "d" * 64,
        "provenance": adapter_provenance,
        "metrics": {
            **base["metrics"],
            "macro_f1": 0.74,
            "evidence_f1": 0.54,
            "accuracy": 0.74,
            "recall_by_label": {"present": 0.74},
            "per_cwe": {"CWE-120": {"count": 20, "accuracy": 0.74}},
        },
    }
    assert compare_source_summaries(base, adapter)["outcome"] == "improved"

    adapter["metrics"]["recall_by_label"] = {"present": 0.67}
    assert compare_source_summaries(base, adapter)["outcome"] == "regressed"

    adapter["case_set_sha256"] = "different-cases"
    with pytest.raises(ValueError, match="different case sets"):
        compare_source_summaries(base, adapter)

    adapter["case_set_sha256"] = "same-cases"
    adapter["provenance"] = {**adapter_provenance, "mode": "constrained"}
    with pytest.raises(ValueError, match="mismatched fields: mode"):
        compare_source_summaries(base, adapter)

    adapter["provenance"] = {
        **adapter_provenance,
        "generation_protocol_sha256": "different-protocol",
    }
    with pytest.raises(ValueError, match="generation_protocol_sha256"):
        compare_source_summaries(base, adapter)


def test_decision_only_comparison_can_report_improvement():
    base, adapter = _comparison_pair()
    base["metrics"]["evidence_f1"] = None
    adapter["metrics"]["evidence_f1"] = None
    base["metrics"]["macro_f1"] = 0.1
    adapter["metrics"]["macro_f1"] = 0.9

    result = compare_source_summaries(base, adapter)

    assert result["outcome"] == "improved"
    assert result["comparison_mode"] == "decision_only"


def test_decision_only_improvement_threshold_boundary():
    base, adapter = _comparison_pair()
    base["metrics"]["evidence_f1"] = None
    adapter["metrics"]["evidence_f1"] = None
    base["metrics"]["macro_f1"] = 0.55
    adapter["metrics"]["macro_f1"] = 0.58
    assert compare_source_summaries(base, adapter)["outcome"] == "improved"

    adapter["metrics"]["macro_f1"] = 0.5799
    assert compare_source_summaries(base, adapter)["outcome"] == "equivalent"


def test_full_report_improvement_threshold_boundary():
    base, adapter = _comparison_pair()
    base["metrics"]["macro_f1"] = 0.26
    adapter["metrics"]["macro_f1"] = 0.29
    base["metrics"]["evidence_f1"] = 0.55
    adapter["metrics"]["evidence_f1"] = 0.58
    result = compare_source_summaries(base, adapter)
    assert result["outcome"] == "improved"
    json.dumps(result, allow_nan=False)

    adapter["metrics"]["evidence_f1"] = 0.5799
    assert compare_source_summaries(base, adapter)["outcome"] == "equivalent"


def test_regression_threshold_boundaries_and_precedence():
    base, adapter = _comparison_pair()
    adapter["metrics"]["macro_f1"] = 0.74
    adapter["metrics"]["evidence_f1"] = 0.54
    base["metrics"]["recall_by_label"] = {"present": 0.05}
    adapter["metrics"]["recall_by_label"] = {"present": 0.03}
    base["metrics"]["per_cwe"]["CWE-120"]["accuracy"] = 0.14
    adapter["metrics"]["per_cwe"]["CWE-120"]["accuracy"] = 0.09
    assert compare_source_summaries(base, adapter)["outcome"] == "improved"

    adapter["metrics"]["recall_by_label"] = {"present": 0.0299}
    assert compare_source_summaries(base, adapter)["outcome"] == "regressed"

    adapter["metrics"]["recall_by_label"] = {"present": 0.03}
    adapter["metrics"]["per_cwe"]["CWE-120"]["accuracy"] = 0.0899
    assert compare_source_summaries(base, adapter)["outcome"] == "regressed"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("macro_f1", "invalid"),
        ("accuracy", True),
        ("schema_validation_pass_rate", float("nan")),
        ("json_parse_success_rate", float("inf")),
    ),
)
def test_comparison_rejects_nonfinite_or_nonnumeric_required_metrics(field, value):
    base, adapter = _comparison_pair()
    adapter["metrics"][field] = value

    with pytest.raises(ValueError, match="finite number"):
        compare_source_summaries(base, adapter)


@pytest.mark.parametrize(
    ("base_evidence", "adapter_evidence"),
    (("invalid", "invalid"), (None, 0.5), (0.5, None)),
)
def test_comparison_only_accepts_evidence_none_for_decision_only_pair(
    base_evidence, adapter_evidence
):
    base, adapter = _comparison_pair()
    base["metrics"]["evidence_f1"] = base_evidence
    adapter["metrics"]["evidence_f1"] = adapter_evidence

    with pytest.raises(ValueError, match="finite number|different evaluation modes"):
        compare_source_summaries(base, adapter)

    base, adapter = _comparison_pair()
    del adapter["metrics"]["evidence_f1"]
    with pytest.raises(ValueError, match="adapter.evidence_f1 is required"):
        compare_source_summaries(base, adapter)


def test_comparison_rejects_invalid_slice_metrics_and_counts():
    base, adapter = _comparison_pair()
    adapter["metrics"]["recall_by_label"]["present"] = False
    with pytest.raises(ValueError, match="finite number"):
        compare_source_summaries(base, adapter)

    base, adapter = _comparison_pair()
    adapter["metrics"]["per_cwe"]["CWE-120"]["count"] = 20.0
    with pytest.raises(ValueError, match="non-negative integer"):
        compare_source_summaries(base, adapter)

    base, adapter = _comparison_pair()
    adapter["metrics"]["per_cwe"] = {}
    with pytest.raises(ValueError, match="counts must sum|different CWE slices"):
        compare_source_summaries(base, adapter)


def test_comparison_rejects_empty_mismatched_or_invalid_recall_labels():
    base, adapter = _comparison_pair()
    base["metrics"]["recall_by_label"] = {}
    adapter["metrics"]["recall_by_label"] = {}
    with pytest.raises(ValueError, match="must not be empty"):
        compare_source_summaries(base, adapter)

    base, adapter = _comparison_pair()
    adapter["metrics"]["recall_by_label"]["not_observed"] = 0.7
    with pytest.raises(ValueError, match="different recall labels"):
        compare_source_summaries(base, adapter)

    base, adapter = _comparison_pair()
    adapter["metrics"]["recall_by_label"] = {"invalid": 0.7}
    with pytest.raises(ValueError, match="contains invalid labels"):
        compare_source_summaries(base, adapter)

    base, adapter = _comparison_pair()
    for summary in (base, adapter):
        summary["metrics"]["total_count"] = 0
        summary["metrics"]["recall_by_label"] = {}
        summary["metrics"]["per_cwe"] = {}
        summary["metrics"]["safety_evaluated_count"] = 0
    with pytest.raises(ValueError, match="total_count must be positive"):
        compare_source_summaries(base, adapter)


def test_comparison_rejects_missing_adapter_or_runtime_fingerprint():
    base, adapter = _comparison_pair()
    adapter["provenance"]["adapter_artifact_sha256"] = None
    with pytest.raises(ValueError, match="complete adapter artifact"):
        compare_source_summaries(base, adapter)

    base, adapter = _comparison_pair()
    adapter["provenance"]["adapter_sha256"] = None
    assert compare_source_summaries(base, adapter)["outcome"] == "equivalent"

    base, adapter = _comparison_pair()
    adapter["provenance"]["packages"] = {"transformers": "different"}
    with pytest.raises(ValueError, match="mismatched fields: packages"):
        compare_source_summaries(base, adapter)

    base, adapter = _comparison_pair()
    adapter["provenance"]["run_role"] = "base"
    with pytest.raises(ValueError, match="run_role=adapter"):
        compare_source_summaries(base, adapter)


def test_comparison_rejects_matching_but_forged_protocol_digest():
    base, adapter = _comparison_pair()
    base["provenance"]["generation_protocol_sha256"] = "0" * 64
    adapter["provenance"]["generation_protocol_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="digest or fields are invalid"):
        compare_source_summaries(base, adapter)


def test_comparison_input_digests_prevent_tracking_identity_collision():
    base, adapter = _comparison_pair()
    comparison = compare_source_summaries(base, adapter)
    first = bind_source_comparison_inputs(
        comparison,
        base_summary_sha256="a" * 64,
        adapter_summary_sha256="b" * 64,
    )
    second = bind_source_comparison_inputs(
        comparison,
        base_summary_sha256="a" * 64,
        adapter_summary_sha256="c" * 64,
    )
    retry = bind_source_comparison_inputs(
        comparison,
        base_summary_sha256="a" * 64,
        adapter_summary_sha256="b" * 64,
    )

    def identity(value: dict) -> str:
        digest = hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return str(build_tracking_receipt("comparison", digest)["identity"])

    assert first["inputs"]["adapter_summary_sha256"] == "b" * 64
    assert identity(first) != identity(second)
    assert identity(first) == identity(retry)


@pytest.mark.parametrize("digest", ["", "A" * 64, "a" * 63])
def test_comparison_input_binding_rejects_invalid_digest(digest):
    base, adapter = _comparison_pair()
    with pytest.raises(ValueError, match="digest must be SHA-256"):
        bind_source_comparison_inputs(
            compare_source_summaries(base, adapter),
            base_summary_sha256=digest,
            adapter_summary_sha256="b" * 64,
        )


def _comparison_pair() -> tuple[dict, dict]:
    common_provenance = {
        "challenge_file_sha256": "challenge",
        "challenge_records_sha256": "records",
        "backend": "unsloth",
        "mode": "raw",
        "max_new_tokens": 512,
        "max_seq_length": 2048,
        "temperature": 0.0,
        **source_generation_protocol_metadata(
            backend="unsloth",
            mode="raw",
            max_new_tokens=512,
            max_seq_length=2048,
            temperature=0.0,
        ),
        "tokenizer_contract_sha256": "tokenizer",
        "base_model_revision": "revision",
        "hardware_signature": "hardware",
        "packages": {"transformers": "5.5.0"},
        "resolved_model_id": "runtime/model",
    }
    metrics = {
        "total_count": 20,
        "macro_f1": 0.7,
        "evidence_f1": 0.5,
        "accuracy": 0.7,
        "schema_validation_pass_rate": 1.0,
        "json_parse_success_rate": 1.0,
        "grounded_span_rate": 1.0,
        "safety_violation_count": 0,
        "safety_evaluated_count": 20,
        "recall_by_label": {"present": 0.7},
        "per_cwe": {"CWE-120": {"count": 20, "accuracy": 0.7}},
    }
    base = {
        "model_id": "base",
        "case_set_sha256": "same-cases",
        "gold_sha256": "same-gold",
        "predictions_sha256": "c" * 64,
        "provenance": {
            **common_provenance,
            "run_role": "base",
            "adapter_artifact_sha256": None,
            "adapter_sha256": None,
        },
        "metrics": deepcopy(metrics),
    }
    adapter = {
        "model_id": "adapter",
        "case_set_sha256": "same-cases",
        "gold_sha256": "same-gold",
        "predictions_sha256": "d" * 64,
        "provenance": {
            **common_provenance,
            "run_role": "adapter",
            "adapter_artifact_sha256": "b" * 64,
            "adapter_sha256": "a" * 64,
        },
        "metrics": deepcopy(metrics),
    }
    return base, adapter
