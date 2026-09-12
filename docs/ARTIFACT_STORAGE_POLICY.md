# Artifact Storage Policy

이 문서는 `AegisLM` fine-tuning 산출물의 저장 위치, 공개 범위, 금지 항목을 정의합니다.

`docs/DATA_STRATEGY.md`가 데이터 저장/제외 정책의 정본이라면, 이 문서는 모델 개발 산출물인 adapter, checkpoint, model card, evaluation artifact의 저장 정책 정본입니다.

## 1. Goal

Phase E tiny SFT PoC 전까지 다음 기준을 고정합니다.

- GitHub에 저장할 수 있는 항목과 금지 항목을 구분한다.
- LoRA/QLoRA adapter 산출물은 Git 밖에서 관리한다.
- Hugging Face Hub 사용 시 기본 공개 범위는 private으로 둔다.
- model card, training config, evaluation summary를 adapter와 연결한다.
- raw dataset, checkpoint, adapter, token, private CTI가 Git에 섞이지 않게 한다.

## 2. Storage Targets

| Storage | Allowed | Not allowed |
| --- | --- | --- |
| GitHub repository | source code, prompts, configs, schema, tests, docs, small synthetic fixtures, experiment log template | raw dataset, malware sample, checkpoint, adapter artifact, merged model, HF token, secrets, private CTI, large logs |
| Hugging Face Hub private repo | LoRA/QLoRA adapter, tokenizer changes, model card, training config snapshot, evaluation summary | raw dataset, intermediate checkpoint, secrets, private CTI, unsafe samples |
| Weights & Biases project | whitelisted scalar metrics, hyperparameters, digests, safe source-v2 case table, run URL/ID | source code, Git diff, console logs, C/C++ source, prompts, raw output, evidence spans, validation errors, dataset/model/checkpoint/adapter artifacts, secrets |
| Local or approved external storage | raw downloaded datasets, intermediate checkpoints, large logs, temporary training outputs | secrets in plain text, untracked public release artifact without owner approval |

GitHub remains the source of truth for code, configuration, documentation, and small safe fixtures. Hugging Face Hub is the default candidate for shareable adapter artifacts once provenance and safety metadata are ready.

## 3. GitHub Policy

The repository may contain:

- training and inference scripts
- prompt templates
- dataset schema and validators
- small metadata-only or synthetic fixtures
- experiment log templates
- evaluation harness code
- evaluation report templates or curated tiny examples
- documentation that points to external artifact locations

The repository must not contain:

- actual malware samples
- executable payloads or packed binaries
- raw downloaded datasets
- model checkpoints
- LoRA/QLoRA adapter artifacts
- merged full model weights
- Hugging Face tokens or API keys
- private CTI or private customer data
- large generated logs or run directories

If an experiment needs to reference an external artifact, commit only the artifact identifier, storage location, version tag, and safety/provenance notes.

## 4. Hugging Face Hub Policy

Hugging Face Hub is the preferred target for adapter artifacts after local validation. The default visibility is private.

Allowed Hugging Face artifacts:

- LoRA/QLoRA adapter files
- tokenizer files only when the tokenizer was intentionally changed
- model card
- training config snapshot
- evaluation summary JSON or concise report artifact
- dependency/version summary needed to reproduce the adapter

Do not upload:

- raw training dataset dumps
- malware samples or executable payloads
- intermediate checkpoints from unstable runs
- secrets, tokens, private CTI, or private customer data
- artifacts whose dataset license or provenance is not understood

Initial repo naming examples:

```text
<org-or-user>/aegislm-gpt-oss-20b-lora-phase-e
<org-or-user>/aegislm-adapter-tiny-sft-poc
```

Initial tag examples:

```text
phase-e-tiny-sft-v0
dataset-fixture-v0
eval-baseline-compare-v0
```

## 5. Model Card Requirements

Every adapter repo must include a model card before it is shared beyond the owner account.

Minimum fields:

- base model: `openai/gpt-oss-20b`
- adapter method: LoRA or QLoRA
- training dataset provenance summary
- excluded data categories
- intended use: defensive analysis explanation, summarization, mapping, and structured reporting
- out-of-scope use: malware generation, exploit execution, evasion, credential theft, persistence guidance
- evaluation summary and command reference
- known limitations
- safety notes
- license and terms notes
- related Git commit, Linear issue, and experiment log reference

The model card must not imply that AegisLM is the final security decision maker. Deterministic analyzer signals, curated labels, and human review remain the decision basis.

## 6. Public Release Gate

No adapter or model artifact is public by default.

Before changing a Hugging Face repo from private to public, all of the following must be true:

- dataset license and provenance have been reviewed
- no raw malware, private CTI, secrets, or private customer data are included
- safety review confirms the adapter is not trained to provide actionable malware guidance
- evaluation results are recorded and linked
- model card is complete
- owner approval is recorded in Linear or PR discussion

Merged full model publication is outside v0 scope and requires a separate issue.

## 7. Experiment Log Linkage

Each training run that creates an adapter should record:

- Linear issue
- Git commit
- base model and adapter method
- dataset path and dataset version
- training command
- package versions
- GPU type and VRAM
- output artifact location
- Hugging Face repo and tag when uploaded
- evaluation summary path
- known failures or safety notes

