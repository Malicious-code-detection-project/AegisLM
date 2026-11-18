# B200 Qwen3-Coder 480B SIGKILL Analysis Process

## Summary

이 문서는 MalwareAnalysisLLM B200 4-GPU 환경에서 `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8` smoke fine-tuning을 시도하며 확인한 `SIGKILL` 사건과 다음 분석 절차를 정리한다.

핵심 결론은 다음과 같다.

- 현재 단계에서는 원인을 OOM으로 확정하지 않는다.
- torchrun 로그 단독으로는 왜 `SIGKILL`이 발생했는지 알 수 없다.
- GPU OOM으로 보이지는 않는다. 실패 직전 GPU memory가 매우 낮고 `CUDA out of memory` 메시지가 없었다.
- host 전체 RAM 부족으로 보이지도 않는다. host `MemAvailable`은 충분했다.
- 가장 강한 현재 가설은 container cgroup memory limit kill이다. 근거는 cgroup `memory.max=800GiB`, `memory.current ~= 800GiB`, `memory.events.oom_kill 4 -> 5`다.
- 다만 CPU pressure, pids limit, external watchdog/admin kill 가능성도 실험으로 분리해야 한다.

## What Happened

실행 대상:

```text
project: <HOME>/workspace/MalwareAnalysisLLM
branch: experiment/b200-qwen3-coder-480b
model: Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8
local model dir: model/base/qwen3-coder-480b-a35b-instruct-fp8
launcher: LLaMA-Factory + torchrun + DeepSpeed ZeRO-3
GPU: 4 x NVIDIA B200
```

실패 지점:

```text
Loading weights: 40%|...
failed (exitcode: -9) local_rank: 0
traceback : Signal 9 (SIGKILL) received by PID ...
```

`SIGTERM`을 받은 rank는 root cause가 아니다. 하나의 rank가 `SIGKILL`된 뒤 `torchrun`이 나머지 rank를 정리하면서 종료 신호를 보낸 것이다.

## 2026-07-02 15:44 KST Observation

사용자가 직접 `B200_MEMORY_GUARD_MODE=monitor`로 실행을 지켜본 뒤, 마지막 4개의 memory watcher JSONL 샘플을 공유했다.

요약:

| KST time | cgroup current | cgroup limit | oom | oom_kill | train ranks | rank RSS | GPU memory |
|---|---:|---:|---:|---:|---:|---|---|
| 15:44:42 | 800.00 GiB | 800.00 GiB | 109 | 4 | 4 | 약 200 GiB x 4 | 약 1688 MiB x 4 |
| 15:44:47 | 792.88 GiB | 800.00 GiB | 156 | 5 | 3 | 약 199 GiB x 3 | 약 1688 MiB x 4 |
| 15:44:52 | 517.43 GiB | 800.00 GiB | 156 | 5 | 0 | worker 사라짐 | GPU0 388 MiB, GPU1-3 1688 MiB |
| 15:44:57 | 109.46 GiB | 800.00 GiB | 156 | 5 | 0 | worker 사라짐 | GPU0 388 MiB, GPU1-3 1688 MiB |

해석:

- 15:44:42에는 이미 cgroup memory가 800GiB limit에 도달했다.
- 15:44:47에는 `oom_kill`이 4에서 5로 증가했고, training worker가 4개에서 3개로 줄었다.
- 15:44:52 이후 worker들이 사라지고 cgroup memory가 급락했다.
- GPU memory는 낮았고 host `MemAvailable`도 충분했다.
- 따라서 torchrun 로그만으로는 원인을 알 수 없지만, memory watcher와 결합하면 container cgroup memory limit kill 가설이 강하다.

## PID, CPU Core, Rank

실행 중 보인 4개의 PID는 CPU core 4개가 아니라 `torchrun --nproc_per_node 4`가 만든 4개의 distributed rank 프로세스다.

- 일반적으로 4 GPU 학습에서는 GPU 1장당 rank 1개를 둔다.
- 각 rank PID는 내부적으로 여러 CPU thread를 사용할 수 있다.
- PID/rank 수를 늘리는 것은 CPU core를 더 할당하는 것과 다르다.
- checkpoint loading 단계에서 각 rank가 모델 shard를 중복으로 읽거나 펼친다면 rank 수를 늘릴수록 총 RSS가 더 커질 수 있다.

따라서 CPU 문제인지 확인은 필요하지만, 단순히 PID/rank를 더 많이 띄우는 것은 안전한 해결책으로 보기 어렵다.

## How To Read The Failure

분석할 때는 아래 순서로 본다.

1. torchrun traceback
   - `exitcode: -9` 또는 `Signal 9 (SIGKILL)`이면 Python exception이 아니라 외부 kill이다.
   - 나머지 rank의 `SIGTERM`은 정리 과정일 수 있으므로 최초 실패 rank를 찾는다.

