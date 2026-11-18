---
type: Project
title: GPT-OSS-20B Q1R10·Q1R11 계약 5-step 스모크
description: 기존 Qwen 데이터와 평가 코드를 유지한 독립 판정·근거 선택 스모크 실행 기록
tags: [aegislm, gpt-oss, smoke, qwen]
timestamp: 2026-09-21
status: completed
---

# Contract

사용자 요청: GPT-OSS-20B에서 약 5-step 스모크를 먼저 수행하고 Qwen3와 같은 평가 기준으로 판단한다.
Q1R10 판정과 Q1R11 근거 선택을 **각각 원본 base에서 5 optimizer steps** 실행한다.
두 adapter는 독립적이며 evidence를 decision adapter에 이어 학습하지 않는다.
이번 스모크 뒤 본 학습은 자동 실행하지 않고 결과를 기록한다.

- run: `gpt-oss-20b-qwen-contract-smoke-20260921-002` (001은 학습 전 기준선 실행부 오류로 보존)
- 서버: `<B200_HOST>`, 실행 프로젝트 `<HOME>/workspace/AegisLM`
- 기존 데이터/평가 코드: `<HOME>/workspace/AegisLM-B200` 및 LLM 영구 볼륨
- 모델: 기존 검증된 GPT-OSS-20B revision `6cee5e81ee83917806bbde320786a8fb61efebee`
- BF16 복원·attention q/k/v/o LoRA rank8/alpha16, LR1e-4, batch1×accumulation32, seed20260728
- 원본 prompt/target 보존. 모델 입력만 native Harmony로 변환하며 final 채널을 미리 지정해 직접 JSON을 생성한다.
- 토큰 손실 금지: 학습 전체와 평가 입력을 검사하며 자르지 않는다. 스모크 sequence cap4096, 생성 상한 decision128/evidence512.
- 원본 SHA256SUMS·group/code 중복·assistant loss mask·EOS·adapter 저장 hash·fresh reload 확인.
- 기존 원본/adapter/파일럿을 덮어쓰지 않는다. W&B 외부 전송 없이 로컬 로그를 저장한다.

# Data and Evaluation

| 목적 | 학습 자료 | 개발 평가 |
|---|---|---|
| 판정 | `phase-f-source-decision-v1/train.jsonl`, 10000행 | validation1000에서 기존 함수 seed20260728로 클래스별50행 선택 |
| 근거 줄 선택 | `phase-f-source-evidence-lines-v1/canonical/train.jsonl`, 9975행 | 기존 development의 challenge/gold/private100행 그대로 |

Decision 선택 ID/hash를 저장한다. 과거 Q1R10 개발셋과 ID까지 동일함을 검증하기 전에는 동일 cohort라고 주장하지 않는다.
Evidence는 정답 assessment를 조건으로 주는 독립 평가이며 **두 단계 연결 E2E 결과가 아니다**.
과거 blind500을 새 blind로 사용하지 않는다. 각 objective에서 base와 reload adapter를 같은 개발셋으로 평가한다.

기존 evaluator를 호출하며 임계값은 낮추지 않는다.

| 지표 | 판정 gate | 근거 gate |
|---|---:|---:|
| 표본 수 | ≥100 | ≥100 |
| JSON parse/schema | 각각 ≥.99 | 각각 ≥.99 |
| precision | ≥.90 | line micro ≥.50 |
| recall | ≥.95 | line micro ≥.50 |
| FPR / abstention | ≤.05 / ≤.05 | 해당 없음 |
| renderer 성공률 | 해당 없음 | 1.00 |
| 예측 누락/초과 | 0 | 0 |

원시 생성 token IDs·decoded text·종료/길이 제한 도달 여부를 보존한다.
평가 입력에서는 마지막 transport 종료 토큰 하나만 제거하며 JSON 내용·근거 줄을 고치지 않는다.

# Interpretation

스모크의 기술적 완료(5step·finite loss·저장·reload)와 품질 gate를 분리한다.
5step만으로 품질을 보장하지 않으며, 기존 Qwen100step과 학습량이 다른 진단 실험이다.
기존 정답 오류 감사는 유지한다. 이번 비교는 같은 benchmark gold에 대한 계약 재현이며 독립 보안 정답 인증이 아니다.
Qwen은 all-module LoRA·2GPU ZeRO3·100step, 이번 스모크는 attention-only LoRA·1GPU·5step이다.
기존 Qwen의 cosine LR/warmup0.1/dropout0.05와 달리 이번 스모크는 constant LR/warmup0/dropout0을 사용한다.
학습량/adapter 대상이 다르므로 결과를 모델 능력의 공정한 최종 순위로 해석하지 않는다.

# Results

