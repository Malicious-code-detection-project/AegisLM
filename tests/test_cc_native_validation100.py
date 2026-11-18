"""The generation cohort must not inherit teacher-forced answers or small counts."""

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from scripts.run_cc_native_validation100 import generation_budget, select_prompts
from scripts import run_cc_native_validation100 as sweep


def cohort():
    rows = []
    cases = []
    for label in ("present", "not_observed"):
        for i in range(50):
            ident = f"{label}-{i}"
            rows.append(
                {
                    "id": ident,
                    "messages": [
                        {"role": "system", "content": "Judge"},
                        {"role": "user", "content": f"code-{i}"},
                        {
                            "role": "assistant",
                            "content": json.dumps({"assessment": label}),
                        },
                    ],
                }
            )
            cases.append(
                {"id": ident, "gold": label, "input_ids": [777], "labels": [777]}
            )
    return rows, {"cases": cases}


def test_all_100_prompts_have_no_answer_or_teacher_forced_tokens():
    rows, selection = cohort()
    original = deepcopy(rows)
    prompts, gold = select_prompts(rows, selection)
    assert len(prompts) == len(gold) == 100
    assert all(set(row) == {"id", "messages"} for row in prompts)
    assert all(
        [m["role"] for m in row["messages"]] == ["system", "user"] for row in prompts
    )
    assert sum(v["assessment"] == "present" for v in gold.values()) == 50
    assert rows == original


def test_two_case_or_duplicate_cohort_cannot_be_used():
    rows, selection = cohort()
    selection["cases"] = selection["cases"][:2]
    with pytest.raises(ValueError, match="100 distinct"):
        select_prompts(rows, selection)
    _, selection = cohort()
    selection["cases"][-1] = selection["cases"][0]
    with pytest.raises(ValueError, match="100 distinct"):
        select_prompts(rows, selection)


def test_gold_mismatch_is_rejected():
    rows, selection = cohort()
    selection["cases"][0]["gold"] = "not_observed"
    with pytest.raises(ValueError, match="Frozen gold differs"):
        select_prompts(rows, selection)


@pytest.mark.parametrize("cap", [128, 512, 2048, 65536, 130000, "context-minus-input"])
def test_generation_caps_fit_without_silently_clamping(cap):
    expected = 130172 if cap == "context-minus-input" else cap
    assert generation_budget(cap, 900, 131072) == expected
    with pytest.raises(ValueError, match="does not fit"):
        generation_budget(130000, 1073, 131072)


def test_failed_generation_preserves_counts_and_marks_progress_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "output_dir": "result",
                "training_reference": "training",
                "execution_protocol": sweep.ISOLATION_PROTOCOL,
            }
        )
    )
    root = tmp_path / "result"
    root.mkdir()
    progress = {
        "status": "running",
        "completed": 302,
        "planned": 1200,
        "current": {"model": "adapter", "budget": 65536, "id": "case"},
    }
    (root / "progress.json").write_text(json.dumps(progress))

    def fail(*args):
        raise RuntimeError("simulated allocation failure")

    monkeypatch.setattr(sweep, "REPO", tmp_path)
    monkeypatch.setattr(sweep, "run", fail)
    monkeypatch.setattr(sys, "argv", ["runner", "run", "--config", str(config_path)])
    with pytest.raises(RuntimeError, match="simulated allocation"):
        sweep.main()
    result = json.loads((root / "progress.json").read_text())
    assert result["status"] == "failed"
    assert result["completed"] == 302 and result["planned"] == 1200
    assert result["current"] == progress["current"]
    assert result["error_file"] == "error.json"
    assert json.loads((root / "error.json").read_text())["progress"] == progress


# A real spawned worker, with no CUDA/model dependency. A fork or reused process
# would inherit the sentinel / leak the live marker and fail these assertions.
PROCESS_SENTINEL = "clean"


