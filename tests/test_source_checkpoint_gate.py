import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path("scripts/run_source_checkpoint_gate.py")
SPEC = importlib.util.spec_from_file_location("run_source_checkpoint_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def _config():
    return json.loads(Path("configs/source_v2_unsloth_v2.json").read_text())


def test_adapter_config_is_bound_to_model_and_revision(tmp_path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(b"weights")
    (adapter / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": _config()["model"]["runtime_model_id"],
                "revision": _config()["model"]["revision"],
            }
        )
    )

    assert diagnostic._validate_adapter_config(adapter, _config()) == "adapter_config"

    value = json.loads((adapter / "adapter_config.json").read_text())
    value["revision"] = "0" * 40
    (adapter / "adapter_config.json").write_text(json.dumps(value))
    with pytest.raises(ValueError, match="identity"):
        diagnostic._validate_adapter_config(adapter, _config())


def test_unbound_legacy_checkpoint_requires_matching_manifest(tmp_path):
    config = _config()
    adapter = tmp_path / "checkpoint-25"
    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(b"weights")
    (adapter / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": config["model"]["runtime_model_id"],
                "revision": None,
            }
        )
    )
    (adapter / "trainer_state.json").write_text(json.dumps({"global_step": 25}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "base_model_id": config["model"]["base_model_id"],
                "resolved_model_id": config["model"]["runtime_model_id"],
                "resolved_model_revision": config["model"]["revision"],
            }
        )
    )

    with pytest.raises(ValueError, match="identity"):
        diagnostic._validate_adapter_config(adapter, config)
    assert (
        diagnostic._validate_adapter_config(adapter, config, legacy_manifest=manifest)
        == "legacy_training_manifest"
    )


def test_resolved_model_identity_is_strict():
    config = _config()
    model = SimpleNamespace(
        config=SimpleNamespace(
            _name_or_path=config["model"]["runtime_model_id"],
            _commit_hash=config["model"]["revision"],
        )
    )

    assert diagnostic._resolved_model_identity(model, config) == (
        config["model"]["runtime_model_id"],
        config["model"]["revision"],
    )
    model.config._commit_hash = "0" * 40
    with pytest.raises(RuntimeError, match="revision"):
        diagnostic._resolved_model_identity(model, config)


def test_active_adapter_requires_name_and_lora_parameters():
    model = SimpleNamespace(
        active_adapters=["default"],
        named_parameters=lambda: iter([("layer.lora_A.weight", object())]),
    )
    assert diagnostic._has_active_adapter(model) is True
    model.active_adapters = []
    assert diagnostic._has_active_adapter(model) is False


def test_diagnostic_report_cannot_authorize_full_training():
    source = SCRIPT.read_text()

    assert '"promotion_authority": False' in source
    assert "run_source_schema_gate(" in source
    assert "PeftModel.from_pretrained(" in source
    reservation = source.index("create_exclusive_artifact_directory(")
    receipt = source.index("wandb_claim = prepare_tracking_receipt(")
    assert receipt < reservation
    assert reservation < source.index("wandb_run = init_wandb_run(", reservation)
    recovery = source.index("if not wandb_claim.needs_logging:")
    assert receipt < recovery < reservation
    assert reservation < source.index("from unsloth import")
