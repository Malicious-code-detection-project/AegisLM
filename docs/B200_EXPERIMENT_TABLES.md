# B200 실험표 — GPT-OSS-20B, 두 GPU DDP

기록일: 2026-10-07 (Asia/Seoul).
이 표는 B200의 실제 runtime·rank별 training receipt·저장 검증·평가 준비 artifacts에서 작성했다.
[A6000 표](A6000_EXPERIMENT_TABLES.md)는 보존된 원 실행의 별도 표다.
실행 방법과 후보 프레임워크 문서는 [B200 재현 레시피](B200_REPRODUCTION_RECIPE.md)에 둔다.

여기서 환경별 구조는 학습 실행 구성·분산·메모리 관리의 차이를 뜻한다.
GPT-OSS 기본 아키텍처나 LoRA 대상 레이어를 새로 바꾼 실험은 아니다.
별도 단일 GPU 100-step 학습은 생략했다.

## 1. B200 환경과 도구 구성

| 항목 | B200 실제 환경 |
| --- | --- |
| GPU | NVIDIA B200 2장, 각183,359 MiB, CUDA capability10.0 |
| 드라이버 | 580.95.05 (이번 재조회) |
| Python | 외부 관리 서버의3.12.3; A6000의3.12.13과 차이 승인·기록 |
| PyTorch / CUDA wheel | 2.14.1+cu130 / CUDA13.0 |
| Transformers / TRL / PEFT | 4.56.2 / 0.22.2 / 0.21.2 |
| Unsloth / Zoo | 2026.9.14 / 2026.9.9 |
| Accelerate / bitsandbytes / Triton / torchao | 1.15.0 / 0.50.2 / 3.8.0 / 0.18.0 |
| Harmony scorer | 별도 CPU 환경, Python3.12.3 / openai-harmony0.0.8 |
| 패키지 대조 | native113개·scorer11개 버전 및 해당 Git provenance를 원 기록과 대조 |
| 분산 | torchrun, 한 노드·두 rank, PyTorch DDP, NCCL |
| 장치 배치 | rank0→GPU0, rank1→GPU1; GPU마다 모델 복제본 |
| 저장 책임 | 최종 adapter·공용 결과는 rank0, 실행 상태·로그는 rank별 |
| 자동 재시도 | torchrun max-restarts=0; 실패 run을 보존하고 새 ID 사용 |
| 원본 저장 경계 | model/data/outputs/artifact 및 장비별 설정은 Git 제외 |

| 구성요소 | 이번 실행에서 맡는 역할 |
| --- | --- |
| Transformers·tokenizer | GPT-OSS 모델 구조와 날짜를 고정한 chat template |
| Unsloth / bitsandbytes | 모델 로딩·지원되는 계산 패치 / NF4 4bit 가중치 |
| PEFT / Unsloth get_peft_model | 같은 LoRA 대상·크기와 학습 파라미터 준비 |
| TRL SFTTrainer | 학습·logging·optimizer/scheduler 진행 |
| Unsloth train_on_responses_only | assistant final 위치만 supervised labels로 유지 |
| Accelerate / PyTorch DDP | Trainer의 분산 실행 연결·gradient 동기화 |

Unsloth는 Trainer·모델 계산도 패치할 수 있으므로 표는 주 역할을 설명하며 완전히 독립된 경계를 뜻하지 않는다.
두 GPU DDP는 두 장의 VRAM을 하나의 모델 저장 공간으로 합치는 방식이 아니다.

## 2. 실제 100-step 학습 조건

