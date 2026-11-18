# B200 480B FP8 Framework Matrix Experiments

This document defines the staged comparison process for Qwen3-Coder 480B FP8
smoke fine-tuning candidates. The current goal is not long training. The goal
is to compare framework load behavior and one-step smoke feasibility with the
same dataset, model path, and telemetry.

## Frameworks

| Tier | Framework | Purpose |
|---:|---|---|
| 0 | LLaMA-Factory | Baseline re-measurement of the current failing path |
| 1 | HF Transformers/TRL | Low-friction direct HF comparison |
| 1 | Axolotl | DeepSpeed/FSDP alternative |
| 1 | torchtune | PyTorch-native Qwen3/FSDP comparison |
| 2 | ms-swift Megatron | Large-model-native Megatron path |
| 2 | NVIDIA NeMo | NVIDIA Qwen3 LoRA/import recipe candidate |
| 3 | Unsloth | Load/inference comparison only unless training path is proven |

## Run Order

1. Export framework datasets from the common AegisLM JSONL input.
2. Run framework `env_check` for all candidates.
3. Run load-only probes under memory telemetry for candidates whose env check passes.
4. Run 1-step smoke only for candidates that pass load-only.
5. Choose a long-run framework only after the result table is complete.

## Commands

Matrix summary:

```bash
.venv/bin/python scripts/run_framework_matrix.py --phase summary
```

Safe env check:

```bash
.venv/bin/python scripts/run_framework_matrix.py --phase env_check
```

Dataset export for all framework formats, limited to smoke validation by default:

```bash
.venv/bin/python scripts/export_framework_datasets.py \
  --input data/processed/aegislm_security_train.jsonl \
  --ignore-errors \
  --max-records 100
```

Omit `--max-records` only when intentionally preparing a full framework export.

Heavy phases are skipped unless explicitly allowed:

```bash
.venv/bin/python scripts/run_framework_matrix.py \
  --framework llamafactory \
  --phase load_only \
  --dry-run
```

Actual load-only probes must be run with framework-specific env/container ready
and with telemetry enabled. Do not start long training from this matrix.

## Required Telemetry

Each load/smoke run must preserve:

- framework, experiment id, model variant, phase, nproc
- cgroup current/peak/max and `memory.events`
- `cpu.stat`, `cpu.pressure`, `memory.pressure`
- `pids.current`, `pids.max`, `pids.events`
- rank/process RSS, VSZ, CPU percent, and thread count
- GPU memory and utilization
- checkpoint loading progress and success/failure time

The 4 observed PIDs in previous runs are distributed ranks, not CPU cores.
Increasing rank/PID count is not equivalent to adding CPU capacity and may
increase checkpoint-loading RSS if weights are duplicated per rank.
