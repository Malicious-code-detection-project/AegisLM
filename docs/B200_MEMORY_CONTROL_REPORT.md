---
type: Decision Note
title: B200 Qwen3-Coder 480B Memory Observation Report
description: Qwen3-Coder 480B FP8 학습에서 자체 soft-stop을 제거하고 observe-only telemetry로 재분석하는 운영 정책
tags: [project, b200, qwen3, finetuning, memory]
timestamp: 2026-07-03
status: active
---

# Summary

현재 정책은 `Qwen3-Coder-480B-A35B-Instruct-FP8` 학습을 코드가 임의로 중단하지 않고, cgroup/CPU/pids/GPU/process telemetry를 관측 전용으로 남기는 것이다.

중요한 정정:

- `cgroup memory.max ~= 800GiB`는 프로젝트 코드가 설정한 값이 아니라 Docker/container cgroup 설정이다.
- 700GiB 부근에서 더 일찍 멈춘 실행은 우리가 추가했던 soft-limit watcher가 학습 process group에 `SIGTERM`을 보낸 결과다.
- 해당 controlled stop 기능은 원인 분석을 흐릴 수 있으므로 retired 처리했다.
- 현재 watcher는 `model/runs/memory/` 아래 JSONL/CSV만 기록하고 학습 process에는 signal을 보내지 않는다.

# Current Policy

## Observe-only Memory Watcher

현재 남긴 조절 지점은 telemetry sampling뿐이다.

```text
B200_MEMORY_GUARD_MODE=monitor
B200_MEMORY_WATCH_INTERVAL_SECONDS=2
```

`B200_MEMORY_GUARD_MODE=monitor`는 기본값이며, 다음을 수행한다.

- 실행 전 cgroup/model shard 상태를 출력한다.
- known-risk profile은 warning으로만 출력한다.
- 학습과 별도로 watcher를 띄워 cgroup/GPU/process snapshot을 기록한다.
- watcher는 학습 process group에 `SIGTERM`이나 `SIGKILL`을 보내지 않는다.

`B200_MEMORY_GUARD_MODE=off`는 watcher를 띄우지 않고 학습을 실행한다. 다만 실행 전 memory budget report는 warning 출력용으로 유지한다.

## Retired Soft-stop Controls

다음 옵션과 동작은 제거됐다.

```text
B200_MEMORY_SOFT_LIMIT_GIB
--soft-limit-gib
--terminate-pgid
--exit-on-soft-limit
os.killpg(...)
```

따라서 이후 480B FP8 재실험에서 발생하는 종료는 프로젝트 watcher가 직접 보낸 signal 때문이 아니다. `torchrun`, cgroup `memory.events`, CPU/pids pressure, 외부 watchdog/admin kill 가능성을 다시 분리해서 봐야 한다.

# What Can Still Be Controlled

## Rank Count

조절 가능:

```text
CUDA_VISIBLE_DEVICES
```

`torchrun --nproc_per_node 4`는 CPU core 4개가 아니라 4개의 distributed rank를 뜻한다. rank 수를 늘리면 CPU core가 늘어나는 것이 아니라 모델 로딩 process 수가 늘어날 수 있다. checkpoint loading 단계에서 각 rank가 큰 RSS를 중복 사용한다면 rank 수 증가는 총 cgroup memory 사용량을 키운다.

우선 실험 순서:

```text
nproc=1 load-only
nproc=2 load-only
nproc=4 load-only
```

## Loader / Framework Path

실제 메모리 피크를 낮추려면 loader 구조가 중요하다.

현재 LLaMA-Factory + torchrun + DeepSpeed ZeRO-3 경로는 checkpoint loading 중 4개 rank가 동시에 큰 RSS를 사용하는 것으로 보인다. 장기 해결 후보는 다음이다.

- ms-swift Megatron: tensor/pipeline/expert parallelism 후보
- NVIDIA NeMo: large-model-native import/fine-tuning recipe 후보
- HF Transformers/TRL: LLaMA-Factory와 loader baseline 비교용
- Axolotl/torchtune: 대체 distributed training path 비교용

