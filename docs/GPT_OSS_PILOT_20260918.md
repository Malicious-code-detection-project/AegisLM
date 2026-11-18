---
type: Project
title: GPT-OSS-20B 첫 파일럿 실험
description: B200에서 검토된 source decision 표본으로 단 한 번의 축소 LoRA 학습과 전후 평가를 실행하는 계약 및 학습 테이블
tags: [aegislm, pilot, gpt-oss, lora]
timestamp: 2026-09-18
status: completed
---

# Goal

본 실험 전 설계·데이터·런타임 문제를 찾는 **파일럿 실험(pilot study)**이다.
GPT-OSS-20B를 NuriLab 연결 후보로 준비하되 이번 결과로 배포를 승인하지 않는다.
사용자는 2026-09-18 모델 다운로드와 **첫 파일럿 1회만** 승인했다.

# Result — 2026-09-18

**단일 32-step 학습·adapter 저장·새 process reload 완료. 후속 학습은 실행하지 않았다.**
실험 전체 wall time 78.23초, training runtime 16.36초, trainable parameters 3,981,312개.
학습 peak allocated/reserved는 42.75/46.89 GiB, reload 평가 peak reserved는 48.91 GiB다.
종료 후 B200 두 장의 사용 메모리·utilization 0을 확인했다.

첫 scorer는 native Harmony `final <|constrain|>JSON<|message|>` 또는 소문자 `json`
형식 4건을 인식하지 못해 base의 schema/accuracy를 잘못 0.80으로 기록했다.
이는 모델 오류가 아닌 평가기 오류다. 저장된 동일 raw prediction 40개를 CPU로만 재채점했다.
정정 결과 **base와 adapter 모두 accuracy·JSON/schema·precision·recall 1.0, FPR 0**이다.
따라서 이 20건에서는 판정 정확도나 형식 준수 개선이 관측되지 않았다.

validation loss 2.585709→0.002729는 고정된 직접 final 답변의 teacher-forced loss다.
이 감소만으로 추론 능력·보안 품질 향상을 주장하지 않는다. 기존 base부터 20/20인 작은
합성 표본의 ceiling effect가 있어 다음 비교에는 더 어려운 별도 검증셋이 필요하다.

원래 `summary.json`은 보존하고 `rescored_summary_v2.json`을 현재 판정으로 사용한다.
실행 코드는 `executed_gpt_oss_pilot.py`로 보존했으며 SHA-256은
`e772218b8df6a44627e2e36a6f5d73138b97b755ba1fc3d9b8da6ce763052f80`이다.
현재 실행 스크립트는 parser가 수정됐으므로 원 run의 실행 코드와 구분한다.

- [정정 결과 JSON](../artifacts/pilots/gpt-oss-20b-reviewed-decision-pilot-20260918-001/rescored_summary_v2.json)
- [학습 측정 JSON](../artifacts/pilots/gpt-oss-20b-reviewed-decision-pilot-20260918-001/train_metrics.json)
- [고정 데이터·runtime manifest](../artifacts/pilots/gpt-oss-20b-reviewed-decision-pilot-20260918-001/manifest.json)

artifact 링크는 로컬 ignored 자료다. 서버 정본은 config의 `run_root`이고 Git 저장소에 포함하지 않는다.
adapter는 해당 run의 `adapter/`에 저장됐으며 safetensors 크기는 약 16 MiB다.
SHA-256: `1728318c0694d13c9a96ea30208978ae53bca77f7fd9dbbf1176164718f6476e`.

# Frozen Contract

- 실행 프로젝트: `<B200_HOST>:<HOME>/workspace/AegisLM`.
- 모델: `openai/gpt-oss-20b`, revision `6cee5e81ee83917806bbde320786a8fb61efebee`.
- 공식 HF blob/LFS hash를 검증한 snapshot attestation을 config에 고정한다.
- 방법: MXFP4 원본을 BF16으로 복원해 frozen base + attention q/k/v/o LoRA.
- B200 GPU 0 한 장, rank 8 / alpha 16, LR 1e-4, batch 1 × accumulation 4, 32 optimizer steps.
- native Harmony, reasoning low, 날짜 2026-09-18 고정, assistant-only loss, 길이 2048 초과 시 거부.
- 런타임: 기존 Mistral 환경의 interpreter를 명시적으로 사용한다. `AegisLM/.venv`는 사용하지 않는다.
  Torch `2.12.1+cu130`, Transformers `5.9.0`, PEFT `0.19.1`, Datasets `4.8.5`, Accelerate `1.13.0`.
  AegisLM의 기존 pyproject/lock을 수정하거나 이 조합과 같다고 주장하지 않는다.
- 단계: base 평가 → 학습 1회 → adapter 저장 → 새 프로세스 reload 평가.
- 생성 평가: 동일 validation 20건, greedy, max_new_tokens 512, final channel의 JSON만 채점.
- 실행 전체 wall-time 상한 3,600초. OOM, NaN/Inf, subprocess 오류, hash/version 불일치 시 중단.
- `RUN_STARTED`와 `TRAIN_STARTED` 배타적 marker로 같은 run의 재학습을 거부한다.
- 다음 run 자동 실행 없음. 실패 후 수정하더라도 새 학습 실행은 별도 결정 대상이다.

# Data and Evaluation Boundary

