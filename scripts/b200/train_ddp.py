"""Two-rank adaptation of the frozen official 100-step tutorial (no GPU imports at import time)."""

import argparse
import ast
import copy
import functools
import hashlib
import json
import math
import os
import platform
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "outputs/b200-step100-v1"
REFERENCE = ROOT / "data/reproduction/b200-step100-v1"
SOURCE_SHA = "74ff47bb9212f482f7378d86f27bc088973e924ae427cc84891d87663131895a"
DEFAULT_RUN = "b200-ddp2-step100-v3"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_path(name: str) -> Path:
    require(
        name.startswith("b200-ddp2-step100-") and "/" not in name and "\\" not in name,
        "Choose a B200 DDP2 step100 run name without path components",
    )
    return ROOT / "outputs" / name


def selected_tree(source: str) -> ast.Module:
    require(
        hashlib.sha256(source.encode()).hexdigest() == SOURCE_SHA,
        "Original tutorial source changed",
    )
    tree = ast.parse(source)
    return ast.Module(
        body=[tree.body[i] for i in [*range(0, 7), *range(19, 50), 54]], type_ignores=[]
    )


def calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Name) and n.func.id == name)
            or (isinstance(n.func, ast.Attribute) and n.func.attr == name)
        )
    ]


def adapt(source: str, run: Path, local_rank: int) -> ast.Module:
    """Preserve the recipe; adapt rank placement/batch and MoE-compatible checkpoint/reduction settings."""
    require(local_rank in (0, 1), "Expected local rank 0 or 1")
    original = selected_tree(source)
    tree = copy.deepcopy(original)
    (loader,) = calls(tree, "load_dataset")
    loader.args = [ast.Constant("json")]
    loader.keywords = cast(
        ast.Call,
        ast.parse(
            "load_dataset('json', data_files={'train': "
            + repr(str(run / "training-messages.jsonl"))
            + "}, split='train')",
            mode="eval",
        ).body,
    ).keywords
    (model_loader,) = calls(tree, "from_pretrained")
    model_loader.keywords.append(
        ast.keyword(
            arg="device_map", value=ast.parse(repr({"": local_rank}), mode="eval").body
        )
    )
    (config,) = calls(tree, "SFTConfig")
    substitutions: dict[str, tuple[int | str, int | str]] = {
        "max_steps": (30, 100),
        "gradient_accumulation_steps": (4, 2),
        "output_dir": ("outputs", str(run / "trainer")),
    }
    for keyword in config.keywords:
        if keyword.arg in substitutions:
            prior, replacement = substitutions[keyword.arg]
            require(
                ast.literal_eval(keyword.value) == prior,
                "Original training setting changed",
            )
            keyword.value = ast.Constant(replacement)
    require(
        all(any(k.arg == key for k in config.keywords) for key in substitutions),
        "Original SFTConfig fields missing",
    )
    config.keywords.append(
        ast.keyword(arg="ddp_find_unused_parameters", value=ast.Constant(True))
    )
    config.keywords.append(
        ast.keyword(arg="gradient_checkpointing", value=ast.Constant(False))
    )
    (peft,) = calls(tree, "get_peft_model")
    (checkpoint,) = [k for k in peft.keywords if k.arg == "use_gradient_checkpointing"]
    require(
        ast.literal_eval(checkpoint.value) == "unsloth",
        "Original checkpoint setting changed",
    )
    checkpoint.value = ast.Constant(False)
    (gpu,) = calls(tree, "get_device_properties")
    require(ast.literal_eval(gpu.args[0]) == 0, "Original GPU statistics changed")
    gpu.args[0] = ast.Constant(local_rank)
    (save,) = calls(tree, "save_pretrained")
    require(
        ast.literal_eval(save.args[0]) == "gpt_oss_lora",
        "Original adapter save changed",
    )
    save.args[0] = ast.Constant(str(run / "gpt_oss_lora"))
    ast.fix_missing_locations(tree)
    # Reversing the documented changes must recover the exact original selected AST.
    reverse = copy.deepcopy(tree)
    (reversed_loader,) = calls(reverse, "load_dataset")
    (original_loader,) = calls(original, "load_dataset")
    reversed_loader.args = original_loader.args
    reversed_loader.keywords = original_loader.keywords
    (reversed_model,) = calls(reverse, "from_pretrained")
    reversed_model.keywords = [
        k for k in reversed_model.keywords if k.arg != "device_map"
    ]
    (reversed_config,) = calls(reverse, "SFTConfig")
    reversed_config.keywords = [
        k
        for k in reversed_config.keywords
        if k.arg not in ("ddp_find_unused_parameters", "gradient_checkpointing")
    ]
    (reversed_peft,) = calls(reverse, "get_peft_model")
    next(
        k for k in reversed_peft.keywords if k.arg == "use_gradient_checkpointing"
    ).value = ast.Constant("unsloth")
    for keyword in reversed_config.keywords:
        if keyword.arg in substitutions:
            keyword.value = ast.Constant(substitutions[keyword.arg][0])
    (reversed_gpu,) = calls(reverse, "get_device_properties")
    reversed_gpu.args[0] = ast.Constant(0)
    (reversed_save,) = calls(reverse, "save_pretrained")
    reversed_save.args[0] = ast.Constant("gpt_oss_lora")
    require(
        ast.dump(reverse) == ast.dump(original),
        "Unexpected change to original training AST",
    )
    return tree


