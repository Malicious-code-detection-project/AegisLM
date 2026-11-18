# DeepSpeed ZeRO-3 Dtype Mismatch Troubleshooting

## Summary

2026-07-03 기준 30B/72B smoke run은 model loading과 첫 forward/backward에 진입한 뒤 첫 optimizer step에서 실패했다. 480B의 checkpoint loading SIGKILL과는 다른 문제로 분리한다.

관측된 핵심 오류는 다음이다.

```text
TypeError: output tensor must have the same type as input tensor
```

traceback은 DeepSpeed ZeRO-3의 `_post_step` 안에서 `persistent_parameters`를 all-gather하는 경로로 들어간다.

```text
deepspeed/runtime/zero/stage3.py _post_step
self.persistent_parameters[0].all_gather(self.persistent_parameters)
deepspeed/runtime/zero/partition_parameters.py _allgather_params_coalesced
torch.distributed.distributed_c10d.py all_gather_into_tensor
```

## Current Evidence

확인된 서버 상태:

```text
deepspeed 0.19.2
torch 2.12.1+cu130
transformers 5.6.0
accelerate 1.11.0
peft 0.18.1
```

설치된 DeepSpeed 0.19.2의 `_allgather_params_coalesced`는 all-gather output buffer를 만들 때 모든 parameter에 대해 첫 번째 parameter dtype을 사용한다.

```python
flat_tensor = torch.empty(tensor_size, dtype=param_list[0].ds_tensor.dtype, device=self.local_device)
```

DeepSpeed upstream PR #8073은 이 동작이 mixed dtype persistent parameters에서 깨진다고 설명하며, 각 parameter의 dtype을 사용하도록 수정했다.

## Interpretation

확인된 사실:

- 30B/72B는 cgroup OOM kill 없이 training loop에 진입했다.
- 두 run 모두 첫 optimizer step에서 동일한 ZeRO-3 all-gather dtype mismatch로 실패했다.
- 현재 설치된 DeepSpeed는 upstream에서 수정된 bug pattern과 같은 구현을 갖고 있다.

추정:

- bf16 base model parameter와 PEFT LoRA adapter parameter가 ZeRO-3 persistent parameter group 안에서 mixed dtype이 되었을 가능성이 높다.
- 30B/72B는 memory budget보다 DeepSpeed 0.19.2 ZeRO-3 + PEFT LoRA + bf16 조합 문제가 먼저 막고 있다.

## Implemented Diagnostic Path

의존성 변경 없이 먼저 ZeRO-2 smoke baseline을 추가했다.

- DeepSpeed config: `configs/deepspeed/ds_z2_bf16_b200.json`
- 30B config: `configs/llamafactory/b200/qwen3_coder_30b_lora_smoke_z2.yaml`
- 72B config: `configs/llamafactory/b200/qwen2_72b_lora_smoke_z2.yaml`
- 30B runner: `scripts/run_smoke_qwen3_coder_30b_z2.sh`
- 72B runner: `scripts/run_smoke_qwen2_72b_z2.sh`

Run order:

```bash
bash scripts/run_smoke_qwen3_coder_30b_z2.sh
bash scripts/run_smoke_qwen2_72b_z2.sh
```

## Decision Rules

- ZeRO-2 30B가 통과하면 dataset, W&B, LLaMA-Factory, PEFT 기본 경로는 정상으로 본다.
- ZeRO-2 72B도 통과하면 작은 모델 계열의 실패 원인은 ZeRO-3 dtype bug로 강하게 판정한다.
- ZeRO-2에서도 같은 dtype 오류가 나면 LLaMA-Factory/PEFT adapter dtype 생성 경로를 추가 조사한다.
- ZeRO-2에서 memory 문제가 나면 batch/cutoff/offload를 먼저 낮춘다.
- 480B는 별도 checkpoint loading/SIGKILL 문제로 유지하고, 30B/72B baseline이 통과한 뒤 다시 다룬다.

## ZeRO-3 Fix Candidates

1. DeepSpeed upstream PR #8073 패치 적용
2. DeepSpeed 0.19.1 downgrade
3. DeepSpeed master 또는 수정 릴리스 upgrade
4. LLaMA-Factory/PEFT adapter dtype 우회

v1에서는 dependency를 바꾸지 않고 ZeRO-2 diagnostic만 추가한다.

## References

- DeepSpeed issue #8072: https://github.com/deepspeedai/DeepSpeed/issues/8072
- DeepSpeed PR #8073: https://github.com/deepspeedai/DeepSpeed/pull/8073
- Hugging Face forum traceback: https://discuss.huggingface.co/t/output-tensor-must-have-the-same-type-as-input-tensor/90729
- ms-swift similar issue: https://github.com/modelscope/ms-swift/issues/3235

## 2026-07-03 ZeRO-2 Smoke Results

두 diagnostic smoke run 모두 성공했다.

| Model | Result | Memory watcher | cgroup current max | oom_kill | Adapter output |
| --- | --- | --- | --- | --- | --- |
| Qwen3-Coder-30B-A3B | Passed | `model/runs/memory/memory_watch_20260703_004754.jsonl` | 280.25 GiB | 6 -> 6 | `model/adapters/qwen3-coder-30b/lora/smoke-z2` |
| Qwen2-72B | Passed | `model/runs/memory/memory_watch_20260703_005217.jsonl` | 668.11 GiB | 6 -> 6 | `model/adapters/qwen2-72b/lora/smoke-z2` |

Observed outcome:

- Both runs reached the first optimizer step and completed `max_steps: 1`.
- W&B online runs were created for both smoke runs.
- Adapter files and `checkpoint-1` were created for both runs.
- No new cgroup `oom_kill` event was observed during either run.

Interpretation:

- The dataset, W&B, LLaMA-Factory SFT path, and PEFT LoRA save path are working for 30B/72B when ZeRO-2 is used.
- The previous 30B/72B failure is now strongly isolated to the ZeRO-3 optimizer/all-gather path.
- The next ZeRO-3-specific fix should compare DeepSpeed PR #8073 patch, DeepSpeed downgrade/upgrade, or adapter dtype handling.

Telemetry caveat:

- The watcher recorded cgroup memory correctly, but the summarized GPU/process fields for these two runs were zero in the parsed records. Treat cgroup current and `oom_kill` as the reliable fields for this diagnostic result, and improve GPU/process parsing before using those columns for performance analysis.
