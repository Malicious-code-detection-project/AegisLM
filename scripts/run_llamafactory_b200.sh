#!/usr/bin/env bash
set -euo pipefail

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3}"
export WANDB_PROJECT="${WANDB_PROJECT:-malware-analysis-llm}"
export WANDB_LOG_MODEL="${WANDB_LOG_MODEL:-false}"
export WANDB_WATCH="${WANDB_WATCH:-false}"
export WANDB_DIR="${WANDB_DIR:-model/wandb}"
export PATH="$PWD/.venv/bin:$PATH"
export PYTHONPATH="$PWD/LLaMA-Factory/src:${PYTHONPATH:-}"

mkdir -p "$WANDB_DIR" model/runs model/adapters model/checkpoints

.venv/bin/llamafactory-cli train configs/llamafactory/b200/qwen3_coder_480b_fp8_lora_smoke.yaml
