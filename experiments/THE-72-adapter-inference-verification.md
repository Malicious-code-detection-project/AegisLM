## the-72-adapter-inference-verification

- Date: 2026-07-02
- Linear issue: THE-72
- Git commit: 2f24955
- Phase: Phase E
- Run type: smoke / verification
- Owner: kwon o seong

### Purpose

Unsloth 기반으로 SFT 학습된 어댑터 가중치(`adapters/tiny-sft-poc`)를 성공적으로 로드하고, 검증용 데이터셋([data/tiny_sft_val.jsonl](file:///home/remoteuser/Desktop/AegisLM/data/tiny_sft_val.jsonl))에 대해 실제 추론(inference)을 정상적으로 수행하여 결과 JSONL을 출력하는 파이프라인(검증 경로)의 안정성을 검증한다.

### Environment

- OS: linux (Ubuntu 24.04 LTS)
- Python: 3.12.13
- Package manager: uv
- PyTorch: 2.10.0+cu128
- Transformers: 5.5.0
- CUDA: 12.8
- GPU: NVIDIA RTX A6000 (1개 / VRAM 47.39 GB)
- Notes: bitsandbytes==0.45.0, unsloth==2026.6.9, single GPU environment

### Inputs

- Dataset path: [data/tiny_sft_val.jsonl](file:///home/remoteuser/Desktop/AegisLM/data/tiny_sft_val.jsonl) (1 record)
- Dataset split: validation
- Dataset version/provenance: Phase C tiny validation set
- Model id: `openai/gpt-oss-20b` (베이스 모델)
- Adapter path: `adapters/tiny-sft-poc` (Unsloth PoC 학습 산출물)
- Prompt contract: `aegislm.prompts.format_baseline_prompt`

### Commands

```bash
uv run scripts/run_adapter_inference.py \
  --dataset data/tiny_sft_val.jsonl \
  --predictions outputs/tiny_sft_val_predictions.jsonl \
  --adapter-path adapters/tiny-sft-poc \
  --run-id verify-adapter-poc \
  --backend unsloth
```

### Artifact Paths

- Prediction JSONL: [outputs/tiny_sft_val_predictions.jsonl](file:///home/remoteuser/Desktop/AegisLM/outputs/tiny_sft_val_predictions.jsonl) (Git-ignored)
- Failure Logs: N/A (성공 완주)

### Results / Output Summary

- **Status**: 성공 (Completed)
- **Processed records**: 1
- **Latency**: 123.56 seconds (첫 기동 시의 모델 로드 및 Triton JIT 커널 컴파일 시간 포함)
- **Output sample check**: `outputs/tiny_sft_val_predictions.jsonl`에 정상적인 JSON 규격 문자열로 어댑터 추론 텍스트가 저장됨.

### Interpretation

- Unsloth FastLanguageModel 로더와 [scripts/run_adapter_inference.py](file:///home/remoteuser/Desktop/AegisLM/scripts/run_adapter_inference.py)를 연동하여 어댑터 가중치 병합 및 4-bit 로딩 과정이 에러 없이 원활하게 구동됨을 입증했습니다.
- 앞서 `THE-71` 표준 TRL 경로에서 겪었던 VRAM OOM 현상 없이, 48GB VRAM RTX A6000 자원 하에서 어댑터 기반 추론 파이프라인이 기술적으로 완전히 동작(검증 경로 확보)함을 확인했습니다.

### Follow-up

- Next Linear issue: THE-73 (held-out fixture로 adapter 평가)
- Blockers: None
- Decision: 이 검증 경로를 활용해 후속 태스크인 held-out fixture에 대한 adapter 정량 평가(`THE-73`)를 착수함.
