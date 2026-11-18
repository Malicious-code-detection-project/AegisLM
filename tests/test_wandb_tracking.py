import sys
from copy import deepcopy
from types import ModuleType
from typing import Any

import pytest

from aegislm.inference.source import source_generation_protocol_metadata
from aegislm.tracking.wandb import (
    finish_active_wandb,
    git_reference,
    init_wandb_run,
    log_source_comparison,
    log_source_evaluation,
    log_wandb_payload,
    safe_training_log_payload,
    source_comparison_wandb_payload,
    source_evaluation_wandb_config,
    source_evaluation_wandb_payload,
    source_training_wandb_config,
    validate_wandb_payload,
    wandb_run_reference,
)


class FakeTable:
    def __init__(self, *, columns: list[str], data: list[list[Any]]):
        self.columns = columns
        self.data = data


class FakeRun:
    id = "fake-run"
    url = "https://wandb.invalid/fake-run"

    def __init__(self):
        self.logged: list[tuple[dict[str, Any], int | None]] = []
        self.summary: dict[str, Any] = {}
        self.finish_codes: list[int] = []

    def log(self, payload: dict[str, Any], step: int | None = None) -> None:
        self.logged.append((payload, step))

    def finish(self, *, exit_code: int) -> None:
        self.finish_codes.append(exit_code)


class FakeWandb(ModuleType):
    Table = FakeTable

    def __init__(self):
        super().__init__("wandb")
        self.run = FakeRun()
        self.init_kwargs: dict[str, Any] | None = None
        self.init_argv: list[str] | None = None

    class Settings:
        def __init__(self, **kwargs: Any):
            self.values = kwargs
            self.argv = list(sys.argv)

    def init(self, **kwargs: Any) -> FakeRun:
        self.init_kwargs = kwargs
        self.init_argv = list(sys.argv)
        return self.run


@pytest.fixture(autouse=True)
def _clean_active_run():
    finish_active_wandb(0)
    yield
    finish_active_wandb(0)


