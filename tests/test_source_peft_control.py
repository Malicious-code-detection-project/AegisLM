import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from safetensors.numpy import save_file

SCRIPT = Path("scripts/train_source_peft_control.py")
SPEC = importlib.util.spec_from_file_location("train_source_peft_control", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


def _config() -> dict:
    return json.loads(Path("configs/source_v2_peft_control.json").read_text())


def test_control_config_binds_recipe_protocol_and_independent_paths(tmp_path):
    path = tmp_path / "control.json"
    path.write_text(json.dumps(_config()), encoding="utf-8")

    loaded = control.load_peft_control_config(path)

    assert loaded["recipe"] == "peft_split_control"
    assert loaded["protocol"] == control.PROTOCOL
    assert loaded["training"]["output_dir"] == "adapters/source-v2-peft-control"
    assert control.source_protocol_sha256(loaded) == control.source_protocol_sha256(
        _config()
    )


def test_control_config_accepts_pair_balanced_ablation_paths(tmp_path):
    config = _config()
    config["canary"]["train_selection_strategy"] = (
        "target_cwe_assessment_round_robin_v1"
    )
    config["training"]["output_dir"] = "adapters/source-v2-peft-cwe-balanced"
    config["training"]["checkpoint_dir"] = "checkpoints/source-v2-peft-cwe-balanced"
    path = tmp_path / "control-balanced.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    loaded = control.load_peft_control_config(path)

    assert (
        control.source_train_selection_strategy(loaded)
        == "target_cwe_assessment_round_robin_v1"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("recipe", "unsloth_split_expert"),
        ("reasoning_effort", "medium"),
        ("padding_side", "right"),
        ("pad_token_id", 199999),
        ("eos_token_ids", [200002]),
        ("do_sample", True),
    ],
)
def test_control_config_rejects_recipe_or_protocol_drift(tmp_path, field, value):
    config = _config()
    if field == "recipe":
        config[field] = value
    else:
        config["protocol"][field] = value
    path = tmp_path / "control.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="recipe|protocol"):
        control.load_peft_control_config(path)


def test_control_config_rejects_frozen_dataset_drift(tmp_path):
    config = _config()
    config["dataset"]["train_path"] = "data/processed/other/train.jsonl"
    path = tmp_path / "control.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="dataset.train_path"):
        control.load_peft_control_config(path)


def test_control_loader_rejects_legacy_unsloth_config():
    with pytest.raises(ValueError, match="recipe"):
        control.load_peft_control_config(Path("configs/source_v2_qlora.json"))


def _fake_split_model(*, corrupt: str | None = None):
    Params4bit = type("Params4bit", (), {})
    Linear4bit = type("Linear4bit", (), {})
    modules = []
    for name in sorted(control._expected_target_names()):
        module = Linear4bit()
        module.weight = Params4bit()
        modules.append((name, module))
    if corrupt is not None:
        replacement = SimpleNamespace(weight=Params4bit())
        modules = [
            (name, replacement if name == corrupt else module)
            for name, module in modules
        ]
    return SimpleNamespace(
        config=SimpleNamespace(num_hidden_layers=24, num_local_experts=32),
        named_modules=lambda: iter(modules),
    )


def test_split_target_preflight_requires_exact_288_quantized_modules():
    pattern = control.build_unsloth_moe_target_regex(
        control.ATTENTION_TARGETS, control.EXPERT_TARGET_LAYERS
    )

    matched = control.validate_split_bnb_targets(_fake_split_model(), pattern)

    assert len(matched) == 288


def test_split_target_preflight_rejects_non_bnb_target():
    pattern = control.build_unsloth_moe_target_regex(
        control.ATTENTION_TARGETS, control.EXPERT_TARGET_LAYERS
    )
    corrupt = "model.layers.7.mlp.experts.gate_up_projs.0"

    with pytest.raises(RuntimeError, match="not bitsandbytes 4-bit"):
        control.validate_split_bnb_targets(_fake_split_model(corrupt=corrupt), pattern)


class _Parameter:
    def __init__(self, size: int, *, requires_grad: bool = True):
        self._size = size
        self.requires_grad = requires_grad

    def numel(self):
        return self._size


def test_trainable_contract_accepts_only_expected_lora_count():
    model = SimpleNamespace(
        named_parameters=lambda: iter(
            [
                ("base.weight", _Parameter(10, requires_grad=False)),
                (
                    "base_model.model.layers.0.self_attn.q_proj.lora_A.default.weight",
                    _Parameter(control.EXPECTED_TRAINABLE_PARAMETERS),
                ),
            ]
        )
    )

    assert (
        control.validate_trainable_adapter(model)
        == control.EXPECTED_TRAINABLE_PARAMETERS
    )


