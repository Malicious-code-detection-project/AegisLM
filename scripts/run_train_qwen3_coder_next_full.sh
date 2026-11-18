#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

exec bash scripts/run_observed_llamafactory_train.sh \
  configs/llamafactory/b200/qwen3_coder_next_lora_full.yaml \
  model/base/qwen3-coder-next \
  qwen3-coder-next-full \
  qwen3-coder-next
