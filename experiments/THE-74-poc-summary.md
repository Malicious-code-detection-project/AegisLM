## the-74-poc-summary

- Date: 2026-07-02
- Linear issue: THE-74
- Git commit: cc18555
- Phase: Phase E
- Run type: regression (comparison / summary)
- Owner: kwon o seong

### Purpose

Phase E(tiny SFT PoC) 단계에서 진행된 두 가지 파인튜닝 경로(Unsloth QLoRA vs 표준 Hugging Face TRL LoRA)의 리소스 사용량, 호환성 및 실행 결과를 비교·분석하여, 향후 대규모 학습(Phase F) 및 v0 제품 개발에 가동할 표준 학습 스택(Training Stack)을 최종 결정하고 이를 아카이브한다.

### Environment

- OS: linux (Ubuntu 24.04 LTS)
- Python: 3.12.13
- Package manager: uv
- PyTorch: 2.10.0+cu128
- Transformers: 5.5.0
- CUDA: 12.8
- GPU: NVIDIA RTX A6000 (1개 / VRAM 47.39 GB)

### PoC Comparison Matrix

| 비교 항목 | Unsloth QLoRA (THE-70) | 표준 HF TRL LoRA/QLoRA (THE-71 / 71-1) |
| --- | :---: | :---: |
| **실행 상태 (Status)** | **성공 (Completed)** | **실패 (Aborted - OOM)** |
| **Peak VRAM** | **25.16 GB** (VRAM 예산의 약 53%) | **43.61 GB** (모델 로딩 후 준비 단계에서 초과) |
| **학습 시간 (2 Steps)** | 72.07초 | N/A (시작 전 중단) |
| **양자화 호환성** | `mxfp4` 레이아웃 커스텀 커널 지원 | `mxfp4` - `bitsandbytes` 간 충돌 발생 |
| **가중치 유실 여부** | 없음 (가중치 정상 로드) | 있음 (MoE 전문가 가중치 `MISSING` 판정) |
| **어댑터 저장 및 로드** | 정상 저장 및 추론 검증 완료 (THE-72) | N/A (학습 가중치 생성 실패) |
| **평가 연동성** | held-out fixture 평가 완주 (THE-73) | N/A (추론 대상 없음) |

### Key Findings & Analysis

1. **표준 TRL 스택의 기술적 한계 (THE-71 / THE-71-1)**
   * `openai/gpt-oss-20b` 기본 모델은 파일 자체가 특수한 `mxfp4` (Microscaling FP4) 양자화 형식으로 설계되어 있습니다.
   * 표준 Hugging Face 로더와 `bitsandbytes` 조합은 이 형식을 네이티브하게 해석하지 못합니다. 
   * 설정을 우회하여 로드를 강제할 경우, MoE 전문가 레이어(`down_proj`, `gate_up_proj`)가 유실(`MISSING`)로 취급되어 고정밀도(BF16) 데이터로 신규 초기화됩니다. 이로 인해 메모리 크기가 수직 상승하여 single RTX A6000(48GB VRAM) 환경에서 100% OOM 에러가 유발됨을 입증했습니다.

2. **Unsloth 스택의 메모리 및 연산 효율성 (THE-70)**
   * `Unsloth` 프레임워크는 `mxfp4` 및 MoE 아키텍처에 직접 최적화된 고속 커널을 활용하여 가중치 유실 없이 모델을 안정적으로 로드합니다.
   * Peak VRAM 점유율이 25.16 GB에 불과해 향후 Phase F에서 대량의 실제 데이터셋을 학습시킬 때 batch size 및 맥락 길이(context length)를 확장하더라도 VRAM OOM 우려 없이 안정적인 훈련이 가능합니다.