def isolated_cpu_worker(config, root, old, config_path, kind, cap):
    import os

    assert PROCESS_SENTINEL == "clean"
    active = root / "active-worker"
    with active.open("x"):
        pass
    if config.get("fail_budget") == cap:
        raise RuntimeError("simulated worker OOM")
    for ident in sweep.read(root / "frozen-inputs.json"):
        sweep.write(
            root / "raw" / f"{kind}-{cap}-{ident}.json",
            {
                "id": ident,
                "model": kind,
                "budget": cap,
                "worker_pid": os.getpid(),
                "execution_protocol": sweep.ISOLATION_PROTOCOL,
            },
        )
    active.unlink()


def isolated_fixture(tmp_path, *, fail_budget=None):
    root, old = tmp_path / "result", tmp_path / "training"
    (root / "raw").mkdir(parents=True)
    (old / "gpt_oss_lora").mkdir(parents=True)
    config = {
        "execution_protocol": sweep.ISOLATION_PROTOCOL,
        "models": ["adapter", "base"],
        "budgets": [128, 512, 2048, 65536, 130000, "context-minus-input"],
        "samples_per_condition": 100,
        "scorer_python": "unused",
        "fail_budget": fail_budget,
    }
    sweep.write(root / "config.json", config)
    sweep.write(root / "frozen-inputs.json", {str(i): {} for i in range(100)})
    sweep.write(root / "prompts.json", [])
    sweep.write(root / "gold.json", {})
    (old / "gpt_oss_lora/adapter_model.safetensors").write_bytes(b"test-only")
    sweep.write(
        root / "prepared.json",
        {
            "planned_calls": 1200,
            "frozen_input_sha256": sweep.digest(root / "frozen-inputs.json"),
            "prompts_sha256": sweep.digest(root / "prompts.json"),
            "gold_sha256": sweep.digest(root / "gold.json"),
            "adapter_sha256": sweep.digest(
                old / "gpt_oss_lora/adapter_model.safetensors"
            ),
        },
    )
    return config, root, old


def test_each_budget_gets_fresh_sequential_process_and_complete_conditions_can_resume(
    tmp_path, monkeypatch
):
    import os

    config, root, old = isolated_fixture(tmp_path)
    torch_before = sys.modules.get("torch")
    monkeypatch.setattr(sys.modules[__name__], "PROCESS_SENTINEL", "parent-state")
    monkeypatch.setattr(sweep, "run_condition", isolated_cpu_worker)
    monkeypatch.setattr(sweep.subprocess, "run", lambda *args, **kwargs: None)
    sweep.run(config, root, old, root / "config.json")
    receipts = [sweep.read(p) for p in sorted((root / "conditions").glob("*.json"))]
    assert len(receipts) == 12
    assert all(r["status"] == "completed" and r["exitcode"] == 0 for r in receipts)
    assert all(r["worker_pid"] != os.getpid() for r in receipts)
    for receipt in receipts:
        rows = list(
            (root / "raw").glob(f"{receipt['model']}-{receipt['budget']}-*.json")
        )
        assert len(rows) == 100
        assert {sweep.read(p)["worker_pid"] for p in rows} == {receipt["worker_pid"]}
    chronological = sorted(receipts, key=lambda r: r["started_at"])
    assert all(
        a["exited_at"] <= b["started_at"]
        for a, b in zip(chronological, chronological[1:])
    )
    assert sweep.read(root / "progress.json")["completed"] == 1200
    assert sys.modules.get("torch") is torch_before  # Controller never imports CUDA.
    sweep.run(config, root, old, root / "config.json")
    assert receipts == [
        sweep.read(p) for p in sorted((root / "conditions").glob("*.json"))
    ]