def test_wandb_is_opt_in_and_requires_env_key(monkeypatch):
    monkeypatch.delenv("WANDB_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="repository .env"):
        init_wandb_run(job_type="training", name="run", config={})


def test_wandb_init_enforces_privacy_and_returns_reference(monkeypatch):
    fake = FakeWandb()
    monkeypatch.setitem(sys.modules, "wandb", fake)
    monkeypatch.setenv("WANDB_API_KEY", "not-a-real-key")
    monkeypatch.setattr(sys, "argv", ["command.py", "--predictions", "/secret/p.jsonl"])

    run = init_wandb_run(
        job_type="evaluation",
        name="safe-run",
        config={"model_id": "model"},
        tags=("source-v2",),
    )

    assert fake.init_kwargs is not None
    assert fake.init_kwargs["project"] == "aegislm"
    assert fake.init_kwargs["group"] == "source-v2"
    assert "not-a-real-key" not in repr(fake.init_kwargs)
    settings = fake.init_kwargs["settings"].values
    assert settings == {
        "mode": "online",
        "console": "off",
        "disable_code": True,
        "disable_git": True,
        "save_code": False,
        "program": "",
        "program_abspath": "",
        "program_relpath": "",
        "host": "",
        "x_disable_meta": True,
        "x_disable_stats": True,
        "x_disable_machine_info": True,
        "x_save_requirements": False,
    }
    assert fake.init_kwargs["settings"].argv == ["command.py"]
    assert fake.init_argv == ["command.py"]
    assert sys.argv == ["command.py", "--predictions", "/secret/p.jsonl"]
    assert wandb_run_reference(run) == {
        "project": "aegislm",
        "group": "source-v2",
        "run_id": "fake-run",
        "run_url": "https://wandb.invalid/fake-run",
    }
    for key in (
        "WANDB_DISABLE_CODE",
        "WANDB_DISABLE_GIT",
        "WANDB_CONSOLE",
        "WANDB_LOG_MODEL",
    ):
        assert __import__("os").environ[key] in {"true", "off", "false"}

    finish_active_wandb(0)
    assert run.finish_codes == [0]


def test_wandb_rejects_sensitive_config_keys(monkeypatch):
    monkeypatch.setenv("WANDB_API_KEY", "not-a-real-key")

    with pytest.raises(ValueError, match="sensitive field"):
        init_wandb_run(
            job_type="training",
            name="bad",
            config={"nested": {"access_token": "must-not-upload"}},
        )


def test_wandb_allows_noncredential_tokenizer_digest(monkeypatch):
    fake = FakeWandb()
    monkeypatch.setitem(sys.modules, "wandb", fake)
    monkeypatch.setenv("WANDB_API_KEY", "not-a-real-key")

    init_wandb_run(
        job_type="evaluation",
        name="tokenizer-digest",
        config={"tokenizer_contract_sha256": "a" * 64},
    )


@pytest.mark.parametrize(
    "key",
    ("credentials", "private_key", "authorization", "client-secret", "passwd"),
)
def test_wandb_rejects_common_sensitive_keys(key, monkeypatch):
    monkeypatch.setenv("WANDB_API_KEY", "not-a-real-key")

    with pytest.raises(ValueError, match="sensitive field"):
        validate_wandb_payload({key: "redacted"})


def test_wandb_rejects_loaded_credential_in_innocuous_value(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf-sensitive-sentinel")

    with pytest.raises(ValueError, match="credential value"):
        log_wandb_payload(FakeRun(), {"note": "Bearer hf-sensitive-sentinel"})


def test_wandb_rejects_credential_as_mapping_key_without_echo(monkeypatch):
    credential = "hf-sensitive-key-sentinel"
    monkeypatch.setenv("HF_TOKEN", credential)

    with pytest.raises(ValueError) as exc_info:
        validate_wandb_payload({"packages": {credential: float("nan")}})

    assert credential not in str(exc_info.value)
    assert "item_0" in str(exc_info.value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object()])
def test_wandb_rejects_nonfinite_or_unsupported_values(value):
    with pytest.raises(ValueError, match="not allowed"):
        log_wandb_payload(FakeRun(), {"metric": value})


def test_wandb_rejects_source_like_strings_in_outbound_payload():
    with pytest.raises(ValueError, match="unsafe string"):
        log_wandb_payload(FakeRun(), {"target_cwe": "int private_source(void);"})


def test_source_evaluation_config_enforces_semantic_provenance(monkeypatch):
    summary = _evaluation_summary()

    config = source_evaluation_wandb_config(summary)

    assert config["provenance"]["run_role"] == "adapter"
    assert config["provenance"]["reasoning_effort"] == "low"
    assert config["provenance"]["pad_token_id"] == 200017
    assert config["provenance"]["eos_token_ids"] == [200002, 199999]
    assert len(config["provenance"]["generation_protocol_sha256"]) == 64
    credential = "hf-package-key-sentinel"
    monkeypatch.setenv("HF_TOKEN", credential)
    summary["provenance"]["packages"] = {credential: "1.0"}
    with pytest.raises(ValueError) as exc_info:
        source_evaluation_wandb_config(summary)
    assert credential not in str(exc_info.value)


def test_source_evaluation_config_rejects_generation_protocol_tampering():
    summary = _evaluation_summary()
    summary["provenance"]["first_eos_trim"] = False

    with pytest.raises(ValueError, match="generation protocol"):
        source_evaluation_wandb_config(summary)


def test_source_evaluation_config_requires_prediction_and_adapter_tree_digests():
    summary = _evaluation_summary()
    summary["provenance"]["adapter_artifact_sha256"] = None
    with pytest.raises(ValueError, match="complete adapter artifact"):
        source_evaluation_wandb_config(summary)

    summary = _evaluation_summary()
    summary["predictions_sha256"] = None
    with pytest.raises(ValueError, match="prediction file"):
        source_evaluation_wandb_config(summary)


def test_source_evaluation_config_allows_optional_adapter_weight_digest():
    summary = _evaluation_summary()
    summary["provenance"]["adapter_sha256"] = None

    config = source_evaluation_wandb_config(summary)

    assert config["provenance"]["adapter_sha256"] is None
    assert len(config["provenance"]["adapter_artifact_sha256"]) == 64


def test_training_curve_allowlist_drops_strings_and_extra_fields():
    assert safe_training_log_payload(
        {
            "loss": 0.5,
            "learning_rate": 0.1,
            "grad_norm": "source text",
            "epoch": 1,
            "output_dir": "/private/checkpoints",
        }
    ) == {
        "training/loss": 0.5,
        "training/learning_rate": 0.1,
        "training/epoch": 1.0,
    }


def test_training_script_disables_stock_transformers_wandb_callback():
    source = __import__("pathlib").Path("scripts/train_source_unsloth.py").read_text()

    assert 'report_to="none"' in source
    assert 'report_to=["wandb"]' not in source
    assert "SafeWandbTrainerCallback" in source


def test_training_script_requires_wandb_key_before_config_read():
    source = __import__("pathlib").Path("scripts/train_source_unsloth.py").read_text()

    assert source.index("        require_wandb_api_key()") < source.index(
        "    config = load_source_training_config(args.config)"
    )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("training", "optimizer", "private_identifier"),
        ("training", "lr_scheduler_type", "credential_buffer"),
        ("training", "attention_target_modules", ["q_proj", "private_identifier"]),
        ("training", "expert_target_layers", [24]),
        ("model", "base_model_id", "private_identifier"),
        ("model", "revision", "a" * 40),
    ),
)
def test_training_wandb_config_rejects_identifier_shaped_out_of_domain_values(
    section, field, value
):
    config = deepcopy(_training_config())
    config[section][field] = value

    with pytest.raises(ValueError, match="source-v2"):
        source_training_wandb_config(config, "canary", False)


