import json
import hashlib
from types import SimpleNamespace

import pytest
import torch

from aegislm.datasets.source import parse_source_record
from aegislm.training.source_gate import (
    GenerationContract,
    HARMONY_ANALYSIS_PREFIX,
    HARMONY_FINAL_MARKER,
    MAX_GATE_PREDICTION_LINE_BYTES,
    canary_gate_evidence_fields,
    rescore_source_gate_predictions,
    run_source_schema_gate,
    trim_generated_token_ids,
    validate_runtime_tokenizer,
)
from aegislm.inference.source import extract_harmony_final


def _contract():
    return GenerationContract(
        reasoning_effort="low",
        padding_side="left",
        pad_token_id=200017,
        eos_token_ids=(200002, 199999),
        do_sample=False,
        max_new_tokens=4,
    )


def test_trim_generated_tokens_stops_at_first_eos_before_batch_padding():
    result = trim_generated_token_ids(
        [10, 200002, 200002, 200017],
        eos_token_ids=(200002, 199999),
        max_new_tokens=4,
    )

    assert result.token_ids == [10, 200002]
    assert result.generated_token_count == 2
    assert result.finish_reason == "eos"
    assert result.eos_token_id == 200002


def test_trim_generated_tokens_reports_length_without_eos():
    result = trim_generated_token_ids(
        [10, 11, 12, 13], eos_token_ids=(200002,), max_new_tokens=4
    )

    assert result.finish_reason == "length"
    assert result.eos_token_id is None


def test_runtime_tokenizer_contract_rejects_special_token_drift():
    tokenizer = SimpleNamespace(
        padding_side="left", pad_token_id=199999, eos_token_id=200002
    )

    with pytest.raises(ValueError, match="pad_token_id mismatch"):
        validate_runtime_tokenizer(tokenizer, _contract())


class _Batch(dict):
    def to(self, device):
        assert device == "cuda"
        return self


class _Tokenizer:
    padding_side = "left"
    pad_token_id: int | None = 200017
    eos_token_id: int | None = 200002

    def __init__(self, valid_json):
        self.valid_json = valid_json
        self.reasoning_efforts = []

    def apply_chat_template(self, conversation, **kwargs):
        assert len(conversation) == 2
        self.reasoning_efforts.append(kwargs["reasoning_effort"])
        return _Batch(
            input_ids=torch.tensor([[200017, 9], [8, 9]]),
            attention_mask=torch.tensor([[0, 1], [1, 1]]),
        )

    def decode(self, token_ids, *, skip_special_tokens):
        if token_ids == [200017, 9]:
            assert skip_special_tokens is False
            return "[PAD] prompt-a"

        if token_ids == [8, 9]:
            assert skip_special_tokens is False
            return "prompt-b"

        if token_ids == [1, 200002]:
            if skip_special_tokens:
                return self.valid_json
            return (
                HARMONY_ANALYSIS_PREFIX
                + "brief"
                + HARMONY_FINAL_MARKER
                + self.valid_json
                + "<|return|>"
            )
        return "not-json"


class _Model:
    def __init__(self):
        self.kwargs = None

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return torch.tensor(
            [
                [200017, 9, 1, 200002, 200017, 200017],
                [8, 9, 2, 3, 4, 5],
            ]
        )


def _gate_records():
    output = {
        "schema_version": "aegislm.source-vulnerability-assessment.v2",
        "scope": {"boundary": "supplied_function", "target_cwe": "CWE-120"},
        "assessment": "not_observed",
        "assessment_basis": [
            {
                "code_spans": ["return 0;"],
                "relationship": "No copy occurs.",
                "conclusion": "Not observed.",
                "confidence": "high",
            }
        ],
        "findings": [],
        "limitations": ["Local only."],
        "recommendations": ["Review."],
    }
    row = {
        "id": "record-a",
        "messages": [
            {"role": "system", "content": "system"},
            {
                "role": "user",
                "content": '{"scope":{"target_cwe":"CWE-120"},'
                '"source_code":"return 0;"}',
            },
            {"role": "assistant", "content": json.dumps(output)},
        ],
    }
    first = parse_source_record(row, require_assistant=True)
    row["id"] = "record-b"
    second = parse_source_record(row, require_assistant=True)
    return [first, second], json.dumps(output)