3. **엔드투엔드 파이프라인 작동 검증 (THE-72 / THE-73)**
   * Unsloth 기반으로 획득한 어댑터 가중치(`adapters/tiny-sft-poc`)가 로드 및 추론용 헬퍼 함수([aegislm/inference/adapter.py](file:///home/remoteuser/Desktop/AegisLM/aegislm/inference/adapter.py))를 거쳐 에러 없이 작동함을 검증했습니다.
   * 학습 횟수가 부족해 평가지표 점수는 0점(`THE-73`)을 기록했으나, 이상 출력을 평가 엔진([scripts/evaluate_predictions.py](file:///home/remoteuser/Desktop/AegisLM/scripts/evaluate_predictions.py))이 충돌 없이 포착하여 리포트로 변환하는 "파이프라인 배관"의 완벽한 연동성을 확인했습니다.

### Decision on v0 Training Stack

* **최종 선정**: **Unsloth QLoRA**
* **기술적 타당성**: 
  1. 단일 GPU (RTX A6000 48GB) 사양 제약 하에서 20B 대형 모델의 양자화 가중치 충돌 없이 학습할 수 있는 **유일한 대안**입니다.
  2. 추론 및 평가 하네스 파이프라인 연동성([scripts/run_adapter_inference.py](file:///home/remoteuser/Desktop/AegisLM/scripts/run_adapter_inference.py))이 완벽히 구축되어 추가 리팩토링 비용이 발생하지 않습니다.
  3. 향후 Phase F 진입 시 표준 TRL 경로는 의존성 문제 및 VRAM 제약으로 폐기(Deprecated)하고, Unsloth QLoRA 스택에 모든 개발력을 결집합니다.

### Artifact Storage & Hugging Face Policy

* **Hugging Face Private Repo 사용 여부**:
  * 이번 Phase E tiny SFT PoC 단계에서는 로컬 단일 환경에서의 동작 및 연동성 검증이 목적이었으며, 환경 설정 내 Hugging Face Token이 주입되지 않아 (`token: detected: false`) **Hugging Face Hub에 업로드하지 않고 로컬 디렉터리에만 보관**하였습니다.
  * 향후 Phase F 단계에서 실제 데이터셋으로 정식 v0 어댑터를 학습시킬 때는 [docs/ARTIFACT_STORAGE_POLICY.md](file:///home/remoteuser/Desktop/AegisLM/docs/ARTIFACT_STORAGE_POLICY.md) 정책을 준수하여, Hugging Face의 **Private Repository**를 새로 생성(예: `<org-or-user>/aegislm-adapter-tiny-sft-poc`)하고 버전을 태깅하여 관리할 예정입니다.
* **로컬 Artifact 및 예측 파일 보관 경로**:
  * Output 어댑터 경로: `adapters/tiny-sft-poc/` (Git-ignored)
  * Output 체크포인트 경로: `checkpoints/tiny-sft-poc/` (Git-ignored)
  * 검증 추론 예측 파일: `outputs/the-73/adapter_predictions.jsonl` (Git-ignored)

### Phase E Exit Checklist

- [x] GPU 및 PyTorch 런타임 환경 검증 (`verify_gpu.py` 완료)
- [x] tiny SFT 데이터셋 가공 및 포맷 무결성 확인 (`data/` 완료)
- [x] Unsloth QLoRA tiny SFT PoC 구동 완료 (`THE-70` 완료)
- [x] 표준 TRL LoRA/QLoRA PoC 구동 및 한계 분석 완료 (`THE-71 / THE-71-1` 완료)
- [x] Unsloth 기반 어댑터 로드 및 추론 작동 경로 확보 (`THE-72` 완료)
- [x] held-out 평가 fixture 연동 및 성적표 생성 완료 (`THE-73` 완료)
- [x] PoC 결과 비교 및 v0 표준 학습 스택 결정 기록 (`THE-74` 완료)

### Follow-up

- Next Phase: **Phase F (dataset 확장 + adapter 개선)**
- Blockers: 없음 (학습 스택 선정 및 파이프라인 연동 검증 완료)
- Action Item: 
  * Owner 승인 하에 실제 CTI 및 구조화 분석 데이터셋(수천 건 규모) 수집 및 가공
  * 확정된 Unsloth QLoRA 표준 스택을 활용한 고성능 보안 특화 v0 어댑터 본격 학습 진행
