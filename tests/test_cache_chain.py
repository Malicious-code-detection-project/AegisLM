from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts.b200 import queue_dynamic


def completed() -> dict[str, Any]:
    return {
        "status": "completed",
        "exit_code": 0,
        "arms": {
            kind: {"status": "completed", "generation_exit": 0, "score_exit": 0}
            for kind in ("base", "adapter")
        },
    }


def test_wait_for_final_scoring_lock() -> None:
    assert not queue_dynamic.predecessor_ready(completed(), True)
    assert queue_dynamic.predecessor_ready(completed(), False)


@pytest.mark.parametrize("status", ["running", "failed", "interrupted", "checking"])
def test_unlocked_unfinished_native_never_starts_dynamic(status: str) -> None:
    state = completed()
    state["status"] = status
    with pytest.raises(ValueError, match="successfully"):
        queue_dynamic.predecessor_ready(state, False)


@pytest.mark.parametrize("field", ["status", "generation_exit", "score_exit"])
def test_both_arms_must_be_successful(field: str) -> None:
    state = deepcopy(completed())
    state["arms"]["adapter"][field] = "failed" if field == "status" else 1
    with pytest.raises(ValueError, match="Both native arms"):
        queue_dynamic.predecessor_ready(state, False)


def test_base_only_completion_is_not_enough() -> None:
    state = completed()
    del state["arms"]["adapter"]
    with pytest.raises(ValueError, match="Both native arms"):
        queue_dynamic.predecessor_ready(state, False)


def test_changed_queued_source_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(queue_dynamic, "ROOT", tmp_path)
    path = tmp_path / "runner.py"
    path.write_text("original")
    expected = {"runner.py": queue_dynamic.evaluate.sweep().digest(path)}
    queue_dynamic.verify_sources(expected)
    path.write_text("changed")
    with pytest.raises(ValueError, match="Queued source changed"):
        queue_dynamic.verify_sources(expected)


def test_wait_then_launch_once_and_refresh_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from types import SimpleNamespace

    monkeypatch.setattr(queue_dynamic, "ROOT", tmp_path)
    (tmp_path / "outputs").mkdir()
    events: list[str] = []
    locks = iter([True, False])
    arms = [{"model": kind, "gpu": "0,1"} for kind in ("base", "adapter")]
    sweep = SimpleNamespace(
        digest=lambda path: "sha",
        now=lambda: "time",
        write=lambda path, data: path.write_text(json.dumps(data)),
    )
    monkeypatch.setattr(queue_dynamic.evaluate, "sweep", lambda: sweep)
    monkeypatch.setattr(queue_dynamic, "native_locked", lambda control: next(locks))
    monkeypatch.setattr(
        queue_dynamic.evaluate,
        "read",
        lambda path: (
            completed() if path.name == "state.json" else {"sources": [], "notes": []}
        ),
    )
    monkeypatch.setattr(
        queue_dynamic.evaluate, "plan", lambda *args: [{"pending_conditions": 0}]
    )
    monkeypatch.setattr(queue_dynamic.evaluate, "arm_complete", lambda arm: True)
    monkeypatch.setattr(queue_dynamic.dynamic_evaluation, "plan", lambda run: arms)
    monkeypatch.setattr(
        queue_dynamic.dynamic_evaluation,
        "execute",
        lambda run: events.append("dynamic"),
    )
    monkeypatch.setattr(
        queue_dynamic.time, "sleep", lambda seconds: events.append("wait")
    )
    monkeypatch.setattr(queue_dynamic.subprocess, "check_output", lambda *a, **kw: "")
    monkeypatch.setattr(
        queue_dynamic.compare_cache,
        "write_report",
        lambda *args: events.append("report"),
    )
    queue_dynamic.execute("trial")
    assert events == ["wait", "dynamic", "report"]
    state = json.loads(
        (tmp_path / "outputs/trial-dynamic-evaluation/queue.json").read_text()
    )
    assert state["status"] == "completed"
    assert state["arms"] == arms
    with pytest.raises(ValueError, match="already exists"):
        queue_dynamic.execute("trial")
    assert events == ["wait", "dynamic", "report"]