CPU prepare PASS: decision/evidence 학습 10000/9975행, dev 각100행.
최대 학습 토큰 1452/1684, 최대 평가 prompt902/1954. 입력 절단 없음.
train/dev ID·group·exact-code overlap 각0. 원본 checksum·native final prefix·EOS 확인.
pytest 5 passed. 작성자와 분리된 계약/코드 검토 완료; 요청 모델과 실제 배정 모델은 별도로 검증하지 않았다.
고정 실행 코드 SHA-256: `de5831449785e82d7ae5415592dd2d10cbf18c17b32fc13d1381e20f2a0d97ef`.
**결과: 기술적 스모크 PASS / Qwen 품질 gate FAIL.**
002 전체 413.87초(약6분54초), process exit0. 각 과제 global_step5·finite loss·저장·별도 process reload 완료.
종료 후 GPU0/1 모두 사용 메모리0 MiB·utilization0%를 확인했다. 본 학습은 실행하지 않았다.

| 지표 | 판정 base | 판정 5-step | Qwen 기준 |
|---|---:|---:|---:|
| JSON / schema | 1.00 / 1.00 | 1.00 / 1.00 | 각각 ≥.99 |
| precision | .5694 | .5811 | ≥.90 |
| recall | .8200 | .8600 | ≥.95 |
| FPR | .6200 | .6200 | ≤.05 |
| abstention | .0300 | .0000 | ≤.05 |
| TP / TN / FP / FN | 41 / 19 / 31 / 9 | 43 / 19 / 31 / 7 | 보고용 |

| 지표 | 근거 base | 근거 5-step | Qwen 기준 |
|---|---:|---:|---:|
| JSON parse | .99 | .99 | ≥.99 |
| schema / renderer | .93 / .93 | .93 / .93 | ≥.99 / 1.00 |
| line precision | .4910 | .5660 | ≥.50 |
| line recall | .5084 | .5290 | ≥.50 |
| line F1 | .4995 | .5469 | 보고용 |
| EOS / 생성 상한 도달 | 99 / 1 | 99 / 1 | 보고용 |

판정은 각100건에서 EOS100·상한 도달0·예측 누락/초과0이다.
근거 reload의 실패7건은 최대8개를 넘는 evidence_ranges6건과 JSON 문자열 미종료1건이다.
후자는 512-token 상한에 도달했다. 출력이나 range를 사후 교정하지 않았다.
이 실패를 데이터 파싱 오류나 GPU 학습 불가로 분류하지 않는다.

| 학습 측정 | 판정 | 근거 |
|---|---:|---:|
| optimizer steps | 5 | 5 |
| training runtime | 23.1903초 | 25.2619초 |
| aggregate train loss | 1.460438 | .765922 |
| peak allocated / reserved GiB | 42.75 / 47.62 | 42.75 / 50.88 |
| trainable parameters | 3981312 | 3981312 |

Adapter SHA-256:

- decision: `89fa5b010f816449a9b9df2767ce462eaad42f5016cdab42765f724511c57ec4`
- evidence: `30cea549c5f7ee7c5f42fcfcd30d5c959b11abd89ea1fe84211183d5184c7f63`

저장된 baseline/reload 예측 파일4개를 기존 evaluator로 CPU 재채점해 metrics/gates가 모두 동일함을 확인했다.
서버 정본은 `TrainingArtifacts/pilots/gpt-oss-20b-qwen-contract-smoke-20260921-002/`이며 adapter는 각 objective의 `adapter/`다.

- [최종 요약](../artifacts/pilots/gpt-oss-20b-qwen-contract-smoke-20260921-002/summary.json)
- [데이터·코드 고정 manifest](../artifacts/pilots/gpt-oss-20b-qwen-contract-smoke-20260921-002/manifest.json)
- [저장 출력 재채점 검증](../artifacts/pilots/gpt-oss-20b-qwen-contract-smoke-20260921-002/replay_verification.json)
- [판정 평가 상세](../artifacts/pilots/gpt-oss-20b-qwen-contract-smoke-20260921-002/decision/reload_metrics.json)
- [근거 평가 상세](../artifacts/pilots/gpt-oss-20b-qwen-contract-smoke-20260921-002/evidence/reload_metrics.json)

다음 비교 후보는 동일 과제를 Qwen과 같은 100-step까지 학습해 보는 것이다.
5-step에서 보인 오탐·range 과다 생성을 학습량 증가만으로 해결할 수 있는지는 아직 미확정이다.
이번 결과를 본 학습 성공이나 두 단계 연결 성능으로 승격하지 않으며, 기존 데이터 재설계로 경로를 다시 바꾸지도 않는다.

# Related

- [실행 설정](../configs/gpt_oss_qwen_smoke_20260921_retry.json)
- [실행 코드](../scripts/gpt_oss_qwen_smoke.py)
- [이전 경로 선택 정정](SOURCE_DATASET_FAILURE_ANALYSIS_20260919.md)
- [기존 판정·근거 평가 결과](../../../training/aegislm_q1r11_fresh_blind_pass_decision_20260730.md)

## 실행부 오류 정정

001은 등록되지 않은 종료 토큰의 ID(None)를 generate에 전달해 baseline 첫 생성에서 실패했다. 학습 시작 marker는 0개다. 원 코드·설정·로그를 보존하고, native EOS <|return|>/200002만 사용하는 수정본을 CPU 회귀 5건과 독립 리뷰·전체 prepare로 검증한 뒤 002를 시작했다. 데이터 또는 모델 학습 실패와 구분한다.
