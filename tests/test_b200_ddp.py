"""CPU rejection checks for the bounded two-GPU adaptation and completed-run receipts."""

import ast
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.b200 import train_ddp as driver


@pytest.mark.parametrize("rank", [0, 1])
def test_ddp_adaptation_preserves_recipe_and_global_batch(
    tmp_path: Path, rank: int
) -> None:
    original = (driver.ROOT / "scripts/b200/reference/training/original.py").read_text()
    tree = driver.adapt(original, tmp_path, rank)
    (config,) = driver.calls(tree, "SFTConfig")
    values = {key.arg: ast.literal_eval(key.value) for key in config.keywords}
    assert (
        values["per_device_train_batch_size"]
        * 2
        * values["gradient_accumulation_steps"]
        == 4
    )
    assert values["max_steps"] == 100
    assert values["seed"] == 3407
    assert values["learning_rate"] == 0.0002
    assert values["optim"] == "adamw_8bit"
    assert values["warmup_steps"] == 5
    assert values["ddp_find_unused_parameters"] is True
    assert values["gradient_checkpointing"] is False
    (model,) = driver.calls(tree, "from_pretrained")
    assert ast.literal_eval(
        next(k.value for k in model.keywords if k.arg == "device_map")
    ) == {"": rank}
    (peft,) = driver.calls(tree, "get_peft_model")
    (original_peft,) = driver.calls(driver.selected_tree(original), "get_peft_model")
    (original_checkpoint,) = [
        k for k in original_peft.keywords if k.arg == "use_gradient_checkpointing"
    ]
    original_checkpoint.value = ast.Constant(False)
    assert ast.dump(peft) == ast.dump(original_peft)
    (mask,) = driver.calls(tree, "train_on_responses_only")
    (original_mask,) = driver.calls(
        driver.selected_tree(original), "train_on_responses_only"
    )
    assert ast.dump(mask) == ast.dump(original_mask)


def test_tampered_original_and_invalid_rank_are_rejected(tmp_path: Path) -> None:
    original = (driver.ROOT / "scripts/b200/reference/training/original.py").read_text()
    with pytest.raises(RuntimeError, match="source changed"):
        driver.adapt(original + "\n# changed\n", tmp_path, 0)
    with pytest.raises(RuntimeError, match="local rank"):
        driver.adapt(original, tmp_path, 2)


def test_plain_or_single_rank_launch_is_rejected_before_creating_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    monkeypatch.setenv("WORLD_SIZE", "1")
    monkeypatch.setenv("LOCAL_RANK", "0")
    monkeypatch.setenv("RANK", "0")
    with pytest.raises(RuntimeError, match="torchrun"):
        driver.train(driver.DEFAULT_RUN)
    assert not (tmp_path / "outputs").exists()


@pytest.fixture
def completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    run = driver.run_path(driver.DEFAULT_RUN)
    driver.write(run / "training-runtime.json", {"status": "completed"})
    for rank in (0, 1):
        driver.write(
            run / f"rank{rank}/training.json",
            {
                "status": "completed",
                "rank": rank,
                "world_size": 2,
                "global_step": 100,
                "effective_records": 8525,
                "updated_tensors": 1,
                "sft_config": {
                    "gradient_accumulation_steps": 2,
                    "per_device_train_batch_size": 1,
                },
                "metrics": {"train_loss": 0.12},
                "final_trainable_hashes": {"lora": "same"},
                "dataset_sha256": "same",
            },
        )
    adapter = run / "gpt_oss_lora/adapter_model.safetensors"
    adapter.parent.mkdir()
    adapter.write_bytes(b"synthetic adapter for receipt rejection tests")
    driver.write(
        run / "adapter-save-verification.json",
        {
            "status": "passed",
            "saved_matches_trained": True,
            "adapter_sha256": driver.digest(adapter),
        },
    )
    return run


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("world_size", 1, "Rank receipt"),
        ("global_step", 99, "Expected 100 steps"),
        ("effective_records", 8524, "Expected 100 steps"),
        ("updated_tensors", 0, "Expected 100 steps"),
        (
            "final_trainable_hashes",
            {"lora": "different"},
            "Rank weight/data disagreement",
        ),
        ("dataset_sha256", "different", "Rank weight/data disagreement"),
    ],
)
def test_invalid_rank_receipt_cannot_pass(
    completed: Path, field: str, bad_value: object, message: str
) -> None:
    receipt = driver.read(completed / "rank1/training.json")
    receipt[field] = bad_value
    driver.write(completed / "rank1/training.json", receipt)
    with pytest.raises(RuntimeError, match=message):
        driver.check(driver.DEFAULT_RUN)
    assert not (completed / "b200-verification.json").exists()


def test_adapter_changed_after_save_verification_is_rejected(completed: Path) -> None:
    (completed / "gpt_oss_lora/adapter_model.safetensors").write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="Saved adapter verification failed"):
        driver.check(driver.DEFAULT_RUN)


def test_complete_matching_rank_receipts_pass(completed: Path) -> None:
    driver.check(driver.DEFAULT_RUN)
    result = driver.read(completed / "b200-verification.json")
    assert result["world_size"] == 2 and result["global_step"] == 100
    assert result["effective_batch_size"] == 4


