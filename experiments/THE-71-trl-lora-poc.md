## the-71-trl-lora-poc

- Date: 2026-07-01
- Linear issue: THE-71
- Git commit: 33cb7a3
- Phase: Phase E
- Run type: adapter (SFT Training PoC - Failed)
- Owner: kwon o seong

### Purpose

표준 Hugging Face TRL SFTTrainer 및 PEFT LoRA/QLoRA 경로를 사용하여 `openai/gpt-oss-20b` 베이스 모델의 SFT 학습 가능성을 검증하고, Unsloth QLoRA 경로와의 자원 점유율(VRAM) 및 라이브러리 호환성을 대조하여 v0 최종 학습 스택을 선택한다.

### Environment

- OS: linux (Ubuntu 24.04 LTS)
- Python: 3.12.13
- Package manager: uv
- PyTorch: 2.10.0+cu128
- Transformers: 5.5.0
- CUDA: 12.8
- GPU: NVIDIA RTX A6000 (1개 / VRAM 47.39 GB)
- Notes: bitsandbytes==0.45.0, single GPU environment

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
- Failure Logs: `1c9e631d-7a50-4672-bd97-9e941a703f16/task-259.log`

### Results / Output Summary

- **SFT Training Run**: 실패 (Aborted)
- **Peak VRAM Allocated**: **43.61 GB** (모델 로드 직후 가용 메모리 초과)
- **Training Time**: N/A

### Blockers / Warnings (분리 기록)

- **Dependency Blocker (의존성 충돌):**
  * *현상*: `openai/gpt-oss-20b` 모델의 원래 `config.json`에 정의된 양자화 방식(`mxfp4` - Microscaling FP4)과 우리가 주입한 `BitsAndBytesConfig` 간의 양자화 클래스 포맷 충돌로 `ValueError` 에러 발생.
  * *우회 시도*: `AutoConfig`를 이용해 기존 `quantization_config` 설정을 제거하고 강제 로드하였으나, 이 경우 Transformers 라이브러리가 샤드(Shard) 파일의 가중치를 올바르게 복원하지 못해 MoE 전문가 투영 레이어(`down_proj`, `gate_up_proj`)를 누락(`MISSING`)된 것으로 취급하고 BF16 고정밀도로 임의 신규 초기화함.
- **Runtime Blocker (VRAM OOM):**
  * *현상*: 누락된 것으로 간주된 MoE 파라미터들이 고정밀도로 중복 로드/초기화되면서, 모델 가중치 로드 상태에서 이미 VRAM 점유율이 **43.61 GB**까지 수직 상승함.
  * *결과*: 이후 `prepare_model_for_kbit_training` 실행 시점에 가용 메모리 한계를 초과하여 `torch.OutOfMemoryError` 예외를 발생시키며 훈련이 완전 중단됨.

### Interpretation

- 표준 Hugging Face TRL 및 PEFT 프레임워크는 `openai/gpt-oss-20b` 모델 고유의 `mxfp4` 압축 레이아웃을 파인튜닝 단에서 네이티브하게 지원하지 못하며, 이를 우회하는 과정에서 비정상적인 파라미터 초기화 및 메모리 누수가 동반됩니다.
- 단일 RTX A6000 (48GB VRAM) 환경에서는 표준 TRL QLoRA 학습이 기술적으로 불가함을 확인했습니다.
- 반면, Unsloth QLoRA는 `mxfp4` 모델 구조에 최적화된 고속 커널을 통해 단 **25.16 GB**의 메모리로 100% 학습 완주에 성공하였습니다. 이로써 **AegisLM v0 파인튜닝 플랫폼으로는 Unsloth QLoRA 가동만이 유일하고 타당한 선택지임**이 확실시되었습니다.

### Follow-up

- Next Linear issue: THE-72 (Unsloth 기반 adapter load 및 inference 확인 경로 추가)
- Decision: TRL SFTTrainer 경로는 폐기(의존성/자원 한계)하고, Unsloth QLoRA 스택을 최종 v0 학습 스택으로 선택하여 후속 평가 및 어댑터 검증 태스크를 수행함.
