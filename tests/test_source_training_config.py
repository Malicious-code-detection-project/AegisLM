import hashlib
import json

import pytest

from aegislm.datasets.source import parse_source_record
from aegislm.training.source_config import load_source_training_config
from aegislm.training.source_config import (
    artifact_directory_sha256,
    create_exclusive_artifact_directory,
    load_canary_gate_report,
    reserve_training_stage,
    resolved_source_generation_contract,
    source_protocol_config,
    source_protocol_sha256,
    source_train_selection_strategy,
    source_training_config_sha256,
    source_training_recipe,
    validate_canary_gate_report,
    validate_source_training_paths,
)
from aegislm.training.source_gate import (
    HARMONY_ANALYSIS_PREFIX,
    HARMONY_FINAL_MARKER,
    canary_gate_evidence_fields,
    rescore_source_gate_predictions,
)


def _config() -> dict:
    return {
        "model": {
            "base_model_id": "openai/gpt-oss-20b",
            "runtime_model_id": "unsloth/gpt-oss-20b-unsloth-bnb-4bit",
            "revision": "1" * 40,
            "cache_dir": "models/cache",
        },
        "dataset": {
            "train_path": "data/train.jsonl",
            "train_sha256": "a" * 64,
            "validation_path": "data/validation.jsonl",
            "validation_sha256": "b" * 64,
        },
        "training": {
            "output_dir": "adapters/source",
            "checkpoint_dir": "checkpoints/source",
            "max_seq_length": 2048,
            "batch_size": 2,
            "eval_batch_size": 2,
            "gradient_accumulation_steps": 4,
            "epochs": 1,
            "learning_rate": 0.0002,
            "warmup_ratio": 0.03,
            "lr_scheduler_type": "cosine",
            "optimizer": "adamw_8bit",
            "weight_decay": 0.01,
            "lora_r": 8,
            "lora_alpha": 16,
            "lora_dropout": 0.05,
            "attention_target_modules": ["q_proj"],
            "expert_target_layers": [7, 15, 23],
            "eval_steps": 100,
            "save_steps": 100,
            "save_total_limit": 3,
            "seed": 3407,
        },
        "canary": {
            "train_size": 1000,
            "validation_size": 40,
            "minimum_schema_pass_rate": 0.9,
            "generation_batch_size": 8,
            "max_new_tokens": 512,
        },
    }


def test_source_training_config_is_strict(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_config()), encoding="utf-8")

    loaded = load_source_training_config(path)

    assert loaded["training"]["expert_target_layers"] == [7, 15, 23]
    assert source_training_recipe(loaded) == "legacy_unsloth"
    assert source_protocol_config(loaded)["reasoning_effort"] == "medium"
    assert source_train_selection_strategy(loaded) == "assessment_round_robin_v1"


def test_source_training_config_accepts_versioned_train_selector(tmp_path):
    config = _config()
    config["canary"]["train_selection_strategy"] = (
        "target_cwe_assessment_round_robin_v1"
    )
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    loaded = load_source_training_config(path)

    assert (
        source_train_selection_strategy(loaded)
        == "target_cwe_assessment_round_robin_v1"
    )


def test_source_training_config_rejects_unknown_keys(tmp_path):
    config = _config()
    config["training"]["packing"] = True
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="Additional properties"):
        load_source_training_config(path)