| 조건 | B200 `b200-ddp2-step100-v3` |
| --- | --- |
| base / revision | `unsloth/gpt-oss-20b-unsloth-bnb-4bit` / `093fba6992ef5a7152481afec0bdfca1ac486998` |
| 양자화 | NF4·double quantization·BF16 compute; verified offline snapshot |
| 데이터 | 동결 v5 train10,000 / validation1,000; test500 미사용 |
| token/mask 검사 | 원 A6000의10,000건 감사와 일치; 유효8,525·제외1,475·partial15 |
| 입력 길이 / 날짜 / seed | 1024 / 2026-10-04 / 3407 |
| GPU당 batch / accumulation | 1 / 2 |
| 전체 batch / steps | 1×GPU2×accum2=4 / optimizer100회 |
| 계획 표본 제시 수 / 입력 token 상한 | 400 / 409,600 |
| LoRA | r8, alpha16, dropout0, bias=none, q/k/v/o/gate/up/down 대상 유지 |
| trainable parameters / tensors | 92,454,912 / 3,264 |
| optimizer / LR / scheduler | adamw_8bit / 2e-4 / linear |
| warmup / weight decay | 5 optimizer steps / 0.001 |
| loss target | 원 공식 final-only mask, assistant JSON+빈 thinking |
| activation checkpointing | **해제**; 설치된 Unsloth reentrant 방식과 sparse MoE DDP 감지의 충돌 회피 |
| ddp_find_unused_parameters | **True**; 입력에 따라 사용되지 않는 expert의 gradient 처리 |
| compiler override | 없음; activation checkpointing 해제와 컴파일 비활성화를 구분 |
| validation / W&B / 외부 timeout | 학습 중 비활성 / report_to=none / 원 실행처럼 추가하지 않음 |

A6000과 달라진 실행 변수는 GPU·드라이버, Python 패치, DDP sampler/reduction,
accumulation4→2, rank별 장치·저장 처리, activation checkpointing이다.
전체 batch는4로 유지했다. 속도 차이를 GPU만의 효과로 해석하거나 두 adapter SHA가 같아야 한다고 요구하지 않는다.

## 3. 실행 이력 — 실패도 별도 보존

| run | optimizer step | 결과 | 원인 / 다음 변경 |
| --- | ---: | --- | --- |
| `b200-step100-v1` | 미실행 | 데이터·환경 준비만 완료 | 단일 GPU 본 학습을 생략 |
| `b200-ddp2-step100-v1` | 0 | 런처 단계 실패 | torchrun이 --run을 자신의 옵션으로 해석; 명령 구분자 -- 검증 후 새 run |
| `b200-ddp2-step100-v2` | 1 | DDP reduction 실패 | sparse MoE unused parameter; checkpointing 해제·unused 감지 활성화 후 새 run |
| `b200-ddp2-step100-v3` | 100 | **학습·저장·검증 완료** | 두 rank 동기화·저장 가중치 일치 확인 |

실패한 v1/v2의 결과를 v3와 합산하지 않는다. v3 학습에 사용된 소스는
`source-identity.json`의 SHA 및 `executed-source/` 복사본으로 보존했다.
후속 init/default 경로 보완은 그 실행에 사용된 코드라고 소급 기록하지 않는다.

## 4. 두 rank의 학습 결과

| 지표 | rank0 / GPU0 | rank1 / GPU1 |
| --- | ---: | ---: |
| 완료 optimizer steps | 100 | 100 |
| 평균 train loss | 0.12981680523604155 | 0.12981680523604155 |
| 마지막 step loss | 0.0814 | 0.0814 |
| Trainer train runtime (초) | 277.8209 | 275.9026 |
| epoch | 0.04691531785127844 | 0.04691531785127844 |
| 변경 tensor / 전체 trainable tensor | 3,176 / 3,264 | 3,176 / 3,264 |
| peak PyTorch allocated (bytes) | 27,308,960,256 | 26,804,643,328 |
| peak PyTorch reserved (bytes) | 28,177,334,272 | 28,020,047,872 |
| source / effective records | 10,000 / 8,525 | 10,000 / 8,525 |