def init(name: str) -> None:
    from scripts.b200 import manage

    manage.verify_data()
    manage.check_data()
    run = run_path(name)
    configs = [
        ROOT / f"configs/{name}-{kind}-validation100.json"
        for kind in ("base", "adapter")
    ]
    require(
        not run.exists() and not any(p.exists() for p in configs),
        "Preserve the previous run/configs; choose a fresh run name",
    )
    require(
        not (SOURCE / "training-runtime.json").exists(),
        "Single-GPU reference was already executed",
    )
    source = (SOURCE / "original.py").read_text()
    selected_tree(source)
    config = read(SOURCE / "config.json")
    config.update(
        experiment_id=name,
        title="B200 two-GPU DDP: frozen v5, 100 steps",
        status="prepared",
    )
    config["distributed"] = {
        "world_size": 2,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 2,
        "effective_batch_size": 4,
        "max_steps": 100,
        "sample_presentations": 400,
        "max_input_tokens": 409600,
        "backend": "nccl",
        "ddp_find_unused_parameters": True,
        "gradient_checkpointing": False,
        "checkpoint_change_reason": "Sparse MoE experts are unused per rank; Unsloth reentrant checkpointing conflicts with DDP unused-parameter detection",
        "external_time_limit": None,
        "single_gpu_experiment_skipped": True,
        "baseline_train_runtime_seconds": 656.811,
        "save_owner": "rank0",
        "hypothesis": "Frozen-data LoRA training completes 100 synchronized steps on B200 GPU0 and GPU1",
        "metrics": [
            "global_step",
            "finite_loss",
            "updated_tensors",
            "rank_hash_agreement",
            "train_runtime",
        ],
        "stop_conditions": [
            "first exception",
            "nonfinite loss",
            "wrong rank/device/data/settings",
            "100 optimizer steps",
        ],
        "comparison_limit": "DDP sampling/reduction, activation checkpointing, GPU kernels and Python patch differ; weights need not equal A6000; speed is not a hardware-only comparison",
    }
    run.mkdir(parents=True)
    for filename in (
        "original.py",
        "LICENSE",
        "common.py",
        "score.py",
        "dataset-audit.json",
        "training-messages.jsonl",
    ):
        shutil.copy2(SOURCE / filename, run / filename)
    write(run / "config.json", config)
    for rank in (0, 1):
        folder = run / f"rank{rank}"
        folder.mkdir()
        (folder / "adapted-training.py").write_text(
            ast.unparse(adapt(source, run, rank)) + "\n"
        )
    for kind, path in zip(("base", "adapter"), configs, strict=True):
        evaluation = read(REFERENCE / "evaluation-config.json")
        evaluation.update(
            experiment_id=f"{name}-{kind}-validation100",
            output_dir=f"outputs/{name}-{kind}-validation100",
            training_reference=f"outputs/{name}",
            selection_reference="data/reproduction/b200-step100-v1/probe-inputs.json",
            scorer_python=str(manage.SCORER),
            models=[kind],
        )
        write(path, evaluation)
    write(run / "results.json", {"training": {"status": "pending"}, "generation": []})
    print(
        json.dumps(
            {"status": "prepared", "run": name, "world_size": 2, "global_batch": 4}
        )
    )


