import json
import sys
from pathlib import Path

import torch
import pytest
from safetensors.torch import save_file

from scripts import diagnose_source_canary as diagnose


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path):
    secret = "RAW-SOURCE-AND-SECRET-SENTINEL"
    predictions = tmp_path / "predictions.jsonl"
    rows = [
        {
            "id": "private-record-id-1",
            "raw_generation": (
                diagnose.HARMONY_ANALYSIS_PREFIX
                + diagnose.HARMONY_FINAL_MARKER
                + "{}"
                + diagnose.HARMONY_EOS
            ),
            "parsed_output": {"assessment": "not_observed"},
            "validation_errors": [],
        },
        {
            "id": "private-record-id-2",
            "raw_generation": (
                "<|end|><|start|>"
                + diagnose.HARMONY_FINAL_MARKER
                + secret
                + diagnose.HARMONY_EOS
                + diagnose.HARMONY_EOS
            ),
            "parsed_output": {"assessment": "not_observed"},
            "validation_errors": ["scope contained " + secret],
        },
        {
            "id": "private-record-id-3",
            "raw_generation": "x" * 8,
            "parsed_output": None,
            "validation_errors": ["invalid JSON: Expecting value " + secret],
        },
        {
            "id": "private-record-id-4",
            "raw_generation": "bad" + diagnose.HARMONY_EOS,
            "parsed_output": None,
            "validation_errors": ["invalid JSON: Extra data " + secret],
        },
    ]
    predictions.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    gate = tmp_path / "gate.json"
    _write_json(
        gate,
        {
            "record_count": 4,
            "schema_pass_rate": 0.25,
            "minimum_schema_pass_rate": 0.9,
            "passed": False,
            "adapter_reload": True,
            "max_new_tokens": 8,
        },
    )
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    adapter_file = adapter_dir / "adapter_model.safetensors"
    save_file(
        {
            "base_model.model.layers.1.self_attn.q_proj.lora_A.weight": torch.ones(
                1, 2
            ),
            "base_model.model.layers.1.mlp.experts.down_projs.0.lora_B.weight": (
                torch.tensor([[1.0, float("nan")]])
            ),
        },
        adapter_file,
    )
    manifest = tmp_path / "manifest.json"
    _write_json(
        manifest,
        {
            "validation_record_count": 4,
            "adapter_sha256": diagnose._file_sha256(adapter_file),
        },
    )
    checkpoints = []
    for step, tensor in ((25, torch.zeros(1)), (125, torch.ones(1))):
        checkpoint = tmp_path / f"checkpoint-{step}"
        checkpoint.mkdir()
        save_file({"weight": tensor}, checkpoint / "adapter_model.safetensors")
        _write_json(checkpoint / "trainer_state.json", {"global_step": step})
        checkpoints.append(checkpoint)
    return secret, predictions, gate, manifest, adapter_dir, checkpoints


def test_diagnosis_is_aggregate_source_free_and_wandb_safe(tmp_path):
    secret, predictions, gate, manifest, adapter, checkpoints = _fixture(tmp_path)

    report = diagnose.diagnose_source_canary(
        predictions_path=predictions,
        gate_report_path=gate,
        manifest_path=manifest,
        adapter_path=adapter,
        checkpoint_paths=list(reversed(checkpoints)),
        token_counter=len,
    )

    analysis = report["prediction_analysis"]
    assert analysis["taxonomy"] == {
        "valid": 1,
        "parsed_contract_invalid": 1,
        "unparsed_with_eos": 1,
        "unparsed_no_eos": 1,
    }
    assert analysis["parse_error_categories"]["expecting_value"] == 1
    assert analysis["parse_error_categories"]["extra_data"] == 1
    assert analysis["harmony"]["canonical_prefix"] == 1
    assert analysis["harmony"]["premature_end_start"] == 1
    assert analysis["mode_collapse"]["all_parsed_same_valid_assessment"] is True
    assert report["adapter"]["tensor_count"] == 2
    assert report["adapter"]["expert_tensor_count"] == 1
    assert report["adapter"]["attention_tensor_count"] == 1
    assert report["adapter"]["nonfinite_element_count"] == 1
    assert report["adapter"]["all_finite"] is False
    assert [item["global_step"] for item in report["checkpoints"]] == [25, 125]
    assert report["consistency"]["gate_record_count_matches_predictions"] is True
    assert report["consistency"]["gate_schema_rate_matches_valid_count"] is True

    serialized = json.dumps(report, allow_nan=False)
    assert secret not in serialized
    assert "private-record-id" not in serialized
    assert "scope contained" not in serialized
    assert str(predictions) not in serialized
    diagnose.validate_wandb_payload(report["wandb_safe_summary"])


