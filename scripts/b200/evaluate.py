"""Run the frozen native base/adapter evaluations and collect their Harmony reports."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
# 생성은 기존 native 환경, Harmony 채점은 별도 CPU 환경의 Python을 사용한다.
NATIVE = "configs/environments/cc-native-step100/.venv/bin/python"
SCORER = "configs/environments/cc-harmony-score/.venv/bin/python"
RUNNER = "scripts/run_cc_native_validation100.py"


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def sweep() -> Any:
    # 공통 평가 모듈을 찾는 경로는 이 코드의 실제 저장소 루트로 고정한다.
    repository = str(Path(__file__).resolve().parents[2])
    if repository not in sys.path:
        sys.path.insert(0, repository)
    from scripts import run_cc_native_validation100

    return run_cc_native_validation100


def plan(run: str, models: str, gpus: str | None) -> list[dict[str, Any]]:
    """Verify existing frozen inputs without preparing or allocating a model."""
    # run은 디렉터리 이름으로 쓰므로 경로 이동 문자와 임의 경로를 받지 않는다.
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run) is None:
        raise ValueError("Invalid training run name")
    # kinds의 순서가 실행 순서다. all이면 base를 끝낸 뒤 adapter를 평가한다.
    kinds = ["base", "adapter"] if models == "all" else [models]
    placements = [
        read(ROOT / f"configs/{run}-{kind}-validation100.json").get("model_device_map")
        for kind in kinds
    ]
    sharded = all(placement == "balanced" for placement in placements)
    if any(placement is not None for placement in placements) and not sharded:
        raise ValueError("Both arms must use the same supported model placement")
    devices = (gpus or ("0,1" if sharded else "0")).split(",")
    if any(re.fullmatch(r"[0-9]+", device) is None for device in devices):
        raise ValueError("Choose valid GPU indexes")
    if sharded:
        if len(devices) != 2 or len(set(devices)) != 2:
            raise ValueError("Model sharding requires two distinct GPU indexes")
        # 각 모델이 두 GPU 메모리를 함께 사용한다. base 완료 후 adapter가 같은 두 장을 사용한다.
        devices = [",".join(devices)] * len(kinds)
    else:
        if len(devices) == 1:
            devices *= len(kinds)
        if len(devices) != len(kinds):
            raise ValueError("Choose one GPU index, or one index per sequential arm")
    training = ROOT / "outputs" / run
    # adapter 저장까지 끝난 학습만 평가 대상으로 삼는다.
    if read(training / "training-runtime.json")["status"] != "completed":
        raise ValueError("Training and adapter save must be completed")
    # arms에는 모델별 GPU, 설정·결과 경로와 계획한 생성 횟수를 담는다.
    arms = []
    for kind, device in zip(kinds, devices, strict=True):
        config_path = Path(f"configs/{run}-{kind}-validation100.json")
        config = read(ROOT / config_path)
        output = Path(f"outputs/{run}-{kind}-validation100")
        if sharded:
            sweep().model_load_kwargs(config, len(device.split(",")))
        # 다른 모델·학습 run의 설정이나 과거 실행 방식이 섞이면 시작 전에 거부한다.
        if (
            config["models"] != [kind]
            or config["training_reference"] != f"outputs/{run}"
            or config["output_dir"] != str(output)
            or config["execution_protocol"] != sweep().ISOLATION_PROTOCOL
        ):
            raise ValueError("Evaluation configuration differs from the selected run")
        # audit는 동결 입력·adapter 검증 결과, pending은 아직 시작하지 않은 조건이다.
        # 조건 도중 끊긴 결과는 원 sampling 흐름을 재현할 수 없어 이 단계에서 거부한다.
        audit, pending = sweep().condition_plan(config, ROOT / output, training)
        arms.append(
            {
                "model": kind,
                "gpu": device,
                "config": str(config_path),
                "output": str(output),
                "planned": audit["planned_calls"],
                "pending_conditions": len(pending),
            }
        )
    for path in (NATIVE, SCORER):
        # 생성만 시작한 뒤 채점 환경 누락을 발견하지 않도록 둘 다 미리 확인한다.
        if not (ROOT / path).is_file():
            raise ValueError(f"Missing environment: {path}")
    return arms


def snapshot(run: str) -> dict[str, Any]:
    """Report current raw counts separately from the last scored snapshot."""
    # control은 전체 실행 기록, 각 모델의 root는 개별 생성·채점 결과 폴더다.
    control = ROOT / f"outputs/{run}-evaluation"
    state = read(control / "state.json") if (control / "state.json").exists() else {}
    arms = []
    for kind in ("base", "adapter"):
        root = ROOT / f"outputs/{run}-{kind}-validation100"
        if not (root / "prepared.json").exists():
            # 준비되지 않은 모델은 계획 횟수도 없으므로 진행률 집계에서 제외한다.
            continue
        prepared = read(root / "prepared.json")
        scored = (
            read(root / "confusion-matrices.json")
            if (root / "confusion-matrices.json").exists()
            else {}
        )
        progress = (
            read(root / "progress.json") if (root / "progress.json").exists() else {}
        )
        # 채점은 일정 간격으로 갱신된다. 실제 생성 완료 수와 마지막 채점 수를 구분한다.
        raw_count = len(list((root / "raw").glob("*.json")))
        arms.append(
            {
                "model": kind,
                "completed_raw": raw_count,
                "planned": prepared["planned_calls"],
                "progress": progress,
                "scored_at": scored.get("scored_at"),
                "groups": [
                    {
                        k: group[k]
                        for k in (
                            "budget",
                            "completed",
                            "planned",
                            "pending",
                            "strict_matrix",
                            "semantic_matrix",
                        )
                    }
                    for group in scored.get("groups", [])
                ],
            }
        )
    return {"run": run, "controller": state, "arms": arms}


def save_summary(run: str) -> dict[str, Any]:
    result = snapshot(run)
    control = ROOT / f"outputs/{run}-evaluation"
    sweep().write(control / "summary.json", result)
    lines = [
        "# B200 자유 생성 평가",
        "",
        "같은 validation100을 상한마다 반복합니다. pending은 invalid가 아닙니다.",
        "",
        "| 모델 | 상한 | 채점/계획 | 기준 | TP | FN | FP | TN | uncertain | invalid | pending |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    # 모델 → 생성 상한 → 채점 기준 순서로 표를 만든다.
    for arm in result["arms"]:
        for group in arm["groups"]:
            # strict는 출력 계약까지 검사하고, semantic은 final JSON의 판단값을 읽는다.
            for label, key in (
                ("strict", "strict_matrix"),
                ("semantic", "semantic_matrix"),
            ):
                # 행: 정답 양성·음성. 열: 예측 양성·음성·판단 보류·출력 무효.
                matrix = group[key]
                # TP/FN/FP/TN, 판단 보류, 출력 무효, 미실행을 별도 열로 보존한다.
                values = [
                    matrix[0][0],
                    matrix[0][1],
                    matrix[1][0],
                    matrix[1][1],
                    matrix[0][2] + matrix[1][2],
                    matrix[0][3] + matrix[1][3],
                    group["pending"],
                ]
                lines.append(
                    f"| {arm['model']} | {group['budget']} | {group['completed']}/{group['planned']} | {label} | "
                    + " | ".join(map(str, values))
                    + " |"
                )
    lines += [
        "",
        "raw 완료 수와 채점 시각은 summary.json에 별도 기록합니다. 원천 라벨은 미검수입니다.",
    ]
    (control / "summary.md").write_text("\n".join(lines) + "\n")
    return result


def terminate(process: subprocess.Popen[Any]) -> None:
    """Stop the controller, its model worker and scorer in their own process group."""
    try:
        # 별도 세션의 프로세스 그룹 전체에 보내 모델 worker·scorer도 함께 종료한다.
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        # 10초는 종료 정리 대기 시간이다. 모델의 생성 시간 상한을 뜻하지 않는다.
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    # 부모가 먼저 종료돼도 자식이 남을 수 있어 남은 프로세스 그룹을 강제 정리한다.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def score_arm(arm: dict[str, Any], environment: dict[str, str], log: Any) -> int:
    return subprocess.run(
        [str(ROOT / SCORER), RUNNER, "score", "--config", arm["config"]],
        cwd=ROOT,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
    ).returncode


def arm_complete(arm: dict[str, Any]) -> bool:
    root = ROOT / arm["output"]
    progress = read(root / "progress.json") if (root / "progress.json").exists() else {}
    report = read(root / "confusion-matrices.json")
    groups = report["groups"]
    # 종료 코드만으로 성공 처리하지 않는다. 진행 기록·raw 개수·두 행렬이 모두 맞아야 한다.
    return (
        progress.get("status") == "completed"
        and progress.get("completed") == progress.get("planned") == arm["planned"]
        and len(list((root / "raw").glob("*.json"))) == arm["planned"]
        and report["complete"] is True
        and sum(group["completed"] for group in groups) == arm["planned"]
        and all(
            # 각 상한의 모든 표본이 끝나고, 행렬 합계가 완료 수와 같아야 한다.
            group["completed"] == group["planned"]
            and group["pending"] == 0
            and sum(map(sum, group["strict_matrix"])) == group["completed"]
            and sum(map(sum, group["semantic_matrix"])) == group["completed"]
            for group in groups
        )
    )


def execute(run: str, arms: list[dict[str, Any]]) -> int:
    """Keep the original base-first order and stop the sweep after its first failure."""
    control = ROOT / f"outputs/{run}-evaluation"
    control.mkdir(exist_ok=True)
    # 시작 전 검증과 최종 채점에는 GPU를 노출하지 않는다.
    environment = dict(os.environ, CUDA_VISIBLE_DEVICES="")
    state: dict[str, Any] = {
        "status": "checking",
        "started_at": sweep().now(),
        "pid": os.getpid(),
        "arms": {arm["model"]: {**arm, "status": "pending"} for arm in arms},
        "runner_sha256": sweep().digest(ROOT / RUNNER),
        "controller_sha256": sweep().digest(Path(__file__)),
    }
    # processes는 시작한 자식, cleaned는 이미 종료 정리를 마친 모델을 추적한다.
    # 정리한 그룹에 다시 신호를 보내지 않도록 cleaned를 따로 유지한다.
    processes: dict[str, subprocess.Popen[Any]] = {}
    cleaned: set[str] = set()
    logs: dict[str, Any] = {}
    # 검증·실행을 모두 통과한 경우에만 성공 코드 0으로 바꾼다.
    exit_status = 1
    with (control / "controller.lock").open("a") as lock:
        # 같은 학습 run의 평가를 중복 실행하면 기다리지 않고 즉시 거부한다.
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

        def persist() -> None:
            sweep().write(control / "state.json", state)

        persist()
        try:
            # 두 모델의 입력·adapter·Harmony 환경을 먼저 검사한 뒤 GPU 생성을 시작한다.
            with (control / "preflight.log").open("a") as log:
                for arm in arms:
                    subprocess.run(
                        [
                            str(ROOT / NATIVE),
                            "scripts/b200/check_ddp_eval.py",
                            arm["model"],
                            "--run",
                            run,
                        ],
                        cwd=ROOT,
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
                    if score_arm(arm, environment, log) != 0:
                        # 초기 채점이 실패하면 생성 자원을 쓰기 전에 전체 실행을 멈춘다.
                        raise RuntimeError(f"{arm['model']} Harmony preflight failed")
            state["status"] = "running"
            persist()
            for arm in arms:
                kind = arm["model"]
                # 재실행 기록이 기존 로그를 덮지 않도록 이어 쓰기 모드를 사용한다.
                logs[kind] = (ROOT / arm["output"] / "generation.log").open("a")
                # 이번 모델이 사용할 물리 GPU 묶음을 노출한다. 분할 로딩 시 두 장을 함께 사용한다.
                child_env = dict(
                    os.environ, CUDA_VISIBLE_DEVICES=arm["gpu"], PYTHONUNBUFFERED="1"
                )
                processes[kind] = subprocess.Popen(
                    [str(ROOT / NATIVE), RUNNER, "run", "--config", arm["config"]],
                    cwd=ROOT,
                    env=child_env,
                    stdout=logs[kind],
                    stderr=subprocess.STDOUT,
                    # 중단 시 부모·worker·scorer를 함께 정리할 별도 프로세스 그룹을 만든다.
                    start_new_session=True,
                )
                state["arms"][kind].update(status="running", pid=processes[kind].pid)
                persist()
                # last_count는 마지막으로 표시한 완료 수다. 같은 진행률을 반복 출력하지 않는다.
                last_count = None
                while processes[kind].poll() is None:
                    # 현재 모델이 종료할 때까지 기다린다. 다음 모델은 아직 시작하지 않는다.
                    count = len(list((ROOT / arm["output"] / "raw").glob("*.json")))
                    if count != last_count:
                        print(
                            f"{kind} GPU{arm['gpu']}: {count}/{arm['planned']}",
                            flush=True,
                        )
                        last_count = count
                    time.sleep(1)
                terminate(processes[kind])
                cleaned.add(kind)
                state["arms"][kind].update(
                    status="completed" if processes[kind].returncode == 0 else "failed",
                    generation_exit=processes[kind].returncode,
                )
                persist()
                if processes[kind].returncode != 0:
                    # worker가 실패하면 같은 모델의 남은 조건과 다음 모델을 자동 재시도하지 않는다.
                    break
            exit_status = (
                0
                if all(process.returncode == 0 for process in processes.values())
                else 1
            )
            state["status"] = "completed" if exit_status == 0 else "failed"
        except KeyboardInterrupt:
            # Ctrl-C와 SIGTERM은 실패와 구분해 중단 상태·종료 코드 130으로 보존한다.
            state["status"] = "interrupted"
            exit_status = 130
        except Exception as error:
            state.update(status="failed", error=type(error).__name__)
            print(f"Evaluation stopped: {error}", file=sys.stderr, flush=True)
        finally:
            # 성공·실패·중단 모두 이 경로로 들어와 남은 자식을 정리하고 결과를 저장한다.
            for kind, process in processes.items():
                if kind not in cleaned:
                    terminate(process)
            for arm in arms:
                kind = arm["model"]
                if kind in logs:
                    # 시작을 시도한 모델만 최종 채점한다. 미착수 모델은 pending으로 남긴다.
                    # 자식 생성 자체가 실패했으면 generation_exit에는 None을 기록한다.
                    generation_exit = (
                        processes[kind].returncode if kind in processes else None
                    )
                    try:
                        score_exit = score_arm(arm, environment, logs[kind])
                        complete = generation_exit == score_exit == 0 and arm_complete(
                            arm
                        )
                    except BaseException as error:
                        # 채점·완료 검증 오류도 기록해, 생성 종료 코드 0만으로 성공하지 않게 한다.
                        score_exit, complete = 1, False
                        state["arms"][kind]["score_error"] = type(error).__name__
                    state["arms"][kind].update(
                        generation_exit=generation_exit,
                        score_exit=score_exit,
                        status="completed" if complete else "failed",
                    )
                    if not complete and exit_status != 130:
                        # 사용자가 중단한 코드 130은 최종 채점 실패로 덮어쓰지 않는다.
                        exit_status, state["status"] = 1, "failed"
                    logs[kind].close()
            state.update(finished_at=sweep().now(), exit_code=exit_status)
            persist()
            save_summary(run)
    print(f"{state['status']}: outputs/{run}-evaluation/summary.md", flush=True)
    return exit_status


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("plan", "run", "start", "status", "stop"))
    parser.add_argument("--run", required=True)
    parser.add_argument("--models", choices=("all", "base", "adapter"), default="all")
    parser.add_argument("--gpus")
    parser.add_argument("--json", action="store_true", help="Print full status JSON")
    args = parser.parse_args()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", args.run) is None:
        parser.error("Invalid training run name")
    session = f"b200-eval-{args.run}"
    if args.action == "status":
        # 상태 조회는 파일만 읽는다. 모델 로딩이나 상태 기록 갱신을 하지 않는다.
        status = snapshot(args.run)
        if args.json:
            print(json.dumps(status, ensure_ascii=False, indent=2))
        else:
            print("실행 관리:", status["controller"].get("status", "실행 기록 없음"))
            for arm in status["arms"]:
                # 마지막 채점은 실제 raw 생성보다 늦을 수 있어 두 횟수를 함께 보여 준다.
                scored = sum(group["completed"] for group in arm["groups"])
                print(
                    f"{arm['model']}: 생성 {arm['completed_raw']}/{arm['planned']}, 채점 {scored}/{arm['planned']}"
                )
            print(f"결과 요약: outputs/{args.run}-evaluation/summary.md")
        return
    if args.action == "stop":
        # tmux의 전경 실행에 Ctrl-C를 보내 execute의 정리 경로로 들어가게 한다.
        subprocess.run(["tmux", "send-keys", "-t", session, "C-c"], check=True)
        return
    arms = plan(args.run, args.models, args.gpus)
    if args.action == "plan":
        # 입력·재개 가능 조건 검증만 수행한 계획이며 실제 GPU 생성은 시작하지 않는다.
        print(json.dumps({"arms": arms, "generation_started": False}, indent=2))
    elif args.action == "start":
        # tmux가 서버에서 전경 실행을 맡으므로 SSH 연결 종료와 분리해 계속 실행할 수 있다.
        control = ROOT / f"outputs/{args.run}-evaluation"
        control.mkdir(exist_ok=True)
        command = [
            "bash",
            "scripts/b200/run-evaluation.sh",
            "run",
            "--run",
            args.run,
            "--models",
            args.models,
            "--gpus",
            arms[0]["gpu"]
            if all(arm["gpu"] == arms[0]["gpu"] for arm in arms)
            else ",".join(arm["gpu"] for arm in arms),
        ]
        # 경로·인자를 셸용으로 인용하고, 전체 실행 로그도 기존 기록에 이어 쓴다.
        shell_command = (
            shlex.join(command)
            + " >> "
            + shlex.quote(str(control / "controller.log"))
            + " 2>&1"
        )
        subprocess.run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                session,
                "-c",
                str(ROOT),
                shell_command,
            ],
            check=True,
        )
        print(f"Started tmux session {session}; use status for progress.")
    else:

        def interrupted(signum: int, frame: Any) -> None:
            # 관리자 종료 신호도 Ctrl-C와 같은 중단·프로세스 정리 경로로 연결한다.
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, interrupted)
        sys.exit(execute(args.run, arms))


if __name__ == "__main__":
    main()
