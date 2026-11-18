from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.b200 import compare_cache, dynamic_evaluation


def test_abstentions_stay_in_full_cohort_metrics() -> None:
    row = {
        "counts": [20, 27, 9, 37, 0, 7],
        "completed": 100,
        "planned": 100,
        "observed_positive": 50,
    }
    result = compare_cache.metrics(row)
    assert result["precision"] == pytest.approx(20 / 29)
    assert result["recall_decisive"] == pytest.approx(20 / 47)
    assert result["positive_detection_recall"] == 0.4
    assert result["f1_decisive"] == pytest.approx(40 / 76)
    assert result["decision_coverage"] == 0.93
    assert result["accuracy_completed"] == 0.57


def test_empty_invalid_and_partial_are_distinct() -> None:
    for counts, completed, coverage in [
        ([0] * 6, 0, None),
        ([0, 0, 0, 0, 0, 100], 100, 0),
    ]:
        result = compare_cache.metrics(
            {"counts": counts, "completed": completed, "planned": 100}
        )
        assert result["precision"] is None
        assert result["decision_coverage"] == coverage
        assert result["completion_rate"] == completed / 100
    result = compare_cache.metrics(
        {
            "counts": [2, 0, 0, 0, 0, 0],
            "completed": 2,
            "planned": 100,
            "observed_positive": 2,
        }
    )
    assert result["positive_detection_recall"] == 1
    assert result["completion_rate"] == 0.02


def test_inconsistent_counts_fail() -> None:
    with pytest.raises(ValueError, match="partition"):
        compare_cache.metrics(
            {"counts": [1, 0, 0, 0, 0, 0], "completed": 100, "planned": 100}
        )


def test_matrices_and_missing_sources(tmp_path: Path) -> None:
    source = {
        "groups": [
            {
                "model": "base",
                "budget": 128,
                "completed": 2,
                "planned": 100,
                "strict_matrix": [[1, 0, 0, 1], [0, 0, 0, 0]],
                "semantic_matrix": [[1, 0, 1, 0], [0, 0, 0, 0]],
            }
        ]
    }
    (tmp_path / "matrix.json").write_text(json.dumps(source))
    manifest: dict[str, Any] = {
        "notes": [],
        "sources": [
            {"path": "matrix.json", "hardware": "B200", "cache": "native"},
            {"path": "missing.json", "hardware": "B200", "cache": "dynamic"},
        ],
    }
    result = compare_cache.collect(manifest, tmp_path)
    assert len(result["rows"]) == 2
    assert len(result["missing_sources"]) == 1
    assert result["rows"][0]["metrics"]["positive_detection_recall"] == 0.5
    manifest["sources"].append(manifest["sources"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        compare_cache.collect(manifest, tmp_path)


@pytest.fixture
def comparison_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(dynamic_evaluation, "ROOT", tmp_path)
    (tmp_path / "configs").mkdir()
    for kind in ("base", "adapter"):
        config = {
            "models": [kind],
            "model_device_map": "balanced",
            "model_gpu_count": 2,
            "output_dir": f"outputs/trial-{kind}-validation100",
            "training_reference": "outputs/trial",
        }
        (tmp_path / "configs" / f"trial-{kind}-validation100.json").write_text(
            json.dumps(config)
        )
    return tmp_path


def test_dynamic_changes_only_identity_and_cache(comparison_root: Path) -> None:
    pairs = dynamic_evaluation.configurations("trial")
    assert [config["models"] for _, config in pairs] == [["base"], ["adapter"]]
    for path, config in pairs:
        assert config["model_gpu_count"] == 2
        assert config["model_device_map"] == "balanced"
        assert config["cache_policy"] == "dynamic"
        assert config["comparison_reference"] != config["output_dir"]
        assert path.name.startswith("trial-dynamic-")


@pytest.mark.parametrize("run", ["../trial", "trial/other", "a;echo", ""])
def test_unsafe_run_names_fail(run: str) -> None:
    with pytest.raises(ValueError, match="run name"):
        dynamic_evaluation.configurations(run)


def test_single_gpu_reference_rejected(comparison_root: Path) -> None:
    path = comparison_root / "configs/trial-base-validation100.json"
    config = json.loads(path.read_text())
    config["model_gpu_count"] = 1
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="both GPUs"):
        dynamic_evaluation.configurations("trial")


def test_native_lock_blocks_dynamic_before_gpu_query(
    comparison_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fcntl

    control = comparison_root / "outputs/trial-evaluation"
    control.mkdir(parents=True)
    monkeypatch.setattr(dynamic_evaluation, "plan", lambda run: [])
    with (control / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            dynamic_evaluation.execute("trial")


def test_foreign_gpu_process_blocks_generation(
    comparison_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (comparison_root / "outputs").mkdir()
    monkeypatch.setattr(dynamic_evaluation, "plan", lambda run: [])
    monkeypatch.setattr(
        dynamic_evaluation.subprocess, "check_output", lambda *a, **kw: "12345\n"
    )
    with pytest.raises(ValueError, match="GPU processes"):
        dynamic_evaluation.execute("trial")


@pytest.mark.parametrize("base_exit", [0, 1])
def test_pipeline_is_sequential_and_stops_on_failure(
    comparison_root: Path, monkeypatch: pytest.MonkeyPatch, base_exit: int
) -> None:
    from types import SimpleNamespace

    (comparison_root / "outputs").mkdir()
    arms = [
        {"model": kind, "config": f"configs/{kind}.json", "output": f"outputs/{kind}"}
        for kind in ("base", "adapter")
    ]
    states: list[dict[str, Any]] = []
    starts: list[str] = []
    exits = iter([base_exit, 0])
    fake_sweep = SimpleNamespace(
        now=lambda: "fixed-time",
        digest=lambda path: "fixed-sha",
        write=lambda path, state: states.append(dict(state)),
        condition_plan=lambda *args: ({}, []),
    )
    monkeypatch.setattr(dynamic_evaluation, "plan", lambda run: arms)
    monkeypatch.setattr(dynamic_evaluation.evaluate, "sweep", lambda: fake_sweep)
    monkeypatch.setattr(
        dynamic_evaluation.evaluate, "read", lambda path: {"complete": True}
    )
    monkeypatch.setattr(dynamic_evaluation.evaluate, "terminate", lambda child: None)
    monkeypatch.setattr(
        dynamic_evaluation.subprocess, "check_output", lambda *a, **kw: ""
    )
    monkeypatch.setattr(dynamic_evaluation.subprocess, "run", lambda *a, **kw: None)

    def launch(command: list[str], **kwargs: Any) -> Any:
        starts.append(command[-1])
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "0,1"
        assert kwargs["start_new_session"] is True
        return SimpleNamespace(wait=lambda: next(exits))

    monkeypatch.setattr(dynamic_evaluation.subprocess, "Popen", launch)
    if base_exit:
        with pytest.raises(RuntimeError, match="next model not started"):
            dynamic_evaluation.execute("trial")
        assert starts == ["configs/base.json"]
        assert states[-1]["status"] == "failed"
    else:
        dynamic_evaluation.execute("trial")
        assert starts == ["configs/base.json", "configs/adapter.json"]
        assert states[-1]["status"] == "completed"