def test_training_wandb_config_projects_only_semantic_values():
    projected = source_training_wandb_config(_training_config(), "canary", False)

    assert projected["base_model_id"] == "openai/gpt-oss-20b"
    assert "output_dir" not in repr(projected)
    assert projected["training"]["optimizer"] == "adamw_8bit"
    assert projected["recipe"] == "legacy_unsloth"
    assert projected["protocol"]["reasoning_effort"] == "medium"
    assert (
        projected["canary"]["train_selection_strategy"] == "assessment_round_robin_v1"
    )


def test_training_wandb_config_projects_versioned_train_selector():
    config = _training_config()
    config["canary"]["train_selection_strategy"] = (
        "target_cwe_assessment_round_robin_v1"
    )

    projected = source_training_wandb_config(config, "canary", False)

    assert (
        projected["canary"]["train_selection_strategy"]
        == "target_cwe_assessment_round_robin_v1"
    )


def test_training_wandb_config_rejects_unknown_train_selector():
    config = _training_config()
    config["canary"]["train_selection_strategy"] = "private_selector"

    with pytest.raises(ValueError, match="source-v2"):
        source_training_wandb_config(config, "canary", False)


def test_training_wandb_config_projects_explicit_protocol():
    config = _training_config()
    config["recipe"] = "unsloth_v2"
    config["protocol"] = {
        "reasoning_effort": "low",
        "padding_side": "left",
        "pad_token_id": 200017,
        "eos_token_ids": [200002, 199999],
        "do_sample": False,
    }

    projected = source_training_wandb_config(config, "canary", False)

    assert projected["recipe"] == "unsloth_v2"
    assert projected["protocol"] == config["protocol"]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("reasoning_effort", "private"),
        ("padding_side", "right"),
        ("pad_token_id", True),
        ("eos_token_ids", [200002, 200002]),
        ("do_sample", True),
    ),
)
def test_training_wandb_config_rejects_invalid_protocol(field, value):
    config = _training_config()
    config["recipe"] = "unsloth_v2"
    config["protocol"] = {
        "reasoning_effort": "low",
        "padding_side": "left",
        "pad_token_id": 200017,
        "eos_token_ids": [200002, 199999],
        "do_sample": False,
    }
    config["protocol"][field] = value

    with pytest.raises(ValueError, match="source-v2"):
        source_training_wandb_config(config, "canary", False)


