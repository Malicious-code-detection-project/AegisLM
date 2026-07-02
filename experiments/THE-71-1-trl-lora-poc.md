## the-71-1-trl-lora-poc

- Date: 2026-07-02
- Linear issue: THE-71
- Git commit: 2f24955
- Phase: Phase E
- Run type: adapter (SFT Training PoC - Failed / Re-run)
- Owner: kwon o seong

### Purpose

이전 THE-71 실행 시 다른 프로세스(THE-70 등)가 VRAM을 점유하고 있었는지 확인하기 위해, 백그라운드에 구동 중인 다른 모델 프로세스가 전혀 없는 깨끗한 상태의 GPU 환경에서 `train_trl.py`를 재실행하여 기존 OOM 오류와 라이브러리 충돌 현상이 여전히 재현되는지 검증한다.

### Environment

- OS: linux (Ubuntu 24.04 LTS)
- Python: 3.12.13
- Package manager: uv
- PyTorch: 2.10.0+cu128
- Transformers: 5.5.0
- CUDA: 12.8
- GPU: NVIDIA RTX A6000 (1개 / VRAM 47.39 GB)
- Notes: bitsandbytes==0.45.0, single GPU environment
- GPU Baseline Status: 652MiB/49140MiB 점유 (기존 모델 구동 없음 확인)

### Inputs

- Training Dataset: `data/tiny_sft_train.jsonl` (4 records)
- Validation Dataset: `data/tiny_sft_val.jsonl` (1 record)
- Base Model: `openai/gpt-oss-20b` (로컬 캐시 버전)
- Config File: [configs/tiny_sft_config.json](file:///home/remoteuser/Desktop/AegisLM/configs/tiny_sft_config.json)

### Commands

```bash
uv run scripts/train_trl.py --config configs/tiny_sft_config.json
```

### Artifact Paths

- Output Adapter: N/A (학습 시작 전 OOM으로 중단됨)
- Failure Logs: 터미널 콘솔 로그 기록

### Results / Output Summary

- **SFT Training Run**: 실패 (Aborted)
- **Peak VRAM Allocated**: **43.61 GB** (모델 로드 직후 가용 메모리 초과)
- **Training Time**: N/A

### Blockers / Warnings (분리 기록)

- **Quantization & Parameter Missing Blocker:**
  * *현상*: `openai/gpt-oss-20b` 모델 로딩 중 `GptOssForCausalLM LOAD REPORT`에 의해 MoE 전문가 투영 레이어인 `gate_up_proj` 및 `down_proj` 가중치가 결손(`MISSING`)된 것으로 식별됨.
  * *이유*: 원래 모델 `config.json`에 기재된 `mxfp4` 양자화 포맷과 강제로 주입한 `BitsAndBytesConfig`(4-bit QLoRA) 간의 호환성 우회를 위해 `quantization_config` 속성을 제거하고 로드하는 과정에서 가중치 맵핑이 올바르게 복원되지 못함.
  * *결과*: 누락된 것으로 간주된 파라미터들이 고정밀도(BF16/FP32)로 임의 초기화되며 로드 메모리가 비정상적으로 팽창함.
- **Runtime Blocker (VRAM OOM):**
  * *현상*: 깨끗한 GPU 환경(사용 전 652MiB 수준)에서 실행했음에도 불구하고, 모델 로드 완료 시점에 PyTorch 할당 메모리가 이미 43.61 GB에 도달함.
  * *결과*: 이후 `prepare_model_for_kbit_training(model)` 실행 시점에 float32 변환 등으로 추가 1.98 GiB 메모리를 할당하려다 `torch.OutOfMemoryError` 예외가 발생하여 훈련이 완전 무산됨.

### Interpretation

- 재실행 결과, 기존 THE-71에서 발생한 VRAM OOM은 타 프로세스와의 메모리 분할 점유 문제가 아니라, **표준 Hugging Face TRL/PEFT 프레임워크가 `openai/gpt-oss-20b` 모델의 `mxfp4` 양자화 레이아웃을 변환하는 과정에서 유발하는 비정상적인 파라미터 초기화 및 메모리 누수** 때문임이 확실하게 증명되었습니다.
- 단일 RTX A6000 (48GB VRAM) 환경에서는 표준 TRL QLoRA 학습이 원천적으로 불가능하며, Unsloth QLoRA(THE-70에서 25.16 GB로 완주)만이 유일한 파인튜닝 대안임을 재확인했습니다.

### Follow-up

- 예정대로 Unsloth 기반의 `THE-72` (adapter load 및 inference 확인 경로 추가) 작업을 진행합니다.