2. GPU memory
   - `CUDA out of memory` 메시지가 있는지 확인한다.
   - 실패 직전 GPU memory가 낮으면 GPU OOM 가능성은 낮다.

3. host memory
   - `free -h`는 host 전체 관점이다.
   - host memory가 충분해도 컨테이너 cgroup 제한 때문에 프로세스가 죽을 수 있다.

4. cgroup memory
   - effective `memory.max`가 finite인지 확인한다.
   - `memory.current`와 `memory.peak`가 `memory.max`에 닿았는지 확인한다.
   - `memory.events`의 `oom` 또는 `oom_kill`이 증가했는지 확인한다.

5. CPU, pids, pressure
   - `cpu.stat`, `cpu.pressure`, `memory.pressure`를 확인한다.
   - `pids.current`, `pids.max`, `pids.events`를 확인한다.
   - rank별 CPU 사용률과 thread 수를 확인한다.

6. process RSS
   - `process_metrics`에서 training rank별 RSS를 확인한다.
   - rank별 RSS가 비슷하고 총합이 cgroup limit에 닿으면 multi-rank checkpoint loading 증폭을 의심한다.

## Why `free -h` Was Misleading

호스트 관점에서는 RAM이 충분해 보였다.

```text
Mem: 2.2TiB total
free: about 1.9TiB
```

하지만 실제 프로세스는 Docker/container cgroup 제한 안에서 동작한다.

```text
/sys/fs/cgroup/.../docker-...scope/memory.max
858993459200

/sys/fs/cgroup/.../docker-...scope/memory.peak
858993467392

/sys/fs/cgroup/.../docker-...scope/memory.events
oom 109
oom_kill 4
```

즉, host에 남은 RAM이 2TiB에 가깝더라도 해당 컨테이너가 800GiB cgroup limit 안에 있으면 프로세스는 나머지 host RAM을 사용할 수 없다.

## Why Download Size Is Not The Training Memory Fix

`download_hf_model.py`는 Hugging Face snapshot을 로컬 `model/base/` 아래에 받는다. 이 단계에서 조절할 수 있는 것은 다음이다.

- 다운로드할 파일 목록 확인
- 예상 총량 확인
- 불필요 파일 제외
- local shard 누락 여부 확인
- 디스크/네트워크 예산 초과 시 다운로드 중단

하지만 480B FP8 fine-tuning은 모델 전체 shard를 필요로 한다. 일부 shard만 내려받는 방식은 학습 메모리를 줄이는 해결책이 아니다. 실제 실패는 다운로드가 끝난 뒤 `from_pretrained`/checkpoint loading 중 4개 rank가 weight를 로딩하는 단계에서 발생했다.


## 2026-07-03 Correction: Project Soft-stop Removed

추가 분석 중 700GiB 부근 조기 종료는 서버의 자연 kill이 아니라 프로젝트에 임시로 추가했던 soft-limit watcher가 학습 process group에 `SIGTERM`을 보낸 결과로 확인됐다. 이 기능은 원인 분석을 흐릴 수 있으므로 제거했다.

현재 상태:

- `scripts/run_smoke_qwen3_coder_480b_fp8.sh` 기본값은 observe-only monitor다.
- `scripts/check_memory_budget.py --watch`는 JSONL/CSV telemetry만 기록한다.
- `--soft-limit-gib`, `--terminate-pgid`, `--exit-on-soft-limit`, `os.killpg(...)` 경로는 제거됐다.
- known-risk는 warning으로만 남고 훈련 시작을 막지 않는다.

따라서 이후 480B FP8 재실험에서 종료가 발생하면 프로젝트 watcher가 직접 signal을 보낸 것이 아니다. torchrun 로그, cgroup `memory.events`, CPU/pids pressure, external watchdog/admin kill 가능성을 다시 분리해 판단한다.

## Commands

환경 확인:

```bash
cd <HOME>/workspace/MalwareAnalysisLLM
.venv/bin/python scripts/check_environment.py
```

훈련 전 memory budget report:

```bash
.venv/bin/python scripts/check_memory_budget.py \
  --model-dir model/base/qwen3-coder-480b-a35b-instruct-fp8 \
  --nproc 4
```

이 명령은 known-risk를 warning으로 출력하지만 훈련 시작을 막지 않는다.

480B FP8 observe-only 실행:

```bash
B200_MEMORY_GUARD_MODE=monitor \
B200_MEMORY_WATCH_INTERVAL_SECONDS=2 \
bash scripts/run_smoke_qwen3_coder_480b_fp8.sh
```

watch mode는 cgroup/GPU 지표와 함께 top-like process snapshot도 남긴다.

```bash
.venv/bin/python scripts/check_memory_budget.py \
  --watch \
  --model-dir model/base/qwen3-coder-480b-a35b-instruct-fp8 \
  --nproc 4 \
  --top-process-count 20 \
  --output-dir model/runs/memory
```

작은 모델 baseline:

