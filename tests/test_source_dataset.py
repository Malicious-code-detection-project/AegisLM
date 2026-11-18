import json
import hashlib

import pytest

from aegislm.datasets.source import (
    load_source_gold,
    load_source_records,
    records_sha256,
    select_source_train_canary,
    select_stratified_canary,
    select_target_cwe_assessment_canary,
    validate_source_split_integrity,
)
from aegislm.datasets.source import parse_source_record


def _record(record_id: str, assessment: str = "present") -> dict:
    output = {
        "schema_version": "aegislm.source-vulnerability-assessment.v2",
        "scope": {"boundary": "supplied_function", "target_cwe": "CWE-120"},
        "assessment": assessment,
        "assessment_basis": [
            {
                "code_spans": ["copy(dst, src);"],
                "relationship": "The copy is not bounded.",
                "conclusion": "The scoped condition is present.",
                "confidence": "high",
            }
        ],
        "findings": (
            [
                {
                    "code_spans": ["copy(dst, src);"],
                    "operation": "Unbounded copy.",
                    "evidence": "The destination size is not checked.",
                    "confidence": "high",
                }
            ]
            if assessment == "present"
            else []
        ),
        "limitations": ["Function-local assessment only."],
        "recommendations": ["Confirm with deterministic analysis."],
    }
    return {
        "id": record_id,
        "code_sha256": hashlib.sha256(b"copy(dst, src);").hexdigest(),
        "messages": [
            {"role": "system", "content": "Return JSON."},
            {
                "role": "user",
                "content": (
                    'Assess.\n{"scope":{"boundary":"supplied_function",'
                    '"target_cwe":"CWE-120"},"source_code":"copy(dst, src);"}\n'
                    "Return JSON."
                ),
            },
            {"role": "assistant", "content": json.dumps(output)},
        ],
    }


def _record_with_cwe(record_id: str, assessment: str, cwe: str) -> dict:
    record = _record(record_id, assessment)
    payload = {
        "scope": {"boundary": "supplied_function", "target_cwe": cwe},
        "source_code": "copy(dst, src);",
    }
    record["messages"][1]["content"] = f"Assess.\n{json.dumps(payload)}\nReturn JSON."
    output = json.loads(record["messages"][2]["content"])
    output["scope"]["target_cwe"] = cwe
    record["messages"][2]["content"] = json.dumps(output)
    return record


def test_load_source_records_and_digest(tmp_path):
    path = tmp_path / "train.jsonl"
    path.write_text(json.dumps(_record("one")) + "\n", encoding="utf-8")

    records = load_source_records(path, require_assistant=True)

    assert records[0].target_cwe == "CWE-120"
    assert records[0].source_code == "copy(dst, src);"
    assert records[0].assessment == "present"
    assert records_sha256(records) == records_sha256(records)


def test_load_source_records_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "train.jsonl"
    line = json.dumps(_record("same"))
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate id"):
        load_source_records(path, require_assistant=True)


def test_load_source_records_rejects_forged_source_digest(tmp_path):
    path = tmp_path / "train.jsonl"
    record = _record("forged")
    record["code_sha256"] = "a" * 64
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        load_source_records(path, require_assistant=True)


def test_source_split_integrity_rejects_id_and_source_leakage():
    train = parse_source_record(_record("shared-id"), require_assistant=True)
    same_id = parse_source_record(_record("shared-id"), require_assistant=True)
    same_source = parse_source_record(_record("different-id"), require_assistant=True)

    with pytest.raises(ValueError, match="record id"):
        validate_source_split_integrity([train], [same_id])
    with pytest.raises(ValueError, match="source code"):
        validate_source_split_integrity([train], [same_source])


@pytest.mark.parametrize(
    "record_id", ["", "contains space", "../escape", "source();", "a" * 129]
)
def test_source_records_reject_unsafe_record_ids(record_id):
    from aegislm.datasets.source import parse_source_record

    with pytest.raises(ValueError, match="safe identifier"):
        parse_source_record(_record(record_id), require_assistant=True)


def test_source_records_reject_source_text_as_target_cwe():
    from aegislm.datasets.source import parse_source_record

    record = _record("safe-id")
    record["messages"][1]["content"] = (
        '{"scope":{"target_cwe":"int private_source(void);"},'
        '"source_code":"copy(dst, src);"}'
    )

    with pytest.raises(ValueError, match="must be a CWE ID"):
        parse_source_record(record, require_assistant=True)


def test_stratified_canary_is_deterministic(tmp_path):
    path = tmp_path / "train.jsonl"
    raw = [_record(f"p{index}", "present") for index in range(4)] + [
        _record(f"n{index}", "not_observed") for index in range(4)
    ]
    path.write_text(
        "\n".join(json.dumps(item) for item in raw) + "\n", encoding="utf-8"
    )
    records = load_source_records(path, require_assistant=True)

    first = select_stratified_canary(records, 4, seed=3407)
    second = select_stratified_canary(records, 4, seed=3407)

    assert [record.record_id for record in first] == [
        record.record_id for record in second
    ]
    assert {record.assessment for record in first} == {"present", "not_observed"}


def test_target_cwe_assessment_canary_is_deterministic_and_nonmutating(tmp_path):
    path = tmp_path / "train.jsonl"
    raw = [
        _record_with_cwe(f"{cwe}-{label}-{index}", label, cwe)
        for cwe in ("CWE-120", "CWE-78", "CWE-190")
        for label in ("present", "not_observed")
        for index in range(3)
    ]
    path.write_text(
        "\n".join(json.dumps(item) for item in raw) + "\n", encoding="utf-8"
    )
    records = load_source_records(path, require_assistant=True)
    original_ids = [record.record_id for record in records]

    first = select_target_cwe_assessment_canary(records, 12, seed=3407)
    second = select_source_train_canary(
        records,
        12,
        seed=3407,
        strategy="target_cwe_assessment_round_robin_v1",
    )

    first_ids = [record.record_id for record in first]
    assert first_ids == [record.record_id for record in second]
    assert len(first_ids) == len(set(first_ids)) == 12
    assert [record.record_id for record in records] == original_ids
    counts: dict[tuple[str, str | None], int] = {}
    for record in first:
        key = (record.target_cwe, record.assessment)
        counts[key] = counts.get(key, 0) + 1
    assert set(counts.values()) == {2}


def test_target_cwe_assessment_canary_requires_every_stratum(tmp_path):
    path = tmp_path / "train.jsonl"
    raw = [
        _record_with_cwe("one", "present", "CWE-120"),
        _record_with_cwe("two", "not_observed", "CWE-120"),
    ]
    path.write_text(
        "\n".join(json.dumps(item) for item in raw) + "\n", encoding="utf-8"
    )
    records = load_source_records(path, require_assistant=True)

    with pytest.raises(ValueError, match="cover every observed stratum"):
        select_target_cwe_assessment_canary(records, 1, seed=3407)


def test_source_train_canary_rejects_unknown_strategy(tmp_path):
    path = tmp_path / "train.jsonl"
    path.write_text(json.dumps(_record("one")) + "\n", encoding="utf-8")
    records = load_source_records(path, require_assistant=True)

    with pytest.raises(ValueError, match="unsupported source train selection"):
        select_source_train_canary(records, 1, seed=3407, strategy="unknown")


def test_load_source_gold_keeps_gold_separate(tmp_path):
    path = tmp_path / "gold.jsonl"
    path.write_text(
        json.dumps({"id": "one", "expected_output": {"assessment": "present"}}) + "\n",
        encoding="utf-8",
    )

    assert load_source_gold(path) == {"one": {"assessment": "present"}}