def test_git_reference_exposes_only_commit_and_dirty_state(tmp_path, monkeypatch):
    class Result:
        def __init__(self, stdout: str):
            self.stdout = stdout

    outputs = iter((Result("a" * 40 + "\n"), Result(" M safe.py\n")))
    monkeypatch.setattr(
        "aegislm.tracking.wandb.subprocess.run", lambda *args, **kwargs: next(outputs)
    )

    assert git_reference(tmp_path) == {"commit": "a" * 40, "dirty": True}


def test_source_evaluation_logs_only_whitelisted_case_columns(monkeypatch):
    fake = FakeWandb()
    monkeypatch.setitem(sys.modules, "wandb", fake)
    summary = _evaluation_summary()

    log_source_evaluation(fake.run, summary)

    payload = fake.run.logged[0][0]
    table = payload["evaluation/cases"]
    assert "source_code" not in table.columns
    assert "raw_output" not in table.columns
    assert "errors" not in table.columns
    assert "secret source text" not in repr(payload)


def test_source_evaluation_rejects_source_text_in_safe_table_slot(monkeypatch):
    fake = FakeWandb()
    monkeypatch.setitem(sys.modules, "wandb", fake)
    summary = _evaluation_summary()
    summary["cases"][0]["target_cwe"] = "int private_source(void);"

    with pytest.raises(ValueError, match="unsafe format"):
        source_evaluation_wandb_payload(summary)

    assert fake.run.logged == []


def test_source_evaluation_normalizes_invalid_prediction_assessment(monkeypatch):
    fake = FakeWandb()
    monkeypatch.setitem(sys.modules, "wandb", fake)
    summary = _evaluation_summary()
    summary["cases"][0]["predicted_assessment"] = "private_identifier"

    prepared = source_evaluation_wandb_payload(summary)
    log_source_evaluation(fake.run, summary)

    assert prepared["case_data"][0][3] == "invalid"
    assert "private_identifier" not in repr(fake.run.logged)


def test_source_evaluation_log_rejects_forged_prepared_mapping(monkeypatch):
    fake = FakeWandb()
    monkeypatch.setitem(sys.modules, "wandb", fake)
    forged = {
        "metrics": {},
        "case_columns": ["predicted_assessment"],
        "case_data": [["private_identifier"]],
        "per_cwe_data": [],
    }

    with pytest.raises(ValueError, match="source-v2"):
        log_source_evaluation(fake.run, forged)

    assert fake.run.logged == []


def test_source_evaluation_rejects_invalid_expected_assessment():
    summary = _evaluation_summary()
    summary["cases"][0]["expected_assessment"] = "private_identifier"

    with pytest.raises(ValueError, match="outside the allowed domain"):
        source_evaluation_wandb_payload(summary)


def test_source_comparison_logs_aggregate_metrics_only():
    run = FakeRun()
    comparison = {
        "outcome": "equivalent",
        "comparison_mode": "full_report",
        "deltas": {
            "macro_f1": 0.0,
            "evidence_f1": 0.0,
            "accuracy": 0.0,
            "schema_validation_pass_rate": 0.0,
        },
        "quality_targets": {
            "json_parse_success_rate": True,
            "schema_validation_pass_rate": True,
            "grounded_span_rate": True,
            "safety_violation_count": True,
        },
        "regression_reasons": {"label_recall": {}, "major_cwe_accuracy": {}},
    }

    log_source_comparison(run, comparison)

    assert run.logged[0][0]["comparison/outcome"] == "equivalent"
    assert "raw_output" not in repr(run.logged)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("outcome", "private_identifier"),
        ("comparison_mode", "credential_buffer"),
    ),
)
def test_source_comparison_rejects_identifier_shaped_out_of_domain_values(field, value):
    comparison = _comparison()
    comparison[field] = value

    with pytest.raises(ValueError, match="source-v2"):
        source_comparison_wandb_payload(comparison)


