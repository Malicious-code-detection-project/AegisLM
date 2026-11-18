"""Tracking must exclude raw source/outputs and preserve partial evaluation counts."""

from copy import deepcopy
import json

import pytest

from scripts.track_cc_native_validation100 import project_snapshot


def snapshot():
    rows = []
    for model in ("adapter", "base"):
        for budget in (128, 512, 2048, 65536, 130000, "context-minus-input"):
            rows.append(
                {
                    "model": model,
                    "budget": budget,
                    "completed": 1,
                    "planned": 100,
                    "pending": 99,
                    "semantic_matrix": [[0, 1, 0, 0], [0, 0, 0, 0]],
                    "strict_matrix": [[0, 0, 0, 1], [0, 0, 0, 0]],
                    "rows": [
                        {
                            "id": "cc-123",
                            "source_label": "present",
                            "assessment": None,
                            "json_valid": True,
                            "schema_valid": False,
                            "final_channel_present": True,
                            "parsed": {
                                "assessment": "not_observed",
                                "extra": "PRIVATE-OUTPUT",
                            },
                            "raw_generation": "PRIVATE-OUTPUT",
                            "input_text": "PRIVATE-SOURCE",
                            "generated_ids": [1],
                            "generated_tokens": 33,
                            "stop_reason": "native_eos",
                            "harmony_parse_error": "PRIVATE-ERROR",
                        }
                    ],
                }
            )
    return {"groups": rows}


def test_raw_source_output_errors_and_paths_are_never_projected():
    source = snapshot()
    original = deepcopy(source)
    projected = project_snapshot(source)
    encoded = json.dumps(projected)
    assert "PRIVATE" not in encoded
    assert "raw_generation" not in encoded and "input_text" not in encoded
    assert projected["groups"][0]["cases"][0][4:6] == ["not_observed", "invalid"]
    assert source == original


def test_pending_is_not_invalid_and_semantic_errors_remain_visible():
    metrics = project_snapshot(snapshot())["metrics"]
    prefix = "evaluation/adapter/max_new_tokens_128"
    assert metrics[f"{prefix}/pending"] == 99
    assert metrics[f"{prefix}/semantic/FN"] == 1
    assert metrics[f"{prefix}/semantic/invalid"] == 0
    assert metrics[f"{prefix}/strict/invalid"] == 1
    assert metrics["evaluation/completed"] == 12
    assert metrics["evaluation/complete"] is False


def test_base_only_tracking_requires_explicit_model_selection():
    data = snapshot()
    data["groups"] = [g for g in data["groups"] if g["model"] == "base"]
    with pytest.raises(ValueError, match="configured model/budget groups"):
        project_snapshot(data)
    metrics = project_snapshot(data, models=["base"])["metrics"]
    assert metrics["evaluation/completed"] == 6
    assert metrics["evaluation/planned"] == 600
    assert not metrics["evaluation/complete"]
    assert not any("/adapter/" in key for key in metrics)
    for group in data["groups"]:
        group["completed"], group["pending"] = 100, 0
        group["semantic_matrix"] = [[0, 100, 0, 0], [0, 0, 0, 0]]
        group["strict_matrix"] = [[0, 0, 0, 100], [0, 0, 0, 0]]
        group["rows"] = [{**group["rows"][0], "id": f"cc-{i:03x}"} for i in range(100)]
    metrics = project_snapshot(data, models=["base"])["metrics"]
    assert metrics["evaluation/completed"] == 600
    assert metrics["evaluation/complete"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "unexpected_model"])
def test_base_only_tracking_rejects_incomplete_or_mixed_conditions(change: str):
    data = snapshot()
    data["groups"] = [g for g in data["groups"] if g["model"] == "base"]
    if change == "missing":
        data["groups"].pop()
    elif change == "duplicate":
        data["groups"][-1] = deepcopy(data["groups"][0])
    else:
        data["groups"][0]["model"] = "adapter"
    with pytest.raises(ValueError, match="configured model/budget groups"):
        project_snapshot(data, models=["base"])


@pytest.mark.parametrize("models", [[], ["base", "base"], ["unknown"]])
def test_tracking_rejects_invalid_model_selection(models: list[str]):
    with pytest.raises(ValueError, match="configured models"):
        project_snapshot(snapshot(), models=models)


def test_matrix_count_mismatch_or_wrong_cohort_is_rejected():
    data = snapshot()
    data["groups"][0]["semantic_matrix"][0][0] = 1
    with pytest.raises(ValueError, match="matrix does not match"):
        project_snapshot(data)
    data = snapshot()
    data["groups"][0]["planned"] = 2
    with pytest.raises(ValueError, match="Unexpected evaluation counts"):
        project_snapshot(data)


def test_malicious_record_id_cannot_leak_free_text():
    data = snapshot()
    data["groups"][0]["rows"][0]["id"] = "leak source code()"
    with pytest.raises(ValueError, match="unsafe string"):
        project_snapshot(data)


def test_isolation_policy_is_in_new_wandb_identity_without_changing_legacy_identity():
    from scripts.track_cc_native_validation100 import safe_config

    config = {
        "experiment_id": "test-evaluation",
        "budgets": [128, 512],
        "models": ["adapter", "base"],
        "runtime_context": 131072,
    }
    audit = dict.fromkeys(
        (
            "train_sha256",
            "validation_sha256",
            "selection_sha256",
            "frozen_input_sha256",
            "adapter_sha256",
        ),
        "0" * 64,
    )
    legacy = safe_config(config, audit)
    assert "execution_protocol" not in legacy
    config["execution_protocol"] = "fresh-process-per-model-budget-v2"
    isolated = safe_config(config, audit)
    assert isolated.pop("execution_protocol") == config["execution_protocol"]
    assert isolated == legacy


def test_dynamic_cache_tracking_has_distinct_identity_without_leaking_paths():
    from scripts.track_cc_native_validation100 import safe_config

    config = {
        "experiment_id": "cache-comparison",
        "budgets": [128],
        "models": ["base"],
        "runtime_context": 131072,
    }
    audit = dict.fromkeys(
        (
            "train_sha256",
            "validation_sha256",
            "selection_sha256",
            "frozen_input_sha256",
            "adapter_sha256",
            "runner_sha256",
        ),
        "0" * 64,
    )
    native = safe_config(config, audit)
    dynamic = safe_config(
        {**config, "cache_policy": "dynamic", "comparison_reference": "/PRIVATE/PATH"},
        audit,
    )
    assert native["generation_mode"] == "official-native-defaults"
    assert "cache_policy" not in native
    assert dynamic["generation_mode"] == "native-sampling-dynamic-cache"
    assert dynamic["cache_policy"] == "dynamic"
    assert dynamic["runner_sha256"] == audit["runner_sha256"]
    assert "PRIVATE" not in json.dumps(dynamic)