def test_trainable_contract_rejects_unfrozen_base():
    model = SimpleNamespace(
        named_parameters=lambda: iter(
            [("base.weight", _Parameter(control.EXPECTED_TRAINABLE_PARAMETERS))]
        )
    )

    with pytest.raises(RuntimeError, match="non-LoRA parameter"):
        control.validate_trainable_adapter(model)


def test_saved_adapter_contract_checks_exact_tensor_domains(tmp_path):
    tensors = {}
    for layer in range(24):
        for module in control.ATTENTION_TARGETS:
            for side in ("A", "B"):
                key = (
                    f"base_model.model.model.layers.{layer}.self_attn.{module}."
                    f"lora_{side}.weight"
                )
                tensors[key] = np.zeros((1,), dtype=np.float32)
    for layer in control.EXPERT_TARGET_LAYERS:
        for projection in ("gate_up_projs", "down_projs"):
            for expert in range(32):
                for side in ("A", "B"):
                    key = (
                        f"base_model.model.model.layers.{layer}.mlp.experts."
                        f"{projection}.{expert}.lora_{side}.weight"
                    )
                    tensors[key] = np.zeros((1,), dtype=np.float32)
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    save_file(tensors, adapter / "adapter_model.safetensors")

    assert control.inspect_saved_adapter(adapter) == {
        "total": 576,
        "attention": 192,
        "experts": 384,
    }


def test_source_uses_required_loader_and_direct_peft_reload():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "FastLanguageModel.from_pretrained(" in source
    assert "AutoModelForCausalLM" not in source
    assert "runtime.FastLanguageModel.get_peft_model(" not in source
    assert "runtime.get_peft_model(model, peft_config)" in source
    assert "runtime.PeftModel.from_pretrained(" in source
    assert "load_persisted_source_tokenizer(" in source
    assert "runtime.AutoTokenizer" in source
    assert "artifact_digest_after != artifact_digest_before" in source
    assert "reasoning_effort=REASONING_EFFORT" in source
    assert "if args.preflight_only:" in source
    assert "exceeds 42 GiB budget" in source
    assert source.index("wandb_claim = prepare_tracking_receipt(") < source.index(
        "reserve_training_stage("
    )
    reservation = source.index("reserve_training_stage(")
    assert reservation < source.index("wandb_run = init_wandb_run(", reservation)
    recovery = source.index("if not wandb_claim.needs_logging:")
    assert recovery < reservation


def test_gate_report_binds_resolved_protocol_hash(tmp_path):
    config = _config()
    adapter = tmp_path / "canary"
    adapter.mkdir()
    final = adapter / "final"
    final.mkdir()
    (final / "adapter_model.safetensors").write_bytes(b"adapter")
    (adapter / "post_training_gate_predictions.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )

    class Record:
        record_id = "one"

        def to_serializable(self):
            return {"id": self.record_id}

    records = [Record()]
    # records_sha256 accepts the record dataclass interface used by source-v2;
    # use the real helper only indirectly in higher-level tests.
    original = control.records_sha256
    control.records_sha256 = lambda value: f"digest-{len(value)}"
    try:
        report = control._write_gate_report(
            adapter,
            final,
            config,
            records,
            records,
            control.GateRunSummary(
                record_count=1,
                passed_count=1,
                schema_pass_rate=1.0,
                parsed_count=1,
                harmony_prefix_count=1,
                harmony_final_count=1,
                finish_reasons={"eos": 1},
            ),
            adapter_artifact_sha256=control.artifact_directory_sha256(final),
            promotion_authority=True,
            tracking=None,
        )
    finally:
        control.records_sha256 = original

    assert report["recipe"] == "peft_split_control"
    assert report["protocol_sha256"] == control.source_protocol_sha256(config)
    assert report["adapter_reload"] is True
    assert report["promotion_authority"] is True
    assert report["report_schema_version"] == "aegislm.source-canary-gate.v2"
    assert len(report["predictions_sha256"]) == 64
    assert len(report["adapter_artifact_sha256"]) == 64
    assert report["finish_reasons"] == {"eos": 1}


def test_saved_adapter_config_drift_rejects_gate(tmp_path):
    adapter = tmp_path / "final"
    adapter.mkdir()
    (adapter / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": control.RUNTIME_MODEL_ID,
                "revision": "wrong-revision",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="base model or revision"):
        control._validate_adapter_base(adapter, _config())


class _GateBackendTokenizer:
    def __init__(self, marker="same"):
        self.marker = marker

    def to_str(self):
        return json.dumps({"model": {"marker": self.marker}})


class _GateTokenizer:
    padding_side = "left"
    pad_token_id = control.PAD_TOKEN_ID
    eos_token_id = control.RETURN_TOKEN_ID
    chat_template = "{{ messages }}"
    special_tokens_map = {"eos_token": "<|return|>", "pad_token": "<|pad|>"}
    model_max_length = 2048
    truncation_side = "right"
    clean_up_tokenization_spaces = False
    split_special_tokens = False

    def __init__(self, marker="same"):
        self.backend_tokenizer = _GateBackendTokenizer(marker)


def _gate_runtime(saved_tokenizer):
    class AutoTokenizer:
        @staticmethod
        def from_pretrained(path, **kwargs):
            assert kwargs == {"local_files_only": True}
            assert path.endswith("/final")
            return saved_tokenizer

    return SimpleNamespace(
        AutoTokenizer=AutoTokenizer,
        PeftModel=SimpleNamespace(
            from_pretrained=lambda model, path, is_trainable: model
        ),
        FastLanguageModel=SimpleNamespace(for_inference=lambda model: None),
        torch=SimpleNamespace(cuda=SimpleNamespace(empty_cache=lambda: None)),
    )


def _valid_adapter_config(adapter, config):
    (adapter / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": config["model"]["runtime_model_id"],
                "revision": config["model"]["revision"],
            }
        ),
        encoding="utf-8",
    )


