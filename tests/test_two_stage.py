"""Contracts, gates, and leakage regression tests for the two-stage port."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

import pytest

from aegislm.datasets.source_evidence_lines import (
    format_evidence_lines_payload,
    render_assessment_from_evidence_lines,
    resolve_evidence_ranges,
    validate_evidence_lines_output,
)
from aegislm.evaluation.harness import Prediction
from aegislm.evaluation.source_evidence_lines import (
    evaluate_source_evidence_predictions,
)
from aegislm.training.two_stage import freeze_tokenizer, validate_row
from scripts.train_source_two_stage import decision_score, predicted_evidence


def evidence() -> dict[str, Any]:
    return {
        "schema_version": "aegislm.source-evidence-lines.v1",
        "evidence_ranges": [{"start_line": 1, "end_line": 1}],
        "confidence": "high",
    }


@pytest.mark.parametrize(
    "ranges",
    [
        [],
        [{"start_line": 2, "end_line": 1}],
        [{"start_line": 1, "end_line": 3}],
        [{"start_line": 1, "end_line": 1}] * 2,
        [{"start_line": True, "end_line": 1}],
    ],
)
def test_invalid_evidence_ranges_rejected(ranges: list[dict[str, Any]]) -> None:
    output = evidence()
    output["evidence_ranges"] = ranges
    assert validate_evidence_lines_output(output, line_count=2)


def test_renderer_copies_input_and_keeps_requested_cwe() -> None:
    source = "int x = 0;\nreturn x;"
    output = render_assessment_from_evidence_lines(
        evidence(), assessment="not_observed", target_cwe="CWE-457", source_code=source
    )
    assert output["scope"]["target_cwe"] == "CWE-457"
    assert output["assessment_basis"][0]["code_spans"] == ["int x = 0;"]
    assert output["assessment"] == "not_observed"


def test_duplicate_text_ranges_resolve_without_duplicate_spans() -> None:
    output = evidence()
    output["evidence_ranges"] = [
        {"start_line": 1, "end_line": 1},
        {"start_line": 3, "end_line": 3},
    ]
    assert resolve_evidence_ranges(output, source_code="x;\ny;\nx;") == ["x;"]


def test_gold_evidence_fixture_scores_one() -> None:
    source = "int x = 0;\nreturn x;"
    prompts = [
        {
            "id": "one",
            "messages": format_evidence_lines_payload(
                target_cwe="CWE-457", source_code=source, assessment="not_observed"
            ),
        }
    ]
    gold = [{"id": "one", "expected_output": evidence()}]
    private = [{"id": "one", "code": {"text": source}}]
    predictions = [Prediction("one", "test", "test", json.dumps(evidence()))]
    result = evaluate_source_evidence_predictions(prompts, gold, private, predictions)
    assert result["metrics"]["evidence_f1"] == 1
    assert result["metrics"]["renderer_pass_rate"] == 1
    assert not result["overall_pass"]  # sample count gate remains active


def test_decision_uses_absolute_qwen_thresholds() -> None:
    gold = [
        {
            "id": str(i),
            "expected_output": {"assessment": "present" if i < 50 else "not_observed"},
        }
        for i in range(100)
    ]
    predictions = [
        Prediction(str(i), "test", "test", json.dumps(r["expected_output"]))
        for i, r in enumerate(gold)
    ]
    assert decision_score(gold, predictions)["overall_pass"]
    for i in range(3):
        predictions[i] = Prediction(
            str(i), "test", "test", '{"assessment":"not_observed"}'
        )
    result = decision_score(gold, predictions)
    assert result["metrics"]["recall"] == 0.94
    assert not result["overall_pass"]


@pytest.mark.parametrize(
    "raw",
    ["not json", '{"assessment":"uncertain"}', '{"assessment":"present","extra":1}'],
)
def test_pipeline_never_replaces_invalid_decision_with_gold(raw: str) -> None:
    data = {
        "private": [
            {"id": "one", "task": {"target_cwe": "CWE-457"}, "code": {"text": "int x;"}}
        ]
    }
    with pytest.raises(ValueError):
        predicted_evidence(data, [Prediction("one", "test", "test", raw)])


def test_evidence_conditions_on_prediction_not_gold() -> None:
    data = {
        "private": [
            {
                "id": "one",
                "task": {"target_cwe": "CWE-457"},
                "code": {"text": "int x;"},
                "gold": "present",
            }
        ]
    }
    rows = predicted_evidence(
        data, [Prediction("one", "test", "test", '{"assessment":"not_observed"}')]
    )
    assert "not_observed" in rows[0]["messages"][1]["content"]
    assert all(m["role"] != "assistant" for m in rows[0]["messages"])


def test_training_contract_rejects_full_report_for_decision() -> None:
    row = {
        "messages": [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": '{"assessment":"present","findings":[]}'},
        ]
    }
    with pytest.raises(ValueError):
        validate_row(row, "decision")


def test_frozen_template_date_and_padding_are_explicit() -> None:
    class Tokenizer:
        chat_template = '{{ strftime_now("%Y-%m-%d") }}'
        pad_token_id = 200017
        padding_side = "left"

    tokenizer = Tokenizer()
    freeze_tokenizer(tokenizer, "2026-09-28", training=True)
    assert tokenizer.padding_side == "right"
    assert "strftime_now" not in tokenizer.chat_template
    saved = deepcopy(tokenizer.chat_template)
    freeze_tokenizer(tokenizer, "2026-09-28", training=False)
    assert tokenizer.chat_template == saved
    assert tokenizer.padding_side == "left"
    with pytest.raises(ValueError):
        freeze_tokenizer(tokenizer, "2026-09-29", training=False)


def test_split_leakage_detects_identical_code_with_renamed_ids() -> None:
    from aegislm.training.two_stage import split_overlap

    def row(identifier: str, code: str) -> dict[str, Any]:
        return {
            "id": identifier,
            "messages": [
                {"role": "user", "content": json.dumps({"source_code": code})}
            ],
        }

    left = [row("train-id", "int x;")]
    right = [row("different-id", "int x;"), row("train-id", "int y;")]
    result = split_overlap(left, right)
    assert result["id_overlap_count"] == 1
    assert result["code_overlap_count"] == 1
    assert len(result["matches"]) == 2