The experiment log may live in Git only if it contains no secrets, private data, raw dataset rows, or large generated logs.

## 8. Related Work

- Linear: THE-63
- `docs/DATA_STRATEGY.md`
- `docs/DATASET_CANDIDATES.md`
- `docs/EVALUATION_PLAN.md`
- `docs/FINETUNING_EXPERIMENT_PLAN.md`

## 9. Current Source-v2 Handoff Bundle

The current source-v2 experiment remains local; no Hugging Face upload is part
of the authorized work.

The default fine-tuned deliverable is base-plus-adapter, not merged weights:

- canonical base model ID and resolved revision
- final PEFT adapter directory; a separate best adapter is included only when
  an implemented, recorded held-out selection procedure produced one
- tokenizer and chat template saved with the adapter
- adapter and training configuration
- package lock/version and GPU/runtime manifest
- frozen dataset manifest/digests, without raw records
- base and adapter prediction JSONL
- machine-readable comparison JSON and human-readable HTML
- model card, intended use, safety notes, and known limitations
- adapter reload and one-record inference example

These artifacts stay under Git-ignored local or approved external storage.
Performance outcome does not determine retention: valid improved, equivalent,
and regressed runs are all preserved and labeled accurately. Project NuriLab
integration and deployment are downstream responsibilities and are not AegisLM
artifact acceptance gates.

Experiment stage directories are immutable identities, not reusable scratch
space. A new run creates its stage exclusively; it must fail before model
loading if that stage or its checkpoint stage already exists. Explicit resume
is allowed only for the matching incomplete reservation and a direct
`checkpoint-N` child. Gate-only output is also exclusively created in a
Git-ignored/external location and cannot be nested under the adapter or
checkpoint being evaluated. Promotion evidence binds the complete adapter
directory and prediction bytes, while raw predictions remain local and ignored.
All other generated source-v2 files follow the same non-clobbering policy:
resolved input/output paths must be distinct, outputs must be Git-ignored or
external, output symlinks are rejected, and an existing different artifact is
never overwritten. Evaluation/comparison reruns are idempotent only when the
existing bytes match exactly. This Git-safety check happens before an
idempotent writer accepts matching bytes. Prediction and gate JSONL writers
first fsync a private same-directory temporary file and atomically publish it
only if the destination is still absent, so an interrupted model call cannot
leave a partially published artifact.

## 10. W&B Tracking Policy

W&B tracking is online and explicitly opt-in through `--wandb`. A local `.env`
may contain `WANDB_API_KEY`, but `.env`, `wandb/`, `outputs/`, and generated
import receipts stay ignored by Git. The committed `.env.example` contains key
names only. Create `.env` with `umask 077` and keep its mode at `0600` on the
shared workstation.

The W&B project/group pair is fixed to `aegislm` / `source-v2`. Job types keep
training, evaluation, comparison, and historical import distinct. Allowed data
is restricted to safe configuration values, package/runtime metadata, content
digests, scalar metrics, and the source-free evaluation table defined in
`docs/EVALUATION_PLAN.md`. W&B Artifacts and automatic model logging are not
used. Automatic CLI, host/program, Git, system-statistics, requirements, and
Transformers configuration collection are disabled. Local manifests remain the
canonical link between adapters, datasets, evaluation files, and W&B run IDs;
evaluation and comparison runs use Git-ignored digest-bound `*.wandb.json`
receipts beside their local result files.
Training and gate commands use the same lifecycle with deterministic run IDs.
Training and persisted-adapter gate receipts live beside the configured stage
directories. Checkpoint-diagnostic receipts use the ignored
`outputs/source-v2/wandb/` receipt directory so retries can select a fresh
immutable diagnostic output directory without changing the W&B identity.

The first standard evaluation/comparison/training/gate receipt is published
with an atomic create-if-absent operation. Its caller also holds a non-blocking
inter-process ownership lock from receipt preparation through remote logging
and finish; a concurrent caller fails closed before W&B initialization. A lock
is released on completion, handled failure, or process exit, after which the
same identity may recover its `pending` state. Pending receipts have no remote
linkage. `logged_pending_finish` and `complete` receipts require a non-empty
W&B run ID and run URL, and malformed receipt JSON is rejected rather than
being treated as an already-complete run. Immediately before W&B initialization,
the receipt becomes `logging_ambiguous`. A crash or uncertain
acknowledgement in that state never retries automatically: an operator must
inspect the deterministic W&B run and explicitly select
`--wandb-reconcile retry-logging` when no payload arrived or
`--wandb-reconcile finish-only` when it did. A `logged_pending_finish` retry
reopens the deterministic run only to retry finish; it bypasses local
stage/output reservation and does not upload metrics or tables again. Error
handlers retain ownership until the active W&B failure-finish call returns.
The separate historical-import
receipt uses its own explicitly marked schema and the same atomic local-write,
exclusive remote-work ownership, and file-locked monotonic status transitions.
It also binds the
complete frozen input-digest set, history/gate
fields, deterministic receipt identity, and derived W&B run ID before a
`complete` state is accepted. Its HTTPS run URL must contain that run ID, and
finish-only recovery must preserve the exact stored tracking reference.
