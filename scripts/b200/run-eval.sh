#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
kind=${1:?Pass base or adapter}
case "$kind" in base|adapter) ;; *) exit 2 ;; esac
native=configs/environments/cc-native-step100/.venv/bin/python
score=configs/environments/cc-harmony-score/.venv/bin/python
config="configs/b200-${kind}-validation100-v1.json"
out="outputs/b200-${kind}-validation100-v1"
"$native" scripts/b200/manage.py check-training
if [[ -e "$out/prepared.json" ]]; then
  echo "This attempt already exists. Preserve it; follow the recipe's interruption guidance." >&2
  exit 1
fi
"$native" scripts/run_cc_native_validation100.py prepare --config "$config"
"$native" scripts/b200/manage.py check-eval "$kind"
"$score" scripts/run_cc_native_validation100.py score --config "$config"
# Run the tracker separately as documented; it never owns a GPU worker.
"$native" scripts/run_cc_native_validation100.py run --config "$config" > "$out/generation.log" 2>&1
"$score" scripts/run_cc_native_validation100.py score --config "$config"