def test_source_comparison_log_rejects_forged_dynamic_keys():
    run = FakeRun()
    comparison = _comparison()
    comparison["deltas"]["private_identifier"] = 0.1

    with pytest.raises(ValueError, match="delta keys"):
        log_source_comparison(run, comparison)

    assert run.logged == []


def test_source_comparison_requires_numeric_non_evidence_deltas():
    comparison = _comparison()
    comparison["deltas"]["macro_f1"] = None

    with pytest.raises(ValueError, match="must be numeric"):
        source_comparison_wandb_payload(comparison)


def _evaluation_summary() -> dict[str, Any]:
    return {
        "model_id": "source-v2-adapter",
        "case_set_sha256": "b" * 64,
        "gold_sha256": "c" * 64,
        "predictions_sha256": "4" * 64,
        "provenance": {
            **source_generation_protocol_metadata(
                backend="unsloth",
                mode="raw",
                max_new_tokens=512,
                max_seq_length=2048,
                temperature=0.0,
            ),
            "backend": "unsloth",
            "mode": "raw",
            "max_new_tokens": 512,
            "max_seq_length": 2048,
            "temperature": 0.0,
            "base_model_revision": "d" * 40,
            "resolved_model_id": "unsloth/gpt-oss-20b",
            "adapter_artifact_sha256": "a" * 64,
            "adapter_sha256": "e" * 64,
            "tokenizer_contract_sha256": "f" * 64,
            "hardware_signature": "1" * 64,
            "run_role": "adapter",
            "packages": {"transformers": "5.5.0"},
            "challenge_file_sha256": "2" * 64,
            "challenge_records_sha256": "3" * 64,
        },
        "metrics": {
            "accuracy": 1.0,
            "macro_f1": 1.0,
            "json_parse_success_rate": 1.0,
            "schema_validation_pass_rate": 1.0,
            "field_completeness": 1.0,
            "safety_violation_count": 0,
            "safety_evaluated_count": 1,
            "evidence_precision": 1.0,
            "evidence_recall": 1.0,
            "evidence_f1": 1.0,
            "grounded_span_rate": 1.0,
            "missing_span_count": 0,
            "hallucinated_span_count": 0,
            "mean_latency_ms": 1.0,
            "recall_by_label": {"present": 1.0},
            "per_cwe": {"CWE-120": {"count": 1, "accuracy": 1.0}},
        },
        "cases": [
            {
                "record_id": "case",
                "target_cwe": "CWE-120",
                "expected_assessment": "present",
                "predicted_assessment": "present",
                "correct": True,
                "json_parse_success": True,
                "schema_valid": True,
                "safety_pass": True,
                "missing_span_count": 0,
                "hallucinated_span_count": 0,
                "latency_ms": 1.0,
                "source_code": "secret source text",
                "raw_output": "secret source text",
                "errors": ["secret source text"],
            }
        ],
    }


def _training_config() -> dict[str, Any]:
    return {
        "model": {
            "base_model_id": "openai/gpt-oss-20b",
            "runtime_model_id": "unsloth/gpt-oss-20b-unsloth-bnb-4bit",
            "revision": "093fba6992ef5a7152481afec0bdfca1ac486998",
        },
        "dataset": {
            "train_sha256": "b" * 64,
            "validation_sha256": "c" * 64,
        },
        "training": {
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
            "attention_target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
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


def _comparison() -> dict[str, Any]:
    return {
        "outcome": "equivalent",
        "comparison_mode": "full_report",
        "deltas": {
            "macro_f1": 0.0,
            "evidence_f1": 0.0,
            "accuracy": 0.0,
            "schema_validation_pass_rate": 0.0,
        },
        "quality_targets": {
            "json_parse_success_rate": True,
            "schema_validation_pass_rate": True,
            "grounded_span_rate": True,
            "safety_violation_count": True,
        },
        "regression_reasons": {"label_recall": {}, "major_cwe_accuracy": {}},
    }