def test_cli_writes_only_safe_aggregate_json(tmp_path, monkeypatch, capsys):
    secret, predictions, gate, manifest, adapter, checkpoints = _fixture(tmp_path)
    output = tmp_path / "diagnosis.json"
    monkeypatch.setattr(diagnose, "_load_token_counter", lambda _path: len)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "diagnose_source_canary.py",
            "--predictions",
            str(predictions),
            "--gate-report",
            str(gate),
            "--manifest",
            str(manifest),
            "--adapter",
            str(adapter),
            "--checkpoint",
            str(checkpoints[0]),
            "--output",
            str(output),
        ],
    )

    diagnose.main()

    text = output.read_text(encoding="utf-8")
    assert secret not in text
    assert "private-record-id" not in text
    assert json.loads(text)["privacy"]["raw_generation_included"] is False
    console = capsys.readouterr().out
    assert secret not in console
    assert "records=4 valid=1" in console


def test_invalid_prediction_shape_does_not_echo_value(tmp_path):
    secret = "DO-NOT-ECHO-THIS-RAW-VALUE"
    path = tmp_path / "predictions.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "record",
                "raw_generation": {"secret": secret},
                "parsed_output": None,
                "validation_errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        diagnose._load_prediction_rows(path)
    except ValueError as exc:
        assert secret not in str(exc)
    else:
        raise AssertionError("invalid raw_generation was accepted")


def test_prediction_loader_rejects_duplicate_ids_and_nonfinite_json(tmp_path):
    path = tmp_path / "predictions.jsonl"
    row = {
        "id": "duplicate",
        "raw_generation": "raw",
        "parsed_output": None,
        "validation_errors": [],
    }
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")

    with pytest.raises(ValueError, match="duplicate id"):
        diagnose._load_prediction_rows(path)

    path.write_text(
        '{"id":"record","raw_generation":"raw","parsed_output":NaN,'
        '"validation_errors":[]}\n'
    )
    with pytest.raises(ValueError, match="invalid JSON"):
        diagnose._load_prediction_rows(path)


def test_prediction_loader_bounds_newline_free_and_total_input(tmp_path, monkeypatch):
    path = tmp_path / "predictions.jsonl"
    path.write_bytes(b"x" * (diagnose.MAX_JSON_BYTES + 1))

    with pytest.raises(ValueError, match="line 1 exceeds"):
        diagnose._load_prediction_rows(path)

    rows = [
        {
            "id": f"record-{index}",
            "raw_generation": "raw",
            "parsed_output": None,
            "validation_errors": [],
        }
        for index in range(2)
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(diagnose, "MAX_PREDICTION_BYTES", 1)

    with pytest.raises(ValueError, match="total size"):
        diagnose._load_prediction_rows(path)


def test_prediction_loader_bounds_record_count(tmp_path, monkeypatch):
    path = tmp_path / "predictions.jsonl"
    rows = [
        {
            "id": f"record-{index}",
            "raw_generation": "raw",
            "parsed_output": None,
            "validation_errors": [],
        }
        for index in range(2)
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(diagnose, "MAX_PREDICTION_RECORDS", 1)

    with pytest.raises(ValueError, match="record count"):
        diagnose._load_prediction_rows(path)


def test_object_loader_uses_a_bounded_single_read(tmp_path, monkeypatch):
    path = tmp_path / "gate.json"
    path.write_bytes(b"{" + b" " * 32 + b"}")
    monkeypatch.setattr(diagnose, "MAX_JSON_BYTES", 8)

    with pytest.raises(ValueError, match="gate report exceeds the size limit"):
        diagnose._load_object(path, "gate report")


def test_cli_rejects_output_input_collision(tmp_path, monkeypatch):
    secret, predictions, gate, manifest, adapter, _checkpoints = _fixture(tmp_path)
    del secret
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "diagnose_source_canary.py",
            "--predictions",
            str(predictions),
            "--gate-report",
            str(gate),
            "--manifest",
            str(manifest),
            "--adapter",
            str(adapter),
            "--output",
            str(predictions),
        ],
    )

    with pytest.raises(SystemExit):
        diagnose.main()


def test_prediction_loader_rejects_symlinked_parent(tmp_path):
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    prediction = real_parent / "predictions.jsonl"
    prediction.write_text(
        json.dumps(
            {
                "id": "record",
                "raw_generation": "raw",
                "parsed_output": None,
                "validation_errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="traverse a symlink"):
        diagnose._load_prediction_rows(linked_parent / prediction.name)


def test_adapter_loader_rejects_symlinked_parent(tmp_path):
    real_parent = tmp_path / "real"
    adapter_dir = real_parent / "adapter"
    adapter_dir.mkdir(parents=True)
    save_file({"weight": torch.ones(1)}, adapter_dir / "adapter_model.safetensors")
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="traverse a symlink"):
        diagnose._adapter_locations(linked_parent / "adapter")
