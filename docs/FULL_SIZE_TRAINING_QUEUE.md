# B200 Full-Size Training Queue

This document records the current full-size training queue for
`<HOME>/workspace/MalwareAnalysisLLM`.

The project is no longer using one-step smoke tests as the main decision point.
The next runs should use the full LLaMA-Factory dataset registration and keep
observe-only telemetry enabled while the user monitors the GPU server directly.

## Current Decision

- Exclude Qwen2/Qwen2.5 72B from the active training queue.
- Resume DeepSeek model download first so the next candidates are ready.
- Train `Qwen/Qwen3-Coder-Next` 80B first.
- Keep `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8` out of the direct
  LLaMA-Factory full-training queue until the checkpoint loading path is changed.

## Download Commands

Load `.env` first so `HF_TOKEN` is available only in the shell.

```bash
cd <HOME>/workspace/MalwareAnalysisLLM
set -a
. ./.env
set +a
export HF_HOME=model/cache/huggingface
```

Resume the default DeepSeek Flash download:

```bash
uv run python scripts/download_hf_model.py \
  --variant deepseek-v4-flash \
  --cache-dir model/cache/huggingface \
  --max-download-gib 360
```

If the cancelled download was the Base variant, use the separate destination:

```bash
uv run python scripts/download_hf_model.py \
  --variant deepseek-v4-flash-base \
  --cache-dir model/cache/huggingface \
  --max-download-gib 420
```

Download Qwen3-Coder-Next 80B for the first real training run:

```bash
uv run python scripts/download_hf_model.py \
  --variant qwen3-coder-next \
  --cache-dir model/cache/huggingface \
  --max-download-gib 220
```

Inspect local shards before running training:

```bash
uv run python scripts/download_hf_model.py \
  --variant qwen3-coder-next \
  --inspect-local
```

## First Real Training Run

Environment:

```bash
cd <HOME>/workspace/MalwareAnalysisLLM
set -a
. ./.env
set +a
export CUDA_VISIBLE_DEVICES=0,1,2,3
export WANDB_PROJECT=malware-analysis-llm
export WANDB_LOG_MODEL=false
export WANDB_WATCH=false
export B200_MEMORY_WATCH_INTERVAL_SECONDS=2
```

Run Qwen3-Coder-Next 80B full training:

```bash
bash scripts/run_train_qwen3_coder_next_full.sh
```

This uses:

- config: `configs/llamafactory/b200/qwen3_coder_next_lora_full.yaml`
- train dataset: `aegislm_security_sft_train_full`
- validation dataset: `aegislm_security_sft_validation_full`
- adapter output: `model/adapters/qwen3-coder-next/lora/full`
- run logs: `model/runs/qwen3-coder-next/lora/full`
- memory logs: `model/runs/memory/`

## Candidate Order

1. `Qwen/Qwen3-Coder-Next` 80B real training.
2. `zai-org/GLM-4.5-Air-FP8` real training compatibility.
3. `deepseek-ai/DeepSeek-V4-Flash` compatibility or real training.
4. `zai-org/GLM-4.5-FP8` load/training limit check.
5. `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8` with Axolotl FSDP2,
   HF/TRL loader comparison, or NeMo/Megatron, not direct LLaMA-Factory first.

## 480B Direction

The 480B failure happens before useful training hyperparameters matter. The
priority is checkpoint loading structure, not batch size, cutoff length, or LoRA
rank. The next 480B path should compare:

- Axolotl FSDP2 with CPU-RAM-efficient loading.
- HF/TRL pure loader baseline.
- NeMo/Megatron tensor, pipeline, or expert parallel loading.

The goal is to avoid per-rank CPU RSS duplication that crosses the current
container cgroup memory boundary.
