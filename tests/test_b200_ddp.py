"""CPU rejection checks for the bounded two-GPU adaptation and completed-run receipts."""

import ast
from pathlib import Path

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