def test_source_training_config_rejects_nonstandard_numeric_constants(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(_config()).replace(
            '"minimum_schema_pass_rate": 0.9', '"minimum_schema_pass_rate": NaN'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid source-v2 training config JSON"):
        load_source_training_config(path)


def test_source_training_config_rejects_exponent_overflow(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(_config()).replace(
            '"learning_rate": 0.0002', '"learning_rate": 1e999'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid source-v2 training config JSON"):
        load_source_training_config(path)


def test_canary_gate_report_loader_is_bounded_and_rejects_nan(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text('{"schema_pass_rate": NaN}', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid canary gate report"):
        load_canary_gate_report(path)

    path.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="byte limit"):
        load_canary_gate_report(path)


def test_canary_gate_report_loader_rejects_nested_exponent_overflow(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text('{"extra":{"overflow":1e309}}', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid canary gate report"):
        load_canary_gate_report(path)


def test_exclusive_artifact_directory_rejects_protected_containment(tmp_path):
    protected = tmp_path / "adapter"
    protected.mkdir()

    with pytest.raises(ValueError, match="protected input"):
        create_exclusive_artifact_directory(
            protected / "gate", forbidden_roots=(protected,)
        )


def test_exclusive_artifact_directory_rejects_symlinked_parent(tmp_path):
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        create_exclusive_artifact_directory(linked_parent / "stage")

    assert not (real_parent / "stage").exists()


def test_artifact_directory_digest_rejects_symlinks(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(b"weights")
    outside = tmp_path / "outside"
    outside.write_text("outside", encoding="utf-8")
    (adapter / "linked").symlink_to(outside)

    with pytest.raises(ValueError, match="symlinks"):
        artifact_directory_sha256(adapter)


def test_artifact_directory_digest_rejects_symlinked_parent(tmp_path):
    real_parent = tmp_path / "real-parent"
    adapter = real_parent / "adapter"
    adapter.mkdir(parents=True)
    (adapter / "adapter_model.safetensors").write_bytes(b"weights")
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="traverse a symlink"):
        artifact_directory_sha256(linked_parent / "adapter")


def test_training_stage_reservation_rejects_rerun_and_unsafe_resume(tmp_path):
    adapter_stage = tmp_path / "adapters" / "canary"
    checkpoint_stage = tmp_path / "checkpoints" / "canary"
    digest = "a" * 64

    reserve_training_stage(
        adapter_stage=adapter_stage,
        checkpoint_stage=checkpoint_stage,
        resume_from_checkpoint=None,
        config_sha256=digest,
        stage="canary",
    )
    checkpoint = checkpoint_stage / "checkpoint-1"
    checkpoint.mkdir()
    (checkpoint / "trainer_state.json").write_bytes(b"original-checkpoint")
    final_adapter = adapter_stage / "final" / "adapter_model.safetensors"
    final_adapter.parent.mkdir()
    final_adapter.write_bytes(b"original-adapter")
    reservation = adapter_stage / ".aegislm-stage-reservation.json"
    checkpoint_reservation = checkpoint_stage / ".aegislm-stage-reservation.json"
    assert checkpoint_reservation.is_file()
    original_reservation = reservation.read_bytes()
    original_checkpoint = (checkpoint / "trainer_state.json").read_bytes()
    original_checkpoint_reservation = checkpoint_reservation.read_bytes()
    original_adapter = final_adapter.read_bytes()

    with pytest.raises(FileExistsError, match="already exists"):
        reserve_training_stage(
            adapter_stage=adapter_stage,
            checkpoint_stage=checkpoint_stage,
            resume_from_checkpoint=None,
            config_sha256=digest,
            stage="canary",
        )
    assert reservation.read_bytes() == original_reservation
    assert (checkpoint / "trainer_state.json").read_bytes() == original_checkpoint
    assert checkpoint_reservation.read_bytes() == original_checkpoint_reservation
    assert final_adapter.read_bytes() == original_adapter
    with pytest.raises(FileExistsError, match="finalized or mixed"):
        reserve_training_stage(
            adapter_stage=adapter_stage,
            checkpoint_stage=checkpoint_stage,
            resume_from_checkpoint=tmp_path,
            config_sha256=digest,
            stage="canary",
        )


@pytest.mark.parametrize(
    ("adapter_suffix", "checkpoint_suffix"),
    [
        ("stage", "stage"),
        ("stage", "stage/nested/checkpoints"),
        ("stage/nested/adapters", "stage"),
    ],
)
def test_training_stage_reservation_rejects_overlapping_roots(
    tmp_path, adapter_suffix, checkpoint_suffix
):
    adapter_stage = tmp_path / adapter_suffix
    checkpoint_stage = tmp_path / checkpoint_suffix

    with pytest.raises(ValueError, match="must not overlap"):
        reserve_training_stage(
            adapter_stage=adapter_stage,
            checkpoint_stage=checkpoint_stage,
            resume_from_checkpoint=None,
            config_sha256="a" * 64,
            stage="canary",
        )

    assert not adapter_stage.exists()


def test_training_stage_reservation_exclusively_claims_shared_checkpoint(tmp_path):
    checkpoint_stage = tmp_path / "checkpoints" / "canary"
    first_adapter = tmp_path / "adapters" / "first"
    second_adapter = tmp_path / "adapters" / "second"

    reserve_training_stage(
        adapter_stage=first_adapter,
        checkpoint_stage=checkpoint_stage,
        resume_from_checkpoint=None,
        config_sha256="a" * 64,
        stage="canary",
    )

    assert (checkpoint_stage / ".aegislm-stage-reservation.json").is_file()
    with pytest.raises(FileExistsError, match="already exists"):
        reserve_training_stage(
            adapter_stage=second_adapter,
            checkpoint_stage=checkpoint_stage,
            resume_from_checkpoint=None,
            config_sha256="a" * 64,
            stage="canary",
        )
    assert not second_adapter.exists()


def test_training_stage_reservation_never_removes_preexisting_adapter(tmp_path):
    adapter_stage = tmp_path / "adapters" / "existing"
    checkpoint_stage = tmp_path / "checkpoints" / "new"
    adapter_stage.mkdir(parents=True)

    with pytest.raises(FileExistsError, match="adapter stage already exists"):
        reserve_training_stage(
            adapter_stage=adapter_stage,
            checkpoint_stage=checkpoint_stage,
            resume_from_checkpoint=None,
            config_sha256="a" * 64,
            stage="canary",
        )

    assert adapter_stage.is_dir()
    assert list(adapter_stage.iterdir()) == []
    assert not checkpoint_stage.exists()


def test_training_stage_resume_rejects_symlinked_checkpoint_stage(tmp_path):
    adapter_stage = tmp_path / "adapters" / "canary"
    checkpoint_stage = tmp_path / "checkpoints" / "canary"
    reserve_training_stage(
        adapter_stage=adapter_stage,
        checkpoint_stage=checkpoint_stage,
        resume_from_checkpoint=None,
        config_sha256="a" * 64,
        stage="canary",
    )
    real_stage = tmp_path / "real-checkpoints"
    checkpoint_stage.rename(real_stage)
    checkpoint_stage.symlink_to(real_stage, target_is_directory=True)

    with pytest.raises(ValueError, match="traverse a symlink"):
        reserve_training_stage(
            adapter_stage=adapter_stage,
            checkpoint_stage=checkpoint_stage,
            resume_from_checkpoint=checkpoint_stage / "checkpoint-1",
            config_sha256="a" * 64,
            stage="canary",
        )


@pytest.mark.parametrize("linked_root", ["adapters", "checkpoints"])
def test_training_stage_resume_rejects_symlinked_parent(tmp_path, linked_root):
    adapter_stage = tmp_path / "adapters" / "canary"
    checkpoint_stage = tmp_path / "checkpoints" / "canary"
    reserve_training_stage(
        adapter_stage=adapter_stage,
        checkpoint_stage=checkpoint_stage,
        resume_from_checkpoint=None,
        config_sha256="a" * 64,
        stage="canary",
    )
    checkpoint = checkpoint_stage / "checkpoint-1"
    checkpoint.mkdir()
    (checkpoint / "trainer_state.json").write_text("{}", encoding="utf-8")
    original_parent = tmp_path / linked_root
    real_parent = tmp_path / f"real-{linked_root}"
    original_parent.rename(real_parent)
    original_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="traverse a symlink"):
        reserve_training_stage(
            adapter_stage=tmp_path / "adapters" / "canary",
            checkpoint_stage=tmp_path / "checkpoints" / "canary",
            resume_from_checkpoint=tmp_path / "checkpoints" / "canary" / "checkpoint-1",
            config_sha256="a" * 64,
            stage="canary",
        )


def test_training_stage_resume_rejects_symlinked_trainer_state(tmp_path):
    adapter_stage = tmp_path / "adapters" / "canary"
    checkpoint_stage = tmp_path / "checkpoints" / "canary"
    reserve_training_stage(
        adapter_stage=adapter_stage,
        checkpoint_stage=checkpoint_stage,
        resume_from_checkpoint=None,
        config_sha256="a" * 64,
        stage="canary",
    )
    checkpoint = checkpoint_stage / "checkpoint-1"
    checkpoint.mkdir()
    outside_state = tmp_path / "trainer_state.json"
    outside_state.write_text("{}", encoding="utf-8")
    (checkpoint / "trainer_state.json").symlink_to(outside_state)

    with pytest.raises(ValueError, match="only real files/directories"):
        reserve_training_stage(
            adapter_stage=adapter_stage,
            checkpoint_stage=checkpoint_stage,
            resume_from_checkpoint=checkpoint,
            config_sha256="a" * 64,
            stage="canary",
        )


@pytest.mark.parametrize("sibling_kind", ["file", "symlink"])
def test_training_stage_resume_rejects_non_directory_checkpoint_sibling(
    tmp_path, sibling_kind
):
    adapter_stage = tmp_path / "adapters" / "canary"
    checkpoint_stage = tmp_path / "checkpoints" / "canary"
    reserve_training_stage(
        adapter_stage=adapter_stage,
        checkpoint_stage=checkpoint_stage,
        resume_from_checkpoint=None,
        config_sha256="a" * 64,
        stage="canary",
    )
    checkpoint = checkpoint_stage / "checkpoint-1"
    checkpoint.mkdir()
    (checkpoint / "trainer_state.json").write_text("{}", encoding="utf-8")
    sibling = checkpoint_stage / "checkpoint-2"
    if sibling_kind == "file":
        sibling.write_text("not a checkpoint directory", encoding="utf-8")
    else:
        outside = tmp_path / "outside-checkpoint"
        outside.mkdir()
        sibling.symlink_to(outside, target_is_directory=True)

    with pytest.raises(FileExistsError, match="mixed checkpoint stage"):
        reserve_training_stage(
            adapter_stage=adapter_stage,
            checkpoint_stage=checkpoint_stage,
            resume_from_checkpoint=checkpoint,
            config_sha256="a" * 64,
            stage="canary",
        )


def test_training_stage_resume_rejects_symlink_anywhere_in_checkpoint_tree(tmp_path):
    adapter_stage = tmp_path / "adapters" / "canary"
    checkpoint_stage = tmp_path / "checkpoints" / "canary"
    reserve_training_stage(
        adapter_stage=adapter_stage,
        checkpoint_stage=checkpoint_stage,
        resume_from_checkpoint=None,
        config_sha256="a" * 64,
        stage="canary",
    )
    checkpoint = checkpoint_stage / "checkpoint-1"
    nested = checkpoint / "optimizer"
    nested.mkdir(parents=True)
    (checkpoint / "trainer_state.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside-state.bin"
    outside.write_bytes(b"outside")
    (nested / "state.bin").symlink_to(outside)

    with pytest.raises(ValueError, match="only real files/directories"):
        reserve_training_stage(
            adapter_stage=adapter_stage,
            checkpoint_stage=checkpoint_stage,
            resume_from_checkpoint=checkpoint,
            config_sha256="a" * 64,
            stage="canary",
        )


def test_source_training_paths_reject_dataset_drift(tmp_path):
    config = _config()
    train = tmp_path / "train.jsonl"
    validation = tmp_path / "validation.jsonl"
    train.write_text("changed", encoding="utf-8")
    validation.write_text("validation", encoding="utf-8")
    config["dataset"]["train_path"] = str(train)
    config["dataset"]["validation_path"] = str(validation)
    config["model"]["cache_dir"] = str(tmp_path / "cache")
    config["training"]["output_dir"] = str(tmp_path / "adapters")
    config["training"]["checkpoint_dir"] = str(tmp_path / "checkpoints")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        validate_source_training_paths(config)


def test_source_training_paths_reject_symlinked_artifact_parent(tmp_path):
    config = _config()
    train = tmp_path / "train.jsonl"
    validation = tmp_path / "validation.jsonl"
    train.write_text("train", encoding="utf-8")
    validation.write_text("validation", encoding="utf-8")
    config["dataset"].update(
        {
            "train_path": str(train),
            "train_sha256": hashlib.sha256(train.read_bytes()).hexdigest(),
            "validation_path": str(validation),
            "validation_sha256": hashlib.sha256(validation.read_bytes()).hexdigest(),
        }
    )
    real_parent = tmp_path / "real-artifacts"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-artifacts"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    config["model"]["cache_dir"] = str(tmp_path / "cache")
    config["training"]["output_dir"] = str(linked_parent / "adapters")
    config["training"]["checkpoint_dir"] = str(tmp_path / "checkpoints")

    with pytest.raises(ValueError, match="symlink"):
        validate_source_training_paths(config)

    assert not (real_parent / "adapters").exists()


def _promotion_fixture(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = _config()
    config["recipe"] = "unsloth_v2"
    config["protocol"] = {
        "reasoning_effort": "low",
        "padding_side": "left",
        "pad_token_id": 200017,
        "eos_token_ids": [200002, 199999],
        "do_sample": False,
    }
    config["canary"]["generation_batch_size"] = 1
    config["canary"]["validation_size"] = 2
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
    records = [first, second]
    raw = (
        HARMONY_ANALYSIS_PREFIX
        + "brief"
        + HARMONY_FINAL_MARKER
        + json.dumps(output)
        + "<|return|>"
    )
    prediction_path = tmp_path / "predictions.jsonl"
    prediction_rows = [
        {
            "id": record.record_id,
            "raw_generation": raw,
            "parsed_output": None,
            "validation_errors": ["ignored"],
            "generation": {
                "generated_token_count": 10,
                "generated_token_ids": [1] * 9 + [200002],
                "finish_reason": "eos",
                "eos_token_id": 200002,
                "harmony_prefix": True,
                "harmony_final": True,
            },
        }
        for record in records
    ]
    prediction_path.write_text(
        "".join(json.dumps(item) + "\n" for item in prediction_rows),
        encoding="utf-8",
    )
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_model.safetensors").write_bytes(b"weights")
    (adapter_dir / "adapter_config.json").write_text("{}\n", encoding="utf-8")
    (adapter_dir / "tokenizer.json").write_text("{}\n", encoding="utf-8")
    evidence = rescore_source_gate_predictions(
        records=records,
        prediction_path=prediction_path,
        contract=resolved_source_generation_contract(config),
    )
    report = {
        "passed": True,
        "adapter_reload": True,
        "recipe": "unsloth_v2",
        "protocol_sha256": source_protocol_sha256(config),
        "config_sha256": source_training_config_sha256(config),
        "train_records_sha256": "train-records",
        "validation_records_sha256": "validation-records",
        "runtime_model_id": config["model"]["runtime_model_id"],
        "runtime_model_revision": config["model"]["revision"],
        "prediction_path": str(prediction_path),
        "minimum_schema_pass_rate": 0.9,
        "generation_batch_size": 1,
        "max_new_tokens": 512,
        **canary_gate_evidence_fields(
            summary=evidence.summary,
            predictions_sha256=evidence.predictions_sha256,
            adapter_artifact_sha256=artifact_directory_sha256(adapter_dir),
        ),
    }
    return config, report, records, prediction_path, adapter_dir


def _validate_fixture(config, report, records, prediction_path, adapter_dir):
    return validate_canary_gate_report(
        report,
        config,
        train_records_sha256="train-records",
        validation_records_sha256="validation-records",
        adapter_dir=adapter_dir,
        prediction_path=prediction_path,
        validation_records=records,
    )


def test_full_gate_rejects_failed_or_stale_report(tmp_path):
    config, report, records, prediction_path, adapter_dir = _promotion_fixture(tmp_path)

    summary = _validate_fixture(config, report, records, prediction_path, adapter_dir)
    assert summary.passed_count == 2
    report["passed"] = False
    with pytest.raises(ValueError, match="passing canary"):
        _validate_fixture(config, report, records, prediction_path, adapter_dir)


@pytest.mark.parametrize("rate", [True, float("nan"), float("inf"), 2.0, -0.1])
def test_full_gate_rejects_boolean_or_nonfinite_rate(tmp_path, rate):
    config, report, records, prediction_path, adapter_dir = _promotion_fixture(tmp_path)
    report["schema_pass_rate"] = rate

    with pytest.raises(ValueError, match="schema_pass_rate"):
        _validate_fixture(config, report, records, prediction_path, adapter_dir)


def test_nonlegacy_recipe_requires_explicit_protocol_and_strict_gate(tmp_path):
    config = _config()
    config["recipe"] = "unsloth_v2"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="protocol is required"):
        load_source_training_config(path)

    config["protocol"] = {
        "reasoning_effort": "low",
        "padding_side": "left",
        "pad_token_id": 200017,
        "eos_token_ids": [200002, 199999],
        "do_sample": False,
    }
    config["canary"]["minimum_schema_pass_rate"] = 0.89
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="minimum_schema_pass_rate"):
        load_source_training_config(path)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        ("training", "max_seq_length", 4096, "max_seq_length=2048"),
        ("canary", "max_new_tokens", 513, "max_new_tokens=512"),
    ],
)
def test_nonlegacy_recipe_enforces_canonical_generation_limits(
    tmp_path, section, field, value, message
):
    config = _config()
    config["recipe"] = "unsloth_v2"
    config["protocol"] = {
        "reasoning_effort": "low",
        "padding_side": "left",
        "pad_token_id": 200017,
        "eos_token_ids": [200002, 199999],
        "do_sample": False,
    }
    config[section][field] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_source_training_config(path)


@pytest.mark.parametrize("field", ["passed", "adapter_reload"])
def test_full_gate_requires_real_boolean_true(tmp_path, field):
    config, report, records, prediction_path, adapter_dir = _promotion_fixture(tmp_path)
    report[field] = 1

    with pytest.raises(ValueError, match=field):
        _validate_fixture(config, report, records, prediction_path, adapter_dir)


def test_full_gate_rejects_aggregate_only_forgery(tmp_path):
    config, report, records, prediction_path, adapter_dir = _promotion_fixture(tmp_path)
    report.update(
        {
            "promotion_authority": False,
            "record_count": 0,
            "passed_count": 0,
            "parsed_count": 0,
            "harmony_prefix_count": 0,
            "harmony_final_count": 0,
            "finish_reasons": {},
            "schema_pass_rate": 1.0,
        }
    )

    with pytest.raises(ValueError, match="passing canary") as excinfo:
        _validate_fixture(config, report, records, prediction_path, adapter_dir)
    assert "promotion_authority" in str(excinfo.value)
    assert "record_count" in str(excinfo.value)


def test_full_gate_requires_real_promotion_boolean_and_fixed_path(tmp_path):
    config, report, records, prediction_path, adapter_dir = _promotion_fixture(tmp_path)
    report["promotion_authority"] = 1

    with pytest.raises(ValueError, match="promotion_authority"):
        _validate_fixture(config, report, records, prediction_path, adapter_dir)

    report["promotion_authority"] = True
    report["prediction_path"] = str(tmp_path / "substituted.jsonl")
    with pytest.raises(ValueError, match="prediction_path"):
        _validate_fixture(config, report, records, prediction_path, adapter_dir)


def test_legacy_gate_cannot_authorize_full_stage(tmp_path):
    config, report, records, prediction_path, adapter_dir = _promotion_fixture(tmp_path)
    config["recipe"] = "legacy_unsloth"
    config.pop("protocol")

    with pytest.raises(ValueError, match="legacy Unsloth evidence"):
        _validate_fixture(config, report, records, prediction_path, adapter_dir)


def test_full_gate_rejects_prediction_and_adapter_tampering(tmp_path):
    config, report, records, prediction_path, adapter_dir = _promotion_fixture(tmp_path)
    rows = [json.loads(line) for line in prediction_path.read_text().splitlines()]
    rows[0]["raw_generation"] = "not JSON"
    prediction_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="gate prediction"):
        _validate_fixture(config, report, records, prediction_path, adapter_dir)

    config, report, records, prediction_path, adapter_dir = _promotion_fixture(
        tmp_path / "adapter-case"
    )
    (adapter_dir / "adapter_config.json").write_text(
        '{"tampered":true}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="adapter_artifact_sha256"):
        _validate_fixture(config, report, records, prediction_path, adapter_dir)


def test_adapter_digest_rejects_symlinked_directory(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(b"weights")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "tokenizer.json").write_text("{}", encoding="utf-8")
    (adapter / "linked-directory").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinks"):
        artifact_directory_sha256(adapter)
