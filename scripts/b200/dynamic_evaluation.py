"""Prepare and run a separate two-GPU dynamic-cache comparison, base then adapter."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.b200 import evaluate  # noqa: E402


def configurations(run: str) -> list[tuple[Path, dict[str, Any]]]:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", run) is None:
        raise ValueError("Invalid run name")
    pairs = []
    for kind in ("base", "adapter"):
        original = evaluate.read(ROOT / f"configs/{run}-{kind}-validation100.json")
        if (
            original["models"] != [kind]
            or original.get("model_device_map") != "balanced"
            or original.get("model_gpu_count") != 2
        ):
            raise ValueError("Reference must shard each model across both GPUs")
        name = f"{run}-dynamic-{kind}-validation100"
        config = {
            **original,
            "experiment_id": name,
            "output_dir": f"outputs/{name}",
            "cache_policy": "dynamic",
            "comparison_reference": original["output_dir"],
        }
        pairs.append((ROOT / "configs" / f"{name}.json", config))
    return pairs


def prepare(run: str) -> None:
    sweep = evaluate.sweep()
    for path, config in configurations(run):
        output = ROOT / config["output_dir"]
        reference = ROOT / config["comparison_reference"]
        old = ROOT / config["training_reference"]
        original = evaluate.read(reference / "config.json")
        audit = sweep.verify_preparation(original, reference, old)
        if output.exists() or path.exists():
            # 기존 결과를 덮어쓰지 않는다. 같은 준비본이면 검증만 수행한다.
            if not path.exists() or evaluate.read(path) != config:
                raise ValueError("Existing dynamic configuration differs")
            sweep.condition_plan(config, output, old)
            continue
        output.mkdir(parents=True)
        (output / "raw").mkdir()
        for name in ("frozen-inputs.json", "prompts.json", "gold.json"):
            shutil.copyfile(reference / name, output / name)
        audit = {
            **audit,
            "prepared_at": sweep.now(),
            "runner_sha256": sweep.digest(ROOT / evaluate.RUNNER),
            "preparation_method": "byte-copy-of-verified-native-inputs",
        }
        sweep.write(output / "config.json", config)
        sweep.write(output / "prepared.json", audit)
        sweep.write(path, config)
        sweep.condition_plan(config, output, old)


def plan(run: str) -> list[dict[str, Any]]:
    arms = []
    for path, config in configurations(run):
        if evaluate.read(path) != config:
            raise ValueError(
                "Dynamic configuration differs from frozen native settings"
            )
        audit, pending = evaluate.sweep().condition_plan(
            config, ROOT / config["output_dir"], ROOT / config["training_reference"]
        )
        arms.append(
            {
                "model": config["models"][0],
                "config": str(path.relative_to(ROOT)),
                "output": config["output_dir"],
                "gpu": "0,1",
                "cache_policy": "dynamic",
                "planned": audit["planned_calls"],
                "pending_conditions": len(pending),
            }
        )
    return arms


def execute(run: str) -> None:
    arms = plan(run)
    control = ROOT / "outputs" / f"{run}-dynamic-evaluation"
    control.mkdir(exist_ok=True)
    # 기존 native controller와 같은 잠금을 잡아 두 평가의 GPU 중복 사용을 막는다.
    with ExitStack() as stack:
        for directory in (ROOT / "outputs" / f"{run}-evaluation", control):
            directory.mkdir(exist_ok=True)
            lock = stack.enter_context((directory / "controller.lock").open("a"))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        active = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
            text=True,
        )
        if active.strip():
            raise ValueError("GPU processes are active; finish native evaluation first")
        state: dict[str, Any] = {
            "status": "checking",
            "started_at": evaluate.sweep().now(),
            "arms": arms,
            "runner_sha256": evaluate.sweep().digest(ROOT / evaluate.RUNNER),
        }
        evaluate.sweep().write(control / "state.json", state)
        try:
            for kind in ("base", "adapter"):
                subprocess.run(
                    [
                        str(ROOT / evaluate.NATIVE),
                        "scripts/b200/check_ddp_eval.py",
                        kind,
                        "--run",
                        run,
                    ],
                    cwd=ROOT,
                    env=dict(os.environ, CUDA_VISIBLE_DEVICES=""),
                    check=True,
                )
            for arm in arms:
                plan(run)  # 매 모델 로드 전에 동결 입력과 코드 해시를 재검증한다.
                state.update(status="running", current=arm["model"])
                evaluate.sweep().write(control / "state.json", state)
                with (control / f"{arm['model']}.log").open("a") as log:
                    child = subprocess.Popen(
                        [
                            str(ROOT / evaluate.NATIVE),
                            evaluate.RUNNER,
                            "run",
                            "--config",
                            arm["config"],
                        ],
                        cwd=ROOT,
                        env=dict(os.environ, CUDA_VISIBLE_DEVICES="0,1"),
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    try:
                        code = child.wait()
                    finally:
                        evaluate.terminate(child)
                    if code:
                        raise RuntimeError(
                            f"{arm['model']} failed with exit {code}; next model not started"
                        )
                _, pending = evaluate.sweep().condition_plan(
                    evaluate.read(ROOT / arm["config"]),
                    ROOT / arm["output"],
                    ROOT / "outputs" / run,
                )
                if (
                    pending
                    or not evaluate.read(
                        ROOT / arm["output"] / "confusion-matrices.json"
                    )["complete"]
                ):
                    raise RuntimeError(
                        "Worker returned without complete generation and scoring"
                    )
            state.update(status="completed")
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["updated_at"] = evaluate.sweep().now()
            evaluate.sweep().write(control / "state.json", state)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "plan", "run"))
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.run)
    elif args.action == "run":

        def interrupted(signum: int, frame: Any) -> None:
            raise KeyboardInterrupt(f"Signal {signum}")

        signal.signal(signal.SIGTERM, interrupted)
        execute(args.run)
    print(json.dumps(plan(args.run), indent=2))


if __name__ == "__main__":
    main()