Trainer runtime은 전체 설치·다운로드·준비·런처 시간을 뜻하지 않는다.
두 rank의 시간을 더해 wall time으로 보고하지 않는다.
PyTorch allocated/reserved와 nvidia-smi의 장치 전체 메모리 값도 구분한다.

| B200 100-step 구간 (두 rank 동일) | 평균 logged train loss | 마지막 loss | 마지막 logged LR |
| --- | ---: | ---: | ---: |
| 1–25 | 0.265464 | 0.1081 | 0.00016000 |
| 26–50 | 0.086096 | 0.0499 | 0.00010737 |
| 51–75 | 0.087908 | 0.0706 | 0.00005474 |
| 76–100 | 0.079804 | 0.0814 | 0.00000211 |

| 검증 | 실제 결과 |
| --- | --- |
| rank별 장치 / NCCL 합산 | GPU0/1 배치·world_size2 확인, 합산3.0 |
| 입력·마스크 / 초기 LoRA hash | 두 rank 일치 |
| 최종 LoRA hash | 두 rank 완전 일치 |
| 실제 파라미터 변경 | 두 rank 모두3,176 tensor 변경 |
| 저장된 adapter | 모든3,264 key·tensor가 학습 직후 PEFT state와 일치 |
| launcher 종료 코드 | 0 |
| 종료 직후 GPU 메모리 | 두 장 모두0 MiB 관측 |
| 관련 CPU 회귀 검사 | 28개 통과 |

최종 adapter SHA256: `34b298f580d1bcdd36981172b334246d10ce40a09658995ef5841d38018ee348`.
학습 완료는 탐지 성능 개선을 뜻하지 않는다. 아래 생성 평가가 아직 미실행이다.

## 5. base·adapter 자유 생성 평가표 — 준비 완료, 생성 미실행

평가 ID는 `b200-ddp2-step100-v3-{base,adapter}-validation100`이다.
같은 validation100(양성50·음성50), 입력232–980토큰, 여섯 데이터 해시·새 adapter SHA 대조와
초기 Harmony scorer 실행을 완료했다. 각 모델600회, 총1,200회 계획이다.
실제 GPU 생성 worker는 아직 실행하지 않았고 raw 결과 파일은 두 arm 모두0개다.

| 모델 | 생성 상한 | 완료/계획 | pending | TP / FN / FP / TN | uncertain / invalid | 상태 |
| --- | --- | ---: | ---: | --- | --- | --- |
| base | 128 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| base | 512 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| base | 2048 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| base | 65536 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| base | 130000 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| base | context-minus-input | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | 128 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | 512 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | 2048 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | 65536 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | 130000 | 0/100 | 100 | — | — | 준비 완료·미실행 |
| adapter | context-minus-input | 0/100 | 100 | — | — | 준비 완료·미실행 |

`—`는 평가 미실행이며 성능0%를 뜻하지 않는다. 초기 scorer JSON의0 행렬도 예측 결과가 아니다.
추후 strict·semantic 행렬을 각각 기록하고 uncertain·invalid·pending을 분리한다.
context-minus-input은 각 입력별 `131072-input_tokens`이다.
native sampling·medium reasoning·native EOS·fresh-process-per-model-budget-v2를 유지하고
gold/final-prefill·추가 generate kwargs·외부 timeout은 추가하지 않는다.
이 문서 갱신에서는 학습이나 생성 평가를 새로 실행하지 않았다.

## 6. 근거 위치와 상태를 읽는 기준

| 근거 | 프로젝트 내 위치 |
| --- | --- |
| 학습 조건 / 실행 source SHA | `outputs/b200-ddp2-step100-v3/config.json`, `source-identity.json`, `executed-source/` |
| 실행 상태·수치 | 같은 run의 `training-runtime.json`, `training.json`, `rank{0,1}/runtime.json`, `training.json`, `progress.json` |
| 저장·완료 검증 | 같은 run의 `adapter-save-verification.json`, `b200-verification.json`, `launcher-exit.json` |
| 환경 대조 | `outputs/b200-{native,score}-environment.json`, `b200-gpu-preflight.json` |
| 평가 준비 | 각 평가 run의 `prepared.json`, `confusion-matrices.json`; 학습 run의 `evaluation-preparation-summary.json` |
| 평가 실행용 config | `configs/b200-ddp2-step100-v3-{base,adapter}-validation100.json` |

