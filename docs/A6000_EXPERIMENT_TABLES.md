# A6000 실험표 — 공식 native v5 기준선

기록 검토일: 2026-10-07 (Asia/Seoul).
이 표는 [학습 계획·상세 이력](FINETUNING_EXPERIMENT_PLAN.md)에 보존된 A6000 기록과
`data/reproduction/b200-step100-v1/`의 동결 메타데이터를 정리한 조회용 표다.
이번 갱신에서 A6000에 접속하거나 학습·평가를 다시 실행하지 않았다.
GPU 실행 결과를 직접 읽은 [B200 실험표](B200_EXPERIMENT_TABLES.md)와 구분한다.

범위는 공식 튜토리얼에 v5 데이터를 연결한 native 30/100-step 계열이다.
이전 v7, compiler-off, final-prefill, 외부 600초 제한 실험은 기존 상세 이력에 보존하며
아래 표와 합산하지 않는다. 원천 라벨·CWE는 미검수이고 test500 본문은 이 재현에 사용하지 않았다.

## 1. 환경과 실행 구성

| 항목 | A6000 native 30/100-step |
| --- | --- |
| GPU | NVIDIA RTX A6000 1장, 49,140 MiB |
| 드라이버 | 595.84 (원 실행 기록) |
| Python | 3.12.13 |
| PyTorch / CUDA wheel | 2.14.1+cu130 / CUDA 13.0 |
| Transformers / TRL / PEFT | 4.56.2 / 0.22.2 / 0.21.2 |
| Unsloth / Zoo | 2026.9.14 / 2026.9.9 |
| Accelerate / bitsandbytes / Triton / torchao | 1.15.0 / 0.50.2 / 3.8.0 / 0.18.0 |
| 학습 경로 | Unsloth 모델 로딩·LoRA 패치 → TRL SFTTrainer → PyTorch 단일 GPU |
| 양자화 | Unsloth BnB 4bit snapshot; NF4·double quantization·BF16 compute |
| activation checkpointing | 원 튜토리얼의 Unsloth reentrant 방식 |
| compiler override | 없음 |
| GPU당 batch / accumulation / 전체 batch | 1 / 4 / 4 |
| 길이 / seed | 1,024 / 3407 |
| LoRA | r8, alpha16, dropout0, bias=none; q/k/v/o/gate/up/down 대상 |
| 학습 대상 | native linearized MoE의 24개 layer 전체; trainable 92,454,912개 |
| optimizer / LR / scheduler | adamw_8bit / 2e-4 / linear |
| warmup / weight decay | 5 optimizer steps / 0.001 |
| loss target | assistant final JSON+return; 빈 thinking, user/system은 loss에서 제외 |
| 학습 중 validation / W&B | 원 예제대로 eval_strategy=no / report_to=none |
| 데이터 | v5 train10,000 → 유효8,525, 제외1,475; 완전 target8,510, partial15 |

버전·모델 식별자:

- Unsloth Git: `5971d280d4b645c8d470d6bb3171b082c4d4d2b8`
- Zoo Git: `867a86383371ebeb8ab1948d085540d134c07b4c`
- 모델: `unsloth/gpt-oss-20b-unsloth-bnb-4bit`
- 모델 revision: `093fba6992ef5a7152481afec0bdfca1ac486998`
- 원 튜토리얼 commit: `92e38e86308748d18fc4cd4b104c4c6d3db1d67e`
- 원 튜토리얼 SHA256: `74ff47bb9212f482f7378d86f27bc088973e924ae427cc84891d87663131895a`
- train SHA256: `b2827d06416fc256811bd6b3b662ff143d0f52604891856620153b2a1ec3e83f`
- training-messages SHA256: `7749661d01f184d44b7fda143b5c89e6d33407d0122914cbf1d9fb2b94af6d64`

같은 모델 아키텍처·LoRA 대상으로 진행한 계열이다. 환경별 구분은 모델 구조 변경을 뜻하지 않는다.

