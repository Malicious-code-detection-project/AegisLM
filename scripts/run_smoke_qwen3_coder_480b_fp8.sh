ㅇ#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${WANDB_API_KEY:-}" ]]; then
  echo "WANDB_API_KEY must be set before starting online W&B training." >&2
  exit 1
fi

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3}"
export WANDB_PROJECT="${WANDB_PROJECT:-malware-analysis-llm}"
export WANDB_LOG_MODEL="${WANDB_LOG_MODEL:-false}"
export WANDB_WATCH="${WANDB_WATCH:-false}"
export WANDB_DIR="${WANDB_DIR:-model/wandb}"
export PATH="$PWD/.venv/bin:$PATH"
export PYTHONPATH="$PWD/LLaMA-Factory/src:${PYTHONPATH:-}"

mkdir -p "$WANDB_DIR" model/runs model/adapters model/checkpoints

MODEL_DIR="model/base/qwen3-coder-480b-a35b-instruct-fp8"
NPROC="$(
  .venv/bin/python - <<'PY'
import os

visible = os.environ.get("CUDA_VISIBLE_DEVICES", "0,1,2,3")
print(len([item for item in visible.split(",") if item.strip()]))
PY
)"
MEMORY_GUARD_MODE="${B200_MEMORY_GUARD_MODE:-fail-fast}"
MEMORY_GUARD_ARGS=(--model-dir "$MODEL_DIR" --nproc "$NPROC")

if [[ "${B200_MEMORY_ALLOW_KNOWN_RISK:-}" == "1" ]]; then
  MEMORY_GUARD_ARGS+=(--allow-known-risk)
fi

case "$MEMORY_GUARD_MODE" in
  fail-fast)
    .venv/bin/python scripts/check_memory_budget.py "${MEMORY_GUARD_ARGS[@]}"
    ;;
  monitor)
    if [[ "${B200_MEMORY_ALLOW_KNOWN_RISK:-}" != "1" ]]; then
      echo "B200_MEMORY_GUARD_MODE=monitor requires B200_MEMORY_ALLOW_KNOWN_RISK=1." >&2
      exit 1
    fi
    .venv/bin/python scripts/check_memory_budget.py "${MEMORY_GUARD_ARGS[@]}"
    .venv/bin/python scripts/check_memory_budget.py \
      --watch \
      --model-dir "$MODEL_DIR" \
      --nproc "$NPROC" \
      --output-dir model/runs/memory &
    MEMORY_WATCH_PID="$!"
    trap 'kill "$MEMORY_WATCH_PID" 2>/dev/null || true' EXIT
    ;;
  off)
    echo "B200 memory guard disabled by B200_MEMORY_GUARD_MODE=off."
    ;;
  *)
    echo "Unknown B200_MEMORY_GUARD_MODE: $MEMORY_GUARD_MODE" >&2
    exit 1
    ;;
esac

.venv/bin/llamafactory-cli train configs/llamafactory/b200/qwen3_coder_480b_fp8_lora_smoke.yaml
