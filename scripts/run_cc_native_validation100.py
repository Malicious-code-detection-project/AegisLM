"""Evaluate each native generation budget in a fresh model process.

Use the original native environment for prepare/run and the Harmony environment
for score. Training and historical two-case generation artifacts are read-only.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from typing import Any, Iterator, cast

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO / "configs/cc_native_step100_validation100_fresh_process_v2.json"
ISOLATION_PROTOCOL = "fresh-process-per-model-budget-v2"
COMPARISON_HASHES = (
    "validation_sha256",
    "train_sha256",
    "selection_sha256",
    "frozen_input_sha256",
    "prompts_sha256",
    "gold_sha256",
    "adapter_sha256",
)


def cache_policy(config: dict[str, Any]) -> str:
    """Keep historical native generation as the default; reject unknown policies."""
    policy = config.get("cache_policy", "native")
    if policy not in ("native", "dynamic"):
        raise ValueError("Unsupported cache policy")
    if config.get("extra_generate_kwargs", {}):
        raise ValueError("Extra generation overrides are not supported")
    return str(policy)


def cache_generate_kwargs(model: Any, policy: str) -> dict[str, Any]:
    """Pass a copied config so Unsloth cannot override the explicit dynamic kwarg."""
    if policy == "native":
        return {}
    if policy != "dynamic":
        raise ValueError("Unsupported cache policy")
    return {
        "generation_config": deepcopy(model.generation_config),
        "cache_implementation": "dynamic",
    }


@contextmanager
def observe_dynamic_cache(model: Any, policy: str) -> Iterator[dict[str, Any]]:
    """Fail before attention computation if the requested dynamic cache is absent."""
    observation: dict[str, Any] = {}
    if policy == "native":
        yield observation
        return
    if policy != "dynamic":
        raise ValueError("Unsupported cache policy")
    attention = next(
        (
            module
            for name, module in model.named_modules()
            if name.endswith(".self_attn")
        ),
        None,
    )
    if attention is None:
        raise ValueError("Cannot observe the GPT-OSS attention cache")

    def observe(module: Any, positional: Any, kwargs: dict[str, Any]) -> None:
        cache = kwargs.get("past_key_values", kwargs.get("past_key_value"))
        name = type(cache).__name__
        if name != "DynamicCache":
            raise ValueError(f"Expected DynamicCache at attention, received {name}")
        observation["cache_class"] = name

    handle = attention.register_forward_pre_hook(observe, with_kwargs=True)
    try:
        yield observation
        if not observation:
            raise ValueError("Dynamic cache was not observed during generation")
    finally:
        handle.remove()


def verify_comparison(config: dict[str, Any], audit: dict[str, Any], old: Path) -> None:
    """Bind dynamic experiments to the original frozen native cohort and runner."""
    if cache_policy(config) != "dynamic":
        return
    reference = REPO / config["comparison_reference"]
    reference_config = read(reference / "config.json")
    if cache_policy(reference_config) != "native":
        raise ValueError("Comparison reference must be native")
    original = verify_preparation(reference_config, reference, old)
    if any(audit[key] != original[key] for key in COMPARISON_HASHES):
        raise ValueError("Dynamic experiment differs from frozen native cohort")
    if audit["runner_sha256"] != digest(Path(__file__)):
        raise ValueError("Prepared dynamic runner changed; prepare a new experiment")


def model_load_kwargs(config: dict[str, Any], visible_devices: int) -> dict[str, Any]:
    """Require both visible GPUs for the explicitly requested model sharding."""
    placement = config.get("model_device_map")
    if placement is None:
        return {}
    if placement != "balanced" or config.get("model_gpu_count") != 2:
        raise ValueError("Unsupported model placement")
    if visible_devices != 2:
        raise ValueError("Model sharding requires exactly two visible GPUs")
    return {"device_map": "balanced"}


def verify_model_placement(model: Any, config: dict[str, Any]) -> dict[str, Any]:
    """Check actual parameter devices, not only visibility or requested placement."""
    devices = sorted({str(parameter.device) for parameter in model.parameters()})
    if config.get("model_device_map") == "balanced" and devices != ["cuda:0", "cuda:1"]:
        raise ValueError(f"Model must occupy both GPUs without CPU offload: {devices}")
    return {
        "requested_device_map": config.get("model_device_map", "native"),
        "parameter_devices": devices,
        "hf_device_map": {
            str(k): str(v) for k, v in getattr(model, "hf_device_map", {}).items()
        },
    }


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def select_prompts(
    validation: list[dict[str, Any]], selection: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """Reuse frozen IDs, never teacher-forced tokens or assistant answers."""
    ids = [row["id"] for row in selection["cases"]]
    if len(ids) != 100 or len(set(ids)) != 100:
        raise ValueError("Expected 100 distinct validation IDs")
    by_id = {row["id"]: row for row in validation}
    prompts, gold = [], {}
    for chosen in selection["cases"]:
        row = by_id[chosen["id"]]
        messages = row["messages"]
        if [m["role"] for m in messages] != ["system", "user", "assistant"]:
            raise ValueError("Unexpected source message roles")
        expected = json.loads(messages[-1]["content"])
        if expected != {"assessment": chosen["gold"]}:
            raise ValueError("Frozen gold differs from validation source")
        prompts.append({"id": row["id"], "messages": messages[:2]})
        gold[row["id"]] = expected
    if Counter(row["assessment"] for row in gold.values()) != {
        "present": 50,
        "not_observed": 50,
    }:
        raise ValueError("Expected 50 present and 50 not_observed")
    return prompts, gold


def generation_budget(budget: int | str, input_length: int, context: int) -> int:
    # 숫자 상한은 그대로 쓰고, 최대 문맥 조건은 입력 토큰을 뺀 남은 공간만 생성한다.
    maximum = context - input_length if budget == "context-minus-input" else int(budget)
    if maximum <= 0 or input_length + maximum > context:
        raise ValueError("Requested generation budget does not fit the context")
    return maximum


def verify_preparation(config: dict[str, Any], root: Path, old: Path) -> dict[str, Any]:
    """Reject changed frozen inputs and adapter before starting or skipping workers."""
    audit = read(root / "prepared.json")
    if config != read(root / "config.json"):
        raise ValueError("Frozen configuration changed")
    # 동결 입력·gold·adapter의 현재 해시를 준비 당시 기록과 대조한다.
    for path, key in (
        (root / "frozen-inputs.json", "frozen_input_sha256"),
        (root / "prompts.json", "prompts_sha256"),
        (root / "gold.json", "gold_sha256"),
        (old / "gpt_oss_lora/adapter_model.safetensors", "adapter_sha256"),
    ):
        if digest(path) != audit[key]:
            raise ValueError(f"Frozen artifact changed: {path.name}")
    verify_comparison(config, audit, old)
    if config.get("model_device_map") is not None and any(
        audit.get(key) != config.get(key)
        for key in ("model_device_map", "model_gpu_count")
    ):
        raise ValueError("Frozen model placement differs")
    return cast(dict[str, Any], audit)


def prepare(config: dict[str, Any], root: Path, old: Path) -> None:
    from transformers import AutoTokenizer

    if (root / "prepared.json").exists():
        raise ValueError("Preparation is frozen; use run to resume")
    cache_policy(config)
    source = read(old / "config.json")
    validation_path = REPO / source["validation_file"]
    train_path = REPO / source["train_file"]
    selection_path = REPO / config["selection_reference"]
    selection = read(selection_path)
    assert digest(validation_path) == selection["input_sha256"]
    assert digest(train_path) == source["train_file_sha256"]
    assert read(REPO / source["dataset_root"] / "split-audit.json")["pass"] is True
    validation = [json.loads(line) for line in validation_path.read_text().splitlines()]
    train = [json.loads(line) for line in train_path.read_text().splitlines()]
    prompts, gold = select_prompts(validation, selection)
    assert set(gold).isdisjoint(row["id"] for row in train)
    train_users = {row["messages"][1]["content"] for row in train}
    assert not any(row["messages"][1]["content"] in train_users for row in prompts)
    snapshot = Path(source["hf_hub_cache"]) / (
        "models--unsloth--gpt-oss-20b-unsloth-bnb-4bit/snapshots/"
        "093fba6992ef5a7152481afec0bdfca1ac486998"
    )
    tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)
    frozen = {}
    for row in prompts:
        features = cast(
            dict[str, list[int]],
            tokenizer.apply_chat_template(
                row["messages"],
                add_generation_prompt=True,
                return_dict=True,
                strftime_now=lambda _: config["prompt_template_date"],
            ),
        )
        frozen[row["id"]] = dict(features)
        for budget in config["budgets"]:
            generation_budget(
                budget, len(features["input_ids"]), config["runtime_context"]
            )
    write(root / "config.json", config)
    write(root / "prompts.json", prompts)
    write(root / "gold.json", gold)
    write(root / "frozen-inputs.json", frozen)
    audit = {
        "prepared_at": now(),
        "selection_policy": selection["policy"],
        "samples_per_condition": len(prompts),
        "gold_counts": {"present": 50, "not_observed": 50},
        "validation_sha256": digest(validation_path),
        "train_sha256": digest(train_path),
        "selection_sha256": digest(selection_path),
        "frozen_input_sha256": digest(root / "frozen-inputs.json"),
        "prompts_sha256": digest(root / "prompts.json"),
        "gold_sha256": digest(root / "gold.json"),
        "adapter_sha256": digest(old / "gpt_oss_lora/adapter_model.safetensors"),
        "planned_calls": 100 * len(config["budgets"]) * len(config["models"]),
        "input_tokens_min": min(len(v["input_ids"]) for v in frozen.values()),
        "input_tokens_max": max(len(v["input_ids"]) for v in frozen.values()),
        "train_id_overlap": 0,
        "train_user_content_overlap": 0,
        "gold_in_generation_input": False,
        "test_used": False,
    }
    if cache_policy(config) == "dynamic":
        audit["runner_sha256"] = digest(Path(__file__))
    verify_comparison(config, audit, old)
    if config.get("model_device_map") is not None:
        audit.update(
            model_device_map=config["model_device_map"],
            model_gpu_count=config["model_gpu_count"],
        )
    write(root / "prepared.json", audit)


def run_condition(
    config: dict[str, Any],
    root: Path,
    old: Path,
    config_path: Path,
    kind: str,
    budget: int | str,
) -> None:
    """Keep the worker's original exception even when the controller only sees exitcode."""
    try:
        _generate_condition(config, root, old, config_path, kind, budget)
    except BaseException as error:
        write(
            root / "conditions" / f"{kind}-{budget}-error.json",
            {
                "model": kind,
                "budget": budget,
                "pid": os.getpid(),
                "failed_at": now(),
                "error": repr(error),
                "traceback": traceback.format_exc(),
            },
        )
        raise