## 2. 학습 결과 — 30-step과 100-step

| 지표 | A6000 30-step | A6000 100-step |
| --- | ---: | ---: |
| 완료 optimizer steps | 30 | 100 |
| 전체 batch | 4 | 4 |
| 계획 표본 제시 수 | 120 | 400 |
| 평균 train loss (원 요약 정밀도) | 0.230625 | 0.130558 |
| 마지막 step loss | 0.0996 | 0.0860 |
| Trainer train runtime (초) | 226.963 | 656.811 |
| epoch (원 요약 정밀도) | 0.01408 | 0.04692 |
| 변경 tensor / 전체 trainable tensor | 3,162 / 3,264 | 3,178 / 3,264 |
| trainable parameters | 92,454,912 | 92,454,912 |
| source / effective records | 10,000 / 8,525 | 10,000 / 8,525 |
| peak PyTorch reserved | 19.295 GiB | 19.295 GiB |
| 학습·adapter 저장 | 완료 | 완료 |

100-step은 유효8,525건 전체를 한 epoch 학습한 결과가 아니다. train loss를 validation loss로 읽지 않는다.

| A6000 100-step 구간 | 평균 logged train loss | 마지막 loss | 마지막 logged LR |
| --- | ---: | ---: | ---: |
| 1–25 | 0.264692 | 0.1021 | 0.00016000 |
| 26–50 | 0.088124 | 0.0593 | 0.00010737 |
| 51–75 | 0.088280 | 0.0704 | 0.00005474 |
| 76–100 | 0.081148 | 0.0860 | 0.00000211 |

실험 ID:

- 30-step: `cc-official-tutorial-v5-token-caps-20261004-v1`
- 100-step: `cc-official-tutorial-v5-max-steps-100-20261004-v1`
- 100-step adapter SHA256: `4f0280021be433758f7ee6e1fc8d09f22846286ab6967892bd0cdbae9691b4b9`
- 실행 코드의 저장소 commit은 이번 동결 training/config에 별도 포함되지 않았다. 원 튜토리얼 commit과 실제 실행 저장소 commit을 동일시하지 않는다.

## 3. 생성 진단 — 동일 validation 2건, 총20호출 완료

대상은 위 100-step 실험이다. 각 행은 같은 양성1·음성1건이며,
5개 상한을 반복한 호출 수를 독립된 10건 또는 validation100 정확도로 해석하지 않는다.
native sampling·medium reasoning·native EOS를 사용했고 외부 timeout과 final-prefill은 없다.

| 모델 | 상한 | 완료/계획 | strict schema 통과 | 원천 라벨 일치 | invalid / uncertain | EOS / token-limit |
| --- | --- | ---: | ---: | ---: | --- | --- |
| base | 128 | 2/2 | 0/2 | 0/2 | 2 / 0 | 0 / 2 |
| base | 512 | 2/2 | 1/2 | 0/2 | 1 / 1 | 1 / 1 |
| base | 2048 | 2/2 | 1/2 | 0/2 | 1 / 0 | 2 / 0 |
| base | 65536 | 2/2 | 1/2 | 1/2 | 1 / 0 | 2 / 0 |
| base | context-minus-input | 2/2 | 2/2 | 2/2 | 0 / 0 | 2 / 0 |
| adapter100 | 128 | 2/2 | 0/2 | 0/2 | 2 / 0 | 0 / 2 |
| adapter100 | 512 | 2/2 | 2/2 | 2/2 | 0 / 0 | 2 / 0 |
| adapter100 | 2048 | 2/2 | 1/2 | 0/2 | 1 / 0 | 2 / 0 |
| adapter100 | 65536 | 2/2 | 2/2 | 1/2 | 0 / 0 | 2 / 0 |
| adapter100 | context-minus-input | 2/2 | 1/2 | 1/2 | 1 / 0 | 2 / 0 |

