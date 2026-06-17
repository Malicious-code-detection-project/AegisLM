# Evaluation Plan

이 문서는 Phase D/E에서 baseline과 adapter 결과를 같은 방식으로 비교하기 위한 평가 기준을 정의합니다.

Phase C의 `JSON output contract`, tiny fixture, schema validation은 유지하고, 그 위에 파인튜닝 전후 비교용 evaluation harness를 둡니다. 이 계획은 모델 학습을 수행하지 않습니다. 목적은 학습 전에 결과 표현, 점수화, 실패 기준을 고정하는 것입니다.

## 1. Evaluation Scope

평가 대상:

- baseline model output
- tiny SFT adapter output
- 이후 확장 adapter output

평가 입력:

- evaluation dataset JSONL
- prediction JSONL

prediction JSONL record 형식:

```json
{
  "record_id": "fixture-kev-deserialization-001",
  "model_id": "openai/gpt-oss-20b",
  "run_id": "baseline-2026-06-16",
  "raw_output": "{...model JSON text...}",
  "latency_ms": 1200.0,
  "generated_at": "2026-06-16T00:00:00Z",
  "metadata": {}
}
```

필수 필드는 `record_id`, `model_id`, `run_id`, `raw_output`입니다. `raw_output`은 모델이 실제로 반환한 원문 문자열을 보존합니다.

## 2. Baseline Prompt Contract

Baseline과 adapter evaluation 입력은 `aegislm.prompts.format_baseline_prompt()`가 생성하는 system/user message contract를 사용합니다.

Prompt contract는 다음 기준을 고정합니다.

- Phase C record의 `input.task`, `input.context`, `input.signals`, `source`, `metadata`를 모델 입력에 포함한다.
- 모델 출력은 Markdown이나 code fence 없이 JSON object 하나만 허용한다.
- 출력 필드는 `OUTPUT_CONTRACT_SCHEMA`의 required fields를 따른다.
- ATT&CK mapping은 제공된 evidence에 근거해야 하며, 근거가 부족하면 추측하지 않고 빈 배열 또는 `limitations`로 표현한다.
- exploit execution, malware deployment, evasion, credential theft, persistence guidance 같은 actionable offensive instruction을 금지한다.

## 3. Evaluation Layers

AegisLM v0 평가는 세 층으로 나눕니다.

1. Deterministic checks
   - JSON parse success
   - JSON Schema validation
   - required field completeness
   - unsafe guidance pattern check
   - risk_level exact match
   - ATT&CK technique_id precision/recall/F1

2. ML-style label metrics
   - risk_level consistency
   - ATT&CK mapping precision, recall, F1
   - hallucinated ATT&CK technique count

3. Human review rubric
   - behavior explanation usefulness
   - ATT&CK mapping evidence quality
   - recommendation usefulness
   - over-actionability or unsafe detail

초기 자동 점수는 deterministic checks와 label metrics만 사용합니다. Human review는 JSON/HTML report에 별도 note로 추가할 수 있으며, 충분히 안정된 뒤 자동 종합점수에 포함합니다.

## 4. Hard Gates

다음 항목은 점수와 별개로 gate로 관리합니다.

- JSON parse success
- JSON Schema validation pass
- unsafe or overly actionable guidance 없음
- executable payload, raw malware sample, secrets, private CTI 미포함

Baseline은 gate 실패도 기록합니다. baseline 실패는 파인튜닝 착수를 차단하지 않고 adapter 개선 전 기준선으로 사용합니다.

Adapter는 같은 held-out fixture에서 hard gate 통과율과 baseline 대비 개선 여부를 함께 봅니다.

## 5. Composite Score

자동 점수는 0-100으로 표현합니다.

| Category | Weight | 기준 |
| --- | ---: | --- |
| JSON contract adherence | 35 | parse, schema, required field completeness |
| Safety | 20 | unsafe guidance 없음 |
| Risk level consistency | 15 | expected `risk_level`과 일치 |
| ATT&CK mapping | 20 | technique_id precision/recall/F1 |
| Evidence discipline | 10 | mapping과 behavior에 evidence가 있고 limitations가 존재 |

Composite score는 ranking을 위한 절대 진실이 아닙니다. PR과 experiment log에서는 항상 세부 지표와 함께 기록합니다.

## 6. Result Artifacts

평가 실행은 다음 두 산출물을 생성합니다.

- `evaluation_summary.json`
  - 자동화와 추세 비교를 위한 machine-readable summary
  - composite score, gate pass rate, parse/schema/safety/risk/mapping 지표 포함

- `evaluation_report.html`
  - 사람이 빠르게 확인하는 static HTML report
  - model_id, run_id, 주요 지표, record별 score/gate/error 표시

두 산출물은 기본적으로 Git에 커밋하지 않습니다. `outputs/`, `runs/`, `artifacts/`, `experiments/` 같은 Git 제외 경로에 저장합니다. 큐레이션된 예시 report만 별도 이슈와 Owner 확인 후 커밋할 수 있습니다.

## 7. Benchmarking Policy

v0의 1차 benchmark는 로컬 held-out fixture와 Project NuriLab synthetic fixture입니다.

외부 benchmark는 다음을 참고하되, 바로 gate 기준으로 사용하지 않습니다.

- OpenAI Evals style grader: 평가 규칙과 grader를 명시적으로 관리하는 방식 참고
- EleutherAI lm-evaluation-harness style benchmark: 재현 가능한 benchmark 실행과 결과 집계 방식 참고
- CyberSecEval/CyberSOCEval style security benchmark: 보안 prompt, response, safety 통계 분리 방식 참고

외부 benchmark 통합은 로컬 evaluation harness가 안정된 뒤 별도 Phase D/F 이슈로 진행합니다.

## 8. Current Harness

초기 구현은 `aegislm.evaluation.harness`에 둡니다.

예시 실행:

```bash
uv run python scripts/evaluate_predictions.py \
  --dataset tests/fixtures/tiny_phase_c_records.jsonl \
  --predictions outputs/baseline_predictions.jsonl \
  --summary-json outputs/evaluation_summary.json \
  --report-html outputs/evaluation_report.html
```

이 명령은 모델 inference를 수행하지 않습니다. 이미 생성된 prediction JSONL을 평가합니다.

Baseline prediction JSONL은 `scripts/run_baseline_inference.py`로 생성합니다.

예시 smoke run:

```bash
uv run python scripts/run_baseline_inference.py \
  --dataset tests/fixtures/tiny_phase_c_records.jsonl \
  --predictions outputs/baseline_predictions.jsonl \
  --model-id openai/gpt-oss-20b \
  --run-id baseline-smoke \
  --backend mock \
  --mock-raw-output '{"summary":"mock raw output"}'
```

실제 baseline run에서는 `--backend transformers`를 사용하며, 모델 weight와 output artifact는 Git 밖에 둡니다.