def _generate_condition(
    config: dict[str, Any],
    root: Path,
    old: Path,
    config_path: Path,
    kind: str,
    budget: int | str,
) -> None:
    """Load a model once in a spawned interpreter for exactly one condition."""
    if kind not in config["models"] or budget not in config["budgets"]:
        raise ValueError("Unknown model/budget condition")
    source = read(old / "config.json")
    assert all(
        os.environ.get(k) is None
        for k in ("UNSLOTH_COMPILE_DISABLE", "TORCHDYNAMO_DISABLE", "PYTHONPATH")
    )
    os.environ.update(
        HF_HUB_CACHE=source["hf_hub_cache"],
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    from unsloth import FastLanguageModel  # type: ignore[import-untyped]
    import torch
    from transformers import TextStreamer

    audit = verify_preparation(config, root, old)
    policy = cache_policy(config)
    adapter = old / "gpt_oss_lora/adapter_model.safetensors"
    # frozen에는 생성에 쓸 입력 토큰만 담긴다. 정답은 별도 gold.json에 있어 입력에 넣지 않는다.
    frozen = read(root / "frozen-inputs.json")
    run_id = now()
    completed = len(list((root / "raw").glob("*.json")))
    # base는 원 모델을, adapter는 이번 학습에서 저장한 LoRA를 불러온다.
    identifier = "unsloth/gpt-oss-20b" if kind == "base" else str(old / "gpt_oss_lora")
    load_kwargs = model_load_kwargs(config, torch.cuda.device_count())
    # 모델 하나의 레이어를 두 GPU에 나눈다. 평가 조건과 모델은 계속 순차 실행한다.
    gpu_memory_before = {
        str(i): {
            "allocated_bytes": torch.cuda.memory_allocated(i),
            "reserved_bytes": torch.cuda.memory_reserved(i),
        }
        for i in range(torch.cuda.device_count())
    }
    before_load = {
        "allocated_bytes": torch.cuda.memory_allocated(),
        "reserved_bytes": torch.cuda.memory_reserved(),
    }
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=identifier,
        dtype=None,
        max_seq_length=config["runtime_context"],
        load_in_4bit=True,
        full_finetuning=False,
        **load_kwargs,
    )
    placement = verify_model_placement(model, config)
    input_device = model.get_input_embeddings().weight.device
    write(
        root / "conditions" / f"{kind}-{budget}-runtime.json",
        {
            "run_id": run_id,
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "model": kind,
            "budget": budget,
            "execution_protocol": ISOLATION_PROTOCOL,
            "memory_before_model_load": before_load,
            "model_placement": placement,
            "gpu_memory_before_model_load": gpu_memory_before,
            "gpu_memory_after_model_load": {
                str(i): {
                    "allocated_bytes": torch.cuda.memory_allocated(i),
                    "reserved_bytes": torch.cuda.memory_reserved(i),
                }
                for i in range(torch.cuda.device_count())
            },
            "memory_after_model_load": {
                "allocated_bytes": torch.cuda.memory_allocated(),
                "reserved_bytes": torch.cuda.memory_reserved(),
            },
            "model_identifier": identifier,
            "model_config": model.config.to_dict(),
            "generation_config": model.generation_config.to_dict(),
            "cache_policy": policy,
            "external_timeout": None,
            "extra_generate_kwargs": {"cache_implementation": "dynamic"}
            if policy == "dynamic"
            else {},
            "rng_policy": "native defaults, no seed reset; each condition starts fresh native RNG",
            "optimizer_steps": 0,
            "backward_calls": 0,
        },
    )
    # 모든 모델·상한에 같은 동결 표본 순서를 적용한다. ident는 표본 ID다.
    for ident, values in frozen.items():
        path = root / "raw" / f"{kind}-{budget}-{ident}.json"
        if path.exists():
            # 부분 조건을 이어 생성하면 native sampling의 난수 흐름이 달라져 재개를 거부한다.
            raise ValueError("Partial conditions cannot resume in a fresh run")
        count = len(values["input_ids"])
        maximum = generation_budget(budget, count, config["runtime_context"])
        write(
            root / "progress.json",
            {
                "status": "running",
                "run_id": run_id,
                "worker_pid": os.getpid(),
                "execution_protocol": ISOLATION_PROTOCOL,
                "completed": completed,
                "planned": audit["planned_calls"],
                "current": {"model": kind, "budget": budget, "id": ident},
                "updated_at": now(),
            },
        )
        print("BEGIN", kind, budget, ident, flush=True)
        inputs = {
            key: torch.tensor([value], device=input_device)
            for key, value in values.items()
        }
        start = time.monotonic()
        torch.cuda.reset_peak_memory_stats()
        with observe_dynamic_cache(model, policy) as observation:
            tokens = model.generate(
                **inputs,
                max_new_tokens=maximum,
                streamer=TextStreamer(tokenizer),
                **cache_generate_kwargs(model, policy),
            )
        full = tokens[0].tolist()
        assert full[:count] == values["input_ids"]
        # 반환 토큰의 앞부분은 입력이다. 이후 생성 토큰만 Harmony 채점 대상으로 저장한다.
        generated = full[count:]
        eos = model.generation_config.eos_token_id
        eos = eos if isinstance(eos, list) else [eos]
        # 자연 EOS 종료와 토큰 상한 소진을 구분해, 잘린 답변을 정상 종료로 오해하지 않게 한다.
        reason = (
            "native_eos"
            if generated and generated[-1] in eos
            else "token_limit"
            if len(generated) == maximum
            else "native_return_other"
        )
        write(
            path,
            {
                "model": kind,
                "budget": budget,
                "id": ident,
                "status": "completed",
                "run_id": run_id,
                "worker_pid": os.getpid(),
                "execution_protocol": ISOLATION_PROTOCOL,
                "cache_policy": policy,
                "cache_observation": observation,
                "generation_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "generation_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                "input_tokens": count,
                "applied_max_new_tokens": maximum,
                "generated_tokens": len(generated),
                "seconds": time.monotonic() - start,
                "stop_reason": reason,
                "eos_token_ids": eos,
                "input_ids": values["input_ids"],
                "generated_ids": generated,
                "raw_generation": tokenizer.decode(
                    generated, skip_special_tokens=False
                ),
                "finished_at": now(),
            },
        )
        # raw 저장이 끝난 표본만 완료 수에 더한다. 생성 중인 표본은 아직 완료가 아니다.
        completed += 1
        write(
            root / "progress.json",
            {
                "status": "running",
                "completed": completed,
                "planned": audit["planned_calls"],
                "updated_at": now(),
            },
        )
        print(
            "DONE",
            completed,
            audit["planned_calls"],
            reason,
            len(generated),
            flush=True,
        )
        if completed == 1 or completed % 10 == 0:
            # 첫 결과와 10건 간격으로 CPU 채점을 갱신한다. 생성·sampling 설정은 바꾸지 않는다.
            subprocess.run(
                [
                    str(REPO / config["scorer_python"]),
                    str(Path(__file__).resolve()),
                    "score",
                    "--config",
                    str(config_path),
                ],
                check=True,
            )
    del model, tokenizer
    import gc

    gc.collect()
    torch.cuda.empty_cache()
    assert digest(adapter) == audit["adapter_sha256"]


