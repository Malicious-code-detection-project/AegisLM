## the-66-gpu-verification

- Date: 2026-06-28
- Linear issue: THE-66
- Git commit: fd9f8e7
- Phase: Phase E
- Run type: smoke
- Owner: jeongminllee

### Purpose

Phase E SFT PoC를 시작하기 전, 단일 공유 GPU 작업용 PC의 하드웨어(RTX A6000), CUDA, PyTorch 연산 및 핵심 SFT 라이브러리(unsloth, transformers, peft, trl)의 버전 호환성과 Git Ignore 격리 상태를 총체적으로 검증한다.

### Environment

- OS: linux (Ubuntu 24.04 LTS)
- Python: 3.12.13
- Package manager: uv
- PyTorch: 2.10.0+cu128
- Transformers: 5.5.0
- CUDA: 12.8
- GPU: NVIDIA RTX A6000 (1개 / VRAM 47.39 GB)
- Notes: unsloth==2026.6.9, CUDA 12.8 runtime, single GPU environment

### Inputs

- Verification Script: `scripts/verify_gpu.py`
- Configuration File: `.gitignore`, `pyproject.toml`

### Commands

```bash
uv run scripts/verify_gpu.py
```

### Artifact Paths

- Diagnostic report JSON: `experiments/env_check_report.json`

### Results / Output Summary

- **GPU Tensor Operation**: [PASS] GPU tensor multiplication successful!
- **Git Ignore Security**: 
  - `.env`, `.env.local`, `checkpoints/`, `adapters/`, `models/`, `unsloth_compiled_cache/`, `experiments/env_check_report.json` 모두 정상적으로 `ignored` 검증 성공 (`[PASS]`).
- **Dependencies Version Summary**:
  - python          : 3.12.13
  - uv              : 0.11.14
  - pytorch         : 2.10.0+cu128
  - cuda            : 12.8
  - unsloth         : 2026.6.9
  - transformers    : 5.5.0
  - datasets        : 4.3.0
  - peft            : 0.19.1
  - trl             : 0.24.0

### Blockers / Warnings

- **Hugging Face Token**:
  - `[WARN] No HF token found` 경고 감지.
  - *조치 계획*: Gated model 로드가 발생하는 69번~70번 이슈(실제 SFT PoC) 착수 전에 `huggingface-cli login` 또는 `HF_TOKEN` 환경 변수를 세팅하여 해결할 예정.

### Interpretation

- RTX A6000 GPU의 CUDA 하드웨어 연산과 설치된 PyTorch, Unsloth, Transformers 등의 버전 정합성이 에러 없이 완전히 충족함을 확인했습니다. 
- Git Ignore 또한 정상적으로 작동하고 있어, 보안 유출 위협이 차단되었습니다.

### Follow-up

- Next Linear issue: THE-67
- Blockers: None (HF Token Warning은 실제 학습 개시 전 로그인하여 해결 가능)
- Decision: start tiny SFT PoC path and prepare the dataset.
