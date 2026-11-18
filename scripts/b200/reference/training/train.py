"""Execute the selected original training AST, changing only the dataset loader and authorized max_steps."""

import ast
import hashlib
import importlib.util
import json
import os
import time
import traceback
from pathlib import Path

from common import ROOT, now, update, write


def main() -> None:
    config = json.loads((ROOT / "config.json").read_text())
    audit = json.loads((ROOT / "dataset-audit.json").read_text())
    assert audit["status"] == "passed"
    assert (
        hashlib.sha256((ROOT / "training-messages.jsonl").read_bytes()).hexdigest()
        == audit["training_messages_sha256"]
    )
    assert Path.cwd() == ROOT
    assert all(
        os.environ.get(key) is None
        for key in ["UNSLOTH_COMPILE_DISABLE", "TORCHDYNAMO_DISABLE", "PYTHONPATH"]
    )
    os.environ["HF_HUB_CACHE"] = config["hf_hub_cache"]
    result = json.loads((ROOT / "results.json").read_text())
    assert result["training"]["status"] == "pending"
    original = (ROOT / "original.py").read_text()
    assert (
        hashlib.sha256(original.encode()).hexdigest()
        == config["tutorial_source_sha256"]
    )
    tree = ast.parse(original)
    indices = [*range(0, 7), *range(19, 50), 54]
    source_nodes = [tree.body[i] for i in indices]
    original_selected = ast.Module(body=source_nodes, type_ignores=[])
    (ROOT / "original-selected-training.py").write_text(
        ast.unparse(original_selected) + "\n"
    )
    adapted = ast.parse(ast.unparse(original_selected))
    changes = 0
    for node in adapted.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "load_dataset"
        ):
            node.value = ast.parse(
                "load_dataset('json', data_files={'train': "
                + repr(str(ROOT / "training-messages.jsonl"))
                + "}, split='train')",
                mode="eval",
            ).body
            changes += 1
    assert changes == 1
    assert config["training"]["max_steps"] == 100
    step_changes = 0
    for node in ast.walk(adapted):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "SFTConfig"
        ):
            for keyword in node.keywords:
                if keyword.arg == "max_steps":
                    assert (
                        isinstance(keyword.value, ast.Constant)
                        and keyword.value.value == 30
                    )
                    keyword.value = ast.Constant(value=100)
                    step_changes += 1
    assert step_changes == 1
    ast.fix_missing_locations(adapted)
    (ROOT / "adapted-training.py").write_text(ast.unparse(adapted) + "\n")
    # Normalize back the single permitted loader change and verify everything else.
    reverse = ast.parse(ast.unparse(adapted))
    originals = [
        n
        for n in source_nodes
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "load_dataset"
    ]
    for node in reverse.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "load_dataset"
        ):
            node.value = originals[0].value
    for node in ast.walk(reverse):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "SFTConfig"
        ):
            for keyword in node.keywords:
                if keyword.arg == "max_steps":
                    assert keyword.value.value == 100
                    keyword.value = ast.Constant(value=30)
    assert ast.dump(reverse, include_attributes=False) == ast.dump(
        original_selected, include_attributes=False
    )
    prior = ast.parse(
        (
            ROOT.parent
            / "cc-official-tutorial-v5-token-caps-20261004-v1/adapted-training.py"
        ).read_text()
    )
    current = ast.parse(ast.unparse(adapted))
    for candidate in [prior, current]:
        for node in ast.walk(candidate):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "load_dataset":
                    for keyword in node.keywords:
                        if keyword.arg == "data_files":
                            keyword.value = ast.parse(
                                "{'train': 'SAME_VERIFIED_DATASET'}", mode="eval"
                            ).body
                if node.func.id == "SFTConfig":
                    for keyword in node.keywords:
                        if keyword.arg == "max_steps":
                            keyword.value = ast.Constant(value=30)
    assert ast.dump(prior, include_attributes=False) == ast.dump(
        current, include_attributes=False
    )
    # Reuse only the prior observer's read-only trainable-parameter hashing helper.
    helper = ROOT.parent / "unsloth-official-tutorial-generation-64-20261004-v1/run.py"
    spec = importlib.util.spec_from_file_location("prior_observer", helper)
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    namespace = {"__name__": "__main__", "__file__": str(ROOT / "adapted-training.py")}
    runtime = {
        "status": "running",
        "started_at": now(),
        "original_training_ast_identical_except_dataset_loader_and_max_steps": True,
        "recipe_changes": [
            "same v5 dataset loader as reference",
            "max_steps 30 to 100",
        ],
        "compared_to_30step_ast_only_max_steps_and_artifact_path": True,
        "executed_nodes": [],
    }
    write(ROOT / "training-runtime.json", runtime)
    before = {}
    result["training"].update(status="running", started_at=now())
    update(result)
    try:
        for index, node in enumerate(adapted.body):
            stage = f"node-{index}"
            if observer.call_attribute(node, "train"):
                stage = "trainer.train"
            runtime["stage"] = stage
            write(ROOT / "training-runtime.json", runtime)
            print("ORIGINAL TRAINING", stage, ast.unparse(node)[:100], flush=True)
            start = time.monotonic()
            exec(
                compile(
                    ast.Module(body=[node], type_ignores=[]),
                    str(ROOT / "adapted-training.py"),
                    "exec",
                ),
                namespace,
                namespace,
            )
            runtime["executed_nodes"].append(
                {"index": index, "seconds": time.monotonic() - start}
            )
            if observer.call_attribute(node, "get_peft_model"):
                before = observer.parameter_hashes(
                    namespace["model"], namespace["torch"]
                )
                write(ROOT / "initial-trainable-hashes.json", before)
            if stage == "trainer.train":
                trainer = namespace["trainer"]
                after = observer.parameter_hashes(
                    namespace["model"], namespace["torch"]
                )
                metrics = {
                    "status": "completed",
                    "global_step": trainer.state.global_step,
                    "metrics": namespace["trainer_stats"].metrics,
                    "effective_records": len(trainer.train_dataset),
                    "source_records": len(namespace["dataset"]),
                    "sft_config": trainer.args.to_dict(),
                    "log_history": trainer.state.log_history,
                    "updated_tensors": sum(before[k] != after[k] for k in before),
                    "trainable_tensors": len(before),
                    "final_trainable_hashes": after,
                    "trainable_parameters": sum(
                        p.numel()
                        for p in namespace["model"].parameters()
                        if p.requires_grad
                    ),
                    "dataset_cache_files": trainer.train_dataset.cache_files,
                    "finished_at": now(),
                }
                write(ROOT / "training.json", metrics)
                assert metrics["global_step"] == 100
                result["training"].update(
                    {
                        k: v
                        for k, v in metrics.items()
                        if k
                        not in [
                            "log_history",
                            "sft_config",
                            "final_trainable_hashes",
                            "dataset_cache_files",
                        ]
                    }
                )
                update(result)
            write(ROOT / "training-runtime.json", runtime)
        assert (ROOT / "gpt_oss_lora/adapter_model.safetensors").exists()
        result["training"]["adapter_saved"] = True
        runtime.update(status="completed", finished_at=now())
    except BaseException as error:
        failure = {
            "type": type(error).__name__,
            "message": str(error),
            "stage": runtime["stage"],
            "traceback": traceback.format_exc(),
        }
        write(ROOT / "training-failure.json", failure)
        result["training"].update(
            status="failed",
            failure={k: v for k, v in failure.items() if k != "traceback"},
        )
        runtime.update(status="failed", finished_at=now())
        update(result)
        write(ROOT / "training-runtime.json", runtime)
        raise
    update(result)
    write(ROOT / "training-runtime.json", runtime)


if __name__ == "__main__":
    main()