def condition_plan(
    config: dict[str, Any], root: Path, old: Path
) -> tuple[dict[str, Any], list[tuple[str, int | str]]]:
    """Validate all frozen conditions before allocating any GPU worker."""
    if config.get("execution_protocol") != ISOLATION_PROTOCOL:
        raise ValueError(
            "Legacy results are read-only; use the fresh-process v2 config"
        )
    audit = verify_preparation(config, root, old)
    frozen = read(root / "frozen-inputs.json")
    # 조건 하나는 모델 종류와 생성 상한의 조합이다. 같은 100건을 조건마다 반복한다.
    conditions = [(kind, cap) for kind in config["models"] for cap in config["budgets"]]
    if len(set(conditions)) != len(conditions):
        raise ValueError("Duplicate conditions")
    if len(frozen) != config["samples_per_condition"] or audit["planned_calls"] != len(
        frozen
    ) * len(conditions):
        raise ValueError("Prepared cohort size differs from the experiment plan")
    receipts = root / "conditions"
    # GPU를 쓰기 전에 모든 조건을 확인한다. pending에는 아직 착수하지 않은 조건만 담는다.
    pending = []
    for kind, cap in conditions:
        receipt_path = receipts / f"{kind}-{cap}.json"
        paths = [root / "raw" / f"{kind}-{cap}-{ident}.json" for ident in frozen]
        if receipt_path.exists():
            # 성공 receipt와 전체 raw가 있어야 완료 조건으로 인정하고 이번 실행에서 건너뛴다.
            receipt = read(receipt_path)
            if (
                receipt.get("status") != "completed"
                or receipt.get("exitcode") != 0
                or receipt.get("execution_protocol") != ISOLATION_PROTOCOL
                or not all(path.exists() for path in paths)
            ):
                raise ValueError(
                    "Interrupted condition: preserve it and use a new output directory"
                )
        elif any(path.exists() for path in paths):
            # 실행 근거가 없는 부분 raw를 새 결과에 섞으면 조건의 재현성을 확인할 수 없다.
            raise ValueError(
                "Unattributed raw results cannot join the fresh-process experiment"
            )
        else:
            # receipt와 raw가 모두 없는 조건만 새 worker에서 시작할 수 있다.
            pending.append((kind, cap))
    return audit, pending