여기서 invalid는 strict assessment-only schema를 통과하지 못한 호출을 가리킨다.
JSON 문법만 유효한 경우와 유효한 uncertain 보류는 별도로 해석한다.
실제 생성 tokens와 TP/TN/FP/FN은 [원 표](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-official-tutorial-v5-max-steps-100)에 보존했다.

## 4. validation100 진단과 자유 생성 평가를 구분

| 실행 종류 | base | adapter100 | 해석 |
| --- | --- | --- | --- |
| teacher-forced forward / final-prefix / decision-token probe | sequence loss1.261358, 조건부 라벨47/100 | sequence loss0.089278, 조건부 라벨56/100 | 정답 prefix를 사용한 진단; 자유 생성 성능이 아님 |
| 조건별 새 프로세스 자유 생성 v2 | 이 run에서0/600 | 302/600 후 OOM | 두 모델 합계302/1200; 평가 미완료 |
| 후속 base 단독 자유 생성 v1 | 600회 계획, 착수 기록만 확인 | 해당 없음 | 완료 수·종료 상태는 A6000 현장 산출물 미확인 |

자유 생성 v2 ID: `cc-native-step100-validation100-fresh-process-20261006-v2`.
후속 base ID: `cc-native-base-validation100-fresh-process-20261006-v1`.
v2 후보 commit: `df6dd7783d05573961c5ad1d09e0e8840fcc9eb0`.
v2 runner SHA256: `717502ed93ba472936939740d51a91484cc68559eabfe265507184fb3bb149ea`.

같은 validation100(양성50·음성50)을 각 상한마다 평가한 v2의 adapter 표다.
strict와 semantic 집계는 원 기록에서 동일했다.

| adapter 상한 | 완료/계획 | TP | FN | FP | TN | uncertain | invalid | pending | 상태 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 128 | 100/100 | 0 | 1 | 0 | 0 | 0 | 99 | 0 | 완료 |
| 512 | 100/100 | 4 | 10 | 2 | 18 | 0 | 66 | 0 | 완료 |
| 2048 | 100/100 | 19 | 21 | 11 | 33 | 0 | 16 | 0 | 완료 |
| 65536 | 2/100 | 2 | 0 | 0 | 0 | 0 | 0 | 98 | 세 번째 입력에서 OOM |
| 130000 | 0/100 | — | — | — | — | — | — | 100 | 미시도 |
| context-minus-input | 0/100 | — | — | — | — | — | — | 100 | 미시도 |

v2의 base 6조건은 모두 미시도다. 후속 base 단독 run과 섞어 집계하지 않는다.
OOM 1건은 pending에 포함하며 FN·invalid로 바꾸지 않는다.
전체는 완료302 + pending898이며 pending은 OOM1 + 미시도897이다.
65536 조건의 완료2건은 모두 양성이므로 전체100건의 성능 지표를 계산하지 않는다.

## 5. 근거와 갱신 범위

- [공식 v5 30-step 이력](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-official-tutorial-v5-dataset-token-caps)
- [공식 v5 100-step 이력](FINETUNING_EXPERIMENT_PLAN.md#2026-10-04-official-tutorial-v5-max-steps-100)
- [validation100 평가 이력](FINETUNING_EXPERIMENT_PLAN.md#2026-10-05-native-step100-validation100-token-caps--평가-표본-수-정정)
- [OOM 원인·평가 방식 분석](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md)
- 원 artifacts: 각 `outputs/<위 실험 ID>/`의 training, audit, raw, score, condition receipt.
- 이번에 읽은 보존 문서의 저장소 HEAD: `0e51218d936a665c2aa2ac32e2dc934ca0efb543` (upstream과 동일). 이는 위 모든 run의 실행 commit이라는 뜻이 아니다.

후속 base 단독 run의 원 결과가 확인되면 해당 행을 갱신한다.
B200의 결과나 미완료 호출을 A6000의 완료 수로 대신 채우지 않는다.
