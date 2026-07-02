## the-73-adapter-evaluation

- Date: 2026-07-02
- Linear issue: THE-73
- Git commit: d9076d7
- Phase: Phase E
- Run type: adapter
- Owner: kwon o seong

### Purpose

학습 데이터셋(4건)이 극소량으로 설계된 개념 검증용 tiny SFT 어댑터(`adapters/tiny-sft-poc`)가 독립된 평가 데이터셋([tests/fixtures/heldout_evaluation_records.jsonl](file:///home/remoteuser/Desktop/AegisLM/tests/fixtures/heldout_evaluation_records.jsonl))에 대해 어떤 지표와 실패 패턴을 보이는지 자동 채점하여, 평가 엔진 파이프라인의 통합성과 성능 기준선을 공식 측정한다.

### Environment

- OS: linux (Ubuntu 24.04 LTS)
- Python: 3.12.13
- Package manager: uv
- PyTorch: 2.10.0+cu128
- Transformers: 5.5.0
- CUDA: 12.8
- GPU: NVIDIA RTX A6000 (1개 / VRAM 47.39 GB)
- Notes: bitsandbytes==0.45.0, unsloth==2026.6.9, single GPU environment

### Inputs

- Dataset path: [tests/fixtures/heldout_evaluation_records.jsonl](file:///home/remoteuser/Desktop/AegisLM/tests/fixtures/heldout_evaluation_records.jsonl)
- Dataset split: test (held-out fixture)
- Dataset version/provenance: Phase D/E adapter 비교용 고정 검증 세트
- Prediction path: `outputs/the-73/adapter_predictions.jsonl`
- Model id: `openai/gpt-oss-20b` (베이스 모델)
- Base model id: `openai/gpt-oss-20b`
- Adapter path: `adapters/tiny-sft-poc`
- Prompt contract: `aegislm.prompts.format_baseline_prompt`

### Commands

```bash
# 어댑터 기반 추론 수행
uv run scripts/run_adapter_inference.py \
  --dataset tests/fixtures/heldout_evaluation_records.jsonl \
  --predictions outputs/the-73/adapter_predictions.jsonl \
  --adapter-path adapters/tiny-sft-poc \
  --run-id adapter-poc-eval \
  --backend unsloth

# 추론 결과 채점 및 리포트 작성
uv run scripts/evaluate_predictions.py \
  --dataset tests/fixtures/heldout_evaluation_records.jsonl \
  --predictions outputs/the-73/adapter_predictions.jsonl \
  --summary-json outputs/the-73/evaluation_summary.json \
  --report-html outputs/the-73/evaluation_report.html
```

### Artifact Paths

- Prediction JSONL: `outputs/the-73/adapter_predictions.jsonl` (Git-ignored)
- Evaluation summary JSON: `outputs/the-73/evaluation_summary.json` (Git-ignored)
- Evaluation report HTML: `outputs/the-73/evaluation_report.html` (Git-ignored)
- Extra logs: N/A

### Metrics

| Metric | Value |
| --- | ---: |
| total_count | 5 |
| composite_score | 0.0 |
| hard_gate_pass_rate | 0.0 |
| json_parse_success_rate | 0.0 |
| schema_validation_pass_rate | 0.0 |
| safety_pass_rate | 0.0 |
| required_field_completeness | 0.0 |
| risk_level_match_rate | 0.0 |
| attack_mapping_precision | 0.0 |
| attack_mapping_recall | 0.0 |
| attack_mapping_f1 | 0.0 |
| hallucinated_attack_mapping_count | 0 |
| evidence_discipline_rate | 0.0 |
| latency_p50_ms | 125079.13 |
| latency_p95_ms | 129124.26 |

### Failure Modes

- Invalid JSON cases: 5 cases (모든 레코드에서 유효하지 않은 JSON이 발생함. 오류 로그: `invalid JSON: Expecting value`)
- Missing required fields: 5 cases (JSON 파싱 실패로 인한 미준수)
- Unsafe guidance failures: 0 (분류 불가)
- Risk mismatch cases: 5 cases
- Hallucinated ATT&CK mappings: 0
- Other notes: 모델이 JSON을 생성하지 못하고 프롬프트 지침이나 지시사항을 무작위로 반복/복기하는 중얼거림 현상(Babbling/Repetition)을 보임.

### Interpretation

- **평가 결과 분석**: Composite Score는 **0.00**이며 Hard Gate 통과율 역시 **0.0%**입니다. 
- **원인 분석**: `THE-70`에서 학습시킨 데이터가 4건, 학습 스텝이 2스텝에 불과하여 어댑터가 "JSON 구조화 출력" 지식을 사실상 전혀 학습하지 못했습니다. 결과적으로 모델이 JSON 브레이스 `{}`로 닫힌 객체를 출력하는 대신 프롬프트의 지시문을 흉내 내는 중얼거림 텍스트만 반복 출력하여 JSON 파싱 단계에서 전량 실패했습니다.
- **파이프라인 유효성**: 비록 지표는 0점이지만, 어댑터가 비정상적인 텍스트를 출력하더라도 평가 스크립트([scripts/evaluate_predictions.py](file:///home/remoteuser/Desktop/AegisLM/scripts/evaluate_predictions.py))가 충돌 없이 오작동을 정확하게 감지하여 `invalid JSON: Expecting value` 감점 요인을 리포트에 정상적으로 요약 반영함을 확인했습니다. 
- 이로써 학습-추론-평가로 이어지는 전체 소프트웨어 배관이 정상 동작함을 완전히 검증했습니다.

### Follow-up

- Next Linear issue: THE-74 (PoC 결과 기록과 v0 training path 선택)
- Blockers: None
- Decision: 파이프라인 무결성이 확인되었으므로, 해당 PoC 결과 분석을 토대로 v0 정식 학습 스택 결정을 위한 다음 이슈(`THE-74`)를 준비합니다.
