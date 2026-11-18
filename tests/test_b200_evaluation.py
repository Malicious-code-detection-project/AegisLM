"""CPU-only checks for frozen plans, sequential execution and partial-result reporting."""

from pathlib import Path
import sys
from typing import Any

import pytest

from scripts import run_cc_native_validation100 as sweep
from scripts.b200 import evaluate


@pytest.fixture
def evaluation_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(evaluate, "ROOT", tmp_path)
    monkeypatch.setattr(sweep, "REPO", tmp_path)
    for env in (evaluate.NATIVE, evaluate.SCORER):
        path = tmp_path / env
        path.parent.mkdir(parents=True)
        path.touch()
    runner = tmp_path / evaluate.RUNNER
    runner.parent.mkdir(parents=True)
    runner.write_text("# CPU fixture only\n")
    old = tmp_path / "outputs/trained"
    (old / "gpt_oss_lora").mkdir(parents=True)
    sweep.write(old / "training-runtime.json", {"status": "completed"})
    (old / "gpt_oss_lora/adapter_model.safetensors").write_bytes(b"fixture-only")
    for kind in ("base", "adapter"):
        root = tmp_path / f"outputs/trained-{kind}-validation100"
        (root / "raw").mkdir(parents=True)
        config = {
            "models": [kind],
            "budgets": [128, 512],
            "samples_per_condition": 100,
            "training_reference": "outputs/trained",
            "output_dir": str(root.relative_to(tmp_path)),
            "execution_protocol": sweep.ISOLATION_PROTOCOL,
        }
        sweep.write(tmp_path / f"configs/trained-{kind}-validation100.json", config)
        sweep.write(root / "config.json", config)
        sweep.write(root / "frozen-inputs.json", {str(i): {} for i in range(100)})
        sweep.write(root / "gold.json", {})
        sweep.write(root / "prompts.json", [])
        audit = {
            "planned_calls": 200,
            "adapter_sha256": sweep.digest(
                old / "gpt_oss_lora/adapter_model.safetensors"
            ),
        }
        for filename, key in (
            ("frozen-inputs.json", "frozen_input_sha256"),
            ("gold.json", "gold_sha256"),
            ("prompts.json", "prompts_sha256"),
        ):
            audit[key] = sweep.digest(root / filename)
        sweep.write(root / "prepared.json", audit)
    return tmp_path


