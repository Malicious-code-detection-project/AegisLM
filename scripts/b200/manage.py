"""CPU-only relocation and integrity checks for the B200 reproduction kit."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "scripts/b200"
TRAIN = ROOT / "outputs/b200-step100-v1"
NATIVE = ROOT / "configs/environments/cc-native-step100/.venv"
SCORER = ROOT / "configs/environments/cc-harmony-score/.venv/bin/python"
HUB = ROOT / "outputs/b200-hf-hub"
REFERENCE = ROOT / "data/reproduction/b200-step100-v1"
SCRIPT_REFERENCE = KIT / "reference"


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def verify_data() -> None:
    manifest = read(ROOT / "configs/b200_reproduction_manifest.json")
    for relative, expected in manifest["files"].items():
        path = ROOT / relative
        require(
            path.is_file() and digest(path) == expected,
            f"Frozen data mismatch: {relative}",
        )
    print(f"Verified {len(manifest['files'])} frozen files")


def pack_data() -> None:
    """Export only the hash-verified data files listed in the committed manifest."""
    verify_data()
    archive = ROOT / "outputs/b200-frozen-data-v1.tar.gz"
    require(
        not archive.exists(),
        "Data archive already exists; preserve the previous export",
    )
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as stream:
        for relative in read(ROOT / "configs/b200_reproduction_manifest.json")["files"]:
            require(
                relative.startswith("data/"), "Only data files belong in this export"
            )
            stream.add(ROOT / relative, arcname=relative, recursive=False)
    archive.with_name(archive.name + ".sha256").write_text(
        f"{digest(archive)}  {archive.name}\n"
    )
    print(archive)


def init() -> None:
    verify_data()
    require(
        not TRAIN.exists(),
        "Training directory already exists; preserve it, do not initialize again",
    )
    config_paths = [
        ROOT / f"configs/b200-{kind}-validation100-v1.json"
        for kind in ("base", "adapter")
    ]
    require(
        not any(p.exists() for p in config_paths), "B200 configuration already exists"
    )
    support_files = (
        ("cc-official-tutorial-v5-token-caps-20261004-v1", "adapted-training.py"),
        ("unsloth-official-tutorial-generation-64-20261004-v1", "run.py"),
    )
    for directory, name in support_files:
        destination = ROOT / "outputs" / directory / name
        require(
            not destination.exists(),
            f"Historical support file already exists: {destination}",
        )
    TRAIN.mkdir(parents=True)
    donor = REFERENCE / "training"
    for name in (
        "original.py",
        "LICENSE",
        "prepare.py",
        "train.py",
        "common.py",
        "score.py",
        "prompts.json",
        "gold.json",
    ):
        source = donor if name.endswith(".json") else SCRIPT_REFERENCE / "training"
        shutil.copy2(source / name, TRAIN / name)
    config = read(donor / "config.json")
    config.update(
        experiment_id="b200-step100-v1",
        title="B200: frozen v5, official 100-step training",
        venv=str(NATIVE),
        hf_hub_cache=str(HUB),
        status="prepared",
    )
    config["reproduction"] = {
        "prompt_template_date": "2026-10-04",
        "hardware": "B200",
        "source": "A6000 official step100",
    }
    write(TRAIN / "config.json", config)
    write(TRAIN / "results.json", {"training": {"status": "pending"}, "generation": []})
    for directory, name in support_files:
        destination = ROOT / "outputs" / directory / name
        require(
            not destination.exists(),
            f"Historical support file already exists: {destination}",
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCRIPT_REFERENCE / directory / name, destination)
    for kind, path in zip(("base", "adapter"), config_paths, strict=True):
        config = read(REFERENCE / "evaluation-config.json")
        config.update(
            experiment_id=f"b200-{kind}-validation100-v1",
            output_dir=f"outputs/b200-{kind}-validation100-v1",
            training_reference=str(TRAIN.relative_to(ROOT)),
            selection_reference="data/reproduction/b200-step100-v1/probe-inputs.json",
            scorer_python=str(SCORER),
            models=[kind],
        )
        write(path, config)
    print(
        "Initialized a new 100-step training run and two independent 600-call evaluation runs"
    )


def check_data() -> None:
    actual = read(TRAIN / "dataset-audit.json")
    expected = read(REFERENCE / "training/dataset-audit.json")
    for key in (
        "status",
        "source_train_records",
        "source_validation_records",
        "test_used",
        "train_validation_id_overlap",
        "training_messages_sha256",
        "pure_mask_source_sha256",
        "counts",
        "records",
    ):
        require(actual[key] == expected[key], f"Training data/masking differs: {key}")
    print(
        "Training messages, all 10,000 token/mask audits and exclusion counts match A6000"
    )


def check_env(kind: str) -> None:
    expected = read(REFERENCE / f"{kind}-packages.json")
    actual = {}
    for name, package in expected.items():
        distribution = importlib.metadata.distribution(name)
        require(
            distribution.version == package["version"],
            f"Package version differs: {name}",
        )
        actual[name] = {"version": distribution.version}
        if package.get("direct_url"):
            direct = json.loads(distribution.read_text("direct_url.json") or "{}")
            require(
                direct.get("vcs_info", {}).get("commit_id")
                == package["direct_url"]["vcs_info"]["commit_id"],
                f"Git revision differs: {name}",
            )
            actual[name]["direct_url"] = direct
    require(platform.python_version() == "3.12.13", "Expected Python 3.12.13")
    write(
        ROOT / f"outputs/b200-{kind}-environment.json",
        {"python": sys.version, "executable": sys.executable, "packages": actual},
    )
    print(f"Verified {len(expected)} {kind} package versions and Git revisions")


def check_training() -> None:
    runtime, training = (
        read(TRAIN / "training-runtime.json"),
        read(TRAIN / "training.json"),
    )
    require(runtime["status"] == "completed", "Training/save not completed")
    require(
        training["status"] == "completed" and training["global_step"] == 100,
        "Expected 100 completed optimizer steps",
    )
    require(training["effective_records"] == 8525, "Effective training cohort differs")
    require(training["updated_tensors"] > 0, "No adapter tensor was updated")
    adapter = TRAIN / "gpt_oss_lora/adapter_model.safetensors"
    require(adapter.is_file(), "Adapter missing")
    write(
        TRAIN / "b200-verification.json",
        {
            "status": "passed",
            "global_step": 100,
            "effective_records": 8525,
            "adapter_sha256": digest(adapter),
            "A6000_adapter_sha256": read(REFERENCE / "evaluation-prepared.json")[
                "adapter_sha256"
            ],
            "weights_expected_identical": False,
        },
    )
    print("Verified 100-step training and newly saved adapter")


def check_eval(kind: str) -> None:
    prepared = read(ROOT / f"outputs/b200-{kind}-validation100-v1/prepared.json")
    expected = read(REFERENCE / "evaluation-prepared.json")
    for key in (
        "validation_sha256",
        "train_sha256",
        "selection_sha256",
        "frozen_input_sha256",
        "prompts_sha256",
        "gold_sha256",
        "input_tokens_min",
        "input_tokens_max",
        "gold_counts",
        "train_id_overlap",
        "train_user_content_overlap",
        "gold_in_generation_input",
        "test_used",
    ):
        require(prepared[key] == expected[key], f"Evaluation cohort differs: {key}")
    require(prepared["planned_calls"] == 600, "Expected 600 calls per model")
    require(
        prepared["adapter_sha256"]
        == digest(TRAIN / "gpt_oss_lora/adapter_model.safetensors"),
        "Wrong B200 adapter",
    )
    print(f"Verified {kind}: same six data hashes, new B200 adapter, 600 planned calls")


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "action",
        choices=(
            "verify-data",
            "pack-data",
            "init",
            "check-data",
            "check-env",
            "check-training",
            "check-eval",
        ),
    )
    parser.add_argument("kind", nargs="?")
    args = parser.parse_args()
    if args.action == "check-env":
        require(args.kind in ("native", "score"), "Choose native or score")
        check_env(args.kind)
    elif args.action == "check-eval":
        require(args.kind in ("base", "adapter"), "Choose base or adapter")
        check_eval(args.kind)
    else:
        {
            "verify-data": verify_data,
            "pack-data": pack_data,
            "init": init,
            "check-data": check_data,
            "check-training": check_training,
        }[args.action]()


if __name__ == "__main__":
    main()
