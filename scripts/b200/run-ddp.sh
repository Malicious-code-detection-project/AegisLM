#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
run=${1:-b200-ddp2-step100-v3}
out="outputs/$run"
if [[ ! -f "$out/config.json" || ! -d "$out/rank0" || ! -d "$out/rank1" ]]; then
  printf 'Initialize this run first: %s\n' "$run" >&2
  exit 1
fi
# Reject historical attempts before registering a trap that writes a receipt.
for receipt in launcher-exit.json launcher-attempt.json rank0/attempt.json rank1/attempt.json; do
  if [[ -e "$out/$receipt" || -L "$out/$receipt" ]]; then
    printf 'Preserve the previous run; choose a fresh run name: %s\n' "$run" >&2
    exit 1
  fi
done
# Claim the launch atomically, including failures before torchrun creates rank attempts.
if ! (set -o noclobber; printf '{"pid":%d}\n' "$$" > "$out/launcher-attempt.json"); then
  printf 'Another launcher already claimed this run: %s\n' "$run" >&2
  exit 1
fi
record_exit() {
  local rc=$?
  trap - EXIT
  if ! (set -o noclobber; printf '{"exit_code":%d}\n' "$rc" > "$out/launcher-exit.json"); then
    printf 'Could not create exit receipt; existing records preserved: %s\n' "$run" >&2
    if [[ "$rc" == 0 ]]; then rc=1; fi
  fi
  exit "$rc"
}
trap record_exit EXIT
source outputs/b200-runtime-env.sh
export CUDA_VISIBLE_DEVICES=0,1
native=configs/environments/cc-native-step100/.venv/bin/python
"$native" scripts/b200/manage.py check-env native --expected-python 3.12.3
"$native" -m torch.distributed.run --standalone --nnodes=1 --nproc-per-node=2 \
  --max-restarts=0 --log-dir "outputs/$run/torchrun-logs" --redirects=3 -- \
  scripts/b200/train_ddp.py train --run "$run"
"$native" scripts/b200/train_ddp.py check --run "$run"