def run(config: dict[str, Any], root: Path, old: Path, config_path: Path) -> None:
    """Skip complete conditions; preserve interrupted native RNG trajectories."""
    audit, pending = condition_plan(config, root, old)
    frozen = read(root / "frozen-inputs.json")
    receipts = root / "conditions"
    receipts.mkdir(exist_ok=True)
    # spawn으로 조건마다 새 Python·모델을 사용해 이전 조건의 모델 상태를 이어받지 않는다.
    context = multiprocessing.get_context("spawn")
    for kind, cap in pending:
        # 완료 조건은 pending에서 제외됐다. 이 반복문은 미착수 조건만 순차 실행한다.
        receipt_path = receipts / f"{kind}-{cap}.json"
        receipt: dict[str, Any] = {
            "model": kind,
            "budget": cap,
            "execution_protocol": ISOLATION_PROTOCOL,
            "status": "starting",
            "started_at": now(),
            "controller_pid": os.getpid(),
        }
        write(receipt_path, receipt)
        write(
            root / "progress.json",
            {
                "status": "loading",
                "completed": len(list((root / "raw").glob("*.json"))),
                "planned": audit["planned_calls"],
                "current": {"model": kind, "budget": cap},
                "execution_protocol": ISOLATION_PROTOCOL,
                "updated_at": now(),
            },
        )
        worker = context.Process(
            target=run_condition,
            args=(config, root, old, config_path, kind, cap),
        )
        try:
            worker.start()
            receipt.update(status="running", worker_pid=worker.pid)
            write(receipt_path, receipt)
            # worker 종료 후 다음 조건을 시작한다. 생성에 별도 시간 상한은 추가하지 않는다.
            worker.join()  # No timeout or concurrent GPU worker.
        except BaseException:
            if worker.pid is not None:
                if worker.is_alive():
                    worker.terminate()
                worker.join()
            receipt.update(
                status="interrupted", exitcode=worker.exitcode, exited_at=now()
            )
            write(receipt_path, receipt)
            raise
        exitcode = worker.exitcode
        worker.close()
        # worker의 성공 종료와 전체 표본 raw 저장이 모두 확인돼야 조건을 완료 처리한다.
        complete = exitcode == 0 and all(
            (root / "raw" / f"{kind}-{cap}-{ident}.json").exists() for ident in frozen
        )
        receipt.update(
            status="completed" if complete else "failed",
            exitcode=exitcode,
            exited_at=now(),
        )
        write(receipt_path, receipt)
        if not complete:
            # 10건 채점 간격 사이에 실패해도, 이미 저장된 부분 raw는 채점해 보존한다.
            try:
                subprocess.run(
                    [
                        str(REPO / config["scorer_python"]),
                        str(Path(__file__).resolve()),
                        "score",
                        "--config",
                        str(config_path),
                    ],
                    check=True,
                )
            except Exception as score_error:
                # 채점 오류는 추가 기록하고, 원 worker 실패 사유는 아래 예외로 유지한다.
                receipt["partial_score_error"] = repr(score_error)
                write(receipt_path, receipt)
            raise RuntimeError(
                f"Condition {kind}/{cap} failed (exitcode={exitcode}); sweep stopped"
            )
    # 모든 조건을 마친 뒤 계획 횟수와 최종 raw 개수가 일치하는지 확인한다.
    completed = len(list((root / "raw").glob("*.json")))
    assert completed == audit["planned_calls"]
    subprocess.run(
        [
            str(REPO / config["scorer_python"]),
            str(Path(__file__).resolve()),
            "score",
            "--config",
            str(config_path),
        ],
        check=True,
    )
    write(
        root / "progress.json",
        {
            "status": "completed",
            "completed": completed,
            "planned": completed,
            "updated_at": now(),
        },
    )