def test_gate_rejects_persisted_tokenizer_drift_before_scoring(tmp_path, monkeypatch):
    config = _config()
    adapter = tmp_path / "final"
    adapter.mkdir()
    _valid_adapter_config(adapter, config)
    monkeypatch.setattr(control, "inspect_saved_adapter", lambda path: {})
    monkeypatch.setattr(control, "artifact_directory_sha256", lambda path: "a" * 64)
    monkeypatch.setattr(
        control,
        "_load_split_base",
        lambda runtime, loaded_config: (object(), _GateTokenizer(), "id", "revision"),
    )
    monkeypatch.setattr(
        control,
        "run_source_schema_gate",
        lambda **kwargs: pytest.fail("scoring must not run for tokenizer drift"),
    )

    with pytest.raises(RuntimeError, match="does not match the pinned base"):
        control._run_reload_and_schema_gate(
            _gate_runtime(_GateTokenizer("drifted")),
            adapter_output=adapter,
            config=config,
            records=[object()],
            prediction_path=tmp_path / "predictions.jsonl",
        )


def test_gate_scores_with_persisted_tokenizer_and_rejects_artifact_mutation(
    tmp_path, monkeypatch
):
    config = _config()
    adapter = tmp_path / "final"
    adapter.mkdir()
    _valid_adapter_config(adapter, config)
    saved_tokenizer = _GateTokenizer()
    seen = {}
    digests = iter(("a" * 64, "b" * 64))
    monkeypatch.setattr(control, "inspect_saved_adapter", lambda path: {})
    monkeypatch.setattr(
        control, "artifact_directory_sha256", lambda path: next(digests)
    )
    monkeypatch.setattr(
        control,
        "_load_split_base",
        lambda runtime, loaded_config: (object(), _GateTokenizer(), "id", "revision"),
    )

    def fake_gate(**kwargs):
        seen["tokenizer"] = kwargs["tokenizer"]
        return control.GateRunSummary(1, 1, 1.0, 1, 1, 1, {"eos": 1})

    monkeypatch.setattr(control, "run_source_schema_gate", fake_gate)

    with pytest.raises(RuntimeError, match="artifact changed"):
        control._run_reload_and_schema_gate(
            _gate_runtime(saved_tokenizer),
            adapter_output=adapter,
            config=config,
            records=[object()],
            prediction_path=tmp_path / "predictions.jsonl",
        )
    assert seen["tokenizer"] is saved_tokenizer


def test_unsloth_gate_also_loads_persisted_tokenizer_and_checks_digest():
    source = Path("scripts/train_source_unsloth.py").read_text(encoding="utf-8")

    assert "load_persisted_source_tokenizer(" in source
    assert "AutoTokenizer," in source
    assert "artifact_digest_after != artifact_digest_before" in source
