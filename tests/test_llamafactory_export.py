from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from aegislm.training.llamafactory import (
    build_dataset_info_entry,
    export_llamafactory_records,
    load_jsonl_records,
    write_llamafactory_dataset,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_phase_c_records.jsonl"


def test_export_llamafactory_records_uses_aegislm_safety_gate() -> None:
    record = json.loads(FIXTURE_PATH.read_text(encoding="utf-8").splitlines()[0])
    record["metadata"]["split"] = "train"

    exported = export_llamafactory_records([record])

    assert len(exported) == 1
    assert exported[0]["system"].startswith("You are AegisLM")
    assert "Record ID:" in exported[0]["instruction"]
    assert exported[0]["input"] == ""
    assert json.loads(exported[0]["output"]) == record["expected_output"]


def test_export_llamafactory_records_can_skip_ineligible_records() -> None:
    eligible = json.loads(FIXTURE_PATH.read_text(encoding="utf-8").splitlines()[0])
    eligible["metadata"]["split"] = "train"

    ineligible = deepcopy(eligible)
    ineligible["metadata"]["split"] = "fixture"

    exported = export_llamafactory_records(
        [eligible, ineligible],
        ignore_errors=True,
    )

    assert len(exported) == 1


def test_write_llamafactory_dataset_json_and_jsonl(tmp_path: Path) -> None:
    records = [{"system": "s", "instruction": "i", "input": "", "output": "{}"}]

    json_path = tmp_path / "dataset.json"
    jsonl_path = tmp_path / "dataset.jsonl"

    write_llamafactory_dataset(records, json_path)
    write_llamafactory_dataset(records, jsonl_path)

    assert json.loads(json_path.read_text(encoding="utf-8")) == records
    assert json.loads(jsonl_path.read_text(encoding="utf-8").strip()) == records[0]


def test_load_jsonl_records_and_dataset_info_entry(tmp_path: Path) -> None:
    source = tmp_path / "records.jsonl"
    source.write_text('{"id": "one"}\n{"id": "two"}\n', encoding="utf-8")

    assert [record["id"] for record in load_jsonl_records(source)] == ["one", "two"]

    entry = build_dataset_info_entry(
        dataset_name="aegislm_security_sft",
        file_name="aegislm_security_sft.json",
    )
    assert entry["aegislm_security_sft"]["columns"]["system"] == "system"
