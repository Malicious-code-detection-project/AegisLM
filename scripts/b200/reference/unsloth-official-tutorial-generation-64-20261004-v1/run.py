"""Execute the original source AST unchanged and observe its returned results.

No model, tokenizer, Trainer, generate, streamer, stopping, or compiler functions
are replaced. No execution deadline is imposed. A failure ends this candidate.
"""

import ast
import hashlib
import importlib.metadata
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "original.py"
MANIFEST = ROOT / "manifest.json"
RESULTS = ROOT / "results.json"
FORBIDDEN_OVERRIDES = (
    "UNSLOTH_COMPILE_DISABLE", "TORCHDYNAMO_DISABLE", "TORCH_COMPILE_DISABLE",
    "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "PYTHONPATH",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")
    temporary.replace(path)


def update_table(results: dict) -> None:
    write_json(RESULTS, results)
    lines = [
        "# unsloth-official-tutorial-generation-64 (training-length-1024, steps-30)",
        "", "원본 실행 셀·설치 처방 그대로. 추가 시간 제한·compiler 우회·종료 토큰·sampling·prefill 설정 없음.",
        "", "| 단계 | 원본 프롬프트 | reasoning | 상한 | 생성량 | 종료 | 상태 |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in results["generation"]:
        lines.append(
            f"| {row['id']} | {row['prompt']} | {row['reasoning_effort']} | 64 | "
            f"{row.get('generated_tokens', '—')} | {row.get('stop_reason', '—')} | {row['status']} |"
        )
    lines += [
        "", f"학습 상태: `{results['training']['status']}`.",
        "", "학습 전후 프롬프트는 원본에서 다르므로 동일 입력 base/adapter 품질 비교로 해석하지 않는다.",
        "학습 전 3회는 원본 LoRA 초기화 뒤·optimizer 업데이트 이전 시연이다.",
        "원본은 validation dataset과 W&B 기록을 설정하지 않는다.",
    ]
    if "failure" in results:
        lines += ["", f"실패 단계: `{results['failure']['stage']}`; `{results['failure']['type']}: {results['failure']['message']}`."]
    (ROOT / "results.md").write_text("\n".join(lines) + "\n")


def parameter_hashes(model: object, torch: object) -> dict:
    return {
        name: hashlib.sha256(
            parameter.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()
        ).hexdigest()
        for name, parameter in model.named_parameters() if parameter.requires_grad
    }


def call_attribute(node: ast.AST, attribute: str) -> ast.Call | None:
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == attribute:
            return child
    return None


def stage_name(node: ast.AST, generation_index: int) -> str:
    # Original disabled optional branches remain disabled; do not observe them as loads.
    if isinstance(node, ast.If):
        return f"original-disabled-branch-line-{node.lineno}"
    if call_attribute(node, "generate"):
        return f"generation-{generation_index + 1}"
    if call_attribute(node, "from_pretrained"):
        return "model-load"
    if call_attribute(node, "get_peft_model"):
        return "lora-injection"
    if call_attribute(node, "train"):
        return "training"
    if call_attribute(node, "save_pretrained"):
        return "adapter-save"
    return f"original-line-{node.lineno}"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    results = json.loads(RESULTS.read_text())
    if manifest["status"] != "installation_pending" or (ROOT / "runtime.json").exists():
        raise RuntimeError("This candidate must execute once; do not overwrite or resume it.")
    installation = json.loads((ROOT / "installation.json").read_text())
    if installation["status"] != "completed":
        raise RuntimeError("Original installer did not complete.")
    assert all(os.environ.get(key) is None for key in FORBIDDEN_OVERRIDES)
    assert Path.cwd() == ROOT
    assert Path(sys.prefix) == Path(manifest["venv"])
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == manifest["source_python_sha256"]
    tree = ast.parse(SOURCE.read_text(), filename=str(SOURCE))
    notebook = json.loads((ROOT / "original.ipynb").read_text())
    notebook_code = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"]
        if cell["cell_type"] == "code" and "%%capture" not in "".join(cell["source"])
    )
    assert ast.dump(tree, include_attributes=False) == ast.dump(ast.parse(notebook_code), include_attributes=False)
    calls = [call_attribute(node, "generate") for node in tree.body if not isinstance(node, ast.If)]
    calls = [call for call in calls if call is not None]
    assert len(calls) == 5
    assert all({key.arg for key in call.keywords} == {None, "max_new_tokens", "streamer"} for call in calls)
    assert all(next(ast.literal_eval(key.value) for key in call.keywords if key.arg == "max_new_tokens") == 64 for call in calls)
    assert manifest["recipe_changes"] == []
    os.environ["HF_HUB_CACHE"] = manifest["hf_hub_cache"]
    versions = {}
    for distribution in importlib.metadata.distributions():
        entry = {"version": distribution.version}
        direct_url = distribution.read_text("direct_url.json")
        if direct_url:
            entry["direct_url"] = json.loads(direct_url)
        versions[distribution.metadata["Name"]] = entry
    write_json(ROOT / "packages.json", versions)
    runtime = {
        "started_at": now(), "python": sys.version, "python_executable": sys.executable,
        "environment_overrides": {"HF_HUB_CACHE": os.environ["HF_HUB_CACHE"]},
        "original_ast_identical": True, "source_sha256": manifest["source_python_sha256"],
        "status": "running", "executed_nodes": [],
    }
    write_json(ROOT / "runtime.json", runtime)
    manifest.update(status="running", started_at=now())
    write_json(MANIFEST, manifest)
    namespace = {"__name__": "__main__", "__file__": str(SOURCE)}
    generation_index = 0
    initial_hashes = {}
    current_stage = "initialization"
    try:
        for index, node in enumerate(tree.body):
            current_stage = stage_name(node, generation_index)
            print(f"\nOBSERVE original node {index}, line {node.lineno}, stage {current_stage}", flush=True)
            runtime["current_stage"] = current_stage
            write_json(ROOT / "runtime.json", runtime)
            generate = call_attribute(node, "generate") if not isinstance(node, ast.If) else None
            training = call_attribute(node, "train") if not isinstance(node, ast.If) else None
            if generate:
                results["generation"][generation_index]["status"] = "running"
            if training:
                results["training"].update(status="running", started_at=now())
            update_table(results)
            started = time.monotonic()
            executable = ast.Module(body=[node], type_ignores=[])
            exec(compile(executable, str(SOURCE), "exec"), namespace, namespace)
            elapsed = time.monotonic() - started
            runtime["executed_nodes"].append({"index": index, "line": node.lineno, "stage": current_stage, "seconds": elapsed})
            if current_stage == "model-load":
                model, tokenizer, torch = namespace["model"], namespace["tokenizer"], namespace["torch"]
                write_json(ROOT / "loaded-model.json", {
                    "model_config": model.config.to_dict(), "generation_config": model.generation_config.to_dict(),
                    "tokenizer_name": tokenizer.name_or_path,
                    "torch_cuda_version": torch.version.cuda,
                    "device": torch.cuda.get_device_name(0),
                })
            if current_stage == "lora-injection":
                model, torch = namespace["model"], namespace["torch"]
                initial_hashes = parameter_hashes(model, torch)
                write_json(ROOT / "trainable-parameters.json", {
                    "parameters": [{"name": name, "shape": list(param.shape), "numel": param.numel(), "dtype": str(param.dtype)}
                                   for name, param in model.named_parameters() if param.requires_grad],
                    "initial_hashes": initial_hashes,
                })
            if generate:
                tokenizer = namespace["tokenizer"]
                input_ids = namespace["inputs"]["input_ids"][0].tolist()
                output_ids = namespace["_"][0].tolist()
                assert output_ids[:len(input_ids)] == input_ids
                generated = output_ids[len(input_ids):]
                eos = namespace["model"].generation_config.eos_token_id
                eos_ids = eos if isinstance(eos, list) else [eos]
                stop = "native_eos" if generated and generated[-1] in eos_ids else "token_limit" if len(generated) == 64 else "native_return_other"
                row = results["generation"][generation_index]
                row.update(status="completed", input_tokens=len(input_ids), generated_tokens=len(generated),
                           seconds=elapsed, stop_reason=stop, eos_token_ids=eos_ids)
                text = tokenizer.decode(generated, skip_special_tokens=False)
                row["final_marker_present"] = "<|channel|>final<|message|>" in text
                detail = dict(row, messages=namespace["messages"], input_ids=input_ids,
                              output_ids=output_ids, generated_ids=generated,
                              input_text=tokenizer.decode(input_ids, skip_special_tokens=False), generated_text=text,
                              generation_config=namespace["model"].generation_config.to_dict(),
                              explicit_generation_keywords=[None, "max_new_tokens", "streamer"])
                write_json(ROOT / f"{row['id']}.json", detail)
                (ROOT / f"{row['id']}.txt").write_text(text)
                generation_index += 1
            if training:
                trainer = namespace["trainer"]
                after_hashes = parameter_hashes(namespace["model"], namespace["torch"])
                results["training"].update(
                    status="completed", global_step=trainer.state.global_step,
                    metrics=namespace["trainer_stats"].metrics,
                    effective_dataset_records=len(trainer.train_dataset),
                    loaded_dataset_records=len(namespace["dataset"]),
                    parameters_changed=sum(after_hashes[name] != value for name, value in initial_hashes.items()),
                    finished_at=now(),
                )
                write_json(ROOT / "training.json", {
                    **results["training"], "log_history": trainer.state.log_history,
                    "sft_config": trainer.args.to_dict(), "updated_parameter_hashes": after_hashes,
                    "dataset_fingerprint": namespace["dataset"]._fingerprint,
                    "dataset_cache_files": namespace["dataset"].cache_files,
                })
            update_table(results)
            write_json(ROOT / "runtime.json", runtime)
        assert generation_index == 5
        assert results["training"]["global_step"] == 30
        runtime.update(status="completed", finished_at=now())
        manifest.update(status="completed", finished_at=now())
    except BaseException as error:
        failure = {"stage": current_stage, "type": type(error).__name__, "message": str(error), "at": now(),
                   "traceback": traceback.format_exc()}
        write_json(ROOT / "failure.json", failure)
        results["failure"] = {key: value for key, value in failure.items() if key != "traceback"}
        if results["training"]["status"] == "running":
            trainer = namespace.get("trainer")
            results["training"].update(status="failed", global_step=getattr(getattr(trainer, "state", None), "global_step", None))
        elif results["training"]["status"] == "pending":
            results["training"]["status"] = "not_run"
        for row in results["generation"]:
            if row["status"] == "running":
                row["status"] = "failed"
            elif row["status"] == "pending":
                row["status"] = "not_run"
        runtime.update(status="failed", finished_at=now(), failure=results["failure"])
        manifest.update(status="failed", finished_at=now(), failure=results["failure"])
        update_table(results)
        write_json(ROOT / "runtime.json", runtime)
        write_json(MANIFEST, manifest)
        raise
    update_table(results)
    write_json(ROOT / "runtime.json", runtime)
    write_json(MANIFEST, manifest)


if __name__ == "__main__":
    main()
