# Evaluation Plan

이 문서는 Phase D/E에서 baseline과 adapter 결과를 같은 방식으로 비교하기 위한 평가 기준을 정의합니다.

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