핵심 질문:

```text
각 rank가 전체 checkpoint를 들고 있는가?
아니면 각 rank가 자기 partition만 들고 있는가?
```

480B급에서는 후자의 구조가 필요하다.

# Smaller-model Baselines

480B 재실험 전에 작은 모델 smoke run으로 다음을 분리한다.

- dataset export/registration 문제인지
- LLaMA-Factory trainer path 문제인지
- W&B logging 문제인지
- Qwen3-Coder template/model 계열 문제인지
- 480B checkpoint loading scale 문제인지

1차 baseline:

```bash
bash scripts/run_smoke_qwen2_72b.sh
```

사용 모델:

```text
<WORKSPACE>/<TEAM>/Model/Text2SQL/LLM_qwen72B
```

2차 Qwen3-Coder baseline:

```bash
.venv/bin/python scripts/download_hf_model.py   --variant qwen3-coder-30b   --max-download-gib 80

bash scripts/run_smoke_qwen3_coder_30b.sh
```

# Logged Fields

JSONL/CSV에는 다음을 남긴다.

- cgroup `memory.max`, `memory.current`, `memory.peak`, `memory.events`
- host `MemAvailable`
- GPU memory/utilization
- CPU `cpu.stat`, `cpu.pressure`
- `memory.pressure`
- `pids.current`, `pids.max`, `pids.events`
- top RSS process snapshot
- rank/process별 thread count
- framework, experiment id, model variant, phase

더 이상 `soft_limit_gib`, `soft_limit_exceeded`, `limit_action`은 기록하지 않는다.

# Current Commands

480B FP8 observe-only run:

```bash
B200_MEMORY_GUARD_MODE=monitor B200_MEMORY_WATCH_INTERVAL_SECONDS=2 bash scripts/run_smoke_qwen3_coder_480b_fp8.sh
```

watcher만 10초 확인:

```bash
.venv/bin/python scripts/check_memory_budget.py   --watch   --duration-seconds 10   --model-dir model/base/qwen3-coder-480b-a35b-instruct-fp8   --nproc 4   --output-dir model/runs/memory   --framework llamafactory   --experiment-id observe-only-check   --model-variant qwen3-coder-480b-fp8   --phase train
```

# Decision Table

| Adjustment | 직접 kill 여부 | Purpose | Recommendation |
|---|---:|---|---|
| observe-only watcher | No | Evidence collection | Default |
| `B200_MEMORY_GUARD_MODE=off` | No | No watcher baseline | Use only when telemetry overhead is questioned |
| `CUDA_VISIBLE_DEVICES` / nproc | No | Rank-count memory scaling | Measure 1/2/4 |
| smaller model smoke | No | Pipeline sanity check | Run before 480B retry |
| framework loader path | No | Reduce checkpoint-load duplication | Compare Megatron/NeMo candidates |
| batch size / cutoff / LoRA rank | No for current load failure | Tune train-step memory | Tune after load succeeds |

# Next Action

1. Run `scripts/run_smoke_qwen2_72b.sh` to verify dataset/LLaMA-Factory/W&B path.
2. Download and run `qwen3-coder-30b` smoke if Qwen3-Coder-specific behavior must be separated.
3. Re-run 480B FP8 with observe-only watcher and user-side monitoring.
4. Compare telemetry around the natural termination point without our soft-stop signal in the loop.

# Related Concepts

- [B200 Qwen3-Coder 480B SIGKILL Analysis Process](B200_QWEN3_480B_MEMORY_PROCESS.md)
- [B200 480B FP8 Framework Matrix Experiments](FRAMEWORK_MATRIX_EXPERIMENTS.md)
- [Qwen3-Coder 480B FP8 SIGKILL Investigation](../../../../../errors/llamafactory-qwen3-coder-480b-fp8-oom-kill.md)
