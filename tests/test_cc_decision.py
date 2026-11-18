"""Decision-only preparation, held-out isolation and fail-closed launch gates."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aegislm.datasets.source_corpus import decision_messages
from aegislm.training import cc_decision as cc
from aegislm.training import two_stage_runtime as runtime
from aegislm.training.two_stage import digest, write_json
from scripts import train_cc_decision as entry


def record(split: str = "train") -> dict[str, Any]:
    return {
        "id": "one",
        "split": split,
        "assessment": "present",
        "target_cwe": "CWE-457",
        "source_code": "int f(void) { int x; return x; }",
        "evidence_ranges": None,
        "annotation": {
            "decision_status": "source_label_unreviewed",
            "approved_for_training": False,
        },
    }


def export(identifier: str, label: str) -> dict[str, Any]:
    row = record("validation")
    row.update(id=identifier, assessment=label)
    return {"id": identifier, "messages": decision_messages(row, answer=True)}


def test_development_subset_uses_validation_only_and_is_order_independent() -> None:
    rows = [
        export(f"validation-{label}-{i}", label)
        for label in ("present", "not_observed")
        for i in range(100)
    ]
    original = deepcopy(rows)
    selected = cc.development_rows(rows)
    assert selected == cc.development_rows(list(reversed(rows)))
    assert len({r["id"] for r in selected}) == 100
    assert Counter(
        json.loads(r["messages"][-1]["content"])["assessment"] for r in selected
    ) == {
        "present": 50,
        "not_observed": 50,
    }
    assert all(r["id"].startswith("validation-") for r in selected)
    assert rows == original


def test_generation_inputs_remove_validation_gold_and_never_use_training() -> None:
    rows = [export("val-one", "present")]
    data = {"exports": {"validation": rows, "train": [export("train-one", "present")]}}
    prompts, gold = cc.evaluation_rows(data, "validation")
    assert [m["role"] for m in prompts[0]["messages"]] == ["system", "user"]
    assert gold == [{"id": "val-one", "expected_output": {"assessment": "present"}}]
    assert len(rows[0]["messages"]) == 3
    with pytest.raises(ValueError, match="evaluation split"):
        cc.evaluation_rows(data, "train")


@pytest.mark.parametrize(
    "change", ["test-answer", "changed-label", "changed-code", "approval", "evidence"]
)
def test_canonical_export_and_review_policy_cannot_be_silently_changed(
    change: str,
) -> None:
    row = record("test" if change == "test-answer" else "train")
    messages = {
        "id": row["id"],
        "messages": decision_messages(row, answer=row["split"] != "test"),
    }
    if change == "test-answer":
        messages["messages"].append(
            {"role": "assistant", "content": '{"assessment":"present"}'}
        )
    elif change == "changed-label":
        row["assessment"] = "not_observed"
    elif change == "changed-code":
        row["source_code"] = "return 0;"
    elif change == "approval":
        row["annotation"]["approved_for_training"] = True
    else:
        row["evidence_ranges"] = [{"start_line": 1, "end_line": 1}]
    with pytest.raises(ValueError):
        cc.validate_export(row, messages, row["split"])


@pytest.mark.parametrize(
    "change", ["steps", "policy", "world-size", "revision", "digest"]
)
def test_config_rejects_settings_not_implemented_by_fixed_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    config = json.loads((cc.ROOT / "configs/cc_source_decision_v5.json").read_text())
    monkeypatch.setenv("WORLD_SIZE", "1")
    if change == "steps":
        config["training"]["max_steps"] = 1
    elif change == "policy":
        config["allow_unreviewed_source_labels"] = False
    elif change == "world-size":
        monkeypatch.setenv("WORLD_SIZE", "2")
    elif change == "revision":
        config["model"]["revision"] = "main"
    else:
        config["dataset"]["inventory_sha256"] = "0" * 64
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        cc.load_config(path)


@pytest.mark.parametrize("changed", ["packages", "assets", "data", "config", "source"])
def test_prepared_candidate_rejects_runtime_or_input_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    config = {"output_dir": str(tmp_path / "output")}
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")
    source = tmp_path / "worker.py"
    source.write_text("original")
    monkeypatch.setattr(cc, "ROOT", tmp_path)
    monkeypatch.setattr(cc, "package_versions", lambda: {"torch": "fixed"})
    monkeypatch.setattr(cc, "tokenizer_assets", lambda config: {"tokenizer": "fixed"})
    monkeypatch.setattr(cc, "verify_inputs", lambda config: {"train": "fixed"})
    manifest = {
        "config_sha256": digest(config_path),
        "source_hashes": {"worker.py": digest(source)},
        "packages": {"torch": "fixed"},
        "tokenizer_assets": {"tokenizer": "fixed"},
        "dataset_hashes": {"train": "fixed"},
    }
    write_json(Path(config["output_dir"]) / "manifest.json", manifest)
    assert cc.context(config, config_path) == manifest
    if changed == "packages":
        monkeypatch.setattr(cc, "package_versions", lambda: {"torch": "changed"})
    elif changed == "assets":
        monkeypatch.setattr(
            cc, "tokenizer_assets", lambda config: {"tokenizer": "changed"}
        )
    elif changed == "data":
        monkeypatch.setattr(cc, "verify_inputs", lambda config: {"train": "changed"})
    elif changed == "config":
        config_path.write_text('{"changed":true}')
    else:
        source.write_text("changed")
    with pytest.raises(ValueError):
        cc.context(config, config_path)


@pytest.mark.parametrize(
    "changed", ["gpu", "wandb", "identity", "train-ids", "optimizer", "tokenizer"]
)
def test_gpu_receipt_is_bound_to_exact_preparation_and_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    config = {"output_dir": str(tmp_path)}
    manifest = {
        "config_sha256": "fixed",
        "tokenizer_sha256": "fixed",
        "preflight_ids": ["train"],
    }
    write_json(tmp_path / "manifest.json", manifest)
    write_json(tmp_path / "preflight/functional-readiness.json", {"pass": True})
    write_json(tmp_path / "preflight/wandb-readiness.json", {"pass": True})
    identity = {"name": "test-gpu"}
    monkeypatch.setattr(entry, "gpu_identity", lambda: identity)
    monkeypatch.setattr(entry, "functional_readiness", lambda *args: {"pass": True})
    receipt = {
        "config_sha256": "fixed",
        "preparation_sha256": digest(tmp_path / "manifest.json"),
        "gpu_sha256": digest(tmp_path / "preflight/functional-readiness.json"),
        "gpu_identity": identity,
        "wandb_readiness_sha256": digest(tmp_path / "preflight/wandb-readiness.json"),
        "train_ids": ["train"],
        "optimizer_steps": 0,
        "tokenizer_sha256": "fixed",
    }
    write_json(tmp_path / "preflight/receipt.json", receipt)
    entry.require_preflight(config, manifest)
    if changed in {"gpu", "wandb"}:
        (
            tmp_path
            / f"preflight/{'functional-readiness' if changed == 'gpu' else 'wandb-readiness'}.json"
        ).write_text('{"pass":true,"changed":true}')
    else:
        field, value = {
            "identity": ("gpu_identity", {"name": "different-gpu"}),
            "train-ids": ("train_ids", ["test"]),
            "optimizer": ("optimizer_steps", 1),
            "tokenizer": ("tokenizer_sha256", "changed"),
        }[changed]
        receipt[field] = value
        (tmp_path / "preflight/receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="binding mismatch"):
        entry.require_preflight(config, manifest)


def test_training_worker_cannot_skip_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(entry, "context", lambda *args: {"date": "2026-10-02"})
    monkeypatch.setattr(entry, "load_project_env", lambda *args: None)
    monkeypatch.setattr(entry, "load_data", lambda *args: {})

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("model loading or training before the launch gate")

    monkeypatch.setattr(runtime, "load_model", forbidden)
    monkeypatch.setattr(runtime, "train", forbidden)
    with pytest.raises(FileNotFoundError):
        entry.worker(
            {"output_dir": str(tmp_path)},
            tmp_path / "config",
            "train",
            "base",
            "development",
        )


def test_preflight_authentication_failure_does_not_load_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(entry, "context", lambda *args: {"date": "2026-10-02"})
    monkeypatch.setattr(entry, "load_project_env", lambda *args: None)
    monkeypatch.setattr(entry, "load_data", lambda *args: {})
    monkeypatch.setattr(entry, "wandb_readiness", lambda: {"pass": False})

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("loading a model despite failed tracking readiness")

    monkeypatch.setattr(runtime, "load_model", forbidden)
    with pytest.raises(RuntimeError, match="W&B readiness failed"):
        entry.worker(
            {"output_dir": str(tmp_path)},
            tmp_path / "config",
            "preflight",
            "base",
            "development",
        )


def test_existing_training_destination_is_rejected_before_model_or_tracking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = {
        "checkpoint_dir": str(tmp_path / "checkpoints"),
        "adapter_dir": str(tmp_path / "adapters"),
    }
    (Path(config["adapter_dir"]) / "decision").mkdir(parents=True)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("loading model or starting a run before destination check")

    monkeypatch.setattr(runtime, "load_model", forbidden)
    monkeypatch.setattr(runtime, "start_tracking", forbidden)
    with pytest.raises(ValueError, match="refusing overwrite"):
        runtime.train(config, "2026-10-02", "decision", [], tmp_path / "output")


def test_wandb_preflight_only_reads_api_and_never_initializes_a_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cc, "load_project_env", lambda *args: None)
    monkeypatch.setenv("WANDB_API_KEY", "test-credential-not-to-log")
    monkeypatch.delenv("WANDB_ENTITY", raising=False)
    calls = []

    class API:
        viewer = {"id": "one"}
        default_entity = "entity"

        def project(self, name: str, entity: str) -> dict[str, str]:
            calls.append((name, entity))
            return {"name": name}

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("preflight created a remote W&B run")

    fake = SimpleNamespace(Api=lambda **kwargs: API(), init=forbidden)
    monkeypatch.setattr(cc.importlib, "import_module", lambda name: fake)
    result = cc.wandb_readiness()
    assert result["pass"]
    assert result["remote_run_created"] is False
    assert calls == [("aegislm", "entity")]
    assert "test-credential" not in json.dumps(result)


def test_stage_is_required_and_baseline_cannot_access_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit) as exc:
        entry.main([])
    assert exc.value.code == 2

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("baseline accessed test before rejecting its split")

    monkeypatch.setattr(entry, "context", forbidden)
    with pytest.raises(ValueError, match="base/development"):
        entry.worker({}, Path("unused"), "baseline", "base", "test")


def test_mask_signature_repair_preserves_function_and_all_forwarded_arguments() -> None:
    import inspect

    received = []

    def original(
        config: Any, inputs_embeds: Any, attention_mask: Any, *, past_key_values: Any
    ) -> Any:
        received.append((config, inputs_embeds, attention_mask, past_key_values))
        return "actual-mask"

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return original(*args, **kwargs)

    module = SimpleNamespace(
        create_causal_mask=wrapper,
        create_sliding_window_causal_mask=wrapper,
        _unsloth_original_create_causal_mask=original,
        _unsloth_original_create_sliding_window_causal_mask=original,
    )
    assert set(inspect.signature(wrapper).parameters) == {"args", "kwargs"}
    runtime.preserve_mask_signatures(module)
    assert module.create_causal_mask is wrapper
    assert inspect.signature(wrapper) == inspect.signature(original)
    proposed = {
        "config": 1,
        "inputs_embeds": 2,
        "attention_mask": 3,
        "past_key_values": 4,
        "unsupported": 5,
    }
    accepted = {
        k: v for k, v in proposed.items() if k in inspect.signature(wrapper).parameters
    }
    assert wrapper(**accepted) == "actual-mask"
    assert received == [(1, 2, 3, 4)]
    runtime.preserve_mask_signatures(module)
    module.__patched_causal_mask__ = True
    with pytest.raises(ValueError, match="before GPT-OSS patching"):
        runtime.preserve_mask_signatures(module)


def test_mask_signature_repair_fails_closed_on_unknown_runtime() -> None:
    with pytest.raises(ValueError, match="original mask factory missing"):
        runtime.preserve_mask_signatures(SimpleNamespace())
    module = SimpleNamespace(
        _unsloth_original_create_causal_mask=lambda unexpected: None
    )
    with pytest.raises(ValueError, match="unexpected original"):
        runtime.preserve_mask_signatures(module)


def test_mask_signature_repair_rejects_prior_alias_without_patch_flag() -> None:
    module = SimpleNamespace(_old_create_causal_mask=lambda **kwargs: None)
    with pytest.raises(ValueError, match="prior GPT-OSS mask alias"):
        runtime.preserve_mask_signatures(module)


def test_unsloth_diagnostic_selects_balanced_train_and_retains_extremes() -> None:
    from scripts.diagnose_cc_unsloth import select_train

    rows = [
        export(f"train-{label}-{i}", label)
        for label in ("present", "not_observed")
        for i in range(40)
    ]
    extremes = [rows[-1]["id"], rows[0]["id"]]
    selected = select_train(rows, extremes)
    assert len(selected) == len({r["id"] for r in selected}) == 64
    assert [r["id"] for r in selected[:2]] == extremes
    assert Counter(
        json.loads(r["messages"][-1]["content"])["assessment"] for r in selected
    ) == {"present": 32, "not_observed": 32}
    assert selected == select_train(list(reversed(rows)), extremes)
    with pytest.raises(ValueError, match="training records"):
        select_train(rows, ["test-id", extremes[0]])
    with pytest.raises(ValueError, match="training records"):
        select_train(rows, [extremes[0], extremes[0]])


def test_unsloth_diagnostic_requires_explicit_stage_and_output() -> None:
    from scripts.diagnose_cc_unsloth import main

    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_zero_lr_warmup_is_not_mistaken_for_optimizer_failure() -> None:
    runtime.verify_adapter_update("same", "same", 0.0, True)
    runtime.verify_adapter_update("before", "after", 1e-4, True)
    with pytest.raises(RuntimeError, match="positive-LR"):
        runtime.verify_adapter_update("same", "same", 1e-4, True)
    with pytest.raises(RuntimeError, match="unverified gradients"):
        runtime.verify_adapter_update("same", "same", 0.0, False)
    for value in (float("nan"), float("inf"), -1e-4):
        with pytest.raises(RuntimeError, match="learning rate"):
            runtime.verify_adapter_update("before", "after", value, True)


@pytest.mark.parametrize(
    "path",
    [
        "owner/aegislm/run123",
        ["owner", "aegislm", "run123"],
        ("owner", "aegislm", "run123"),
    ],
)
def test_tracking_path_does_not_join_each_character(path: Any) -> None:
    assert runtime.wandb_run_path(SimpleNamespace(path=path)) == "owner/aegislm/run123"


@pytest.mark.parametrize(
    "path",
    [
        "owner/other/run123",
        "owner/aegislm",
        "owner/aegislm/",
        "https://host/owner/aegislm/run123",
    ],
)
def test_tracking_path_rejects_wrong_or_incomplete_destination(path: str) -> None:
    with pytest.raises(ValueError, match="W&B"):
        runtime.wandb_run_path(SimpleNamespace(path=path))


def test_diagnostic_loss_reads_raw_trainer_keys_before_wandb_prefixing() -> None:
    from scripts.diagnose_cc_unsloth import validated_training_loss
    from aegislm.tracking import safe_training_log_payload

    logs = {"loss": 1.75, "grad_norm": 19.0, "learning_rate": 0.0}
    outbound = safe_training_log_payload(logs)
    assert "training/loss" in outbound and "loss" not in outbound
    assert validated_training_loss(logs) == 1.75
    assert validated_training_loss({"epoch": 1.0}) is None
    for key in ("loss", "grad_norm"):
        with pytest.raises(RuntimeError, match="nonfinite"):
            validated_training_loss({key: float("nan")})


def update_evidence() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    updates = [
        {"step": 1, "optimizer_lr": 0.0, "fingerprint": "before"},
        {"step": 2, "optimizer_lr": 1e-4, "fingerprint": "after"},
    ]
    training = {
        "pass": True,
        "optimizer_steps": 2,
        "gradient_checks": 2,
        "loss": 2.0,
        "before_sha256": "before",
        "after_sha256": "after",
        "updates": updates,
        "adapter_sha256": "saved",
        "provenance": {"recipe": "smoke"},
    }
    observed = {
        "steps": 2,
        "gradient_checks": 2,
        "losses": [1.9, 2.1],
        "before_sha256": "before",
        "after_sha256": "after",
        "updates": updates,
    }
    reload = {
        "pass": True,
        "optimizer_steps": 0,
        "active_adapters": ["default"],
        "after_sha256": "after",
        "adapter_sha256": "saved",
        "provenance": {"recipe": "smoke"},
    }
    return training, observed, reload


def test_functional_readiness_accepts_verified_update_after_zero_lr_warmup() -> None:
    from aegislm.training.cc_readiness import validate_update_evidence

    validate_update_evidence(*update_evidence())


@pytest.mark.parametrize(
    "change",
    [
        "missing-step",
        "missing-gradient",
        "nonfinite-loss",
        "zero-lr-only",
        "no-update",
        "reload-change",
        "adapter-change",
        "reload-trains",
    ],
)
def test_functional_readiness_rejects_unverified_training_or_reload(
    change: str,
) -> None:
    from aegislm.training.cc_readiness import validate_update_evidence

    training, observed, reload = update_evidence()
    if change == "missing-step":
        training["optimizer_steps"] = 1
    elif change == "missing-gradient":
        training["gradient_checks"] = 1
    elif change == "nonfinite-loss":
        observed["losses"][0] = float("nan")
    elif change == "zero-lr-only":
        training["updates"][1]["optimizer_lr"] = 0.0
    elif change == "no-update":
        training["after_sha256"] = "before"
    elif change == "reload-change":
        reload["after_sha256"] = "other"
    elif change == "adapter-change":
        reload["adapter_sha256"] = "other"
    else:
        reload["optimizer_steps"] = 1
    with pytest.raises(ValueError, match="training/update/reload"):
        validate_update_evidence(training, observed, reload)


def test_functional_readiness_rejects_change_only_during_zero_lr_step() -> None:
    from aegislm.training.cc_readiness import validate_update_evidence

    training, observed, reload = update_evidence()
    training["updates"][0]["fingerprint"] = "after"
    with pytest.raises(ValueError, match="training/update/reload"):
        validate_update_evidence(training, observed, reload)


@pytest.mark.parametrize(
    "change",
    [
        None,
        "receipt",
        "reload",
        "remote-id",
        "remote-name",
        "remote-recipe",
        "remote-revision",
    ],
)
def test_tracking_evidence_binds_the_same_current_run(change: str | None) -> None:
    from aegislm.training.cc_readiness import validate_tracking_binding

    recorded = {"id": "run123", "path": "owner/aegislm/run123"}
    training = {
        "wandb": dict(recorded),
        "provenance": {"diagnostic_namespace": "current", "base_revision": "pinned"},
    }
    reloaded = {"wandb": dict(recorded)}
    receipt = {**recorded, "remote_readiness_confirmed": True}
    remote = SimpleNamespace(
        id="run123",
        path=["owner", "aegislm", "run123"],
        name="current-decision-runtime-smoke",
        config={"recipe": "cc_unsloth_smoke_v1", "model_revision": "pinned"},
        summary={
            "diagnostic/training_pass": True,
            "diagnostic/adapter_reload_pass": True,
            "diagnostic/optimizer_steps": 2,
        },
    )
    if change == "receipt":
        receipt.update(id="old", path="owner/aegislm/old")
    elif change == "reload":
        reloaded["wandb"]["id"] = "old"
    elif change == "remote-id":
        remote.id = "old"
    elif change == "remote-name":
        remote.name = "older-decision-runtime-smoke"
    elif change == "remote-recipe":
        remote.config["recipe"] = "other"
    elif change == "remote-revision":
        remote.config["model_revision"] = "other"
    if change is None:
        validate_tracking_binding(training, reloaded, receipt, remote)
    else:
        with pytest.raises(ValueError, match="W&B"):
            validate_tracking_binding(training, reloaded, receipt, remote)
