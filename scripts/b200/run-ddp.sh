#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
run=${1:-b200-ddp2-step100-v1}
out="outputs/$run"
trap 'rc=$?; printf "{\"exit_code\":%d}\n" "$rc" > "$out/launcher-exit.json"' EXIT
source outputs/b200-runtime-env.sh
export CUDA_VISIBLE_DEVICES=0,1
native=configs/environments/cc-native-step100/.venv/bin/python
"$native" scripts/b200/manage.py check-env native --expected-python 3.12.3
"$native" -m torch.distributed.run --standalone --nnodes=1 --nproc-per-node=2 \
  --max-restarts=0 --log-dir "outputs/$run/torchrun-logs" --redirects=3 -- \
  scripts/b200/train_ddp.py train --run "$run"
"$native" scripts/b200/train_ddp.py check --run "$run"