```bash
bash scripts/run_smoke_qwen2_72b.sh

.venv/bin/python scripts/download_hf_model.py \
  --variant qwen3-coder-30b \
  --max-download-gib 80

bash scripts/run_smoke_qwen3_coder_30b.sh
```

## Next Experiments

지금 단계의 목표는 학습 성공이 아니라 load 단계에서 CPU, RAM, cgroup, pids, loader 경로를 분리하는 것이다.

Experiment 0: observe-only 로그 정합성 확인

- 입력: torchrun 실패 로그, memory watcher JSONL/CSV.
- 산출: KST 기준 timeline 표.
- 성공 기준: `SIGKILL` 발생 시점, `oom_kill` 변화, rank RSS 변화가 프로젝트 soft-stop 없이 설명 가능해야 한다.

Experiment 1: smaller-model pipeline baseline

- 기존 72B 모델로 1-step smoke를 실행한다.
- 필요 시 `Qwen/Qwen3-Coder-30B-A3B-Instruct`로 Qwen3-Coder 계열 smoke를 실행한다.
- 성공 기준: dataset export, LLaMA-Factory trainer, W&B loss logging, adapter creation path가 정상 동작한다.

Experiment 2: nproc별 model load RSS 측정

- `nproc=1`, `2`, `4`로 동일 FP8 모델 load-only probe를 실행한다.
- train step 없이 checkpoint loading만 측정한다.
- 성공 기준: rank당 RSS가 약 200GiB로 반복되는지, 총 RSS가 rank 수에 거의 선형으로 증가하는지 확인한다.

Experiment 3: CPU/thread/pids 관측

- 각 rank의 CPU 사용률, thread 수, RSS, VSZ를 함께 기록한다.
- cgroup `cpu.stat`, `cpu.pressure`, `memory.pressure`, `pids.current`, `pids.max`, `pids.events`를 수집한다.
- 성공 기준: CPU throttling, pids limit, memory pressure 중 어떤 신호가 SIGKILL 직전 증가하는지 분리한다.

Experiment 4: LLaMA-Factory 경로와 순수 HF load 경로 비교

- 순수 `transformers.from_pretrained` load-only probe와 LLaMA-Factory launcher 경로를 분리 측정한다.
- 성공 기준: 메모리 증폭이 HF loader 자체인지, LLaMA-Factory/DeepSpeed 초기화 순서에서 커지는지 구분한다.

Experiment 5: DeepSpeed ZeRO 설정 영향 확인

- 기존 `ds_z3_b200.json`을 기준으로 load 단계에서 CPU offload, zero init, gather 옵션이 실제로 적용되는지 로그를 남긴다.
- 성공 기준: ZeRO partition 이전에 각 rank가 checkpoint를 중복 로딩하는지 판단한다.

Experiment 6: 컨테이너 limit 변경 후 동일 실험

- container cgroup limit을 800GiB보다 높인 뒤 같은 `nproc=4` load-only probe를 실행한다.
- 성공 기준: 40% 부근 SIGKILL이 사라지는지, peak memory가 어디까지 올라가는지 측정한다.

각 실험은 최소한 cgroup current/peak/max, `oom`, `oom_kill`, CPU stat, pids stat, rank별 RSS/thread 수, GPU memory, checkpoint loading 진행률, 성공/실패 시각을 남긴다.

## Team Checklist

실행 전:

- `.env`에 `HF_TOKEN`, `WANDB_API_KEY`가 설정되어 있는지 확인한다.
- `model/base/qwen3-coder-480b-a35b-instruct-fp8` shard가 누락 없이 존재하는지 확인한다.
- `scripts/check_memory_budget.py`가 container cgroup limit을 어떻게 판단하는지 확인한다.
- `free -h`만 보고 안전하다고 판단하지 않는다.
- PID/rank 수와 CPU core 수를 혼동하지 않는다.
- 현재 watcher가 학습 process에 signal을 보내지 않는 observe-only 상태인지 확인한다.

실행 중:

- W&B loss logging 여부를 확인한다.
- `model/runs/memory/`의 `memory_current`, `memory_peak`, `oom_kill` 변화를 확인한다.
- `model/runs/memory/`의 `process_metrics` 또는 `top_*` 컬럼으로 어떤 rank/process가 RSS를 키우는지 확인한다.
- CPU throttling, pids limit, memory pressure도 함께 확인한다.
- GPU OOM인지, cgroup memory kill인지, CPU/pids 계열 문제인지 로그를 분리해서 기록한다.

실행 후:

- 성공 여부와 관계없이 model load success/failure, first train step, peak memory, W&B logging, adapter/checkpoint 생성 여부를 기록한다.
- 실패 시 `SIGKILL`, `CUDA out of memory`, `memory.events`, `cpu.stat`, `pids.events` 값을 구분해서 기록한다.

## Current Default

현재 기본 run script는 observe-only monitor다.

```text
B200_MEMORY_GUARD_MODE=monitor
```

known-risk 상태는 warning으로만 남고 훈련 시작을 막지 않는다.
