# Experiment Log Template

이 문서는 Phase D baseline evaluation과 Phase E 이후 adapter evaluation 결과를 같은 형식으로 기록하기 위한 템플릿입니다.

실제 실행 산출물(`prediction JSONL`, `evaluation_summary.json`, `evaluation_report.html`, checkpoint, adapter, raw dataset, large logs)은 Git에 커밋하지 않습니다. 이 템플릿은 기록 형식만 정의합니다.

## 사용 원칙

- 하나의 evaluation run마다 하나의 log entry를 작성한다.
- baseline과 adapter 결과를 같은 필드로 기록한다.
- 점수만 기록하지 않고 command, dataset, model, artifact path, failure mode를 함께 기록한다.
- private CTI, secrets, raw malware sample, raw dataset row, checkpoint, adapter artifact는 log에 직접 넣지 않는다.
- 외부 저장소 artifact는 identifier, version tag, storage location, provenance note만 기록한다.

## Log Entry

````markdown
## <run_id>

- Date: <YYYY-MM-DD>
- Linear issue: <THE-XX>
- Git commit: <short sha>
- Phase: <Phase D/E/F>
- Run type: <baseline | adapter | smoke | regression>
- Owner: <name>

### Purpose

<이 run을 실행한 이유를 적는다. 예: Phase C fixture smoke, real baseline before fine-tuning, adapter regression comparison.>

### Environment

- OS: <name/version>
- Python: <version>
- Package manager: uv
- PyTorch: <version or N/A>
- Transformers: <version or N/A>
- CUDA: <version or N/A>
- GPU: <model/count or N/A>
- Notes: <driver, VRAM, CPU-only reason, etc.>

### Inputs

- Dataset path: <path or external artifact id>
- Dataset split: <fixture | held-out | validation | test>
- Dataset version/provenance: <source, date, license/terms note>
- Prediction path: <outputs/.../predictions.jsonl>
- Model id: <model id or adapter id>
- Base model id: <base model id, if adapter run>
- Adapter artifact: <external path/id or N/A>
- Prompt contract: <prompt module/version/commit>

### Commands

```bash
<inference command>
<evaluation command>
```

### Artifact Paths

- Prediction JSONL: <outputs/.../predictions.jsonl>
- Evaluation summary JSON: <outputs/.../evaluation_summary.json>
- Evaluation report HTML: <outputs/.../evaluation_report.html>
- Extra logs: <outputs/... or N/A>

### Metrics

| Metric | Value |
| --- | ---: |
| total_count | <number> |
| composite_score | <number> |
| hard_gate_pass_rate | <0.0-1.0> |
| json_parse_success_rate | <0.0-1.0> |
| schema_validation_pass_rate | <0.0-1.0> |
| safety_pass_rate | <0.0-1.0> |
| required_field_completeness | <0.0-1.0> |
| risk_level_match_rate | <0.0-1.0> |
| attack_mapping_precision | <0.0-1.0> |
| attack_mapping_recall | <0.0-1.0> |
| attack_mapping_f1 | <0.0-1.0> |
| hallucinated_attack_mapping_count | <number> |
| evidence_discipline_rate | <0.0-1.0> |
| latency_p50_ms | <number or N/A> |
| latency_p95_ms | <number or N/A> |

### Failure Modes

- Invalid JSON cases: <count and short summary>
- Missing required fields: <count and short summary>
- Unsafe guidance failures: <count and short summary>
- Risk mismatch cases: <count and short summary>
- Hallucinated ATT&CK mappings: <count and short summary>
- Other notes: <short notes>

### Interpretation

<결과 해석을 짧게 적는다. Composite score만으로 결론 내리지 말고 hard gate, schema, safety, mapping 지표를 함께 해석한다.>

### Follow-up

- Next Linear issue: <THE-XX or N/A>
- Blockers: <none or list>
- Decision: <continue baseline work | prepare held-out set | start tiny SFT | rerun required>
````

## Example: THE-58 Smoke Run

이 예시는 harness 검증용 mock output입니다. 실제 `openai/gpt-oss-20b` baseline benchmark로 해석하지 않습니다.

````markdown
## the-58-smoke

- Date: 2026-06-17
- Linear issue: THE-58
- Git commit: cb72fbd
- Phase: Phase D
- Run type: smoke
- Owner: Jeong Min LEE

### Purpose

Phase C tiny fixture에서 prediction JSONL 생성과 evaluation summary/report 생성 흐름을 검증한다.

### Environment

- OS: local development environment
- Python: 3.12.13
- Package manager: uv
- PyTorch: N/A
- Transformers: N/A
- CUDA: N/A
- GPU: N/A
- Notes: mock backend, no model loading

### Inputs

- Dataset path: `tests/fixtures/tiny_phase_c_records.jsonl`
- Dataset split: fixture
- Dataset version/provenance: Phase C synthetic/metadata-only fixture
- Prediction path: `outputs/the-58/baseline_predictions.jsonl`
- Model id: `mock-baseline-smoke`
- Base model id: N/A
- Adapter artifact: N/A
- Prompt contract: `aegislm.prompts.format_baseline_prompt`

### Commands

```bash
uv run python scripts/run_baseline_inference.py \
  --dataset tests/fixtures/tiny_phase_c_records.jsonl \
  --predictions outputs/the-58/baseline_predictions.jsonl \
  --model-id mock-baseline-smoke \
  --run-id the-58-smoke \
  --backend mock \
  --mock-raw-output '{"summary":"mock raw output"}'

uv run python scripts/evaluate_predictions.py \
  --dataset tests/fixtures/tiny_phase_c_records.jsonl \
  --predictions outputs/the-58/baseline_predictions.jsonl \
  --summary-json outputs/the-58/evaluation_summary.json \
  --report-html outputs/the-58/evaluation_report.html
```

### Artifact Paths

- Prediction JSONL: `outputs/the-58/baseline_predictions.jsonl`
- Evaluation summary JSON: `outputs/the-58/evaluation_summary.json`
- Evaluation report HTML: `outputs/the-58/evaluation_report.html`
- Extra logs: N/A

### Metrics

| Metric | Value |
| --- | ---: |
| total_count | 5 |
| composite_score | 39.4286 |
| hard_gate_pass_rate | 0.0 |
| json_parse_success_rate | 1.0 |
| schema_validation_pass_rate | 0.0 |
| safety_pass_rate | 1.0 |
| required_field_completeness | 0.1429 |
| risk_level_match_rate | 0.0 |
| attack_mapping_precision | 0.0 |
| attack_mapping_recall | 0.0 |
| attack_mapping_f1 | 0.0 |
| hallucinated_attack_mapping_count | 0 |
| evidence_discipline_rate | 0.0 |
| latency_p50_ms | N/A |
| latency_p95_ms | N/A |

### Failure Modes

- Invalid JSON cases: 0
- Missing required fields: 5 cases, mock output only contains `summary`
- Unsafe guidance failures: 0
- Risk mismatch cases: 5 cases, risk_level missing
- Hallucinated ATT&CK mappings: 0
- Other notes: expected failure for harness smoke validation

### Interpretation

The smoke run confirms that the evaluation harness records incomplete but parseable output as schema and hard-gate failure. This is not a real baseline model score.

### Follow-up

- Next Linear issue: THE-60 or actual baseline run follow-up
- Blockers: real model runtime environment not exercised
- Decision: use this format for future baseline and adapter evaluation logs
````
