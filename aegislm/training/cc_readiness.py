"""Validate real batch-1 tuning evidence before the provisional v5 comparison."""

from __future__ import annotations

import importlib
import json
import math
from pathlib import Path
from typing import Any

from aegislm.artifacts import validate_no_symlink_components
from aegislm.evaluation.harness import load_jsonl
from aegislm.training.cc_decision import (
    ROOT,
    gpu_identity,
    package_versions,
    tokenizer_assets,
    verify_inputs,
)
from aegislm.training.source_config import artifact_directory_sha256
from aegislm.training.two_stage import digest


def validate_update_evidence(
    training: dict[str, Any], observed: dict[str, Any], reload: dict[str, Any]
) -> None:
    """Accept zero-LR warmup, but require complete finite updates and exact frozen reload."""
    if (
        training["pass"] is not True
        or training["optimizer_steps"] != 2
        or training["gradient_checks"] != 2
        or observed["steps"] != 2
        or observed["gradient_checks"] != 2
        or len(observed["losses"]) != 2
        or not all(math.isfinite(float(x)) for x in observed["losses"])
        or not math.isfinite(float(training["loss"]))
        or training["before_sha256"] == training["after_sha256"]
        or observed["before_sha256"] != training["before_sha256"]
        or observed["after_sha256"] != training["after_sha256"]
        or observed["updates"] != training["updates"]
        or [u["step"] for u in training["updates"]] != [1, 2]
        or any(
            not math.isfinite(u["optimizer_lr"]) or u["optimizer_lr"] < 0
            for u in training["updates"]
        )
        or not any(
            u["optimizer_lr"] > 0 and u["fingerprint"] != previous
            for previous, u in zip(
                [training["before_sha256"]]
                + [x["fingerprint"] for x in training["updates"][:-1]],
                training["updates"],
                strict=True,
            )
        )
        or training["updates"][-1]["fingerprint"] != training["after_sha256"]
        or reload["pass"] is not True
        or reload["optimizer_steps"] != 0
        or not reload["active_adapters"]
        or reload["after_sha256"] != training["after_sha256"]
        or reload["adapter_sha256"] != training["adapter_sha256"]
        or reload["provenance"] != training["provenance"]
    ):
        raise ValueError("incomplete finite training/update/reload evidence")


def validate_tracking_binding(
    training: dict[str, Any],
    reloaded: dict[str, Any],
    receipt: dict[str, Any],
    remote: Any,
) -> None:
    """Reject another run's receipt even if its remote summary reports success."""
    from aegislm.training.two_stage_runtime import wandb_run_path

    recorded = {key: receipt[key] for key in ("id", "path")}
    namespace = training["provenance"]["diagnostic_namespace"]
    if (
        receipt["remote_readiness_confirmed"] is not True
        or training["wandb"] != recorded
        or reloaded["wandb"] != recorded
        or receipt["path"].split("/")[-1] != receipt["id"]
        or remote.id != receipt["id"]
        or wandb_run_path(remote) != receipt["path"]
        or remote.name != f"{namespace}-decision-runtime-smoke"
        or remote.config.get("recipe") != "cc_unsloth_smoke_v1"
        or remote.config.get("model_revision")
        != training["provenance"]["base_revision"]
        or remote.summary.get("diagnostic/training_pass") is not True
        or remote.summary.get("diagnostic/adapter_reload_pass") is not True
        or remote.summary.get("diagnostic/optimizer_steps") != 2
    ):
        raise ValueError("diagnostic W&B run binding or remote summary mismatch")


def functional_readiness(
    config: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Bind saved diagnostic evidence to current model/data/code/device and remote summary."""
    policy = config["readiness"]
    if policy["policy"] != "batch1_training_and_reload_v1":
        raise ValueError("unsupported functional readiness policy")
    output = Path(policy["training_diagnostic"]).absolute()
    if not output.is_relative_to(ROOT / "outputs"):
        raise ValueError("diagnostic outside outputs")
    validate_no_symlink_components(output, description="diagnostic")
    training = json.loads((output / "diagnostic.json").read_text())
    observed = json.loads((output / "observed-training.json").read_text())
    reloaded = json.loads((output / "reload.json").read_text())
    inputs = json.loads((output / "inputs.json").read_text())
    validate_update_evidence(training, observed, reloaded)
    prov = training["provenance"]
    if (
        training["config_sha256"] != manifest["config_sha256"]
        or training["config_snapshot"] != config
        or inputs != {key: training[key] for key in inputs}
        or training["dataset_hashes"] != verify_inputs(config)
        or training["packages"] != package_versions()
        or training["tokenizer_assets"] != tokenizer_assets(config)
        or training["source_hashes"] != manifest["source_hashes"]
        or training["gpu"] != gpu_identity()
        or prov["base_revision"] != config["model"]["revision"]
        or prov["tokenizer_sha256"] != manifest["tokenizer_sha256"]
        or prov["diagnostic_namespace"] != output.name
        or training["training"] != {**config["training"], "max_steps": 2}
        or training["test_or_validation_used_for_optimizer"] is not False
    ):
        raise ValueError("functional readiness candidate binding mismatch")
    for name, expected in training["source_hashes"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("diagnostic code changed")
    from scripts.diagnose_cc_unsloth import select_train

    rows = load_jsonl(
        Path(config["dataset"]["root"]) / "decision-candidates/train.jsonl"
    )
    if training["train_ids"] != [
        r["id"] for r in select_train(rows, manifest["preflight_ids"])
    ]:
        raise ValueError("diagnostic used different training IDs")
    adapter = ROOT / "adapters" / output.name / "final"
    if (
        json.loads((adapter.parent / "training.json").read_text()) != training
        or artifact_directory_sha256(adapter) != training["adapter_sha256"]
    ):
        raise ValueError("diagnostic saved adapter changed")
    receipt = json.loads((output / "wandb.json").read_text())
    remote = importlib.import_module("wandb").Api(timeout=20).run(receipt["path"])
    validate_tracking_binding(training, reloaded, receipt, remote)
    return {
        "pass": True,
        "policy": policy["policy"],
        "diagnostic_optimizer_steps": 2,
        "diagnostic_path": str(output.relative_to(ROOT)),
        "diagnostic_sha256": digest(output / "diagnostic.json"),
        "reload_sha256": digest(output / "reload.json"),
        "adapter_sha256": training["adapter_sha256"],
        "train_ids": training["train_ids"],
        "wandb_path": receipt["path"],
        "remote_summary_confirmed": True,
        "quality_evaluated": False,
        "production_approved": False,
    }