def test_gate_uses_explicit_protocol_and_reports_finish_reasons(tmp_path):
    records, valid_json = _gate_records()
    tokenizer = _Tokenizer(valid_json)
    model = _Model()
    path = tmp_path / "predictions.jsonl"

    summary = run_source_schema_gate(
        model=model,
        tokenizer=tokenizer,
        records=records,
        prediction_path=path,
        batch_size=2,
        contract=_contract(),
    )

    assert summary.passed_count == 1
    assert summary.schema_pass_rate == 0.5
    assert summary.finish_reasons == {"eos": 1, "length": 1}
    assert summary.harmony_prefix_count == 1
    assert tokenizer.reasoning_efforts == ["low"]
    assert model.kwargs is not None
    assert model.kwargs["pad_token_id"] == 200017
    assert model.kwargs["eos_token_id"] == [200002, 199999]
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[0]["generation"]["generated_token_count"] == 2
    assert rows[1]["generation"]["finish_reason"] == "length"
    assert [row["id"] for row in rows] == ["record-a", "record-b"]

    assert rows[0]["extracted_final"] == valid_json
    assert rows[0]["parsed_output"] == json.loads(valid_json)

    assert rows[1]["extracted_final"] == "not-json"
    assert rows[1]["parsed_output"] is None
    assert any(
        error.startswith("invalid JSON:") for error in rows[1]["validation_errors"]
    )

    expected_inputs = [
        ([200017, 9], [0, 1], "[PAD] prompt-a"),
        ([8, 9], [1, 1], "prompt-b"),
    ]

    for idx, (token_ids, mask, decoded) in enumerate(expected_inputs):
        saved_input = rows[idx]["input"]

        assert saved_input["messages"] == list(records[idx].prompt_messages)
        assert saved_input["target_cwe"] == records[idx].target_cwe
        assert saved_input["input_ids"] == token_ids
        assert saved_input["attention_mask"] == mask
        assert saved_input["decoded_input"] == decoded

        assert saved_input["input_ids"] == model.kwargs["input_ids"][idx].tolist()
        assert (
            saved_input["attention_mask"]
            == model.kwargs["attention_mask"][idx].tolist()
        )

    with pytest.raises(FileExistsError):
        run_source_schema_gate(
            model=model,
            tokenizer=tokenizer,
            records=records,
            prediction_path=path,
            batch_size=2,
            contract=_contract(),
        )


def test_gate_evidence_is_rescored_from_raw_and_bound_to_digest(tmp_path):
    records, valid_json = _gate_records()
    prediction_path = tmp_path / "predictions.jsonl"
    raw = (
        HARMONY_ANALYSIS_PREFIX
        + "brief"
        + HARMONY_FINAL_MARKER
        + valid_json
        + "<|return|>"
    )
    rows = [
        {
            "id": record.record_id,
            "raw_generation": raw,
            "parsed_output": {"forged": True},
            "validation_errors": ["forged stored error"],
            "generation": {
                "generated_token_count": 2,
                "finish_reason": "eos",
                "eos_token_id": 200002,
                "generated_token_ids": [1, 200002],
                "harmony_prefix": True,
                "harmony_final": True,
            },
        }
        for record in records
    ]
    prediction_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    evidence = rescore_source_gate_predictions(
        records=records, prediction_path=prediction_path, contract=_contract()
    )

    assert evidence.summary.passed_count == 2
    assert evidence.summary.parsed_count == 2
    assert (
        evidence.predictions_sha256
        == hashlib.sha256(prediction_path.read_bytes()).hexdigest()
    )
    fields = canary_gate_evidence_fields(
        summary=evidence.summary,
        predictions_sha256=evidence.predictions_sha256,
        adapter_artifact_sha256="a" * 64,
    )
    assert fields["promotion_authority"] is True
    assert fields["record_count"] == 2


@pytest.mark.parametrize(
    ("finish_reason", "token_ids"), [("length", [1, 2, 3, 4]), ("unknown", [1])]
)
def test_nonlegacy_gate_never_passes_without_configured_eos(
    tmp_path, finish_reason, token_ids
):
    records, valid_json = _gate_records()
    raw = HARMONY_ANALYSIS_PREFIX + "brief" + HARMONY_FINAL_MARKER + valid_json
    row = {
        "id": records[0].record_id,
        "raw_generation": raw,
        "generation": {
            "generated_token_count": len(token_ids),
            "finish_reason": finish_reason,
            "eos_token_id": None,
            "generated_token_ids": token_ids,
            "harmony_prefix": True,
            "harmony_final": True,
        },
    }
    path = tmp_path / "predictions.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    evidence = rescore_source_gate_predictions(
        records=[records[0]], prediction_path=path, contract=_contract()
    )

    assert evidence.summary.parsed_count == 1
    assert evidence.summary.passed_count == 0