def test_worker_failure_stops_sweep_and_blocks_partial_resume(tmp_path, monkeypatch):
    config, root, old = isolated_fixture(tmp_path, fail_budget=512)
    monkeypatch.setattr(sweep, "run_condition", isolated_cpu_worker)
    scored = []
    monkeypatch.setattr(
        sweep.subprocess,
        "run",
        lambda argv, **kwargs: scored.append(argv),
    )
    with pytest.raises(RuntimeError, match="adapter/512 failed"):
        sweep.run(config, root, old, root / "config.json")
    assert len(list((root / "raw").glob("*.json"))) == 100
    assert len(scored) == 1 and scored[0][2] == "score"
    assert sweep.read(root / "conditions/adapter-512.json")["status"] == "failed"
    assert not (root / "conditions/adapter-2048.json").exists()
    with pytest.raises(ValueError, match="Interrupted condition"):
        sweep.run(config, root, old, root / "config.json")


def test_scoring_failure_does_not_hide_original_worker_failure(tmp_path, monkeypatch):
    config, root, old = isolated_fixture(tmp_path, fail_budget=128)
    monkeypatch.setattr(sweep, "run_condition", isolated_cpu_worker)

    def scoring_fails(*args, **kwargs):
        raise RuntimeError("scorer unavailable")

    monkeypatch.setattr(sweep.subprocess, "run", scoring_fails)
    with pytest.raises(RuntimeError, match="Condition adapter/128 failed"):
        sweep.run(config, root, old, root / "config.json")
    receipt = sweep.read(root / "conditions/adapter-128.json")
    assert receipt["status"] == "failed"
    assert "scorer unavailable" in receipt["partial_score_error"]


def test_old_outputs_and_changed_frozen_inputs_cannot_join_new_protocol(tmp_path):
    config, root, old = isolated_fixture(tmp_path)
    sweep.write(root / "raw/adapter-128-0.json", {"legacy": True})
    with pytest.raises(ValueError, match="Unattributed"):
        sweep.run(config, root, old, root / "config.json")
    (root / "prompts.json").write_text('["changed"]')
    with pytest.raises(ValueError, match="Frozen artifact changed"):
        sweep.run(config, root, old, root / "config.json")


def test_legacy_cli_run_rejected_without_overwriting_historical_progress(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"output_dir": "result"}))
    root = tmp_path / "result"
    root.mkdir()
    original = b'{"status":"failed","completed":302}'
    (root / "progress.json").write_bytes(original)
    monkeypatch.setattr(sweep, "REPO", tmp_path)
    monkeypatch.setattr(sys, "argv", ["runner", "run", "--config", str(config_path)])
    with pytest.raises(ValueError, match="Legacy results are read-only"):
        sweep.main()
    assert (root / "progress.json").read_bytes() == original
    assert not (root / "error.json").exists()


def test_condition_worker_preserves_original_error(tmp_path, monkeypatch):
    config, root, old = isolated_fixture(tmp_path)
    (root / "conditions").mkdir()

    def fail(*args):
        raise RuntimeError("original allocation error")

    monkeypatch.setattr(sweep, "_generate_condition", fail)
    with pytest.raises(RuntimeError, match="original allocation error"):
        sweep.run_condition(config, root, old, root / "config.json", "adapter", 65536)
    error = sweep.read(root / "conditions/adapter-65536-error.json")
    assert error["budget"] == 65536
    assert "original allocation error" in error["traceback"]


def test_dynamic_kwarg_survives_unsloth_config_override_without_mutating_model():
    from types import SimpleNamespace

    model = SimpleNamespace(
        generation_config=SimpleNamespace(
            cache_implementation=None,
            eos_token_id=[2],
            temperature=0.7,
        )
    )
    original = deepcopy(model.generation_config)
    kwargs = sweep.cache_generate_kwargs(model, "dynamic")
    # Reproduce the installed wrapper's config mutation and final HF kwarg merge.
    kwargs["generation_config"].cache_implementation = "static"
    effective = {**vars(kwargs.pop("generation_config")), **kwargs}
    assert effective == {**vars(original), "cache_implementation": "dynamic"}
    assert model.generation_config == original
    assert sweep.cache_generate_kwargs(model, "native") == {}
    assert sweep.cache_policy({}) == "native"
    with pytest.raises(ValueError, match="Unsupported cache"):
        sweep.cache_policy({"cache_policy": "typo"})
    with pytest.raises(ValueError, match="Extra generation"):
        sweep.cache_policy({"extra_generate_kwargs": {"temperature": 0}})


