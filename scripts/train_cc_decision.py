"""Prepare or explicitly execute the provisional v5 decision-only comparison."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aegislm.environment import load_project_env  # noqa: E402
from aegislm.training.cc_readiness import functional_readiness  # noqa: E402
from aegislm.training.cc_decision import (  # noqa: E402
    context,
    evaluation_rows,
    gpu_identity,
    load_config,
    load_data,
    prepare,
    wandb_readiness,
)
from aegislm.training.two_stage import digest, write_json  # noqa: E402
from scripts.train_source_two_stage import decision_score  # noqa: E402


def provenance(config: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Bind a saved adapter to the exact prepared comparison candidate."""
    return {
        "recipe": config["recipe"],
        "config_sha256": manifest["config_sha256"],
        "preparation_sha256": digest(Path(config["output_dir"]) / "manifest.json"),
        "dataset_inventory_sha256": config["dataset"]["inventory_sha256"],
        "base_revision": config["model"]["revision"],
        "tokenizer_sha256": manifest["tokenizer_sha256"],
    }


def require_preflight(config: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Require bound successful GPU and remote read-only tracking checks."""
    output = Path(config["output_dir"])
    receipt = json.loads((output / "preflight/receipt.json").read_text())
    gpu = output / "preflight/functional-readiness.json"
    if (
        receipt["config_sha256"] != manifest["config_sha256"]
        or receipt["preparation_sha256"] != digest(output / "manifest.json")
        or receipt["gpu_sha256"] != digest(gpu)
        or not json.loads(gpu.read_text())["pass"]
        or json.loads(gpu.read_text()) != functional_readiness(config, manifest)
        or receipt["gpu_identity"] != gpu_identity()
        or receipt["tokenizer_sha256"] != manifest["tokenizer_sha256"]
        or receipt["train_ids"] != manifest["preflight_ids"]
        or receipt["optimizer_steps"] != 0
        or receipt["wandb_readiness_sha256"]
        != digest(output / "preflight/wandb-readiness.json")
    ):
        raise ValueError("GPU preflight/config binding mismatch")
    if not json.loads((output / "preflight/wandb-readiness.json").read_text())["pass"]:
        raise ValueError("online W&B readiness required")


def worker(
    config: dict[str, Any], path: Path, stage: str, model_kind: str, split: str
) -> None:
    """Keep model loads isolated; only the explicit train worker may update weights."""
    from aegislm.training.two_stage_runtime import (
        generate,
        load_model,
        train,
    )

    if stage not in {"preflight", "baseline", "train", "evaluate"}:
        raise ValueError("unsupported worker stage")
    if stage == "baseline" and (model_kind != "base" or split != "development"):
        raise ValueError("pre-training baseline is base/development only")
    load_project_env(ROOT)
    manifest = context(config, path)
    data = load_data(config)
    output = Path(config["output_dir"])
    date = manifest["date"]
    if stage == "preflight":
        tracking = wandb_readiness()
        write_json(output / "preflight/wandb-readiness.json", tracking)
        if not tracking["pass"]:
            raise RuntimeError("W&B readiness failed; see local report")
        readiness = functional_readiness(config, manifest)
        write_json(output / "preflight/functional-readiness.json", readiness)
        write_json(
            output / "preflight/receipt.json",
            {
                "config_sha256": manifest["config_sha256"],
                "preparation_sha256": digest(output / "manifest.json"),
                "gpu_sha256": digest(output / "preflight/functional-readiness.json"),
                "gpu_identity": gpu_identity(),
                "wandb_readiness_sha256": digest(
                    output / "preflight/wandb-readiness.json"
                ),
                "tokenizer_sha256": manifest["tokenizer_sha256"],
                "train_ids": manifest["preflight_ids"],
                "optimizer_steps": 0,
            },
        )
        return
    require_preflight(config, manifest)
    if stage == "train":
        baseline = json.loads((output / "baseline/development.json").read_text())
        if (
            baseline["metrics"]["total_count"] != 100
            or baseline["metrics"]["missing_prediction_count"]
            or baseline["metrics"]["extra_prediction_count"]
            or baseline["config_sha256"] != manifest["config_sha256"]
            or baseline["input_ids"] != manifest["development_ids"]
        ):
            raise ValueError("complete base development evaluation required")
        if (
            (output / "decision").exists()
            or (Path(config["checkpoint_dir"]) / "decision").exists()
            or (Path(config["adapter_dir"]) / "decision").exists()
        ):
            raise ValueError(
                "training attempt already exists; no implicit retry/resume"
            )
        write_json(
            output / "decision/intent.json",
            {
                "config_sha256": manifest["config_sha256"],
                "train_count": 10000,
                "max_steps": 100,
                "test_used_for_training": False,
            },
        )
        train(
            config,
            date,
            "decision",
            data["exports"]["train"],
            output / "decision",
            provenance=provenance(config, manifest),
        )
        return
    if stage == "evaluate":
        training = json.loads((output / "decision/training.json").read_text())
        if training["steps"] != 100 or not training["gradients_checked"]:
            raise ValueError(
                "a complete fixed final training run is required before test"
            )
    adapter = (
        Path(config["adapter_dir"]) / "decision/final"
        if model_kind == "adapter"
        else None
    )
    model, tokenizer = load_model(
        config, date, adapter, provenance=provenance(config, manifest)
    )
    prompts, gold = evaluation_rows(data, split)
    folder = (
        output / "baseline"
        if stage == "baseline"
        else output / "evaluation" / model_kind
    )
    predictions = generate(
        model, tokenizer, prompts, folder / f"{split}.jsonl", "decision", model_kind
    )
    report = decision_score(gold, predictions)
    report.update(
        {
            "evaluation_split": split,
            "label_status": "source_label_unreviewed",
            "test_used_for_selection": False,
            "config_sha256": manifest["config_sha256"],
            "input_ids": [r["id"] for r in prompts],
            "adapter_reloaded": model_kind == "adapter",
        }
    )
    write_json(folder / f"{split}.json", report)
    if model_kind == "adapter":
        from aegislm.tracking import validate_wandb_payload

        receipt = json.loads((output / "decision/wandb.json").read_text())
        payload = {
            f"{split}/{k}": v
            for k, v in report["metrics"].items()
            if isinstance(v, (int, float))
        }
        validate_wandb_payload(payload)
        importlib.import_module("wandb").Api().run(receipt["path"]).summary.update(
            payload
        )


def main(argv: list[str] | None = None) -> None:
    """No default/all training: run only the explicitly requested stage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/cc_source_decision_v5.json")
    )
    parser.add_argument(
        "--stage",
        choices=("prepare", "preflight", "baseline", "train", "evaluate"),
        required=True,
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--model-kind",
        choices=("base", "adapter"),
        default="base",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--split",
        choices=("development", "validation", "test"),
        default="development",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.worker:
        if args.stage == "prepare":
            raise ValueError("prepare is not a GPU worker")
        worker(config, args.config, args.stage, args.model_kind, args.split)
        return
    if args.stage == "prepare":
        manifest = prepare(config, args.config)
        print(
            json.dumps(
                {"pass": manifest["pass"], "token_audit": manifest["token_audit"]}
            ),
            flush=True,
        )
        return
    manifest = context(config, args.config)

    def launch(
        stage: str, model_kind: str = "base", split: str = "development"
    ) -> None:
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--config",
                str(args.config.resolve()),
                "--stage",
                stage,
                "--worker",
                "--model-kind",
                model_kind,
                "--split",
                split,
            ],
            cwd=ROOT,
            check=True,
        )

    if args.stage != "evaluate":
        launch(args.stage)
        return
    require_preflight(config, manifest)
    for model_kind in ("base", "adapter"):
        for split in ("development", "validation", "test"):
            launch("evaluate", model_kind, split)
    output = Path(config["output_dir"])
    reports = {
        kind: json.loads((output / "evaluation" / kind / "test.json").read_text())
        for kind in ("base", "adapter")
    }
    if reports["base"]["input_ids"] != reports["adapter"]["input_ids"]:
        raise ValueError("base/adapter test IDs differ")
    write_json(
        output / "comparison.json",
        {
            "reports": reports,
            "same_test_ids": True,
            "test_count": 500,
            "checkpoint_selection": "fixed-final-100-steps",
            "provisional_source_labels": True,
            "overall_pass": reports["adapter"]["overall_pass"],
        },
    )


if __name__ == "__main__":
    main()