def test_gate_evidence_rejects_substituted_order_and_nan(tmp_path):
    records, _valid_json = _gate_records()
    prediction_path = tmp_path / "predictions.jsonl"
    row = {
        "id": records[1].record_id,
        "raw_generation": "not-json",
        "parsed_output": None,
        "validation_errors": [],
        "generation": {
            "generated_token_count": 1,
            "finish_reason": "length",
            "eos_token_id": None,
            "generated_token_ids": [1],
            "harmony_prefix": False,
            "harmony_final": False,
        },
    }
    prediction_path.write_text(
        json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="id/order mismatch"):
        rescore_source_gate_predictions(
            records=records, prediction_path=prediction_path, contract=_contract()
        )

    prediction_path.write_text(
        '{"id":"record-a","raw_generation":NaN}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="invalid gate prediction JSON"):
        rescore_source_gate_predictions(
            records=records, prediction_path=prediction_path, contract=_contract()
        )


def test_gate_evidence_rejects_oversized_newline_free_record(tmp_path):
    records, _valid_json = _gate_records()
    prediction_path = tmp_path / "predictions.jsonl"
    prediction_path.write_bytes(b"x" * (MAX_GATE_PREDICTION_LINE_BYTES + 1))

    with pytest.raises(ValueError, match="line exceeds"):
        rescore_source_gate_predictions(
            records=records, prediction_path=prediction_path, contract=_contract()
        )


def test_gate_evidence_rejects_symlinked_prediction_parent(tmp_path):
    records, _valid_json = _gate_records()
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    (real_parent / "predictions.jsonl").write_text("{}\n", encoding="utf-8")
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="traverse a symlink"):
        rescore_source_gate_predictions(
            records=records,
            prediction_path=linked_parent / "predictions.jsonl",
            contract=_contract(),
        )


def test_gate_rescore_rejects_tampered_termination_evidence(tmp_path):
    records, valid_json = _gate_records()
    row = {
        "id": records[0].record_id,
        "raw_generation": (
            HARMONY_ANALYSIS_PREFIX + "brief" + HARMONY_FINAL_MARKER + valid_json
        ),
        "generation": {
            "generated_token_count": 2,
            "generated_token_ids": [1, 200002],
            "finish_reason": "eos",
            "eos_token_id": 200002,
            "harmony_prefix": True,
            "harmony_final": True,
        },
    }
    path = tmp_path / "predictions.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="raw EOS marker"):
        rescore_source_gate_predictions(
            records=[records[0]], prediction_path=path, contract=_contract()
        )


@pytest.mark.parametrize("token_ids", [[1], [-1]])
def test_gate_rescore_rejects_unclaimed_raw_eos_or_negative_ids(tmp_path, token_ids):
    records, valid_json = _gate_records()
    row = {
        "id": records[0].record_id,
        "raw_generation": (
            HARMONY_ANALYSIS_PREFIX
            + "brief"
            + HARMONY_FINAL_MARKER
            + valid_json
            + "<|return|>"
        ),
        "generation": {
            "generated_token_count": 1,
            "generated_token_ids": token_ids,
            "finish_reason": "unknown",
            "eos_token_id": None,
            "harmony_prefix": True,
            "harmony_final": True,
        },
    }
    path = tmp_path / "predictions.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="token IDs|raw EOS marker"):
        rescore_source_gate_predictions(
            records=[records[0]], prediction_path=path, contract=_contract()
        )


def test_extract_harmony_final_only_strips_a_trailing_terminator():
    raw = (
        HARMONY_ANALYSIS_PREFIX
        + "brief"
        + HARMONY_FINAL_MARKER
        + '{"limitations":["literal <|return|> marker"]}'
        + "<|return|>"
    )

    assert extract_harmony_final(raw) == '{"limitations":["literal <|return|> marker"]}'