Unsloth Git: `5971d280d4b645c8d470d6bb3171b082c4d4d2b8`.
Zoo Git: `867a86383371ebeb8ab1948d085540d134c07b4c`.
실행 저장소 HEAD: `0e51218d936a665c2aa2ac32e2dc934ca0efb543`에 당시 uncommitted DDP 변경을 적용했다.
따라서 HEAD만으로 실행 코드를 재현할 수 없고 source-identity 및 보존한 소스를 함께 사용해야 한다.
실행 명령은 같은 run의 `launcher.json`에 보존된
`bash scripts/b200/run-ddp.sh b200-ddp2-step100-v3`이다.

training/config의 `status=prepared`는 초기화 당시 상태다. 완료 여부는 runtime·training·verification으로 읽는다.
그 config의 generation2건·5상한은 원 training config에서 상속된 과거 진단 설정이며
현재100건·6상한 평가는 위 별도 평가 config가 기준이다. 원 실행 artifacts는 이 문서 갱신에서 수정하지 않는다.

공유 표에는 개인 절대 경로·접속값·원본 메시지를 넣지 않는다.
LLaMA-Factory·Axolotl은 [레시피14절](B200_REPRODUCTION_RECIPE.md#14-llama-factoryaxolotl-후보-비교--문서-준비만)의 문서 조사만 수행했고 설치·실험하지 않았다.


### 2026-10-08: 공용 환경 파일의 GPU 선택 설명

`outputs/b200-runtime-env.sh`에는 보존된 단일 장치 기본값 `CUDA_VISIBLE_DEVICES=0`이 있다.
실제 학습 launcher `run-ddp.sh`는 source 직후 `0,1`로 덮어쓰고 두 rank를 실행한다.
v3의 rank0·rank1 완료 기록은 각각 `world_size=2`, `global_step=100`이다.
평가 launcher에는 기존 단일 장치 선택을 명시했다. GPU 없는 CPU 대역 검증에서
학습 자식 프로세스에는 `0,1`과 `--nproc-per-node=2`, 평가에는 `0`이 전달됨을 확인했다.
공용 환경 파일의 기존 변수 값과 완료된 실행 artifacts는 바꾸지 않았고 GPU 재실행은 하지 않았다.

## 7. 2026-10-08 Git 공유 준비

두 GPU 100-step 완료와 저장 검증 결과를 기존 산출물에서 다시 확인했다. 자유 생성 평가는 여전히 0/1,200회다.
학습 당시 `train_ddp.py` SHA256은 `cdd8c64aa3b32a70d3f0c29474672a33d82a61cb394b9d6ea1c071438c55491f`이며,
원 실행 소스와 `source-identity.json`은 해당 run의 Git 제외 위치에 보존한다.
공유 코드는 학습 후 초기화·실행 경로 보완과 이번 타입 표기·서식 정리를 포함하므로, 새 커밋을 원 학습의 실행 revision으로 소급 표시하지 않는다.

CPU 검증은 루트 manifest·lock의 개발 도구를 설치한 별도 비공개 환경에서 수행하고,
기존 native 환경의 라이브러리를 읽기 전용으로 참조했다. GPU는 검증 프로세스에 노출하지 않았다.
pytest 597개, Ruff lint·format, mypy, DDP 실행 셸 문법과 Git diff 공백 검사를 통과했다.
검증 로그는 `.private/b200-git-publish-20261008/`에 보존한다. 학습 환경과 기존 adapter·동결 데이터·평가 입력은 변경하지 않았다.