def test_plan_uses_frozen_inputs_and_preserves_all_files(evaluation_root: Path) -> None:
    before = {p: p.read_bytes() for p in evaluation_root.rglob("*") if p.is_file()}
    arms = evaluate.plan("trained", "all", None)
    assert [(a["model"], a["gpu"], a["pending_conditions"]) for a in arms] == [
        ("base", "0", 2),
        ("adapter", "0", 2),
    ]
    assert before == {
        p: p.read_bytes() for p in evaluation_root.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("gpus", ["0,1,2", "a", "-1"])
def test_bad_gpu_selection_rejected(evaluation_root: Path, gpus: str) -> None:
    with pytest.raises(ValueError, match="GPU index"):
        evaluate.plan("trained", "all", gpus)


def test_completed_conditions_skip_but_partial_conditions_block(
    evaluation_root: Path,
) -> None:
    root = evaluation_root / "outputs/trained-base-validation100"
    (root / "conditions").mkdir()
    for ident in range(100):
        sweep.write(root / f"raw/base-128-{ident}.json", {})
    sweep.write(
        root / "conditions/base-128.json",
        {
            "status": "completed",
            "exitcode": 0,
            "execution_protocol": sweep.ISOLATION_PROTOCOL,
        },
    )
    assert evaluate.plan("trained", "all", "0,1")[0]["pending_conditions"] == 1
    sweep.write(root / "raw/base-512-0.json", {})
    with pytest.raises(ValueError, match="Unattributed"):
        evaluate.plan("trained", "all", None)


def test_changed_adapter_and_unsafe_run_name_rejected(evaluation_root: Path) -> None:
    with pytest.raises(ValueError, match="run name"):
        evaluate.plan("../trained", "all", None)
    (
        evaluation_root / "outputs/trained/gpt_oss_lora/adapter_model.safetensors"
    ).write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        evaluate.plan("trained", "all", None)


def test_summary_preserves_pending_and_two_matrix_definitions(
    evaluation_root: Path,
) -> None:
    root = evaluation_root / "outputs/trained-base-validation100"
    (evaluation_root / "outputs/trained-evaluation").mkdir()
    sweep.write(root / "raw/base-128-0.json", {})
    group = {
        "budget": 128,
        "completed": 3,
        "planned": 100,
        "pending": 97,
        "strict_matrix": [[1, 0, 0, 1], [0, 0, 0, 1]],
        "semantic_matrix": [[1, 1, 0, 0], [0, 1, 0, 0]],
    }
    sweep.write(
        root / "confusion-matrices.json",
        {"scored_at": "earlier", "complete": False, "groups": [group]},
    )
    result = evaluate.save_summary("trained")
    assert result["arms"][0]["completed_raw"] == 1
    assert result["arms"][0]["groups"][0] == group
    text = (evaluation_root / "outputs/trained-evaluation/summary.md").read_text()
    assert "| strict | 1 | 0 | 0 | 0 | 0 | 2 | 97 |" in text
    assert "| semantic | 1 | 1 | 0 | 1 | 0 | 0 | 97 |" in text


@pytest.mark.parametrize("base_exit", [0, 1])
def test_controller_checks_both_arms_then_runs_sequentially_and_stops_on_failure(
    evaluation_root: Path, monkeypatch: pytest.MonkeyPatch, base_exit: int
) -> None:
    arms = evaluate.plan("trained", "all", "0,1")
    events: list[Any] = []

    class Process:
        pid = 999999

        def __init__(self, command: list[str], **kwargs: Any) -> None:
            self.kind = "base" if "-base-" in command[-1] else "adapter"
            self.returncode = base_exit if self.kind == "base" else 0
            events.append(
                (
                    "start",
                    self.kind,
                    kwargs["env"]["CUDA_VISIBLE_DEVICES"],
                    kwargs["start_new_session"],
                )
            )

        def poll(self) -> int:
            return self.returncode

    def checked(command: list[str], **kwargs: Any) -> Any:
        events.append(("check", command[2], kwargs["env"]["CUDA_VISIBLE_DEVICES"]))
        return None

    monkeypatch.setattr(evaluate.subprocess, "run", checked)
    monkeypatch.setattr(evaluate.subprocess, "Popen", Process)
    monkeypatch.setattr(
        evaluate, "terminate", lambda p: events.append(("stop", p.kind))
    )
    monkeypatch.setattr(evaluate, "score_arm", lambda *args: 0)
    monkeypatch.setattr(evaluate, "arm_complete", lambda arm: True)
    assert evaluate.execute("trained", arms) == base_exit
    starts = [event for event in events if event[0] == "start"]
    assert starts[0] == ("start", "base", "0", True)
    assert len(starts) == (1 if base_exit else 2)
    if not base_exit:
        assert events.index(("stop", "base")) < events.index(
            ("start", "adapter", "1", True)
        )
    assert len([event for event in events if event[0] == "check"]) == 2


def test_zero_exit_is_insufficient_without_completed_evidence(
    evaluation_root: Path,
) -> None:
    arm = evaluate.plan("trained", "base", None)[0]
    root = evaluation_root / arm["output"]
    sweep.write(root / "confusion-matrices.json", {"complete": True, "groups": []})
    assert evaluate.arm_complete(arm) is False


def test_tmux_start_uses_background_session_and_quoted_paths(
    evaluation_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands = []
    monkeypatch.setattr(
        evaluate.subprocess, "run", lambda command, **kwargs: commands.append(command)
    )
    monkeypatch.setattr(sys, "argv", ["evaluate", "start", "--run", "trained"])
    evaluate.main()
    assert commands[0][:5] == ["tmux", "new-session", "-d", "-s", "b200-eval-trained"]
    assert "scripts/b200/run-evaluation.sh run --run trained" in commands[0][-1]
    assert ">>" in commands[0][-1]


@pytest.mark.parametrize("final_score_fails", [False, True])
def test_start_failure_preserves_generation_and_scoring_error_classification(
    evaluation_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_score_fails: bool,
) -> None:
    arms = evaluate.plan("trained", "all", None)
    starts: list[list[str]] = []
    scores: list[str] = []

    def failed_start(command: list[str], **kwargs: Any) -> None:
        starts.append(command)
        raise OSError("simulated process start failure")

    def score(arm: dict[str, Any], *args: Any) -> int:
        scores.append(arm["model"])
        # Both preflight scores succeed; only the final score may fail.
        if len(scores) == 3 and final_score_fails:
            raise RuntimeError("simulated final scoring failure")
        return 0

    def unexpected_completion(arm: dict[str, Any]) -> bool:
        pytest.fail("A process that never started cannot be complete")

    monkeypatch.setattr(evaluate.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(evaluate.subprocess, "Popen", failed_start)
    monkeypatch.setattr(evaluate, "score_arm", score)
    monkeypatch.setattr(evaluate, "arm_complete", unexpected_completion)
    assert evaluate.execute("trained", arms) == 1
    state = sweep.read(evaluation_root / "outputs/trained-evaluation/state.json")
    assert state["status"] == "failed"
    assert state["error"] == "OSError"
    assert state["exit_code"] == 1
    base = state["arms"]["base"]
    assert base["status"] == "failed"
    assert base["generation_exit"] is None
    assert base["score_exit"] == (1 if final_score_fails else 0)
    if final_score_fails:
        assert base["score_error"] == "RuntimeError"
    else:
        assert "score_error" not in base
    assert state["arms"]["adapter"]["status"] == "pending"
    assert len(starts) == 1
    assert "-base-" in starts[0][-1]
    assert scores == ["base", "adapter", "base"]


def test_interrupt_stops_worker_group_and_records_partial_status(
    evaluation_root, monkeypatch
):
    arms = evaluate.plan("trained", "all", None)
    stopped = []

    class Process:
        pid = 999999
        returncode = None

        def __init__(self, *args, **kwargs):
            pass

        def poll(self):
            raise KeyboardInterrupt

    def stop(process):
        stopped.append(process.pid)
        process.returncode = -15

    monkeypatch.setattr(evaluate.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(evaluate.subprocess, "Popen", Process)
    monkeypatch.setattr(evaluate, "terminate", stop)
    monkeypatch.setattr(evaluate, "score_arm", lambda *args: 0)
    assert evaluate.execute("trained", arms) == 130
    assert stopped == [999999]
    state = sweep.read(evaluation_root / "outputs/trained-evaluation/state.json")
    assert state["status"] == "interrupted"
    assert state["arms"]["adapter"]["status"] == "pending"


def test_status_is_read_only_and_reports_current_counts(
    evaluation_root, monkeypatch, capsys
):
    before = {p: p.read_bytes() for p in evaluation_root.rglob("*") if p.is_file()}
    monkeypatch.setattr(sys, "argv", ["evaluate", "status", "--run", "trained"])
    evaluate.main()
    output = capsys.readouterr().out
    assert "base: 생성 0/200, 채점 0/200" in output
    assert "adapter: 생성 0/200, 채점 0/200" in output
    assert before == {
        p: p.read_bytes() for p in evaluation_root.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("gpus", [None, "0,1", "1,0"])
def test_sharded_plan_assigns_both_gpus_to_each_arm(evaluation_root, monkeypatch, gpus):
    for kind in ("base", "adapter"):
        config_path = evaluation_root / f"configs/trained-{kind}-validation100.json"
        config = sweep.read(config_path)
        config.update(model_device_map="balanced", model_gpu_count=2)
        sweep.write(config_path, config)
        output = evaluation_root / config["output_dir"]
        sweep.write(output / "config.json", config)
        prepared = sweep.read(output / "prepared.json")
        prepared.update(model_device_map="balanced", model_gpu_count=2)
        sweep.write(output / "prepared.json", prepared)
    arms = evaluate.plan("trained", "all", gpus)
    assert [arm["gpu"] for arm in arms] == [gpus or "0,1"] * 2
    for bad in ("0", "0,0", "0,1,2"):
        with pytest.raises(ValueError, match="two distinct"):
            evaluate.plan("trained", "all", bad)
    commands = []
    monkeypatch.setattr(
        evaluate.subprocess, "run", lambda command, **kwargs: commands.append(command)
    )
    monkeypatch.setattr(sys, "argv", ["evaluate", "start", "--run", "trained"])
    evaluate.main()
    assert "--gpus 0,1 " in commands[0][-1]
    assert "0,1,0,1" not in commands[0][-1]


def test_model_sharding_refuses_single_gpu_and_cpu_offload():
    from types import SimpleNamespace

    config = {"model_device_map": "balanced", "model_gpu_count": 2}
    assert sweep.model_load_kwargs({}, 1) == {}
    assert sweep.model_load_kwargs(config, 2) == {"device_map": "balanced"}
    with pytest.raises(ValueError, match="two visible"):
        sweep.model_load_kwargs(config, 1)
    for devices in (("cuda:0",), ("cuda:1",), ("cuda:0", "cuda:1", "cpu")):
        model = SimpleNamespace(
            parameters=lambda: [SimpleNamespace(device=d) for d in devices]
        )
        with pytest.raises(ValueError, match="both GPUs"):
            sweep.verify_model_placement(model, config)
    model = SimpleNamespace(
        parameters=lambda: [SimpleNamespace(device=d) for d in ("cuda:0", "cuda:1")]
    )
    assert sweep.verify_model_placement(model, config)["parameter_devices"] == [
        "cuda:0",
        "cuda:1",
    ]