def test_changed_mask_counts_are_rejected() -> None:
    audit = {
        "records": [
            {"id": str(i), "tokens": 2, "supervised_tokens": 1} for i in range(8525)
        ]
    }
    records = [
        {"id": str(i), "input_ids": [1, 2], "labels": [-100, 2]} for i in range(8525)
    ]
    assert len(driver.dataset_signature(records, audit)) == 64
    records[300]["labels"] = [-100, -100]
    with pytest.raises(RuntimeError, match="Supervision differs"):
        driver.dataset_signature(records, audit)


@pytest.fixture
def launcher_repo(tmp_path: Path) -> Path:
    """Run the real shell launcher against a CPU-only native interpreter stub."""
    scripts = tmp_path / "scripts/b200"
    scripts.mkdir(parents=True)
    shutil.copyfile(driver.ROOT / "scripts/b200/run-ddp.sh", scripts / "run-ddp.sh")
    run = tmp_path / "outputs" / driver.DEFAULT_RUN
    for rank in (0, 1):
        (run / f"rank{rank}").mkdir(parents=True)
    (run / "config.json").write_text("{}\n")
    (tmp_path / "outputs/b200-runtime-env.sh").write_text("# Test-only environment\n")
    native = tmp_path / "configs/environments/cc-native-step100/.venv/bin/python"
    native.parent.mkdir(parents=True)
    native.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> outputs/native-calls.log\n'
        'if [[ "$1" == "-m" ]]; then exit "${TEST_TRAIN_EXIT:-0}"; fi\n'
    )
    native.chmod(0o755)
    return tmp_path


def launch(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(repo / "scripts/b200/run-ddp.sh"), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_launcher_default_matches_initializer(launcher_repo: Path) -> None:
    result = launch(launcher_repo)
    assert result.returncode == 0, result.stderr
    calls = (launcher_repo / "outputs/native-calls.log").read_text()
    assert f"train --run {driver.DEFAULT_RUN}" in calls
    receipt = launcher_repo / "outputs" / driver.DEFAULT_RUN / "launcher-exit.json"
    assert json.loads(receipt.read_text()) == {"exit_code": 0}


@pytest.mark.parametrize("exit_code", [0, 17])
def test_launcher_rerun_preserves_first_exit_and_does_not_invoke_native(
    launcher_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
) -> None:
    monkeypatch.setenv("TEST_TRAIN_EXIT", str(exit_code))
    first = launch(launcher_repo, driver.DEFAULT_RUN)
    assert first.returncode == exit_code
    receipt = launcher_repo / "outputs" / driver.DEFAULT_RUN / "launcher-exit.json"
    original = receipt.read_bytes()
    calls = (launcher_repo / "outputs/native-calls.log").read_bytes()
    assert json.loads(original) == {"exit_code": exit_code}
    monkeypatch.setenv("TEST_TRAIN_EXIT", "23")
    second = launch(launcher_repo, driver.DEFAULT_RUN)
    assert second.returncode != 0
    assert receipt.read_bytes() == original
    assert (launcher_repo / "outputs/native-calls.log").read_bytes() == calls


@pytest.mark.parametrize(
    "artifact",
    [
        "rank0/attempt.json",
        "rank1/attempt.json",
        "launcher-attempt.json",
        "launcher-exit.json",
    ],
)
def test_launcher_refuses_existing_attempt_before_trap(
    launcher_repo: Path,
    artifact: str,
) -> None:
    run = launcher_repo / "outputs" / driver.DEFAULT_RUN
    original = b'{"preserve":"original"}\n'
    (run / artifact).write_bytes(original)
    result = launch(launcher_repo, driver.DEFAULT_RUN)
    assert result.returncode != 0
    assert (run / artifact).read_bytes() == original
    assert not (launcher_repo / "outputs/native-calls.log").exists()
    if artifact != "launcher-exit.json":
        assert not (run / "launcher-exit.json").exists()


def test_launcher_rejects_uninitialized_run_without_receipt(
    launcher_repo: Path,
) -> None:
    name = "b200-ddp2-step100-not-initialized"
    result = launch(launcher_repo, name)
    assert result.returncode != 0
    assert "Initialize this run first" in result.stderr
    assert not (launcher_repo / "outputs" / name).exists()
    assert not (launcher_repo / "outputs/native-calls.log").exists()


def test_launcher_preserves_failure_before_rank_attempts(launcher_repo: Path) -> None:
    (launcher_repo / "outputs/b200-runtime-env.sh").unlink()
    first = launch(launcher_repo, driver.DEFAULT_RUN)
    assert first.returncode != 0
    run = launcher_repo / "outputs" / driver.DEFAULT_RUN
    receipt = (run / "launcher-exit.json").read_bytes()
    claim = (run / "launcher-attempt.json").read_bytes()
    assert json.loads(receipt)["exit_code"] == first.returncode
    assert not (run / "rank0/attempt.json").exists()
    assert not (run / "rank1/attempt.json").exists()
    second = launch(launcher_repo, driver.DEFAULT_RUN)
    assert second.returncode != 0
    assert (run / "launcher-exit.json").read_bytes() == receipt
    assert (run / "launcher-attempt.json").read_bytes() == claim
