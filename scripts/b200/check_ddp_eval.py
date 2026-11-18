"""Verify the frozen evaluation cohort and newly trained two-GPU adapter without generation."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def check(run_name: str, kind: str) -> None:
    from scripts.b200 import manage, train_ddp

    train_ddp.check(run_name)
    config = manage.read(ROOT / f"configs/{run_name}-{kind}-validation100.json")
    manage.require(
        config["models"] == [kind]
        and config["training_reference"] == f"outputs/{run_name}",
        "Wrong evaluation arm or training reference",
    )
    manage.require(
        config["output_dir"] == f"outputs/{run_name}-{kind}-validation100",
        "Wrong evaluation directory",
    )
    prepared = manage.read(ROOT / config["output_dir"] / "prepared.json")
    reference = manage.read(
        ROOT / "data/reproduction/b200-step100-v1/evaluation-prepared.json"
    )
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
        manage.require(prepared[key] == reference[key], f"Evaluation differs: {key}")
    manage.require(
        prepared["planned_calls"] == 600, "Expected 600 planned calls for this arm"
    )
    adapter = ROOT / f"outputs/{run_name}/gpt_oss_lora/adapter_model.safetensors"
    manage.require(
        prepared["adapter_sha256"] == manage.digest(adapter), "Wrong two-GPU adapter"
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "run": run_name,
                "kind": kind,
                "planned_calls": 600,
                "generation_started": False,
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("kind", choices=("base", "adapter"))
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    check(args.run, args.kind)


if __name__ == "__main__":
    main()
