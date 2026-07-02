## the-70-unsloth-qlora-poc

- Date: 2026-07-01
- Linear issue: THE-70
- Git commit: bd1327c
- Phase: Phase E
- Run type: adapter (SFT Training PoC)
- Owner: kwon o seong

### Purpose

Unsloth QLoRA를 사용하여 `openai/gpt-oss-20b` 베이스 모델의 초소형 파인튜닝(SFT) PoC 학습 루프를 직접 수행하고, 이 과정에서의 리소스 소모량(VRAM), 소요 시간, 의존성 호환성 및 어댑터 가중치 저장 결과를 검증하여 일지에 기록한다.

### Environment

- OS: linux (Ubuntu 24.04 LTS)
- Python: 3.12.13
- Package manager: uv
- PyTorch: 2.10.0+cu128
- Transformers: 5.5.0
- CUDA: 12.8
- GPU: NVIDIA RTX A6000 (1개 / VRAM 47.39 GB)
- Notes: unsloth==2026.6.9, single GPU environment

### Inputs

- Training Dataset: `data/tiny_sft_train.jsonl` (4 records, `split: "train"` 변환)
- Validation Dataset: `data/tiny_sft_val.jsonl` (1 record, `split: "validation"` 변환)
- Dataset version/provenance: [tests/fixtures/tiny_phase_c_records.jsonl](file:///home/remoteuser/Desktop/AegisLM/tests/fixtures/tiny_phase_c_records.jsonl)에서 추출 및 재가공
- Config File: [configs/tiny_sft_config.json](file:///home/remoteuser/Desktop/AegisLM/configs/tiny_sft_config.json)
- Base Model: `openai/gpt-oss-20b` (로컬 캐시 완료)

### Commands

```bash
uv run scripts/train_unsloth.py --config configs/tiny_sft_config.json
```

### Artifact Paths

- Output Adapter: `adapters/tiny-sft-poc/` (Git-ignored)
- Output Checkpoint: `checkpoints/tiny-sft-poc/` (Git-ignored)

### Results / Output Summary

- **Trainable Parameters**: 3,981,312 out of 20,918,738,496 (0.02% trained)
- **Training Epochs**: 1
- **Total steps**: 2 steps (Batch size = 2, Gradient accumulation = 1)
- **Training Loss**:
  - Step 1: 6.341
  - Step 2: 6.221
- **Elapsed Time**: 72.07 seconds
- **Peak VRAM Usage**: **25.16 GB** (RTX A6000 48GB 메모리 예산의 약 53%)
- **Adapter Saving**: `adapters/tiny-sft-poc` 폴더 아래 가중치(`adapter_model.safetensors`, `adapter_config.json`, `tokenizer_config.json` 등)가 정상 저장됨.

### Blockers / Warnings

- **Gradient Accumulation Warning**:
  * *현상*: 기존 설정의 `"gradient_accumulation_steps": 4`, `"batch_size": 2` 조합은 필요한 최소 샘플 수(8개)가 학습 데이터셋 수(4개)보다 많아 SFTTrainer 동작 시 에러를 유발할 수 있음.
  * *조치*: `scripts/train_unsloth.py` 스크립트 내부에서 데이터셋 크기가 배치 설정보다 작을 경우 `gradient_accumulation_steps`를 임시로 1로 낮춰 학습을 완주하도록 동적 예외 처리 로직 추가 적용.
- **Hugging Face Token Warning**:
  * *현상*: 환경 체크 시 `token: detected: false`가 기록되었으나, 학습 타겟인 `openai/gpt-oss-20b` 모델이 서버 내 캐시 디렉터리에 로컬 다운로드 완료 상태였기 때문에 토큰 인증 없이 정상 로드됨.

### Interpretation

- Unsloth QLoRA를 통한 20B 대형 모델의 4-bit 학습 연산이 단일 RTX A6000(48GB VRAM) 환경에서 매우 안정적으로 동작함을 입증했습니다. 
- 피크 메모리(25.16 GB)가 하드웨어 한계의 절반 수준에 머물러 있어 향후 실데이터셋 확장 시 배치 크기 및 맥락 길이를 확대하더라도 VRAM OOM 에러 없이 훈련이 가능함을 시사합니다.

### Follow-up

- Next Linear issue: THE-71 (TRL LoRA 또는 QLoRA 경로 검증)
- Blockers: None
- Decision: Proceed to the TRL-based PoC comparison.