def parameter_hashes(model: Any, torch: Any) -> dict[str, str]:
    return {
        name: hashlib.sha256(
            p.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()
        ).hexdigest()
        for name, p in model.named_parameters()
        if p.requires_grad
    }


def signature(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def dataset_signature(dataset: Any, audit: dict[str, Any]) -> str:
    expected = [row for row in audit["records"] if row["supervised_tokens"] > 0]
    require(len(expected) == len(dataset) == 8525, "Effective cohort changed")
    sha = hashlib.sha256()
    for actual, prior in zip(dataset, expected, strict=True):
        ids, labels = actual["input_ids"], actual["labels"]
        require(
            len(ids) == min(prior["tokens"], 1024),
            "Token lengths differ from frozen audit",
        )
        require(
            sum(v != -100 for v in labels) == prior["supervised_tokens"],
            "Supervision differs from frozen audit",
        )
        if "id" in actual:
            require(actual["id"] == prior["id"], "Training ID order changed")
        sha.update(
            json.dumps([prior["id"], ids, labels], separators=(",", ":")).encode()
        )
    return sha.hexdigest()


def train(name: str) -> None:
    run = run_path(name)
    local_rank = int(os.environ.get("LOCAL_RANK", "-1"))
    rank = int(os.environ.get("RANK", "-1"))
    require(
        int(os.environ.get("WORLD_SIZE", "0")) == 2 and rank == local_rank in (0, 1),
        "Launch with torchrun --standalone --nnodes=1 --nproc-per-node=2",
    )
    require(
        os.environ.get("CUDA_VISIBLE_DEVICES") == "0,1",
        "Both B200 GPUs must be visible",
    )
    folder = run / f"rank{rank}"
    require(folder.is_dir(), "Initialize this run first")
    with (folder / "attempt.json").open("x") as stream:
        json.dump({"started_at": now(), "pid": os.getpid(), "rank": rank}, stream)
    runtime = {
        "status": "running",
        "rank": rank,
        "local_rank": local_rank,
        "started_at": now(),
        "stage": "validation",
    }
    write(folder / "runtime.json", runtime)
    torch: Any = None
    try:
        require(
            platform.python_version() == "3.12.3", "Expected accepted Python 3.12.3"
        )
        config, audit = read(run / "config.json"), read(run / "dataset-audit.json")
        require(
            config["training"]["max_steps"] == 100
            and config["training"]["max_seq_length"] == 1024,
            "Expected 100-step/1024-token bounds",
        )
        require(
            config["distributed"]["effective_batch_size"] == 4,
            "Expected global batch four",
        )
        expected_audit = read(REFERENCE / "training/dataset-audit.json")
        require(
            audit == expected_audit and audit["status"] == "passed",
            "Frozen mask audit changed",
        )
        require(
            digest(run / "training-messages.jsonl")
            == audit["training_messages_sha256"],
            "Frozen training messages changed",
        )
        require(
            all(
                os.environ.get(k) is None
                for k in (
                    "UNSLOTH_COMPILE_DISABLE",
                    "TORCHDYNAMO_DISABLE",
                    "TORCH_COMPILE_DISABLE",
                    "PYTHONPATH",
                )
            ),
            "Compiler overrides must be unset",
        )
        require(
            os.environ.get("HF_HUB_OFFLINE") == "1"
            and os.environ.get("TRANSFORMERS_OFFLINE") == "1",
            "Use the verified offline model snapshot",
        )
        os.environ["HF_HUB_CACHE"] = config["hf_hub_cache"]
        for key, leaf in (
            ("HF_DATASETS_CACHE", "datasets-cache"),
            ("TRITON_CACHE_DIR", "triton-cache"),
            ("TORCHINDUCTOR_CACHE_DIR", "torchinductor-cache"),
        ):
            os.environ[key] = str(folder / leaf)
        os.environ["UNSLOTH_COMPILE_LOCATION"] = str(run / "unsloth_compiled_cache")
        os.chdir(folder)
        runtime["stage"] = "import_unsloth"
        write(folder / "runtime.json", runtime)
        import unsloth  # type: ignore[import-untyped]  # noqa: F401
        import torch as torch_module

        torch = torch_module
        from transformers import PreTrainedTokenizerBase, TrainerCallback

        require(torch.cuda.device_count() == 2, "Expected exactly two visible GPUs")
        torch.cuda.set_device(local_rank)
        require(
            torch.cuda.get_device_properties(local_rank).name == "NVIDIA B200",
            "Expected B200",
        )
        if not torch.distributed.is_initialized():
            torch.distributed.init_process_group("nccl")
        probe = torch.tensor([float(rank + 1)], device=f"cuda:{local_rank}")
        torch.distributed.all_reduce(probe)
        require(probe.item() == 3.0, "Two-GPU NCCL reduction failed")
        write(
            folder / "gpu-preflight.json",
            {
                "status": "passed",
                "rank": rank,
                "device": local_rank,
                "gpu": torch.cuda.get_device_properties(local_rank).name,
                "nccl_sum": probe.item(),
                "world_size": 2,
            },
        )
        original_template = PreTrainedTokenizerBase.apply_chat_template

        @functools.wraps(original_template)
        def fixed_date(self: Any, *values: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("strftime_now", lambda _: "2026-10-04")
            return original_template(self, *values, **kwargs)

        setattr(PreTrainedTokenizerBase, "apply_chat_template", fixed_date)

        class Progress(TrainerCallback):
            def on_log(
                self,
                args: Any,
                state: Any,
                control: Any,
                logs: Any = None,
                **kwargs: Any,
            ) -> None:
                for key in ("loss", "grad_norm", "learning_rate"):
                    if logs and key in logs:
                        require(math.isfinite(float(logs[key])), f"Nonfinite {key}")
                write(
                    folder / "progress.json",
                    {
                        "step": state.global_step,
                        "max_steps": state.max_steps,
                        "rank": rank,
                        "logs": logs,
                        "updated_at": now(),
                    },
                )

        tree = adapt((run / "original.py").read_text(), run, local_rank)
        source_path = folder / "adapted-training.py"
        require(
            source_path.read_text() == ast.unparse(tree) + "\n",
            "Prepared DDP AST changed",
        )
        namespace: dict[str, Any] = {
            "__name__": "__main__",
            "__file__": str(source_path),
        }
        before: dict[str, str] = {}
        cohort_sha = None
        metrics = None
        for index, node in enumerate(tree.body):
            training = bool(calls(node, "train"))
            saving = bool(calls(node, "save_pretrained"))
            runtime.update(
                stage="trainer.train"
                if training
                else "adapter.save"
                if saving
                else f"node-{index}"
            )
            write(folder / "runtime.json", runtime)
            if rank == 0:
                write(run / "training-runtime.json", runtime)
            if saving and rank != 0:
                continue
            print(f"RANK {rank} STAGE {runtime['stage']}", flush=True)
            started = time.monotonic()
            exec(
                compile(
                    ast.Module(body=[node], type_ignores=[]), str(source_path), "exec"
                ),
                namespace,
            )
            if calls(node, "get_peft_model"):
                model = namespace["model"]
                require(
                    all(
                        p.device.type == "cuda" and p.device.index == local_rank
                        for p in model.parameters()
                    ),
                    "Model parameters span the wrong device",
                )
                before = parameter_hashes(model, torch)
                require(
                    len(before) == 3264
                    and sum(p.numel() for p in model.parameters() if p.requires_grad)
                    == 92454912,
                    "LoRA targets/parameter count changed",
                )
                write(folder / "initial-trainable-hashes.json", before)
            if calls(node, "train_on_responses_only"):
                trainer = namespace["trainer"]
                require(
                    trainer.args.world_size == 2 and trainer.args.process_index == rank,
                    "Trainer is not configured for two-rank DDP",
                )
                require(
                    trainer.args.per_device_train_batch_size == 1
                    and trainer.args.gradient_accumulation_steps == 2,
                    "Global batch changed",
                )
                require(
                    trainer.args.max_steps == 100 and trainer.args.seed == 3407,
                    "Step/seed changed",
                )
                require(
                    trainer.args.ddp_find_unused_parameters is True,
                    "MoE unused-parameter detection must be enabled",
                )
                require(
                    trainer.args.gradient_checkpointing is False
                    and not namespace["model"].is_gradient_checkpointing,
                    "Reentrant checkpointing must be disabled for sparse MoE DDP",
                )
                cohort_sha = dataset_signature(trainer.train_dataset, audit)
                receipts = [None, None]
                torch.distributed.all_gather_object(
                    receipts, {"data": cohort_sha, "initial": signature(before)}
                )
                require(
                    receipts[0] == receipts[1],
                    "Ranks have different data or initial LoRA weights",
                )
                trainer.add_callback(Progress())
                write(
                    folder / "ready.json",
                    {
                        "rank": rank,
                        "world_size": 2,
                        "device": local_rank,
                        "effective_records": 8525,
                        "dataset_sha256": cohort_sha,
                        "initial_hashes_sha256": signature(before),
                        "gradient_checkpointing": False,
                        "ddp_find_unused_parameters": True,
                    },
                )
            if training:
                trainer, model = namespace["trainer"], namespace["model"]
                require(
                    isinstance(
                        trainer.model_wrapped, torch.nn.parallel.DistributedDataParallel
                    ),
                    "Trainer did not use DistributedDataParallel",
                )
                after = parameter_hashes(model, torch)
                require(before.keys() == after.keys(), "Trainable tensor set changed")
                metrics = {
                    "status": "trained",
                    "rank": rank,
                    "world_size": 2,
                    "global_step": trainer.state.global_step,
                    "metrics": namespace["trainer_stats"].metrics,
                    "effective_records": len(trainer.train_dataset),
                    "source_records": len(namespace["dataset"]),
                    "updated_tensors": sum(before[k] != after[k] for k in before),
                    "trainable_tensors": len(before),
                    "trainable_parameters": 92454912,
                    "final_trainable_hashes": after,
                    "dataset_sha256": cohort_sha,
                    "sft_config": trainer.args.to_dict(),
                    "log_history": trainer.state.log_history,
                    "peak_allocated_bytes": torch.cuda.max_memory_allocated(local_rank),
                    "peak_reserved_bytes": torch.cuda.max_memory_reserved(local_rank),
                    "train_call_seconds": time.monotonic() - started,
                    "finished_at": now(),
                }
                require(
                    metrics["global_step"] == 100 and metrics["updated_tensors"] > 0,
                    "Incomplete training/no updates",
                )
                require(
                    math.isfinite(float(metrics["metrics"]["train_loss"])),
                    "Nonfinite training loss",
                )
                receipts = [None, None]
                torch.distributed.all_gather_object(
                    receipts,
                    {"steps": 100, "final": signature(after), "data": cohort_sha},
                )
                require(
                    receipts[0] == receipts[1], "Ranks have different final weights"
                )
                metrics["rank_hash_agreement"] = True
                write(folder / "training.json", metrics)
        if rank == 0:
            from peft import get_peft_model_state_dict
            from safetensors.torch import load_file

            saved = load_file(str(run / "gpt_oss_lora/adapter_model.safetensors"))
            state = get_peft_model_state_dict(namespace["model"])
            require(
                saved.keys() == state.keys(),
                "Saved adapter tensor set differs from trained model",
            )
            require(
                all(
                    torch.equal(saved[key], value.detach().cpu())
                    for key, value in state.items()
                ),
                "Saved adapter weights differ from trained model",
            )
            write(
                run / "adapter-save-verification.json",
                {
                    "status": "passed",
                    "tensor_count": len(saved),
                    "saved_matches_trained": True,
                    "adapter_sha256": digest(
                        run / "gpt_oss_lora/adapter_model.safetensors"
                    ),
                },
            )
        torch.distributed.barrier()
        require(
            (run / "gpt_oss_lora/adapter_model.safetensors").is_file(),
            "Adapter missing",
        )
        require(metrics is not None, "Training metrics missing")
        metrics = cast(dict[str, Any], metrics)
        metrics["status"] = "completed"
        write(folder / "training.json", metrics)
        runtime.update(status="completed", finished_at=now())
        write(folder / "runtime.json", runtime)
        torch.distributed.barrier()
        if rank == 0:
            write(run / "training.json", metrics)
            write(run / "training-runtime.json", runtime)
            write(
                run / "results.json",
                {
                    "training": {
                        k: v
                        for k, v in metrics.items()
                        if k
                        not in ("sft_config", "log_history", "final_trainable_hashes")
                    },
                    "generation": [],
                },
            )
    except BaseException as error:
        failure = {
            "type": type(error).__name__,
            "message": str(error),
            "stage": runtime["stage"],
            "traceback": traceback.format_exc(),
            "rank": rank,
        }
        write(folder / "failure.json", failure)
        runtime.update(status="failed", finished_at=now())
        write(folder / "runtime.json", runtime)
        if rank == 0:
            write(run / "training-runtime.json", runtime)
        raise
    finally:
        if torch is not None and torch.distributed.is_initialized():
            torch.distributed.destroy_process_group()


def check(name: str) -> None:
    run = run_path(name)
    require(
        read(run / "training-runtime.json")["status"] == "completed",
        "Training/save not completed",
    )
    receipts = [read(run / f"rank{rank}/training.json") for rank in (0, 1)]
    for rank, result in enumerate(receipts):
        require(
            result["status"] == "completed"
            and result["rank"] == rank
            and result["world_size"] == 2,
            "Rank receipt incomplete",
        )
        require(
            result["global_step"] == 100
            and result["effective_records"] == 8525
            and result["updated_tensors"] > 0,
            "Expected 100 steps, frozen cohort and actual updates",
        )
        require(
            result["sft_config"]["gradient_accumulation_steps"] == 2
            and result["sft_config"]["per_device_train_batch_size"] == 1,
            "Expected global batch four",
        )
        require(
            math.isfinite(float(result["metrics"]["train_loss"])),
            "Nonfinite training loss",
        )
    require(
        receipts[0]["final_trainable_hashes"] == receipts[1]["final_trainable_hashes"]
        and receipts[0]["dataset_sha256"] == receipts[1]["dataset_sha256"],
        "Rank weight/data disagreement",
    )
    adapter = run / "gpt_oss_lora/adapter_model.safetensors"
    require(adapter.is_file(), "Adapter missing")
    saved = read(run / "adapter-save-verification.json")
    require(
        saved["status"] == "passed"
        and saved["saved_matches_trained"] is True
        and saved["adapter_sha256"] == digest(adapter),
        "Saved adapter verification failed",
    )
    write(
        run / "b200-verification.json",
        {
            "status": "passed",
            "world_size": 2,
            "global_step": 100,
            "effective_batch_size": 4,
            "effective_records": 8525,
            "rank_hash_agreement": True,
            "adapter_sha256": digest(adapter),
            "weights_expected_identical_to_A6000": False,
        },
    )
    print(
        json.dumps(
            {"status": "passed", "run": name, "world_size": 2, "global_step": 100}
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("init", "train", "check"))
    parser.add_argument("--run", default=DEFAULT_RUN)
    args = parser.parse_args()
    if args.action == "init":
        sys.path.insert(0, str(ROOT))
    {"init": init, "train": train, "check": check}[args.action](args.run)


if __name__ == "__main__":
    main()