`phase-f-sard-grounded-v3-20260918-r4` 중 기존 AI 보조 검토 PASS **100행만** 사용한다.
88행은 exact-match 판정을 이관했고 12행은 재검토했으며 **전문가 서명이 아니다**.
생성된 evidence target은 이번에 학습하지 않고 `assessment`만 투영한다.

학습 80행·검증 20행으로 나누고 group ID와 exact-code hash 중복을 금지한다.
검증은 present 10건·not_observed 10건으로 고정한다. 희소 CWE 전체의 성능을 대표하지 않는다.
과거 실험 개발자가 이미 본 데이터이며 새 blind test가 아니다. 과거 train과의 중복도 일반화 주장의 근거가 될 수 없다.

부모 데이터의 3,420/5,750 pair 공급 부족과 `approved_for_training=false`는 유지한다.
사용자의 축소 실험 요청은 별도 pilot contract이며 부모 데이터의 전체 학습 승격이 아니다.
판정은 요청된 CWE·함수 범위로 제한하며 전체 프로그램 안전성·malware 탐지 성능과 구분한다.

# Training Table

| ID | 역할 | 데이터 | Steps | LR / rank | 실행 상태 | 측정 결과 | 다음 조건 |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| P0-base | 학습 전 기준선 | validation 20 | 0 | 해당 없음 | 완료·CPU 재채점 | accuracy/schema 1.0, loss 2.585709 | 동일 prompt·gold 고정 |
| P1-pilot | 최초 단일 학습 | train 80 | 32 | 1e-4 / 8 | 완료 | train loss 0.244140, 16.36초 | adapter 저장 PASS |
| P1-reload | 새 process 후속 평가 | validation 20 | 0 | P1 adapter | 완료·CPU 재채점 | accuracy/schema 1.0, loss 0.002729 | reload PASS, 품질 향상은 미입증 |
| P2 | 더 어려운 독립 평가·후속 학습 설계 | 미확정 | 미확정 | 미확정 | NOT_AUTHORIZED | 미실행 | ceiling effect와 NuriLab 입력/출력 계약 검토 후 사용자 결정 |

loss는 supervised assistant-token 가중 평균, JSON/schema rate, accuracy, precision,
recall, FPR, uncertain/invalid, 생성 budget 소진, 시간, GPU peak memory를 기록한다.
invalid·uncertain은 accuracy에서 정답으로 세지 않고 별도 수치를 보고한다.
진단 품질 gate는 reload schema≥0.95 및 accuracy≥base이며 보안 모델 승인 gate가 아니다.

# How to Run

`configs/gpt_oss_pilot_20260918.json`의 절대경로와 고정 해시를 확인한다.

```bash
cd <HOME>/workspace/AegisLM
PY=<HOME>/workspace/AegisLM_Mistral-small-4-119B/.venv/bin/python
$PY scripts/gpt_oss_pilot.py prepare --config configs/gpt_oss_pilot_20260918.json
$PY scripts/gpt_oss_pilot.py run --config configs/gpt_oss_pilot_20260918.json
```

준비된 run은 덮어쓰지 않는다. `run`은 자동으로 세 단계를 순서대로 실행하고 종료한다.
`baseline/train/reload`는 parent orchestration의 내부 child 명령으로만 허용한다.
원본 데이터·model·output은 영구 볼륨에 두고 Git에 넣지 않는다.
실행 후 `status.json`, `summary.json`, 단계별 metrics/log, trainer_state, adapter hashes가 근거다.

**이 run은 이미 완료됐으므로 위 명령을 다시 실행하지 않는다.** 현재 parser 수정으로
script hash가 다르며, 기존 run/학습 marker도 재실행을 거부한다. 다음 실험은 별도 승인과 새 ID가 필요하다.
재채점 도구 `scripts/rescore_gpt_oss_pilot.py`는 저장된 prediction만 읽고 GPU를 사용하지 않는다.

# Validation and Acceptance

- 실행 전 테스트: 로컬·B200 각각 10 passed, Ruff PASS.
- 독립 Terra 리뷰: R1–R4 수정 후 PASS. Luna 독립 검증: 동일 후보 hash·10 tests·Ruff PASS.
- 실제 tokenizer preflight: 80/20 rows, labels 40/40 및 10/10, group/code overlap 0, max 478 tokens.
- 실제 GPU: 32 optimizer steps, save/reload PASS, 학습 1회, 종료 code 0.
- 실제 출력 반례로 평가기 수정 후 13 regression tests·Ruff PASS; 학습 재실행 0.
- 역할 요청 모델: Terra `gpt-5.6-terra/high`, Luna `gpt-5.6-luna/low`를 도구에 지정해 별도 세션으로 실행.
  parent 조율 역할 이름을 모델 전환으로 기록하지 않는다. 실제 제공 모델의 별도 runtime identity는 unknown.
- 수용: 기술적 파일럿 완료. 전체 데이터 학습과 NuriLab 배포는 계속 미승인.

# Related Concepts

- [프로젝트 운영 하네스](HARNESS_V3_1.md)
- [실행 코드](../scripts/gpt_oss_pilot.py)
- [고정 설정](../configs/gpt_oss_pilot_20260918.json)
- [파일럿 연구 정의](https://pmc.ncbi.nlm.nih.gov/articles/PMC4792418/)
- [공식 GPT-OSS-20B 모델 안내](https://developers.openai.com/api/docs/models/gpt-oss-20b)
- [Axolotl GPT-OSS 학습·Harmony 안내](https://docs.axolotl.ai/docs/models/gpt-oss.html)
