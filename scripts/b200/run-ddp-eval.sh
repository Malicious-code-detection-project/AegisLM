#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
kind=${1:?Pass base or adapter}
run=${2:?Pass the completed two-GPU training run name}
case "$kind" in base|adapter) ;; *) exit 2 ;; esac
source outputs/b200-runtime-env.sh
# Native generation preserves the original one-device evaluation protocol.
export CUDA_VISIBLE_DEVICES=0
native=configs/environments/cc-native-step100/.venv/bin/python
score=configs/environments/cc-harmony-score/.venv/bin/python
config="configs/${run}-${kind}-validation100.json"
out="outputs/${run}-${kind}-validation100"
"$native" scripts/b200/check_ddp_eval.py "$kind" --run "$run"
if [[ -e "$out/progress.json" ]]; then
  echo 'Preserve the existing generation attempt and use its documented resume protocol.' >&2
  exit 1
fi
"$score" scripts/run_cc_native_validation100.py score --config "$config"
"$native" scripts/run_cc_native_validation100.py run --config "$config" > "$out/generation.log" 2>&1
"$score" scripts/run_cc_native_validation100.py score --config "$config"
