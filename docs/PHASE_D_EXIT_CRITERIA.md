# Phase D Exit Criteria

이 문서는 Phase D baseline inference + evaluation을 언제 완료로 판단하고, Phase E tiny SFT PoC로 넘어갈 수 있는지 정의합니다.

Phase D의 목적은 모델을 학습하는 것이 아니라, 학습 전 기준선을 재현 가능한 방식으로 남기는 것입니다. 실패한 baseline 결과도 adapter 개선 전 비교 기준으로 기록합니다.

## 1. Phase D 완료 조건

Phase D는 다음 조건이 모두 충족될 때 완료로 판단합니다.

- baseline prompt contract가 고정되어 있고 `aegislm.prompts.format_baseline_prompt()`로 재사용할 수 있다.
- baseline inference runner가 prediction JSONL을 생성할 수 있다.
- evaluation harness가 prediction JSONL에서 `evaluation_summary.json`과 `evaluation_report.html`을 생성할 수 있다.
- Phase C tiny fixture smoke run 결과가 기록되어 있다.
- Phase D/E adapter 비교용 held-out fixture가 준비되어 있고 training data에 포함하지 않는다고 명시되어 있다.
- experiment log template에 command, environment, dataset, model, metric, artifact path, failure mode를 기록할 수 있다.
- artifact storage policy가 prediction, report, adapter, checkpoint, raw dataset의 Git 포함 여부를 구분한다.
- README, AGENTS, docs 문서가 Phase D 진행 중 상태와 Phase E 착수 조건을 충돌 없이 설명한다.

## 2. Phase E 착수 Gate

Phase E tiny SFT PoC는 아래 gate가 통과된 뒤 별도 Linear 이슈로 시작합니다.

| Gate | Required evidence |
| --- | --- |
| Baseline runnable | `scripts/run_baseline_inference.py`가 target dataset으로 prediction JSONL을 생성한다. |
| Evaluation runnable | `scripts/evaluate_predictions.py`가 summary JSON과 HTML report를 생성한다. |
| Baseline recorded | experiment log 형식으로 run id, command, environment, dataset path, model id, artifact path, metrics, failure mode를 기록한다. |
| Held-out protected | `tests/fixtures/heldout_evaluation_records.jsonl`은 `test` split이며 adapter training data에 포함하지 않는다. |
| Artifact policy followed | generated outputs는 Git 밖 `outputs/`, `runs/`, `artifacts/`, `experiments/` 또는 승인된 외부 저장소에 둔다. |
| Safety constraints clear | raw malware, executable payload, secrets, private CTI, unsafe operational guidance가 학습/평가 산출물에 포함되지 않는다. |
| Quality gates pass | 코드 변경이 포함된 경우 `pytest`, `ruff`, `mypy` 기준을 통과한다. |

Phase E 착수 판단은 composite score만으로 하지 않습니다. JSON contract adherence, safety, risk consistency, ATT&CK mapping, evidence discipline, failure mode를 함께 봅니다.

## 3. Baseline Run Requirements

실제 baseline run은 smoke run과 구분합니다.

- Smoke run: `--backend mock`으로 harness 흐름과 실패 기록을 검증한다.
- Real baseline run: `openai/gpt-oss-20b`를 로컬 GPU 환경에서 실행하고 model raw output을 prediction JSONL에 보존한다.

Real baseline run은 최소한 다음 dataset 중 하나를 대상으로 수행합니다.

- `tests/fixtures/heldout_evaluation_records.jsonl`
- Owner가 승인한 metadata-only 또는 synthetic evaluation dataset

Baseline prediction JSONL은 다음 정보를 포함해야 합니다.

- `record_id`
- `model_id`
- `run_id`
- `raw_output`
- 가능하면 `latency_ms`, `generated_at`, runtime metadata

## 4. Evaluation Result Requirements

Evaluation 결과는 다음 산출물로 기록합니다.

- `evaluation_summary.json`: machine-readable metrics와 hard gate 결과
- `evaluation_report.html`: 사람이 검토할 record별 결과와 오류 요약
- experiment log entry: command, environment, inputs, artifact paths, metrics, failure modes, interpretation, follow-up

필수 기록 metric:

- total_count
- composite_score
- hard_gate_pass_rate
- json_parse_success_rate
- schema_validation_pass_rate
- safety_pass_rate
- required_field_completeness
- risk_level_match_rate
- attack_mapping_precision / recall / f1
- hallucinated_attack_mapping_count
- evidence_discipline_rate
- latency metric, 측정할 수 없는 경우 N/A

## 5. Failure Mode Requirements

Phase E로 넘어가기 전에 다음 failure mode를 count와 짧은 해석으로 기록합니다.

- invalid JSON
- missing required fields
- invalid enum
- unsafe or overly actionable guidance
- risk level mismatch
- hallucinated ATT&CK mapping
- evidence 없는 behavior 또는 mapping
- empty or vague recommendations
- latency or runtime failure
- model load or tokenizer/chat-template failure

Baseline 실패는 Phase E 착수를 자동으로 막지 않습니다. 다만 실패 유형이 기록되지 않았거나 adapter와 비교할 기준선이 없는 경우 Phase E를 시작하지 않습니다.

## 6. Storage and Git Policy

Git에 커밋할 수 있는 항목:

- source code
- prompt templates
- schema and validators
- small metadata-only or synthetic fixtures
- documentation
- experiment log template 또는 민감정보가 제거된 짧은 예시

Git에 커밋하지 않는 항목:

- prediction JSONL generated from actual model runs
- `evaluation_summary.json` generated from actual runs
- `evaluation_report.html` generated from actual runs
- raw datasets
- model checkpoints
- LoRA/QLoRA adapter artifacts
- Hugging Face tokens, API keys, secrets
- private CTI or private customer data
- actual malware samples or executable payloads

Generated output은 기본적으로 `outputs/`, `runs/`, `artifacts/`, `experiments/` 또는 승인된 외부 저장소에 둡니다. 외부 artifact는 experiment log에 identifier, path, version tag, provenance note만 기록합니다.

## 7. Go / No-Go Checklist

Phase E tiny SFT PoC로 넘어가기 전 확인합니다.

- [ ] real baseline inference run이 target environment에서 실행되었다.
- [ ] prediction JSONL이 생성되고 raw output이 보존되었다.
- [ ] evaluation summary JSON과 HTML report가 생성되었다.
- [ ] experiment log entry가 작성되었다.
- [ ] 주요 failure mode가 기록되었다.
- [ ] held-out evaluation fixture가 training data에서 제외되었다.
- [ ] generated artifacts가 Git 밖에 저장되었다.
- [ ] Phase E에서 사용할 dataset, adapter storage, evaluation fixture가 명시되었다.
- [ ] Owner가 Phase E tiny SFT PoC 착수를 승인했다.

## 8. Related Work

- Linear: THE-61
- Blockers completed: THE-58, THE-59, THE-60
- `docs/EVALUATION_PLAN.md`
- `docs/EXPERIMENT_LOG_TEMPLATE.md`
- `docs/ARTIFACT_STORAGE_POLICY.md`
- `docs/FINETUNING_EXPERIMENT_PLAN.md`