class FakeAttention:
    def register_forward_pre_hook(self, hook, *, with_kwargs):
        assert with_kwargs
        self.hook = hook
        self.removed = False
        return self

    def remove(self):
        self.removed = True


@pytest.mark.parametrize("observed", ["DynamicCache", "StaticCache", None])
def test_dynamic_cache_is_observed_and_hook_is_always_removed(observed):
    from types import SimpleNamespace

    attention = FakeAttention()
    model = SimpleNamespace(
        named_modules=lambda: [("model.layers.0.self_attn", attention)]
    )

    def generate():
        with sweep.observe_dynamic_cache(model, "dynamic") as evidence:
            if observed:
                attention.hook(
                    attention, (), {"past_key_values": type(observed, (), {})()}
                )
        return evidence

    if observed == "DynamicCache":
        assert generate() == {"cache_class": "DynamicCache"}
    else:
        with pytest.raises(ValueError, match="DynamicCache|not observed"):
            generate()
    assert attention.removed


def test_cache_hook_cleanup_preserves_generation_exception():
    from types import SimpleNamespace

    attention = FakeAttention()
    model = SimpleNamespace(named_modules=lambda: [("model.self_attn", attention)])
    with pytest.raises(RuntimeError, match="original OOM"):
        with sweep.observe_dynamic_cache(model, "dynamic"):
            raise RuntimeError("original OOM")
    assert attention.removed
    with sweep.observe_dynamic_cache(object(), "native") as evidence:
        assert evidence == {}


def test_dynamic_comparison_rejects_different_cohort_and_changed_runner(
    tmp_path, monkeypatch
):
    config, reference, old = isolated_fixture(tmp_path)
    original = sweep.read(reference / "prepared.json")
    for key in sweep.COMPARISON_HASHES:
        original.setdefault(key, "0" * 64)
    sweep.write(reference / "prepared.json", original)
    dynamic = {
        **config,
        "cache_policy": "dynamic",
        "comparison_reference": str(reference),
    }
    audit = {**original, "runner_sha256": sweep.digest(Path(sweep.__file__))}
    sweep.verify_comparison(dynamic, audit, old)
    audit["frozen_input_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="differs from frozen"):
        sweep.verify_comparison(dynamic, audit, old)
    audit["frozen_input_sha256"] = original["frozen_input_sha256"]
    audit["runner_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="runner changed"):
        sweep.verify_comparison(dynamic, audit, old)


@pytest.mark.parametrize("cache_class", [None, "StaticCache"])
def test_dynamic_scoring_rejects_outputs_without_cache_evidence(
    tmp_path, monkeypatch, cache_class
):
    from types import SimpleNamespace

    config, root, old = isolated_fixture(tmp_path)
    config.update(cache_policy="dynamic", models=["base"], budgets=[128])
    sweep.write(root / "gold.json", {"case": {"assessment": "present"}})
    sweep.write(
        root / "raw/base-128-case.json",
        {
            "cache_policy": "dynamic",
            "cache_observation": {"cache_class": cache_class},
        },
    )
    (old / "score.py").write_text(
        "# Scoring must be rejected before calling the scorer.\n"
    )
    monkeypatch.setitem(
        sys.modules,
        "openai_harmony",
        SimpleNamespace(
            HarmonyEncodingName=SimpleNamespace(HARMONY_GPT_OSS="test"),
            load_harmony_encoding=lambda _: None,
        ),
    )
    monkeypatch.setattr(sweep, "verify_preparation", lambda *args: {})
    monkeypatch.setattr(sys, "path", list(sys.path))
    with pytest.raises(ValueError, match="unverified dynamic cache output"):
        sweep.score(config, root, old)
    assert not (root / "confusion-matrices.json").exists()
