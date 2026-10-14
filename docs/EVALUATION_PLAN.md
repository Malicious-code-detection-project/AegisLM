# Evaluation Plan

이 문서는 Phase D/E에서 baseline과 adapter 결과를 같은 방식으로 비교하기 위한 평가 기준을 정의합니다.

2026-10-13 후속 프로젝트 검증은 사용자 결정에 따라 **판정 / 근거 / 권고사항**
세 항목을 대상으로 설계한다. 심각도는 후속 과제다.
[외부 벤치마크 조사와 적용안](#2026-10-13-benchmark-scoring)은 설계 기록이며,
아래 기존 Phase C/D contract·종합점수나 현재 scorer를 변경한 구현은 아니다.
2026-10-14에는 [확정 사항·파일럿 준비 순서·미결정 항목](#2026-10-14-three-field-pilot)을
정리했다. 파일럿 수량과 채점 방식은 제안 단계이며 GPU 실행은 시작하지 않았다.

Phase C의 `JSON output contract`, tiny fixture, schema validation은 유지하고, 그 위에 파인튜닝 전후 비교용 evaluation harness를 둡니다. 이 계획은 모델 학습을 수행하지 않습니다. 목적은 학습 전에 결과 표현, 점수화, 실패 기준을 고정하는 것입니다. Phase D 완료 여부와 Phase E 착수 gate는 [PHASE_D_EXIT_CRITERIA.md](PHASE_D_EXIT_CRITERIA.md)를 따릅니다.

## 1. Evaluation Scope

평가 대상:

- baseline model output
- tiny SFT adapter output
- 이후 확장 adapter output

평가 입력:

- evaluation dataset JSONL
- prediction JSONL

Phase D/E adapter 비교용 held-out fixture는 `tests/fixtures/heldout_evaluation_records.jsonl`에 둔다. 이 파일은 `test` split이며 adapter training data로 사용하지 않는다.

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

필수 필드는 `record_id`, `model_id`, `run_id`, `raw_output`입니다. 일반
evaluation 경로에서 `raw_output`은 모델이 실제로 반환한 원문 문자열입니다.
Source-v2 canonical Unsloth 경로는 예외적으로 전체 Harmony suffix를
`raw_generation`에, 그 final channel에서 추출한 점수화 문자열을
`raw_output`에 저장하고 `generation`에 종료 메타데이터를 둡니다. 평가기는
이 envelope를 다시 추출·검증하고 두 문자열이 다르면 결과를 거부합니다.

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

두 산출물은 기본적으로 Git에 커밋하지 않습니다. `outputs/`, `runs/`, `artifacts/`, `experiments/` 같은 Git 제외 경로에 저장합니다. 큐레이션된 예시 report만 별도 이슈와 Owner 확인 후 커밋할 수 있습니다. Phase D 종료 전에는 [PHASE_D_EXIT_CRITERIA.md](PHASE_D_EXIT_CRITERIA.md)의 storage and Git policy를 함께 확인합니다.

## 7. Benchmarking Policy

v0의 1차 benchmark는 로컬 held-out fixture와 Project NuriLab synthetic fixture입니다. `tests/fixtures/heldout_evaluation_records.jsonl`은 benign, KEV exploited, non-KEV high severity, ambiguous ATT&CK mapping, safety refusal 후보를 포함하는 고정 비교 세트입니다.

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
  --dataset tests/fixtures/heldout_evaluation_records.jsonl \
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

## 9. Phase D Fixture Smoke Run

THE-58에서는 Phase C tiny fixture를 사용해 baseline prediction JSONL 생성부터 evaluation summary/report 생성까지의 흐름을 확인합니다.

로컬 smoke run은 실제 모델 benchmark가 아닙니다. `--backend mock`은 evaluation harness가 invalid or incomplete model output을 어떻게 기록하는지 확인하기 위한 재현 가능한 실패 기준선입니다.

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

예상 관찰:

- prediction JSONL, `evaluation_summary.json`, `evaluation_report.html`이 생성된다.
- mock output은 JSON parse에는 성공하지만 required fields가 부족해 schema/hard gate는 실패한다.
- 이 실패 결과는 harness 검증용이며, 실제 `openai/gpt-oss-20b` baseline 점수로 기록하지 않는다.
- `outputs/`는 Git 제외 경로이므로 생성 산출물은 커밋하지 않는다.

## 10. Source-v2 Base/Adapter Comparison

The source-v2 path is separate from the historical Phase C ATT&CK/risk harness.
Both base and adapter runs use identical challenge messages, tokenizer/chat
template, decoding mode, max_new_tokens, temperature, and hardware.
Prediction artifacts record challenge and prediction-file digests, the
tokenizer contract digest, pinned base revision, complete adapter-directory
digest, decoding settings, package versions, and hardware signature. The
comparison command rejects missing or mismatched case, decoding, tokenizer,
revision, or hardware provenance.
It also requires distinct base/adapter run roles, no adapter fingerprint on the
base run, and a valid SHA-256 complete-artifact fingerprint on the adapter run.
The weight-only digest is diagnostic and never substitutes for the artifact
identity. Unsloth
inference aborts if requested, adapter-declared, and resolved base identity or
revision differ or the runtime does not expose an actual resolved revision.

Gold isolation is mandatory. scripts/run_source_inference.py accepts only
challenge JSONL containing system/user messages. gold.jsonl is first loaded by
scripts/evaluate_source_predictions.py after prediction generation completes.

Report these evaluations separately:

- primary: phase-f-source-v5-r1 500-record full-report challenge
- secondary: phase-f-source-untouched-blind-480-v1 480-record decision-only
  challenge

The primary set is held out from training but is not called fully blind if it
was visible during pipeline development. The secondary set supports label
metrics only; evidence metrics remain null and are not combined with primary
metrics.

The decision-only evaluator requires both `present` and `not_observed` in the
gold cohort for its binary-label coverage gate. Prediction diversity does not
satisfy that gate. Non-string `assessment` values (including arrays and objects)
are schema-invalid predictions recorded in the report, not evaluation crashes.
For evidence-line evaluation, the challenge's complete `numbered_source_code`
must equal `number_source_code(private_source_code)` before scoring or rendering.
Matching IDs and line counts alone are insufficient; mismatched inputs raise
`ValueError` instead of producing evidence scores.

Automatic source-v2 metrics:

- assessment accuracy, confusion matrix, macro-F1, and per-label recall
- per-CWE accuracy, with major slices defined as n >= 20
- JSON parse/schema rates and required-field completeness
- exact evidence span precision, recall, F1, grounding, missing, hallucinated
- safety violation count and mean latency
- experiment-log peak VRAM and wall time

Outcome rules:

- primary full-report improved: macro-F1 and evidence F1 both rise at least 3
  points
- secondary decision-only improved: macro-F1 rises at least 3 points; evidence
  remains not applicable
- regressed: any label recall falls more than 2 points, or a major CWE slice
  falls more than 5 points
- equivalent: neither condition applies

Operational targets are recorded separately: JSON parse/schema at least 99%,
grounded spans 100%, and zero safety violations. Missing a target documents a
limitation; it does not erase a reproducible adapter.

Primary commands:

    uv run python scripts/run_source_inference.py \
      --dataset data/processed/phase-f-source-v5-r1/challenge.jsonl \
      --predictions outputs/source-v2/base-primary.jsonl \
      --model-id unsloth/gpt-oss-20b-unsloth-bnb-4bit \
      --model-revision 093fba6992ef5a7152481afec0bdfca1ac486998 \
      --run-id base-primary --backend unsloth

    uv run python scripts/run_source_inference.py \
      --dataset data/processed/phase-f-source-v5-r1/challenge.jsonl \
      --predictions outputs/source-v2/adapter-primary.jsonl \
      --model-id source-v2-qlora \
      --base-model-id unsloth/gpt-oss-20b-unsloth-bnb-4bit \
      --model-revision 093fba6992ef5a7152481afec0bdfca1ac486998 \
      --adapter-path adapters/source-v2-qlora/full/final \
      --run-id adapter-primary --backend unsloth

    uv run python scripts/evaluate_source_predictions.py \
      --challenge data/processed/phase-f-source-v5-r1/challenge.jsonl \
      --gold data/processed/phase-f-source-v5-r1/gold.jsonl \
      --predictions outputs/source-v2/base-primary.jsonl \
      --summary-json outputs/source-v2/base-primary-summary.json \
      --report-html outputs/source-v2/base-primary.html

    uv run python scripts/evaluate_source_predictions.py \
      --challenge data/processed/phase-f-source-v5-r1/challenge.jsonl \
      --gold data/processed/phase-f-source-v5-r1/gold.jsonl \
      --predictions outputs/source-v2/adapter-primary.jsonl \
      --summary-json outputs/source-v2/adapter-primary-summary.json \
      --report-html outputs/source-v2/adapter-primary.html

    uv run python scripts/compare_source_runs.py \
      --base-summary outputs/source-v2/base-primary-summary.json \
      --adapter-summary outputs/source-v2/adapter-primary-summary.json \
      --output outputs/source-v2/primary-comparison.json

Repeat the two inference and evaluation commands for
`data/processed/phase-f-source-untouched-blind-480-v1/challenge.jsonl` and its
`gold.jsonl`, using distinct `base-secondary` and `adapter-secondary` run IDs
and output paths. Compare those summaries separately; decision-only evidence
metrics remain null and must not be combined with the primary report.

    uv run python scripts/run_source_inference.py \
      --dataset data/processed/phase-f-source-untouched-blind-480-v1/challenge.jsonl \
      --predictions outputs/source-v2/base-secondary.jsonl \
      --model-id unsloth/gpt-oss-20b-unsloth-bnb-4bit \
      --model-revision 093fba6992ef5a7152481afec0bdfca1ac486998 \
      --run-id base-secondary --backend unsloth

    uv run python scripts/run_source_inference.py \
      --dataset data/processed/phase-f-source-untouched-blind-480-v1/challenge.jsonl \
      --predictions outputs/source-v2/adapter-secondary.jsonl \
      --model-id source-v2-qlora \
      --base-model-id unsloth/gpt-oss-20b-unsloth-bnb-4bit \
      --model-revision 093fba6992ef5a7152481afec0bdfca1ac486998 \
      --adapter-path adapters/source-v2-qlora/full/final \
      --run-id adapter-secondary --backend unsloth

    uv run python scripts/evaluate_source_predictions.py \
      --challenge data/processed/phase-f-source-untouched-blind-480-v1/challenge.jsonl \
      --gold data/processed/phase-f-source-untouched-blind-480-v1/gold.jsonl \
      --predictions outputs/source-v2/base-secondary.jsonl \
      --summary-json outputs/source-v2/base-secondary-summary.json \
      --report-html outputs/source-v2/base-secondary.html

    uv run python scripts/evaluate_source_predictions.py \
      --challenge data/processed/phase-f-source-untouched-blind-480-v1/challenge.jsonl \
      --gold data/processed/phase-f-source-untouched-blind-480-v1/gold.jsonl \
      --predictions outputs/source-v2/adapter-secondary.jsonl \
      --summary-json outputs/source-v2/adapter-secondary-summary.json \
      --report-html outputs/source-v2/adapter-secondary.html

    uv run python scripts/compare_source_runs.py \
      --base-summary outputs/source-v2/base-secondary-summary.json \
      --adapter-summary outputs/source-v2/adapter-secondary-summary.json \
      --output outputs/source-v2/secondary-comparison.json

Raw Unsloth generation is the canonical local mode. An explicitly numeric
loopback (`127.0.0.0/8` or `::1`) OpenAI-compatible endpoint may
additionally use constrained JSON-schema mode. Non-loopback URLs, URL
credentials, redirects, query strings, and fragments are rejected before a
source-bearing request is built. The client installs an empty proxy handler so
ambient HTTP(S) proxy variables cannot route the request off-host.
Raw and constrained results are never combined into one score. The HTTP client
does not follow redirects while carrying the optional bearer credential, caps
the response and message-content byte sizes, and applies the same strict JSON
nesting/non-finite-number checks used by local artifacts.

Source-v2 local comparison uses batch size 1 until the pinned Unsloth runtime's
batch-dependent generation divergence is resolved. Generation explicitly binds
low reasoning, left padding, pad token 200017, EOS tokens 200002/199999, and a
512-token ceiling with a 2,048-token sequence limit. Canonical Unsloth commands
reject different limits instead of silently retaining the same protocol name.
Every non-legacy training config enforces those same 512/2,048 values, so an
edited training or checkpoint-diagnostic config cannot bypass the inference
contract.
Post-EOS batch padding is removed before decoding and each
case preserves the raw Harmony suffix and records its bounded generated token
IDs, finish reason, generated-token count, terminating EOS ID, and Harmony
flags. The extracted final-channel text is stored separately for scoring. Gate
rescoring uses the resolved `GenerationContract` rather than a permissive
default: it independently checks the configured EOS set and ceiling, first-EOS
trim, raw trailing EOS marker, token count, finish reason, and Harmony flags.
Missing or tampered provenance is a run failure; a complete but malformed or
empty model response remains a scored case failure and does not abort the
evaluation batch. The resolved protocol and its digest are part
of inference provenance and therefore must match between base and adapter.
Balanced-JSON salvage,
forced prefixes, and constrained decoding remain diagnostic modes and never
contribute to the canonical raw score.

Source inference, evaluation JSON/HTML, comparison JSON, receipts, and
checkpoint diagnostics must resolve to distinct Git-ignored/external paths.
The Unsloth model/tokenizer cache is validated as Git-ignored or external and
symlink-free before either pinned or legacy loader is imported or called. An
implicit library-default cache (`cache_dir=None`) is rejected.
Writers reject output symlinks and never overwrite different existing bytes;
idempotent evaluation/comparison reruns accept only byte-identical local
results. Every comparison JSON embeds the exact base and adapter summary-file
SHA-256 digests; its local bytes and deterministic W&B receipt/run identity
therefore differ when either input artifact differs, even if aggregate metrics
are identical. Inputs cannot alias outputs, and checkpoint diagnostic directories are
reserved before model or W&B initialization.

The older `run_adapter_inference.py` entrypoint remains available only for the
Phase D/E generic adapter smoke flow. Without explicit base identity and
revision it uses a marked unpinned legacy path and cannot produce a source-v2
comparable run. Canonical comparisons use `run_source_inference.py` with pinned
identity and the strict raw-generation envelope.

For a local adapter run, the complete symlink-free adapter tree is hashed and
the adapter declaration is checked before the base model is loaded. The saved
tokenizer is loaded locally and must fingerprint identically to the pinned base
tokenizer under the resolved contract. The adapter tree is checked again before
and after each response; provenance is published only after that stable check.
Checkpoint diagnostics record the full tree digest and persisted-tokenizer
fingerprint when an adapter is used.

As of 2026-09-11, the original 1,000-record Unsloth canary and both explicit
batch-1 recovery canaries (`unsloth_v2` and `peft_split_control`) failed their
held-out contract gate at 0/40. The recovery adapters were freshly reloaded and
contained the expected 576 finite attention/expert LoRA tensors. Full training
and the primary/secondary base-versus-adapter comparison remain NOT_RUN. This
is a training-path failure, not a comparison outcome of improved, equivalent,
or regressed. The W&B runs `mdotwa7l` and `4a0wl8na` retain aggregate failure
evidence only; local JSON remains the result SSOT.

### W&B tracking

Append `--wandb` to either source-v2 evaluation command and the comparison
command to create online runs. All commands still write their canonical local
JSON/HTML artifacts first; W&B is an opt-in tracking view, not the result SSOT.
Each tracked evaluation or comparison writes a sibling `*.wandb.json` receipt
containing the local result digest and W&B run ID/URL. The deterministic run ID
uses `resume="never"` initially, `resume="allow"` only for an interrupted
same-digest receipt, and no-ops after a completed receipt. The caller holds an
exclusive non-blocking receipt claim until W&B finish; concurrent invocations
fail before remote initialization and cannot duplicate tables or metrics. A
logged-but-unfinished retry reopens the same run for finish only and skips the
evaluation table, comparison payload, and metric logging. A
`logging_ambiguous` receipt blocks automatic retry until the operator inspects
the deterministic run and passes `--wandb-reconcile retry-logging` or
`--wandb-reconcile finish-only`.

Evaluation runs upload only the documented aggregate metrics and a safe case
table containing record ID, target CWE, expected/predicted assessment, boolean
parse/schema/safety/correctness flags, evidence error counts, and latency. The
table never contains C/C++ source, prompts, raw model output, validation error
text, or evidence spans. Comparison runs upload aggregate deltas, quality-target
flags, and regression counts only. Their outcome, mode, delta keys/ranges,
quality-target keys/types, and regression label/CWE domains are projected and
validated before W&B initialization; the logging helper repeats that projection
so direct callers cannot bypass it.

Expected assessments must be one of the schema labels. An invalid or missing
model assessment is converted to the fixed `invalid` sentinel before W&B
initialization; the model-provided value is never copied into the table.

Record IDs, CWE IDs, model IDs, revisions, content digests, backend/mode/role,
package names/versions, decoding numbers, and hardware fingerprint are checked
against bounded semantic domains before they enter W&B. Unknown package keys,
source-like strings, non-finite values, and loaded credentials in either mapping
keys or values are rejected without echoing the untrusted value.

All W&B run types use project `aegislm` and group `source-v2`. Source-code,
Git-diff, console, CLI arguments, host/program metadata, system statistics,
dependency snapshots, model, checkpoint, adapter, and raw artifact upload are
disabled. The stock Transformers W&B callback is also disabled; training uses
an allowlisted scalar-only callback. The commit SHA and a dirty-worktree boolean
are recorded manually; file names and diff contents are not. This policy follows the supported
[W&B environment controls](https://docs.wandb.ai/models/track/environment-variables)
and the [W&B Transformers integration](https://docs.wandb.ai/models/integrations/huggingface).

### Native tutorial validation100 generation tracking

The 2026-10-05 native step100 sweep uses an opt-in CPU tracking sidecar while
generation continues unchanged. It reads saved evaluation snapshots and records
them in an `evaluation` run, not a training run. It can backfill already completed
evaluations; it does not recreate missing training losses or historical GPU stats.

Each configured model has six budget groups with 100 planned cases each:
base plus adapter plans 1,200 calls; an explicitly selected base-only run plans
600. The tracker requires every configured group exactly once and rejects
missing, duplicate, or unexpected groups. Planned and completed counts follow
that configuration in both W&B metrics and local tracking progress.
Upload only completed,
pending, complete flags and the semantic/strict TP/FN/FP/TN/uncertain/invalid
counts. Positive and negative completed counts expose partial-cohort imbalance.
`label_match_over_completed` has the completed-case denominator and is explicitly
partial until a group reaches 100. Pending cases never enter confusion matrices.

After a group completes, its safe table columns are `model`, `generation_budget`,
`record_id`, `expected_assessment`, `semantic_assessment`, `strict_assessment`,
`json_valid`, `schema_valid`, `generated_tokens`, `stop_reason`. Predicted values
are projected to present/not_observed/uncertain/invalid. Semantic and strict
confusion charts contain only these fixed labels and counts; empty uncertain and
invalid ground-truth rows in the square W&B chart are not extra source labels.
Source, prompts, parsed extra fields, raw output, error messages and token IDs
are not sent. The sidecar uses the existing project/group, privacy controls,
deterministic evaluation receipt and exclusive ownership lock. An ambiguous
tracking interruption requires remote inspection and explicit reconciliation,
as with standard evaluation receipts; no automatic replay occurs.

<a id="2026-10-10-project-evaluation-proposal"></a>

## 2026-10-10: 취약점 포함 프로젝트 평가 논의 — 아직 미실행

사용자는 실제 취약점이 정상 코드와 함께 존재하는 C/C++ 프로젝트에서 모델의
발견 능력을 확인할 필요를 제기했다. 다음 내용은 후속 평가 설계 제안이며, 기존
함수 단위 scorer·schema·평가 gate를 변경하거나 새 GPU 실행을 승인한 기록이 아니다.
데이터 선택과 사례 검증은 아직 완료되지 않았다.

현재 근거는 [동적 캐시 base·adapter 1200회 결과](FINETUNING_EXPERIMENT_PLAN.md#2026-10-10-dynamic-cache-results)다.
128 상한은 양쪽 모두 출력 오류 100건이었고, adapter/130000은 semantic 기준
출력 오류 7건으로 가장 적었다. 그러나 실제 양성 50건 중 정탐 20·미탐 27·출력
오류 3건이므로 출력 완성과 올바른 취약점 판단을 구분해야 한다. 상한별 seed가
고정되지 않아 최고 점수를 생성 상한의 인과 효과로 단정하지 않는다.

### 입력과 정답의 분리

| 구분 | 보유 자료·평가 질문 |
| --- | --- |
| 모델 입력 | 취약 버전의 프로젝트 소스. 프로젝트 탐색 평가에서는 취약 위치·정답 CWE·패치를 알려주지 않음 |
| 평가자 정답 | 대상 취약점, 소스 revision, 수정 패치, 재현 근거, 확인한 원인과 위치 |
| 취약 버전 평가 | 알려진 문제의 위치와 원인을 실제로 발견했는가? |
| 수정 버전 대조 | 해당 문제가 제거된 뒤에도 같은 문제를 있다고 보고하는가? |

현재 함수 평가에서 target CWE를 제공한 조건과, CWE·위치를 주지 않는 프로젝트
탐색은 다른 과업이다. 두 결과를 같은 confusion matrix로 합치지 않는다.
패치·취약점 보고서·재현 오류 위치와 벤치마크 정답 표식은 모델 입력에서 분리한다.
수정 버전 전체 또는 알려진 취약점이 없는 함수를 일괄 음성으로 라벨링하지 않는다.
정답 목록에 없는 새 경고도 검수 없이 모두 FP로 처리하지 않는다.

### 단계별 비교 제안

1. 알려진 취약 함수에 호출자·피호출자·타입 정의를 함께 제공해 판단 능력을 확인한다.
2. 같은 사례의 전체 프로젝트에서 관련 코드를 찾고 판단하도록 해 탐색 능력을 확인한다.
3. 같은 소스를 직접 빌드한 바이너리에서 추출한 표현으로 비교한다. 바이너리 경로는 별도 실험이다.

1단계는 위치를 알고 제공하는 진단 실험이므로 프로젝트 전체에서 스스로 발견한
성능으로 보고하지 않는다. 2단계에서는 필요한 코드가 모델에게 도달하지 못한
검색 실패와, 도달한 근거를 잘못 해석한 판단 실패를 구분해 기록한다.
프로젝트 전체를 단일 프롬프트에 넣을 수 있다고 가정하지 않는다.

첫 후보는 소수의 ARVO 검증 사례이며, Magma와 OSS-Fuzz 기록을 대안으로 검토한다.
구체적인 프로젝트·사례 수는 아직 선택하지 않았다. libtiff(C)·Poppler(C++)는 대화에서
예시로 든 후보일 뿐 채택된 평가 세트가 아니다.
[공급처·다운로드 위치·기존 ARVO 검수 이력](DATASET_CANDIDATES.md#2026-10-10-vulnerable-project-candidates)을 먼저 확인한다.

사례 채택 시 기존 학습/validation/test와 프로젝트·commit·함수 중복을 확인하고,
동일 취약점의 수정 전후는 같은 평가 분할에 묶는다. 공개 사례가 사전학습에
포함됐는지는 별도 확인 한계로 남긴다. raw 소스·바이너리·재현 자료는 Git 밖에
보존하고, 모델·revision·탐색 도구·입력 문맥·생성 조건·호출 예산을 base/adapter에
동일하게 적용한다. 최종 평가 단위와 판정 일치 규칙은 구현 전에 확정해야 한다.

### 남은 작업

- 현재 adapter 미탐 사례의 원천 라벨·제공 문맥·응답을 대조한다. 양성 근거 부족과 모델의 누락을 구분한다.
- Harmony 파싱 실패는 원 token을 확인해 파서가 지원하지 않는 표현과 잘못 생성된 헤더를 구분한다.
- adapter W&B의 artifact 이름 길이 오류는 다음 실행 전에 수정·검증할 대상이다. 아래 2026-10-11 결정에 따라 기존 실행은 재전송하지 않는다. 로컬 생성·채점 600건은 완료됐고 원격 추적은 590건에서 중단된 이력을 보존한다.
- 프로젝트 후보의 취약·수정 대응 및 재현 가능성을 검증한 뒤 평가 세트를 확정한다.

이번 문서화에서는 위 작업을 새로 실행하거나 추적 오류를 복구하지 않았다.

## 2026-10-11: 이후 학습·평가의 W&B 필수 포함

사용자는 기존 동적 캐시 실험의 W&B 추가 업로드는 하지 않고 로컬 최종 결과로
마무리하되, 다음부터 진행하는 학습·평가에는 W&B를 반드시 포함하도록 지시했다.
기존 base·adapter 생성·채점 및 비교분석은 완료된 작업으로 취급하며, adapter의
590/600 원격 추적 기록을 600/600 업로드 완료로 표시하지 않는다.

새 학습·평가 실험의 진행 기준은 다음과 같다.

- 시작 전에 W&B run 생성·연결과 run URL 기록을 확인한다. 연결되지 않은 상태로 본 실험을 시작하지 않는다.
- 실험 종류에 맞는 허용된 학습 지표·평가 집계와 진행도를 기록한다. 원문 소스·프롬프트·원시 응답 비전송 정책은 유지한다.
- 종료 후 로컬 최종 결과와 W&B 최종 집계·종료 기록을 대조한다. 추적 오류가 있으면 실행 결과와 추적 상태를 나누어 보고하고, 추적까지 완료됐다고 선언하지 않는다.
- 추적 복구는 저장된 로컬 결과와 기존 receipt를 보존하며 진행한다. W&B 오류만을 이유로 GPU 실험을 다시 실행하지 않는다.

이는 이후 실험의 운영 기준이다. 기존 CLI의 opt-in 인터페이스를 이번 문서 수정으로
변경한 것은 아니며, 새 실행 명령·계획에는 W&B 활성화를 명시한다.

## 2026-10-11: 프로젝트 평가에서도 동적 캐시·생성 상한별 비교 유지

사용자는 후속 프로젝트 평가도 동적 캐시와 생성 토큰 길이별로 진행할 필요를
명시했다. 따라서 모델과 생성 상한을 비교 축으로 유지하며, cache policy는
`dynamic`으로 고정한다. 아래 조건은 평가 준비에 반영할 기준이며, 프로젝트
선정·호출 예산·탐색 방식이 확정되기 전에 GPU 실행을 시작하는 승인은 아니다.

| 항목 | 후속 평가 조건 |
| --- | --- |
| 모델 | 동일 기준의 base와 A6000 100-step adapter |
| 캐시 | 두 모델 모두 DynamicCache, 실제 사용 증거 기록 |
| 생성 상한 | 128, 512, 2048, 65536, 130000, context-minus-input |
| 입력 | 모델·상한 간 동일 평가 사례 사용. 직접 판단 비교에서는 동일한 입력 문맥 사용 |
| GPU 초기화 | 모델·상한 조건마다 기존 worker 종료 후 새 프로세스에서 모델 재로딩 |
| 추적 | W&B 필수. 모델·상한별 결과와 실행 실패를 구분해 기록 |
| 결과 | 실제 생성 토큰 수·종료 이유·출력 유효성·판단 결과와 메모리 기록 |

생성 상한은 실제 생성 길이가 아니다. 이전 함수 평가에서 128의 최종 출력이
모두 실패했더라도 후속 프로젝트 입력에서의 결과는 새로 관측한다. 130000의
관측 점수가 가장 좋았다는 이유로 그 조건만 선택하지 않는다.

프로젝트 문맥이 길어지면 `입력 토큰 + 생성 상한`이 런타임 문맥 한도를 넘을 수
있다. 각 입력에서 실행 가능한 상한을 사전에 확인하고, 불가능한 고정 상한은
실행 불가로 표시한다. 입력을 몰래 자르거나 상한을 낮추어 같은 조건으로
보고하지 않는다. `context-minus-input`은 실제 입력 토큰을 제외한 잔여 예산이다.

직접 판단을 한 사례당 한 번 호출하면, N개 사례의 명목 호출 수는
2모델 × 6상한 × N이다. 취약·수정 버전을 각각 평가하면 두 버전을 별도 입력으로
계수한다. 여러 차례 검색·도구 호출이 필요한 프로젝트 탐색은 이 계산에 그대로
포함하지 않으며, 호출당 생성 상한과 사례당 전체 호출·토큰 예산을 별도로 정한다.

기존 실험의 조건별 비고정 RNG 한계를 반복하지 않도록, 후속 실행 전에 seed와
반복 횟수 정책을 확정한다. 탐색 경로가 달라져 모델이 읽은 코드가 달라지는
경우에는 동일 문맥 판단 비교와 별도의 전체 탐색 결과로 해석한다.

<a id="2026-10-12-a6000-verification-transition"></a>

## 2026-10-12: A6000 파인튜닝 종료·프로젝트 검증 준비 착수

사용자는 A6000의 GPT 파인튜닝을 현재 단계에서 마치고 검증을 시작하기로 했다.
기존 100-step adapter를 검증 대상으로 고정하고 추가 학습·CPT·아키텍처 변경은
이번 범위에서 수행하지 않는다. 완료한 함수 평가 1200건과 캐시 비교·분석은
그대로 보존하며 프로젝트 검증과 별도의 결과로 취급한다.

착수 시 다음 두 CPU 명령을 실행했고 모두 `status=verified`로 종료했다.
이 검사는 기존 동결 입력·adapter·실행기 무결성 확인이며 새 프로젝트 평가의
성능이나 GPU 실행 가능성을 검증한 것은 아니다.

```bash
python3 scripts/run_cc_native_validation100.py verify --config configs/cc_dynamic_base_validation100_v1.json
python3 scripts/run_cc_native_validation100.py verify --config configs/cc_dynamic_adapter_validation100_v1.json
```

기존 ARVO `manual-review-result.json`도 직접 확인했다. 11건의 조기 검수 실패는
기록된 crash family와 패치 근거의 불일치로 보고됐다. 예를 들어 libsass의
selector 비교 변경이나 fluent-bit의 해제 후 NULL 반환 변경이 버퍼 범위 밖
읽기의 직접 근거인지 확인되지 않았다. 따라서 crash 유형을 그대로 CWE 정답으로
변환하지 않고, 사례별 소스·패치·재현의 대응부터 검증한다.

후속 준비는 영문 CWE XML 원본→JSON→Markdown과 조회 경로, 프로젝트 사례 검수,
모델 입력·평가자 정답 분리 순서로 진행한다. CWE는 우선 참조 문서로 관리하며
사전 내용을 추가 학습하지 않는다.
영문 CWE 4.20 XML→JSON→Markdown 및 ID·키워드 조회는 CPU 검증까지 완료했다.
[변환 계약·검증 기록](DATA_STRATEGY.md#2026-10-12-cwe-reference)을 따른다.
일반 설명의 잔여 CVE 언급 3개 항목은 모델 연결 전 사례별 누출 검토 대상이다.
프로젝트 gold 검수와 모델 RAG 연결·성능 비교는 아직 미완료다.
새 GPU 평가는 앞 절의 DynamicCache·6개 생성 상한·조건별 모델 재로딩·W&B 필수
기준을 따른다. 후보·호출 예산을 확정하고, 이전에 관측한 NVML 드라이버/라이브러리
불일치 및 W&B artifact 이름 길이 문제를 확인한 뒤 실행한다. 이번 착수에서는
시스템 변경·이미지 실행·GPU 생성·W&B 전송을 수행하지 않았다.

<a id="2026-10-13-benchmark-scoring"></a>

## 2026-10-13: 외부 보안 평가의 채점 기준과 세 항목 평가 적용안

### 결정과 조사 범위

사용자가 정한 모델 결과 항목은 **판정 / 근거 / 권고사항** 세 가지다.
판정 값은 `present`, `not_observed`, `uncertain`을 기준으로 논의했으며,
심각도·치명도는 이후 개발 범위로 남긴다. 참조 순서는 CWE, 보완할 외부 기준·검수된
벤치마크 자료, 근거 부족 시 추가 검토다. 참조 분류를 찾지 못한 것과 취약성이
관측되지 않은 것은 다른 상태다. 출처·버전·소스 hash·검토 이력은 평가자 metadata로
보관하며 모델에 네 번째 출력 항목을 요구하지 않는다.

2026-10-13에 아래 공식 문서·원 논문·공개 채점 코드를 확인했다. 기관별 점수는
측정 대상이 다르므로 동일한 보안 종합점수로 비교하지 않는다. 이 절은 조사 및
적용 제안이며, 외부 benchmark 실행·모델 평가·새 scorer 구현 결과가 아니다.

### 1. OWASP Foundation — Benchmark

각 테스트의 의도한 CWE와 취약 여부를 expected results로 고정하고 TP/FN/TN/FP를
계수한다. TPR=`TP/(TP+FN)`, FPR=`FP/(FP+TN)`, 분류별 점수는 Youden 지수
`TPR-FPR`다. 전부 취약하다고 보고하면 TPR과 FPR이 모두 1이므로 점수는 0이다.
가령 TPR 0.8, FPR 0.1이면 점수 0.7이다. 음수도 가능하며 accuracy와 다른 지표다.
현재 안내의 테스트 언어는 Java/Python이고 실제 프로그램보다 단순한 사례라는
한계를 명시한다. C/C++ 프로젝트에는 채점 원리를 참고하며 직접 점수를 비교하지 않는다.
[공식 채점 설명](https://owasp.org/projects/benchmark?tab=scoring).

**적용 제안:** 양성과 검증된 음성을 함께 구성하고 confusion matrix, 탐지율,
오탐률을 우선 보고한다. CWE별 결과와 전체 결과를 구분하고 macro 평균인지
전체 건수를 합산한 micro 집계인지 명시한다. 불확실·출력 오류가 있는 현재 문제에
OWASP 이진 점수를 그대로 붙이지 않는다.

### 2. NIST SAMATE — SATE / Juliet

SATE는 최고의 제품을 뽑는 인증·순위 경쟁이 아닌 도구 효과성 연구다.
SATE V 보고서는 precision, recall, 탐지 가능한 약점 종류의 coverage,
지원 약점만을 대상으로 한 applicable recall과 취약·수정 코드 구분 능력을 다룬다.
보고서 §3.3.5.5의 discrimination은 취약 코드 탐지와 대응 수정 코드 비탐지가
함께 성립해야 성공으로 인정한다. 합성 자료의 양성 비율에서 얻은 precision을
실제 프로그램 precision과 직접 비교하지 않도록 설명한다.
[SATE 소개](https://www.nist.gov/itl/csd/secure-systems-and-applications/samate/static-analysis-tool-exposition-sate),
[SATE V, §1.5·§3.3.5](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.500-326.pdf).

**적용 제안:** 취약·수정 쌍의 두 판정을 모두 맞힌 비율을 기록한다. 지원 범위 밖
CWE를 결과를 본 뒤 제외하지 않고 평가 전 범위와 전체 분모를 고정한다.
여기서 NIST의 coverage는 약점 종류 범위이며 아래의 모델 응답률과 별개다.

### 3. PrimeVul 연구팀 — 실제 C/C++ 취약점 탐지

논문 §IV는 commit 기준 시간순 분할과 취약·수정 쌍 평가를 제안한다.
VD-S는 `FNR @ FPR <= 0.5%`이며 **낮을수록 좋다**. 공개 구현은 양성 예측
확률로 ROC를 만들고 허용 FPR 이하의 지점에서 FNR을 계산한다.
쌍 평가에는 둘 다 정답, 둘 다 취약, 둘 다 비취약, 반대로 판정한 결과를 구분한다.
[원 논문 §IV](https://arxiv.org/html/2403.18624v2),
[공개 VD-S 구현](https://github.com/DLVulDet/PrimeVul/blob/main/calc_vd_score.py).

**적용 제안:** 쌍 비교와 데이터 분리 원칙을 우선 채택할 후보로 둔다.
현재 세 항목 응답에는 임계값 조절용 연속 점수가 없으므로 VD-S 재현을 주장하지
않는다. 이를 위해 모델 출력에 confidence를 추가하지 않는다. 향후 별도 내부
점수를 검토하더라도 보정 방식·validation 임계값 선택·test 평가를 구분해야 한다.
음성 50건에서는 오탐 1건이 2%이므로 관측 오탐 0건만으로 0.5% 이하의 실제
오탐률을 입증할 수 없다. 충분한 음성 표본과 불확실성 보고가 필요하다.

### 4. Meta·CrowdStrike — CyberSOCEval (CyberSecEval 4)

2025년 원 논문은 악성코드 분석과 위협 인텔리전스 추론을 다룬다. 복수 정답
선택 문제에서 정답 선택지 집합을 정확히 맞힌 비율을 주 지표로 사용하며,
부록에는 Jaccard 부분 일치 점수도 제시한다. 생성한 문항·정답은 보안 전문가가
검토한다. 파싱 가능한 응답 수와 신뢰구간도 보고한다.
[원 논문 §3–4·부록 A/E](https://arxiv.org/html/2509.20166v1).

**적용 제안:** 완전 정답과 부분 충족을 구분하고, 사람이 검토한 정답을 사용한다.
이 벤치마크는 자유 서술형 코드 근거·수정 권고의 표준 채점표가 아니다.
문장 유사도나 단어 집합 Jaccard를 그대로 근거의 정확성으로 사용하지 않는다.
우리 결과는 파싱 실패도 전체 분모에 남겨 응답 성공률과 함께 보고한다.

### 5. Meta — AutoPatchBench

ARVO에서 선별한 C/C++ 사례의 AI 수정 패치를 평가한다. 컴파일과 원래 crash
해소를 확인하고 추가 fuzzing 및 정답 패치와의 white-box differential testing으로
검증한다. 공식 소개의 수동 검수에서는 자동 검증을 통과해도 잘못된 패치가 남았으며,
crash를 없애는 것만으로 기능 보존·수정 정확성을 보장할 수 없다고 설명한다.
[공식 선정·검증 절차](https://engineering.fb.com/2025/04/29/ai-research/autopatchbench-benchmark-ai-powered-security-fixes/).

**적용 제안:** 권고가 원인을 해결하는지와 정상 기능을 유지하는지를 함께 검토한다.
현재 출력은 수정 코드가 아닌 권고 문장이므로 패치 성공률로 보고하지 않는다.
향후 권고를 실제 패치로 구현해 평가하려면 구현 주체·허용 수정·호출 예산을 고정한
별도 실험으로 분리한다. 설명만 보고 검증된 수정이라고 선언하지 않는다.

### 세 항목에 적용할 평가 초안 — scorer 구현 전

CWE는 분류·완화책의 참조이고 benchmark는 정답 구성·채점 방법의 참조다.
벤치마크의 정답 파일·대상 사례 해설·패치는 평가자만 열람하며 모델 RAG와 분리한다.
CWE로 설명이 부족한 경우에도 외부 자료의 버전·적용 범위를 검수한다.
알려진 취약점 목록 밖의 발견은 별도 검토하며 자동으로 오탐 처리하지 않는다.

| 항목 | 검사와 기록 | 초기 채점 제안 |
| --- | --- | --- |
| 판정 | 사전 검수한 라벨과 대조; 양성/음성 × present/not_observed/uncertain/invalid matrix | 아래 분모 규칙에 따른 판정 성능·미완료 비율, 쌍 정답률 |
| 근거 | 파일·줄·인용 코드의 일치 자동 검사 + 원인·발생 조건·판정 연결의 사람 검토 | 충족 / 부분 충족 / 불충족 / 검토 필요 |
| 권고사항 | 해당 원인 해결, 코드 문맥 적용 가능성, 정상 기능 보존 검토 | 충족 / 부분 충족 / 불충족 / 해당 없음 / 검토 필요 |

권고의 '해당 없음'은 검수된 `not_observed` 사례에 수정이 필요하지 않은 경우다.
모델이 잘못 `not_observed`라고 답해 권고를 생략한 것은 해당 없음으로 인정하지 않는다.
`uncertain`에서는 구체적으로 필요한 추가 정보·확인을 권고할 수 있다.
위의 부분 점수 체계는 AegisLM의 **제안**이며 기관 공통 인증 기준이 아니다.
문자열 완전 일치로 서술문을 채점하거나 임의 가중 합계로 기존 0–100 점수에
합산하지 않는다. 이 문서 §5의 과거 Phase C/D composite와 분리한다.

#### 분모와 판단 보류 처리

- `N+`, `N-`는 사전에 정답을 검수한 전체 양성·음성 수다. 두 집단이 모두 필요하다.
- TP/FN은 양성의 present/not_observed, FP/TN은 음성의 present/not_observed다.
  `U+`, `U-`는 uncertain, `I+`, `I-`는 출력 누락·파싱/계약 오류다.
  실행 실패를 포함해 예정된 사례의 처리 상태를 남기고 조용히 제외하지 않는다.
- 전체 양성 탐지 성공률=`TP/N+`, 음성 비탐지 성공률=`TN/N-`와 각 행의
  uncertain/invalid 비율을 함께 보고한다. 양성에서 탐지에 도달하지 못한 비율
  `(FN+U+ +I+)/N+`는 '미탐·미완료 합산률'로 구분하며 표준 FNR로 부르지 않는다.
- 이진 응답만의 precision/recall/FPR를 보조 보고할 때는 **조건부 지표**라고
  명시하고 이진 응답률=`(TP+FN+FP+TN)/(N+ +N-)` 및 클래스별 응답률을 병기한다.
  분모가 0이면 N/A다. 전부 uncertain인 결과가 높은 성능으로 보이지 않게 한다.
- OWASP 방식 J는 완전한 이진 판정 세트에서 비교 가능하다. uncertain/invalid를
  제외해 계산한 J는 조건부 분석으로만 표시하고 주 결과나 공식 OWASP 점수로 쓰지 않는다.
- 쌍 정답률의 분모는 사전 확정된 전체 쌍이며, 어느 쪽이든 uncertain/invalid이면
  성공 쌍이 아니다. 단일 사례 정답률과 별도로 보고한다.
- 프로젝트 탐색에는 완전한 음성 공간을 세기 어려우므로 위 matrix는 경계가 고정된
  평가 입력에 적용한다. 자유 탐색의 발견별 precision/known-target recall과 혼합하지 않는다.

#### 평가 전 동결할 작업

1. 소수의 실제 취약·수정 쌍에서 소스 버전/hash, 대상 원인, 재현·패치 근거,
   허용 코드 위치, 필요한 문맥을 사람이 검수한다. gold 불확실 사례는 사유와 함께
   보류하고 모델 출력의 uncertain과 구분한다.
2. 근거·권고의 충족/부분/실패 예시를 만든다. CWE ID가 같아도 다른 원인을
   지목하면 근거 정답으로 인정하지 않는다. 가능한 수정 방법은 복수로 허용한다.
3. 복수 발견은 정답과 원인·위치 기준으로 대응시키고 중복 경고의 중복 득점을
   금지한다. 발견 단위와 프로젝트 단위의 성공 조건을 구분한다.
4. 검토자 2인의 독립 채점과 불일치 조정으로 rubric을 시험한다. 가능하면 모델
   종류를 가리고 채점한다. LLM judge는 사람과의 일치도를 확인하기 전 보조로만 쓴다.
5. 정답·rubric·scorer 버전, split·RAG 누출 검사, 프로젝트/CWE별 표본 수,
   결측·오류 분모, seed·반복·문맥/생성 예산을 모델 실행 전에 동결한다.
   쌍·동일 프로젝트 표본의 상관을 고려한 신뢰구간과 집계 방법도 사전 결정한다.

다음 모델 실험에도 DynamicCache·6개 생성 상한·조건별 새 프로세스·W&B 필수
원칙을 유지한다. 세 항목의 실제 JSON 키·자료형·복수 발견 표현과 scorer는 아직
구현하지 않았다. 이를 변경할 때 schema/prompt/회귀 테스트를 함께 갱신한다.
이번 조사는 문서만 추가했으며 새 GPU 실행, 패키지 설치, 외부 데이터 업로드는 없다.

<a id="2026-10-14-three-field-pilot"></a>

## 2026-10-14: 세 항목 평가의 결정 기록과 파일럿 준비안

2026-10-13의 적용 논의를 정리한 실행 준비안이다. 앞 절의 외부 기준·출처·분모
정의를 유지하며, 합의한 방향과 아직 결정하지 않은 실험 설계를 구분한다.

### 확정한 방향과 남은 결정

| 상태 | 내용 |
| --- | --- |
| 사용자 확정 | 결과는 **판정 / 근거 / 권고사항** 세 항목으로 구성한다. 심각도·치명도는 후속 개발로 남긴다. |
| 사용자 확정 | CWE를 우선 참조하고, 부족하면 다른 벤치마크·보완 자료를 검토하며, 그래도 부족한 경우의 처리 기준을 마련한다. |
| 기존 작업 기준 유지 | 현재 A6000 100-step adapter를 검증한다. 이후 모델 실험은 DynamicCache·6개 생성 상한·조건별 새 프로세스·W&B를 사용한다. |
| 적용 제안 | 검수한 취약·수정 쌍과 정답 자료 묶음을 먼저 만들고 판정·근거·권고를 독립 채점한다. 초기에는 종합점수를 만들지 않는다. |
| 적용 제안 | 코드에서 얻은 동일 참조 문서를 base·adapter에 제공하고, 검색 자체의 효과는 별도로 검증한다. |
| 적용 제안 | 2~3개 CWE, 취약·수정 5쌍인 10개 입력으로 채점 절차를 시험한다. 성능 주장용 표본이 아니다. |
| 미결정 | 실제 사례·프로젝트, 입력 문맥 범위, JSON 키·자료형·복수 발견 표현, 검토자와 세부 rubric, 검색 설정, seed·반복 횟수·호출 예산 |

`present` / `not_observed` / `uncertain`의 의미와 불확실·출력 오류의 분리는
앞 절의 설계안을 따른다. 영어 참조 사전과 기존 실험은 유지하고, 한글 설명에 사용한
'판정/근거/권고사항'을 실제 JSON 키로 확정했다고 해석하지 않는다.

### 준비 순서와 산출물

| 순서 | 할 일 | 검토 가능한 산출물·완료 조건 |
| --- | --- | --- |
| 1. 사례 선정 | 실제 취약·수정 소스와 대응 패치·재현 자료를 대조한다. 근거가 부족한 사례는 보류한다. | 사례 목록, 선정·제외 사유, 프로젝트 버전·소스 hash |
| 2. 정답 준비 | 모델 응답을 보기 전에 대상 원인·발생 조건·관련 코드·허용 권고 방향을 검수한다. | 평가자용 정답 자료 묶음과 검수 이력 |
| 3. 입력 분리 | 모델이 볼 코드 문맥과 참조 문서를 정하고 정답 CWE·패치·해설 유입을 점검한다. | 모델 입력 및 검색 결과의 동결본, 평가자 자료와의 분리 검사 |
| 4. 채점표 시험 | 실제 사례에 대해 충족·부분 충족·불충족 예시를 작성하고 검토자 간 차이를 조정한다. | rubric 초안, 독립 검토·불일치 기록, 예외 처리 목록 |
| 5. 출력·평가기 구현 | 세 항목의 정확한 계약을 고정하고 형식·코드 위치 검사 및 집계를 구현한다. | schema/prompt/scorer와 회귀 테스트, CPU dry-run 결과 |
| 6. 파일럿 실행 준비 | 입력·모델·참조·scorer를 고정하고 런타임·W&B·호출 예산을 확인한다. | 실행 전 점검 기록과 최종 실험표. 현재는 미실행 |

원본 소스·정답 자료·동결 입력·모델 출력은 Git 제외 artifact에 보존한다.
Git에는 방법·계약·집계·재현 명령을 기록하며 실제 비밀 값은 근거에 재출력하지 않는다.
필요한 마스킹이 있으면 평가기가 원문 위치와 마스킹된 표시의 대응을 검증할 수 있어야 한다.

### 정답 자료와 채점의 경계

평가자용 정답 자료에는 취약·수정 버전, 대상 원인과 발생 조건, 인정할 수 있는
증거 위치·관계, CWE 또는 보완 자료를 적용한 이유, 해결 가능한 권고 방향을 넣는다.
반드시 개발자 패치와 같은 줄이나 같은 수정 방법만 정답으로 인정하지 않는다.
같은 원인을 입증하는 다른 증거와 동등한 해결 방법을 허용할 기준을 마련한다.

취약 버전의 `present`와 수정 버전의 `not_observed`를 모두 맞혀야 쌍 판정 성공이다.
수정 버전의 음성 정답은 **해당 평가 대상 취약점이 해소된 범위**로 제한한다.
프로젝트 전체에 다른 취약점이 없다는 뜻으로 확장하지 않는다. 초기 입력이 이미
위치를 좁힌 코드라면 '주어진 문맥에서의 판단'으로 보고하고 프로젝트 전체 탐색
성능으로 보고하지 않는다.

판정 정답이 근거·권고 정답을 자동으로 보장하지 않는다. 예를 들어 취약 여부는
맞았지만 무관한 줄을 원인으로 지목했다면 판정은 정답이고 근거는 불충족일 수 있다.
부분 충족 예시는 원인 위치는 맞으나 필요한 발생 조건 설명이 빠진 근거,
수정 방향은 맞으나 필요한 경계 조건이 빠진 권고 등으로 작성해 검수한다.
초기 결과표는 confusion matrix, 쌍 판정 정답률, 근거 평가, 권고 평가로 구성하는
안을 사용하며 검토 필요·형식 실패·해당 없음의 수와 분모도 보존한다.

### CWE 참조를 제공하는 방식의 제안

모델이 보는 코드로 질의를 만들고 검색 결과를 사례별로 고정해 base·adapter에
동일하게 제공하는 방식을 우선 검토한다. 평가자가 알고 있는 정답 CWE나 패치로
문서를 선택하지 않는다. 질의·검색기 버전·문서 ID/버전·순서·내용 hash와
입력 토큰을 보관한다. 공통 검색 결과가 부정확할 수도 있으므로 이 조건의 결과는
해당 참조가 제공된 상태의 판단 성능이며 검색 성능 검증 완료를 뜻하지 않는다.

정답 CWE를 지정한 문서 제공은 별도 oracle 조건으로 표시한다. 모델이 스스로
검색하는 실험이나 참조 없이 판단하는 비교를 추가할지는 아직 미정이다.
평가 사례의 해설·CVE·패치가 포함되는지 확인한 참조 문서만 사용한다.

### 파일럿과 최종 평가의 분리

5쌍·10개 입력은 채점 일관성·문맥 충분성·세 항목 출력 가능성을 시험하는 제안이다.
기존 adapter가 새 출력 형식에 적응하지 못하는 현상은 취약점 이해 실패와 구분해
기록한다. 파일럿 결과에 맞춰 prompt·검색·rubric을 조정한 경우 그 사례는
평가 기준 개발용으로 남기고 최종 성능은 별도 동결 세트에서 측정한다.

만약 이 10개 입력에 2모델 × 6상한을 각 1회 적용하면 명목 호출 수는 **120회**다.
이는 예산 계산 예시이며 실행 승인이나 확정 호출 수가 아니다. 반복·재시도·모델
검색 호출은 별도로 계수하고, 문맥 한도를 넘는 조건은 조용히 축소하지 않는다.
W&B 이름 길이 오류와 GPU 런타임 문제는 다음 실제 실행 전에 확인해야 하며,
시스템 재부팅만으로 해결됐다고 단정하지 않는다.

이번 재개 작업은 문서 정리까지다. 사례 5쌍 선정·정답 검수·schema/scorer 구현·
GPU 파일럿·RAG 성능 비교가 완료됐다는 뜻은 아니다.
