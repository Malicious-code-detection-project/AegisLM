"""CPU/mocked checks for the user-run fresh recipe; no real training required."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aegislm.datasets.source import SourceAssessmentRecord
from aegislm.tracking.wandb import source_training_wandb_config
from aegislm.training import fresh
from aegislm.training.source_config import reserve_training_stage
from aegislm.training.source_gate import GateRunSummary
from scripts import train_source_unsloth_fresh as entrypoint


def _config() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "configs/source_v2_unsloth_fresh.json"
    return fresh.load_fresh_config(path)


def _data() -> fresh.FreshData:
    def records(prefix: str, count: int) -> list[SourceAssessmentRecord]:
        return [
            SourceAssessmentRecord(
                f"{prefix}-{index}",
                (
                    {"role": "system", "content": "Return JSON."},
                    {"role": "user", "content": "{}"},
                    {"role": "assistant", "content": "{}"},
                ),
            )
            for index in range(count)
        ]

    train = records("train", 1001)
    validation = records("validation", 41)
    return fresh.FreshData(train, validation, train[:1000], validation[:40])


class FakeTokenizer:
    def apply_chat_template(
        self,
        conversation: Any,
        *,
        tokenize: bool,
        add_generation_prompt: bool = False,
        return_dict: bool = False,
        reasoning_effort: str = "medium",
    ) -> Any:
        assert reasoning_effort == "low"
        ids = [10, 11] if add_generation_prompt else [10, 11, 20, 21]
        return {"input_ids": ids, "attention_mask": [1] * len(ids)}


def test_committed_fresh_config_preserves_gate_and_uses_new_paths():
    config = _config()
    assert config["recipe"] == fresh.FRESH_RECIPE
    assert config["canary"]["minimum_schema_pass_rate"] == 0.9
    assert config["training"]["learning_rate"] == 5e-5
    assert config["training"]["output_dir"] == "adapters/source-v2-unsloth-fresh-v1"


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("recipe", None, "unsloth_v2"),
        ("canary", "validation_size", 8),
        ("canary", "generation_batch_size", 8),
        ("canary", "minimum_schema_pass_rate", 0.5),
        ("canary", "train_selection_strategy", "target_cwe_assessment_round_robin_v1"),
        ("protocol", "reasoning_effort", "medium"),
    ],
)
def test_fresh_rejects_weakened_or_changed_contract(tmp_path, section, key, value):
    config = _config()
    if key is None:
        config[section] = value
    else:
        config[section][key] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        fresh.load_fresh_config(path)


def test_fresh_requires_explicit_challenge(tmp_path):
    config = _config()
    del config["dataset"]["challenge_path"]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="challenge_path"):
        fresh.load_fresh_config(path)


def test_stage_selection_keeps_smoke_out_of_full_and_gate_unchanged():
    data = _data()
    smoke_train, smoke_gate = fresh.select_fresh_stage(data, "smoke")
    assert smoke_train == data.canary_train[:32]
    assert smoke_gate == data.gate[:8]
    assert fresh.select_fresh_stage(data, "canary") == (data.canary_train, data.gate)
    assert fresh.select_fresh_stage(data, "full") == (data.train, data.gate)
    with pytest.raises(ValueError):
        fresh.select_fresh_stage(data, "unknown")


def test_prepare_loads_only_local_pinned_tokenizer(monkeypatch, tmp_path):
    config = _config()
    requests = []
    snapshot = tmp_path / config["model"]["revision"]
    monkeypatch.setattr(
        fresh, "resolve_fresh_tokenizer_snapshot", lambda _config: snapshot
    )

    def from_pretrained(model_id, **kwargs):
        assert model_id == str(snapshot)
        assert kwargs["local_files_only"] is True
        assert "revision" not in kwargs  # Already bound by the local snapshot path.
        return FakeTokenizer()

    def import_module(name):
        requests.append(name)
        assert name == "transformers"
        return SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=from_pretrained)
        )

    monkeypatch.setattr(fresh.importlib, "import_module", import_module)
    report = fresh.prepare_fresh_tokens(config, _data())
    assert requests == ["transformers"]
    assert report["train"]["min_supervised_tokens"] == 2
    assert report["validation"]["records"] == 41
    assert report["tokenizer"]["revision"] == config["model"]["revision"]


@pytest.mark.parametrize("configured_complete", [False, True])
def test_tokenizer_cache_selection_preserves_revision_and_precedence(
    monkeypatch,
    tmp_path,
    configured_complete,
):
    config = _config()
    revision = config["model"]["revision"]
    configured = tmp_path / "configured" / revision
    default = tmp_path / "default" / revision
    configured.mkdir(parents=True)
    default.mkdir(parents=True)
    for filename in fresh.FRESH_TOKENIZER_FILES:
        (default / filename).write_text("{}")
        if configured_complete:
            (configured / filename).write_text("{}")
    calls = []

    def cached(repo_id, filename, *, cache_dir, revision):
        assert repo_id == config["model"]["runtime_model_id"]
        assert revision == config["model"]["revision"]
        calls.append(cache_dir)
        path = (default if cache_dir is None else configured) / filename
        return str(path) if path.is_file() else None

    def import_module(name):
        assert name == "huggingface_hub"
        return SimpleNamespace(try_to_load_from_cache=cached)

    monkeypatch.setattr(fresh.importlib, "import_module", import_module)
    assert fresh.resolve_fresh_tokenizer_snapshot(config) == (
        configured if configured_complete else default
    )
    assert (None in calls) is not configured_complete


def test_tokenizer_resolver_never_mixes_partial_caches(monkeypatch, tmp_path):
    config = _config()
    snapshot = tmp_path / config["model"]["revision"]
    snapshot.mkdir()
    for filename in fresh.FRESH_TOKENIZER_FILES:
        (snapshot / filename).write_text("{}")

    def cached(repo_id, filename, *, cache_dir, revision):
        # The union is complete, but neither individual cache is complete.
        if (cache_dir is None) == (filename == "tokenizer.json"):
            return str(snapshot / filename)
        return object()  # HF's cached-missing sentinel is not a path.

    monkeypatch.setattr(
        fresh.importlib,
        "import_module",
        lambda name: SimpleNamespace(try_to_load_from_cache=cached),
    )
    with pytest.raises(FileNotFoundError, match="No complete tokenizer snapshot"):
        fresh.resolve_fresh_tokenizer_snapshot(config)


def test_tokenization_retains_prompt_mask_and_rejects_attention_mismatch():
    rows = fresh.tokenize_fresh_records(_data().train[:1], FakeTokenizer(), _config())
    assert rows[0]["labels"] == [-100, -100, 20, 21]

    class BadMask(FakeTokenizer):
        def apply_chat_template(self, *args, **kwargs):
            output = super().apply_chat_template(*args, **kwargs)
            output["attention_mask"] = [1]
            return output

    with pytest.raises(ValueError, match="attention mask length"):
        fresh.tokenize_fresh_records(_data().train[:1], BadMask(), _config())


@pytest.mark.parametrize(
    "arguments",
    [
        ["--prepare-only", "--wandb"],
        ["--prepare-only", "--resume-from-checkpoint", "checkpoint-10"],
        ["--prepare-only", "--reload-only"],
        ["--reload-only", "--wandb"],
        ["--wandb-reconcile", "finish-only"],
    ],
)
def test_invalid_cli_modes_fail_before_runtime_loading(arguments):
    with pytest.raises(SystemExit):
        entrypoint.parse_args(arguments)


def test_prepare_main_never_enters_training(monkeypatch):
    monkeypatch.chdir(entrypoint.REPO_ROOT)
    monkeypatch.setattr(entrypoint, "load_fresh_config", lambda _path: _config())
    monkeypatch.setattr(entrypoint, "load_fresh_data", lambda _config: _data())
    monkeypatch.setattr(entrypoint, "prepare_fresh_tokens", lambda *args: {"ok": True})
    monkeypatch.setattr(
        entrypoint, "run_training", lambda *args: pytest.fail("training called")
    )
    entrypoint.main(["--prepare-only"])


def test_full_gate_failure_prevents_training(monkeypatch):
    monkeypatch.chdir(entrypoint.REPO_ROOT)
    monkeypatch.setattr(entrypoint, "load_fresh_config", lambda _path: _config())
    monkeypatch.setattr(entrypoint, "load_fresh_data", lambda _config: _data())

    def reject(*args):
        raise ValueError("canary failed")

    monkeypatch.setattr(entrypoint, "require_fresh_canary", reject)
    monkeypatch.setattr(
        entrypoint, "run_training", lambda *args: pytest.fail("training called")
    )
    with pytest.raises(ValueError, match="canary failed"):
        entrypoint.main(["--stage", "full"])


def test_fresh_paths_are_read_only_and_reject_dataset_output_overlap(tmp_path):
    config = _config()
    inputs = tmp_path / "dataset"
    inputs.mkdir()
    for split in ("train", "validation", "challenge"):
        path = inputs / f"{split}.jsonl"
        path.write_text("{}\n")
        config["dataset"][f"{split}_path"] = str(path)
        config["dataset"][f"{split}_sha256"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    config["model"]["cache_dir"] = str(tmp_path / "cache")
    config["training"]["output_dir"] = str(tmp_path / "adapters")
    config["training"]["checkpoint_dir"] = str(tmp_path / "checkpoints")
    fresh.validate_fresh_paths(config)
    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "adapters").exists()
    config["training"]["output_dir"] = str(inputs / "adapters")
    with pytest.raises(ValueError, match="dataset"):
        fresh.validate_fresh_paths(config)


def test_smoke_reservation_refuses_overwrite_and_changed_config_resume(tmp_path):
    arguments = dict(
        adapter_stage=tmp_path / "adapter" / "smoke",
        checkpoint_stage=tmp_path / "checkpoints" / "smoke",
        config_sha256="a" * 64,
        stage="smoke",
    )
    reserve_training_stage(**arguments, resume_from_checkpoint=None)
    with pytest.raises(FileExistsError):
        reserve_training_stage(**arguments, resume_from_checkpoint=None)
    checkpoint = arguments["checkpoint_stage"] / "checkpoint-10"
    checkpoint.mkdir()
    (checkpoint / "trainer_state.json").write_text("{}")
    reserve_training_stage(**arguments, resume_from_checkpoint=checkpoint)
    arguments["config_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="reservation"):
        reserve_training_stage(**arguments, resume_from_checkpoint=checkpoint)


def test_smoke_gate_has_no_promotion_authority(monkeypatch):
    monkeypatch.setattr(fresh, "artifact_directory_sha256", lambda _path: "a" * 64)
    monkeypatch.setattr(fresh, "file_sha256", lambda _path: "b" * 64)
    reports = []
    monkeypatch.setattr(
        fresh, "write_fresh_json", lambda path, report: reports.append(report)
    )
    summary = GateRunSummary(8, 8, 1.0, 8, 8, 8, {"eos": 8})
    report = fresh.write_fresh_gate(_config(), _data(), "smoke", summary, "a" * 64)
    assert report["passed"] is True
    assert report["promotion_authority"] is False
    assert reports == [report]


def test_fresh_wandb_projection_is_source_free():
    projected = source_training_wandb_config(_config(), "smoke", False)
    assert projected["stage"] == "smoke"
    assert projected["recipe"] == fresh.FRESH_RECIPE
    serialized = json.dumps(projected)
    assert "data/processed/" not in serialized
    assert "source_code" not in serialized


def test_training_callback_rejects_nonfinite_loss_without_wandb():
    callback = entrypoint.make_training_callback(
        SimpleNamespace(TrainerCallback=object),
        SimpleNamespace(),
        None,
    )
    with pytest.raises(RuntimeError, match="non-finite"):
        callback.on_log(
            None,
            SimpleNamespace(is_world_process_zero=True),
            None,
            logs={"loss": float("nan")},
        )


@pytest.mark.parametrize(
    "stage,passed,expected",
    [
        ("smoke", False, 0),
        ("canary", False, 1),
        ("full", False, 1),
        ("canary", True, 0),
    ],
)
def test_wandb_finish_recovery_preserves_local_failure(
    tmp_path, stage, passed, expected
):
    assert fresh.fresh_stage_exit_code(tmp_path, stage) == 1
    (tmp_path / "post_training_gate.json").write_text(
        json.dumps(
            {
                "recipe": fresh.FRESH_RECIPE,
                "stage": stage,
                "adapter_reload": True,
                "passed": passed,
            }
        )
    )
    assert fresh.fresh_stage_exit_code(tmp_path, stage) == expected


class TraceTokenizer:
    def decode(self, token_ids: list[int], *, skip_special_tokens: bool) -> str:
        assert skip_special_tokens is False
        assert -100 not in token_ids
        return ",".join(str(token_id) for token_id in token_ids)


def _trace_features() -> dict[str, list[int]]:
    return {
        "input_ids": [10, 11, 20, 21],
        "attention_mask": [1, 1, 1, 1],
        "labels": [-100, -100, 20, 21],
    }


def test_training_trace_excludes_ignore_index_from_decoding():

    features = {
        "input_ids": [10, 11, 20, 21],
        "attention_mask": [1, 1, 1, 1],
        "labels": [-100, -100, 20, 21],
    }

    trace = fresh.build_training_trace(_data().train[0], features, TraceTokenizer())

    assert trace["id"] == "train-0"
    assert trace["labels"] == [-100, -100, 20, 21]
    assert trace["decoded_input"] == "10,11,20,21"
    assert trace["decoded_masked_input"] == "10,11"
    assert trace["decoded_supervised_labels"] == "20,21"
    assert trace["masked_token_count"] == 2
    assert trace["supervised_token_count"] == 2


def test_training_traces_writes_jsonl(tmp_path: Path):
    path = tmp_path / "training-trace.jsonl"
    records = _data().train[:2]

    fresh.write_training_traces(
        path,
        records,
        [_trace_features(), _trace_features()],
        TraceTokenizer(),
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert [row["id"] for row in rows] == ["train-0", "train-1"]
    for row in rows:
        assert row["labels"] == [-100, -100, 20, 21]
        assert row["decoded_supervised_labels"] == "20,21"

    assert set(tmp_path.iterdir()) == {path}


def test_training_traces_refuses_overwrite(tmp_path: Path):
    path = tmp_path / "training-trace.jsonl"
    original = b"existing trace\n"
    path.write_bytes(original)

    with pytest.raises(FileExistsError):
        fresh.write_training_traces(
            path,
            _data().train[:1],
            [_trace_features()],
            TraceTokenizer(),
        )

    assert path.read_bytes() == original
    assert set(tmp_path.iterdir()) == {path}


def test_training_traces_cleans_up_after_partial_failure(tmp_path: Path):
    path = tmp_path / "training-trace.jsonl"
    broken_features = _trace_features()
    broken_features["labels"] = []

    with pytest.raises(ValueError, match="training feature lengths differ"):
        fresh.write_training_traces(
            path,
            _data().train[:2],
            [_trace_features(), broken_features],
            TraceTokenizer(),
        )

    assert not path.exists()
    assert list(tmp_path.iterdir()) == []
