"""Wait for a completed native evaluation, then run the frozen dynamic comparison."""

from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.b200 import compare_cache, dynamic_evaluation, evaluate  # noqa: E402


def predecessor_ready(state: dict[str, Any], locked: bool) -> bool:
    # completed를 먼저 기록한 뒤 최종 채점할 수 있으므로 잠금 해제까지 기다린다.
    if locked:
        return False
    if state.get("status") != "completed" or state.get("exit_code") != 0:
        raise ValueError("Native evaluation did not finish successfully")
    if set(state.get("arms", {})) != {"base", "adapter"} or any(
        arm.get("status") != "completed"
        or arm.get("generation_exit") != 0
        or arm.get("score_exit") != 0
        for arm in state["arms"].values()
    ):
        raise ValueError("Both native arms must finish generation and scoring")
    return True


def native_locked(control: Path) -> bool:
    with (control / "controller.lock").open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def verify_sources(expected: dict[str, str]) -> None:
    for path, digest in expected.items():
        if evaluate.sweep().digest(ROOT / path) != digest:
            raise ValueError(f"Queued source changed: {path}")


def execute(run: str) -> None:
    arms = dynamic_evaluation.plan(run)
    native = ROOT / "outputs" / f"{run}-evaluation"
    control = ROOT / "outputs" / f"{run}-dynamic-evaluation"
    control.mkdir(exist_ok=True)
    state_path = control / "queue.json"
    with (control / "queue.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # 재시작으로 실패·중단 이력을 덮거나 이중 실행하지 않는다.
        if state_path.exists():
            raise ValueError("Queue receipt already exists; inspect before requeuing")
        expected = {
            path: evaluate.sweep().digest(ROOT / path)
            for path in (
                evaluate.RUNNER,
                "scripts/b200/evaluate.py",
                "scripts/b200/dynamic_evaluation.py",
                "scripts/b200/compare_cache.py",
                "scripts/b200/queue_dynamic.py",
            )
        }
        state: dict[str, Any] = {
            "status": "waiting_native",
            "queued_at": evaluate.sweep().now(),
            "pid": os.getpid(),
            "predecessor": str(native.relative_to(ROOT)),
            "arms": arms,
            "source_sha256": expected,
            "poll_seconds": 30,
        }

        def persist() -> None:
            state["updated_at"] = evaluate.sweep().now()
            evaluate.sweep().write(state_path, state)

        persist()
        try:
            while True:
                verify_sources(expected)
                locked = native_locked(native)
                predecessor = evaluate.read(native / "state.json")
                if predecessor_ready(predecessor, locked):
                    # 종료 코드 외에 모든 raw·receipt·행렬의 완결성도 검사한다.
                    native_arms = evaluate.plan(run, "all", "0,1")
                    if any(
                        arm["pending_conditions"] or not evaluate.arm_complete(arm)
                        for arm in native_arms
                    ):
                        raise ValueError("Native results are incomplete")
                    active = subprocess.check_output(
                        [
                            "nvidia-smi",
                            "--query-compute-apps=pid",
                            "--format=csv,noheader",
                        ],
                        text=True,
                    )
                    if not active.strip():
                        break
                    state["status"] = "waiting_gpu_release"
                else:
                    state["status"] = "waiting_native"
                persist()
                time.sleep(30)
            state.update(status="running_dynamic", started_at=evaluate.sweep().now())
            persist()
            # 기존 검증된 실행기가 다시 잠금을 잡고 GPU0·1, base→adapter를 강제한다.
            dynamic_evaluation.execute(run)
            manifest = evaluate.read(
                ROOT / "docs/results/cache-comparison-manifest.json"
            )
            compare_cache.write_report(
                compare_cache.collect(manifest, ROOT),
                ROOT / "outputs" / f"{run}-cache-comparison",
            )
            state["status"] = "completed"
        except KeyboardInterrupt:
            state["status"] = "interrupted"
            raise
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            persist()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()

    def interrupted(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt(f"Signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    execute(args.run)


if __name__ == "__main__":
    main()
