"""CPU checks for clone-based setup, immutable inputs and data-only transfer."""

import hashlib
import json
from pathlib import Path
import tarfile

import pytest

from scripts.b200 import manage


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Relocate the launcher into a clone-shaped workspace with synthetic data."""
    reference = tmp_path / "data/reproduction/b200-step100-v1"
    monkeypatch.setattr(manage, "ROOT", tmp_path)
    monkeypatch.setattr(manage, "TRAIN", tmp_path / "outputs/b200-step100-v1")
    monkeypatch.setattr(manage, "NATIVE", tmp_path / "native/.venv")
    monkeypatch.setattr(manage, "SCORER", tmp_path / "score/.venv/bin/python")
    monkeypatch.setattr(manage, "HUB", tmp_path / "outputs/b200-hf-hub")
    monkeypatch.setattr(manage, "REFERENCE", reference)
    manage.write(reference / "training/config.json", {"training": {"max_steps": 100}})
    manage.write(reference / "training/prompts.json", [])
    manage.write(reference / "training/gold.json", [])
    manage.write(
        reference / "evaluation-config.json",
        {
            "budgets": [128, 512, 2048, 65536, 130000, "context-minus-input"],
            "samples_per_condition": 100,
            "runtime_context": 131072,
            "execution_protocol": "fresh-process-per-model-budget-v2",
        },
    )
    files = {
        str(p.relative_to(tmp_path)): manage.digest(p)
        for p in reference.rglob("*.json")
    }
    manage.write(tmp_path / "configs/b200_reproduction_manifest.json", {"files": files})
    return tmp_path


def test_export_contains_only_manifest_data(clone: Path) -> None:
    (clone / ".env").write_text("THIS_MUST_NOT_BE_EXPORTED=true")
    manage.pack_data()
    archive = clone / "outputs/b200-frozen-data-v1.tar.gz"
    expected = manage.read(clone / "configs/b200_reproduction_manifest.json")["files"]
    with tarfile.open(archive) as stream:
        assert set(stream.getnames()) == set(expected)
        for member in stream.getmembers():
            payload = stream.extractfile(member)
            assert payload is not None
            assert hashlib.sha256(payload.read()).hexdigest() == expected[member.name]
    assert (
        archive.with_name(archive.name + ".sha256")
        .read_text()
        .startswith(manage.digest(archive))
    )


def test_tampered_data_blocks_init_and_export(clone: Path) -> None:
    (manage.REFERENCE / "training/gold.json").write_text('["modified"]')
    for action in (manage.init, manage.pack_data):
        with pytest.raises(RuntimeError, match="Frozen data mismatch"):
            action()
    assert not manage.TRAIN.exists()
    assert not (clone / "outputs/b200-frozen-data-v1.tar.gz").exists()


def test_init_relocates_training_and_separates_evaluation_arms(clone: Path) -> None:
    manage.init()
    training = manage.read(manage.TRAIN / "config.json")
    assert training["venv"] == str(manage.NATIVE)
    assert training["hf_hub_cache"] == str(manage.HUB)
    for kind in ("base", "adapter"):
        config = manage.read(clone / f"configs/b200-{kind}-validation100-v1.json")
        assert config["models"] == [kind]
        assert len(config["budgets"]) * config["samples_per_condition"] == 600
        assert config["training_reference"] == "outputs/b200-step100-v1"
        assert config["selection_reference"].startswith("data/reproduction/")
        assert config["scorer_python"] == str(manage.SCORER)
    original = (manage.TRAIN / "config.json").read_bytes()
    with pytest.raises(RuntimeError, match="Training directory already exists"):
        manage.init()
    assert (manage.TRAIN / "config.json").read_bytes() == original


def test_existing_support_file_blocks_init_before_training_directory(
    clone: Path,
) -> None:
    path = (
        clone
        / "outputs/cc-official-tutorial-v5-token-caps-20261004-v1/adapted-training.py"
    )
    path.parent.mkdir(parents=True)
    path.write_text("preserve this attempt")
    with pytest.raises(RuntimeError, match="Historical support file already exists"):
        manage.init()
    assert path.read_text() == "preserve this attempt"
    assert not manage.TRAIN.exists()


@pytest.mark.parametrize(
    ("status", "steps", "message"),
    [
        ("failed", 100, "Training/save not completed"),
        ("completed", 99, "100 completed optimizer steps"),
        ("completed", 100, "Adapter missing"),
    ],
)
def test_incomplete_training_cannot_pass(
    clone: Path, status: str, steps: int, message: str
) -> None:
    manage.write(manage.TRAIN / "training-runtime.json", {"status": status})
    manage.write(
        manage.TRAIN / "training.json",
        {
            "status": "completed",
            "global_step": steps,
            "effective_records": 8525,
            "updated_tensors": 1,
        },
    )
    with pytest.raises(RuntimeError, match=message):
        manage.check_training()


def test_preserved_tutorial_matches_original_source() -> None:
    manifest = json.loads(
        (
            Path(__file__).parents[1] / "configs/b200_reproduction_manifest.json"
        ).read_text()
    )
    assert all(path.startswith("data/") for path in manifest["files"])
    assert manage.digest(manage.SCRIPT_REFERENCE / "training/original.py") == (
        "74ff47bb9212f482f7378d86f27bc088973e924ae427cc84891d87663131895a"
    )
