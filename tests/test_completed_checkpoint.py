"""CPU-only terminal checkpoint contracts; no model loading or training."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aegislm.training import fresh
from aegislm.training.source_config import file_sha256, source_training_config_sha256
from scripts import train_source_unsloth_fresh as entrypoint


def _checkpoint(tmp_path: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    config = fresh.load_fresh_config(
        Path(__file__).resolve().parents[1] / "configs/source_v2_unsloth_fresh.json"
    )
    path = tmp_path / "checkpoint-2"
    path.mkdir()
    (path / "adapter_model.safetensors").write_bytes(b"mock adapter; not a real model")
    (path / "adapter_config.json").write_text("{}", encoding="utf-8")
    state = {
        "global_step": 2,
        "max_steps": 2,
        "log_history": [
            {"step": 1, "loss": 1.2, "grad_norm": 0.4},
            {"step": 2, "loss": 1.0, "grad_norm": 0.2},
        ],
    }
    (path / "trainer_state.json").write_text(json.dumps(state), encoding="utf-8")
    evidence = {
        "schema_version": fresh.CHECKPOINT_EVIDENCE_SCHEMA,
        "config_sha256": source_training_config_sha256(config),
        "stage": "smoke",
        "train_records_sha256": "d" * 64,
        "tokenizer_contract_sha256": "c" * 64,
        "global_step": 2,
        "max_steps": 2,
        "gradients_checked": True,
        "trainable_before_sha256": "a" * 64,
        "trainable_after_sha256": "b" * 64,
        "trainer_state_sha256": file_sha256(path / "trainer_state.json"),
        "adapter_sha256": file_sha256(path / "adapter_model.safetensors"),
        "adapter_config_sha256": file_sha256(path / "adapter_config.json"),
    }
    return path, config, evidence


def _save_evidence(path: Path, evidence: dict[str, Any]) -> None:
    fresh.write_fresh_json(path / fresh.CHECKPOINT_EVIDENCE_FILE, evidence)


def _load(path: Path, config: dict[str, Any]) -> dict[str, Any] | None:
    return fresh.load_completed_checkpoint(
        path, config=config, stage="smoke", train_records_digest="d" * 64
    )


def test_terminal_checkpoint_requires_digest_bound_training_evidence(tmp_path):
    path, config, evidence = _checkpoint(tmp_path)
    with pytest.raises(ValueError, match="lacks saved training evidence"):
        _load(path, config)
    _save_evidence(path, evidence)
    loaded = _load(path, config)
    assert loaded is not None
    assert loaded["training_loss"] == pytest.approx(1.1)
    assert loaded["evidence_sha256"] == file_sha256(
        path / fresh.CHECKPOINT_EVIDENCE_FILE
    )


@pytest.mark.parametrize(
    "filename",
    [
        "adapter_model.safetensors",
        "adapter_config.json",
        "trainer_state.json",
    ],
)
def test_terminal_checkpoint_rejects_changed_files(tmp_path, filename):
    path, config, evidence = _checkpoint(tmp_path)
    _save_evidence(path, evidence)
    with (path / filename).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="match|mismatch"):
        _load(path, config)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("stage", "canary"),
        ("config_sha256", "0" * 64),
        ("train_records_sha256", "0" * 64),
        ("gradients_checked", False),
        ("gradients_checked", 1),
        ("trainable_after_sha256", "a" * 64),
        ("tokenizer_contract_sha256", "invalid"),
    ],
)
def test_terminal_checkpoint_rejects_invalid_evidence(tmp_path, key, value):
    path, config, evidence = _checkpoint(tmp_path)
    evidence[key] = value
    _save_evidence(path, evidence)
    with pytest.raises(ValueError):
        _load(path, config)


def test_incomplete_checkpoint_keeps_normal_resume_without_evidence(tmp_path):
    path, config, _ = _checkpoint(tmp_path)
    state_path = path / "trainer_state.json"
    state = json.loads(state_path.read_text())
    state["max_steps"] = 3
    state_path.write_text(json.dumps(state))
    assert _load(path, config) is None


def test_older_resume_cannot_overwrite_newer_completed_evidence(tmp_path):
    path, config, _ = _checkpoint(tmp_path)
    state_path = path / "trainer_state.json"
    state = json.loads(state_path.read_text())
    state["max_steps"] = 3
    state_path.write_text(json.dumps(state))
    newer = tmp_path / "checkpoint-3"
    newer.mkdir()
    (newer / fresh.CHECKPOINT_EVIDENCE_FILE).write_text("{}")
    with pytest.raises(ValueError, match="newer completed checkpoint"):
        _load(path, config)


@pytest.mark.parametrize(
    "history",
    [
        [],
        [{"step": 1, "loss": float("nan")}],
        [{"step": 1, "loss": True}],
        [{"step": 1, "loss": 1.0}, {"step": 1, "loss": 0.8}],
        [{"step": 1, "loss": 1.0, "grad_norm": float("inf")}],
    ],
)
def test_checkpoint_loss_rejects_incomplete_or_nonfinite_history(history):
    with pytest.raises(ValueError):
        fresh.checkpoint_logged_loss({"global_step": 2, "log_history": history})


def test_final_save_callback_produces_usable_evidence(tmp_path, monkeypatch):
    path, config, evidence = _checkpoint(tmp_path)
    monkeypatch.setattr(entrypoint, "trainable_fingerprint", lambda *_: "b" * 64)
    context = {
        key: evidence[key]
        for key in (
            "config_sha256",
            "stage",
            "train_records_sha256",
            "tokenizer_contract_sha256",
        )
    }
    callback = entrypoint.make_training_callback(
        SimpleNamespace(TrainerCallback=object), object(), None, context
    )
    callback.initial_fingerprint = "a" * 64
    callback.gradients_checked = True
    callback.losses = [1.2, 1.0]
    callback.on_save(
        SimpleNamespace(output_dir=tmp_path),
        SimpleNamespace(global_step=2, max_steps=2, is_world_process_zero=True),
        None,
        object(),
    )
    loaded = _load(path, config)
    assert loaded is not None
    assert loaded["training_loss"] == pytest.approx(1.1)


def test_terminal_recovery_restores_weights_without_training(tmp_path, monkeypatch):
    path, config, evidence = _checkpoint(tmp_path)
    _save_evidence(path, evidence)
    loaded = _load(path, config)
    assert loaded is not None
    calls = []
    peft = SimpleNamespace(
        load_peft_weights=lambda *args, **kwargs: {"weights": "fixture"},
        set_peft_model_state_dict=lambda *args, **kwargs: calls.append("restore"),
    )

    def import_module(name):
        assert name == "peft"
        return peft

    monkeypatch.setattr(entrypoint.importlib, "import_module", import_module)
    monkeypatch.setattr(entrypoint, "trainable_fingerprint", lambda *_: "b" * 64)
    trainer = SimpleNamespace(
        args=object(),
        get_train_dataloader=lambda: [],
        set_initial_training_values=lambda *_: (2,),
        train=lambda **_: pytest.fail("completed checkpoint must not train"),
    )
    transformers = SimpleNamespace(
        TrainerState=SimpleNamespace(
            load_from_json=lambda _: SimpleNamespace(global_step=2)
        )
    )
    checks = SimpleNamespace()
    entrypoint.recover_completed_checkpoint(
        trainer,
        SimpleNamespace(peft_config={"default": object()}),
        checks,
        object(),
        transformers,
        path,
        loaded,
        "c" * 64,
    )
    assert calls == ["restore"]
    assert trainer.state.global_step == 2
    assert checks.gradients_checked is True
    assert checks.initial_fingerprint == "a" * 64
    assert checks.losses == [pytest.approx(1.1)]


@pytest.mark.parametrize(
    ("steps", "tokenizer", "fingerprint"),
    [
        (3, "c" * 64, "b" * 64),
        (2, "0" * 64, "b" * 64),
        (2, "c" * 64, "0" * 64),
    ],
)
def test_terminal_recovery_rejects_runtime_mismatch(
    tmp_path, monkeypatch, steps, tokenizer, fingerprint
):
    path, config, evidence = _checkpoint(tmp_path)
    _save_evidence(path, evidence)
    loaded = _load(path, config)
    assert loaded is not None
    peft = SimpleNamespace(
        load_peft_weights=lambda *args, **kwargs: {},
        set_peft_model_state_dict=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(entrypoint.importlib, "import_module", lambda _: peft)
    monkeypatch.setattr(entrypoint, "trainable_fingerprint", lambda *_: fingerprint)
    trainer = SimpleNamespace(
        args=object(),
        get_train_dataloader=lambda: [],
        set_initial_training_values=lambda *_: (steps,),
    )
    with pytest.raises(ValueError, match="schedule|tokenizer|weights"):
        entrypoint.recover_completed_checkpoint(
            trainer,
            SimpleNamespace(peft_config={"default": object()}),
            SimpleNamespace(),
            object(),
            object(),
            path,
            loaded,
            tokenizer,
        )