def score(config: dict[str, Any], root: Path, old: Path) -> None:
    if cache_policy(config) == "dynamic":
        verify_preparation(config, root, old)
    from openai_harmony import (  # type: ignore[import-not-found]
        HarmonyEncodingName,
        load_harmony_encoding,
    )

    sys.path.insert(0, str(old))
    spec = importlib.util.spec_from_file_location(
        "original_harmony_scorer", old / "score.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    gold = read(root / "gold.json")
    groups = []
    for model in config["models"]:
        for budget in config["budgets"]:
            strict, semantic = [[0] * 4 for _ in range(2)], [[0] * 4 for _ in range(2)]
            details = []
            for ident, expected in gold.items():
                path = root / "raw" / f"{model}-{budget}-{ident}.json"
                if not path.exists():
                    # 아직 생성하지 않은 표본은 pending이다. 오분류·출력 무효로 채점하지 않는다.
                    continue
                row = read(path)
                if cache_policy(config) == "dynamic" and (
                    row.get("cache_policy") != "dynamic"
                    or row.get("cache_observation", {}).get("cache_class")
                    != "DynamicCache"
                ):
                    raise ValueError("Cannot score unverified dynamic cache output")
                result = module.score_tokens(encoding, row["generated_ids"], expected)
                i = 0 if expected["assessment"] == "present" else 1
                parsed = result.get("parsed")
                # semantic은 final 채널의 판단값을 읽는다. strict 계약 검사는 result에 따로 있다.
                semantic_label = (
                    parsed.get("assessment")
                    if isinstance(parsed, dict) and result["final_channel_present"]
                    else None
                )
                labels = ["present", "not_observed", "uncertain"]
                for matrix, label in (
                    (strict, result["assessment"]),
                    (semantic, semantic_label),
                ):
                    matrix[i][labels.index(label) if label in labels else 3] += 1
                details.append(
                    {
                        "id": ident,
                        "source_label": expected["assessment"],
                        "generated_tokens": row["generated_tokens"],
                        "stop_reason": row["stop_reason"],
                        **result,
                    }
                )
            assert sum(map(sum, strict)) == sum(map(sum, semantic)) == len(details)
            groups.append(
                {
                    "model": model,
                    "budget": budget,
                    "completed": len(details),
                    "planned": 100,
                    "pending": 100 - len(details),
                    "strict_matrix": strict,
                    "semantic_matrix": semantic,
                    "rows": details,
                }
            )
    report = {
        "scored_at": now(),
        "cache_policy": cache_policy(config),
        "execution_protocol": config.get(
            "execution_protocol", "shared-process-across-budgets-v1"
        ),
        "complete": all(g["completed"] == 100 for g in groups),
        "matrix_rows": ["present", "not_observed"],
        "matrix_columns": ["present", "not_observed", "uncertain", "invalid"],
        "samples_per_condition": 100,
        "test_used": False,
        "groups": groups,
    }
    write(root / "confusion-matrices.json", report)
    lines = [
        "# Native step100 — validation100 generation budgets",
        "",
        "Each condition uses the same 50 positive and 50 negative validation inputs. Pending is not invalid.",
        "",
        f"Execution protocol: `{report['execution_protocol']}`.",
        f"Cache policy: `{report['cache_policy']}`.",
        "",
        "| Model | Generation cap | Completed / 100 | TP | FN | FP | TN | Uncertain | Invalid | Pending |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in groups:
        matrix = group["semantic_matrix"]
        values = [
            matrix[0][0],
            matrix[0][1],
            matrix[1][0],
            matrix[1][1],
            matrix[0][2] + matrix[1][2],
            matrix[0][3] + matrix[1][3],
        ]
        lines.append(
            f"| {group['model']} | {group['budget']} | {group['completed']}/100 | "
            + " | ".join(map(str, values))
            + f" | {group['pending']} |"
        )
    lines.extend(
        [
            "",
            "Table reads final JSON assessment. Strict schema matrices are stored separately in JSON. Unreviewed source labels; no new training; test500 untouched.",
        ]
    )
    (root / "confusion-matrices.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "verify", "run", "score"])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = read(config_path)
    if args.action == "run" and config.get("execution_protocol") != ISOLATION_PROTOCOL:
        raise ValueError(
            "Legacy results are read-only; use the fresh-process v2 config"
        )
    root, old = REPO / config["output_dir"], REPO / config["training_reference"]
    cache_policy(config)
    if args.action == "verify":
        audit = verify_preparation(config, root, old)
        print(
            json.dumps(
                {
                    "status": "verified",
                    "planned_calls": audit["planned_calls"],
                    "cache_policy": cache_policy(config),
                }
            )
        )
        return
    root.mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir(exist_ok=True)
    if args.action == "score":
        score(config, root, old)
        return
    with (root / "run.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "prepare":
            prepare(config, root, old)
        else:
            try:
                run(config, root, old, config_path)
            except BaseException as error:
                failed_at = now()
                progress_path = root / "progress.json"
                progress = read(progress_path) if progress_path.exists() else None
                write(
                    root / "error.json",
                    {
                        "failed_at": failed_at,
                        "error": repr(error),
                        "progress": progress,
                    },
                )
                write(
                    progress_path,
                    {
                        **(progress or {}),
                        "status": "failed",
                        "failed_at": failed_at,
                        "error_file": "error.json",
                    },
                )
                raise


if __name__ == "__main__":
    main()
