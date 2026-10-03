# GPT-OSS-20B Fine-Tuning Experiment Plan

2026-09-28 data reconstruction: the new provisional C/C++ decision corpus is
`data/processed/cc-source-candidates-20260928-v5` (10,000/1,000/500).
Its final overlap and 4,096-token training-format audits pass. The six-source
normalization pool and exact reconstruction command are documented in
`docs/DATA_STRATEGY.md`. This does not replace the old frozen training config:
source CWE labels are unreviewed, evidence targets remain null, and no new
training run was started. Establish reviewed decision/evidence gold before
switching the two-stage experiment to this corpus.

2026-10-02: the user-requested intermediate cleanup is complete. The reusable
pool/index now live at `data/cache/cc-source-normalized-20260928`; exclusions
are preserved in the history bundle. Replay from these paths reproduced all
eight dataset JSONL files and three non-path metadata files byte-for-byte.
Intermediate v2-v4 data and v3/v4 audit directories were removed after preservation;
the original v5 remains unchanged. The separate cleanup manifest, replay and
final export audits are in `outputs/cc-source-cleanup-20261002`. See
`docs/DATA_STRATEGY.md`, “2026-10-02: 재생성 의존성 이관 및 중간 폴더 정리 완료”.
The v5 decision-only execution configuration is now separate from the old recipe;
see “2026-10-02: v5 decision-only execution” for the current preflight record.
The old two-stage configuration is still frozen to historical datasets; no
new training run or Git commit/push was performed in this cleanup step.

This document defines the AegisLM fine-tuning and model development
experiment track.

AegisLM is a separate LLM model development project that can be linked
with Project NuriLab later. This document focuses on learning the fine-tuning
workflow, preparing local experiments, and building a path toward security
analysis-specialized LLMs.

## 1. Goal

Fine-tune a local LLM to explain malware-like script behavior and produce
structured JSON reports for suspicious code, vulnerability context, and CTI
metadata.

The model is not the final security decision maker. Deterministic analyzer
signals, rule findings, and curated evidence remain the basis for judgement.
The fine-tuned model is used for explanation, TTP mapping, prioritization, and
structured reporting.

## 2. Starting Model

Use the official OpenAI open-weight model as the v0 baseline:

- Model: `openai/gpt-oss-20b`
- Source: Hugging Face model card
- License: Apache 2.0, subject to the gpt-oss usage policy
- Serving / training target: local GPU infrastructure, not use OPENAI_API_KEY

Do not use `gpt-oss-20b-base` as the v0 baseline. Current evidence suggests it
is a community-derived base-like LoRA model, not the official OpenAI baseline.
It may be evaluated later as a comparison target only after provenance,
formatting compatibility, and safety implications are reviewed.

## 3. Learning Roadmap

The first milestone is not a large training run. The first milestone is to
understand the minimum set of concepts needed to run, inspect, and evaluate a
small fine-tuning experiment without treating the training command as a black
box.

Study in this order:

1. LLM fundamentals
   - Transformer decoder architecture
   - tokenizer, token budget, context length, and chat template
   - causal language modeling
   - pretraining, continued pretraining, supervised fine-tuning, and alignment

2. Fine-tuning fundamentals
   - instruction dataset structure
   - prompt / completion and chat-style message formats
   - train / validation split
   - loss, epoch, batch size, gradient accumulation, learning rate, and
     overfitting
   - why structured JSON generation needs explicit formatting examples and
     validation

3. Parameter-efficient fine-tuning
   - LoRA: train adapter parameters while keeping the base model mostly frozen
   - QLoRA: train adapters on top of a quantized base model to reduce VRAM use
   - adapter save / load / merge concepts
   - when not to merge an adapter into the base model

4. Tooling
   - Hugging Face Transformers for model and tokenizer loading
   - Hugging Face Datasets for JSONL dataset handling
   - TRL SFTTrainer for supervised fine-tuning
   - PEFT for LoRA / QLoRA adapter configuration
   - Unsloth for efficient local gpt-oss experiments
   - vLLM or another local serving stack for post-training inference checks

5. gpt-oss-specific requirements
   - gpt-oss models are open-weight models and are not served through the
     OpenAI API.
   - gpt-oss models use the harmony response format. Training and inference
     examples must preserve the expected chat / response format.
   - Learn base-model inference before attempting fine-tuning.
   - Compare Unsloth and TRL on a small dataset before choosing the long-running
     path.

6. Security-domain knowledge
   - MITRE ATT&CK tactics and techniques
   - CVE / CWE / NVD terminology
   - CISA KEV context
   - malware-like behavior categories
   - CTI report structure
   - safe dataset construction for defensive malware-analysis tasks

## 4. Strategy

Use a staged strategy. Do not jump from zero fine-tuning experience to a large
security dataset or custom model layer.

### Stage 0: Baseline Inference

Goal: prove that the base model can be loaded, prompted, and evaluated.

- Load `openai/gpt-oss-20b` locally.
- Run a small set of security-analysis prompts without training.
- Verify the model can produce JSON-like outputs.
- Record common failures: invalid JSON, missing fields, hallucinated ATT&CK
  techniques, unsafe guidance, and vague recommendations.

Exit criteria:

- Base inference works on the target GPU machine.
- A small prompt set and expected JSON schema are documented.
- Failure modes are recorded before training starts.
- Phase E starts only after the gate in `docs/PHASE_D_EXIT_CRITERIA.md` is satisfied.

### Stage 1: Tiny SFT PoC

Goal: learn the full training loop with minimal risk.

- Prepare a tiny JSONL dataset from metadata-only or synthetic examples.
- Run one Unsloth QLoRA PoC.
- Run one Hugging Face TRL LoRA / QLoRA PoC if compatibility allows it.
- Save adapter outputs outside the Git repository according to
  `docs/ARTIFACT_STORAGE_POLICY.md`.
- Compare JSON validity, output quality, VRAM usage, training time, and
  inference latency.

Exit criteria:

- At least one adapter can be trained and loaded.
- Evaluation shows whether training improved JSON contract adherence.
- The experiment log records package versions, commands, dataset path, and
  observed failures.

### Stage 2: Dataset and Evaluation First

Goal: improve data and evaluation before scaling training.

- Build a repeatable dataset preparation script later, but keep raw datasets
  outside Git.
- Define held-out evaluation examples before training on a larger dataset.
- Add automatic checks for JSON parse success and required field completeness.
- Add human review notes for behavior explanation quality and ATT&CK mapping.

Exit criteria:

- Training examples and evaluation examples are separated.
- Evaluation can catch invalid JSON and hallucinated mappings.
- Dataset sources and safety constraints are documented.

### Stage 3: Security-Specialized Adapter

Goal: train a useful adapter for defensive malware-like behavior explanation.

- Scale only after Stage 1 and Stage 2 are stable.
- Prefer QLoRA first on the RTX A6000 48 GB environment.
- Keep the model role limited to explanation, prioritization, mapping, and
  structured reporting.
- Do not train examples that provide step-by-step attack execution guidance.

Exit criteria:

- Adapter produces valid JSON at a high rate on held-out examples.
- Human review finds explanations useful and not overly actionable.
- Inference can run through the intended local serving path.

### Stage 4: Model-Building Research

Goal: explore direct model-building work only after the fine-tuning path is
understood.

- Study model architecture changes, adapter composition, continued
  pretraining, and custom heads / layers separately.
- Do not modify model architecture during v0.
- Treat direct layer construction as a research track after dataset quality,
  baseline evaluation, and LoRA / QLoRA behavior are understood.

Exit criteria:

- A specific limitation of LoRA / QLoRA is documented.
- The proposed architecture change has a measurable evaluation target.
- The safety and storage rules are updated before custom training begins.

## 5. Target Task

Primary v0 task:

```text
malware-like script behavior explanation
```

The model should receive static analysis results, vulnerability metadata, CTI
context, or curated report snippets and produce structured JSON that explains
suspicious behavior.

The model must not be trained to generate deployable malware, bypass logic,
credential theft workflows, persistence instructions, or exploit execution
steps.

## 6. Dataset Plan

Detailed source usage, preprocessing, tokenization/chunking, split, and
fine-tuning/evaluation/RAG separation rules are maintained in
`DATA_STRATEGY.md`. This section defines the high-level dataset direction only.

Datasets will be installed and stored on the NVIDIA GPU machine or approved GPU
server storage, not in this Git repository.

The repository may contain scripts, schema definitions, prompts, and evaluation
logic later. It must not contain large downloaded datasets, real malware
payloads, API keys, private CTI, or sensitive data.

### v0: Metadata and Report Data

Allowed v0 sources:

- NVD / NIST CVE data
- CISA KEV catalog
- MITRE ATT&CK STIX / TAXII data
- VirusTotal metadata and reports, subject to API terms
- MalwareBazaar metadata and reports, subject to API terms
- Public CTI reports and defensive malware analysis writeups
- Synthetic suspicious Python snippets created for benign static analysis
- Existing Project NuriLab normalized static analysis outputs

v0 must not store executable malware payloads in this repository.

### v1: Real Sample Handling

Actual malware sample download, unpacking, or storage is a separate v1 track.

Before v1 starts, require:

- isolated analysis environment
- no execution on the development machine
- no sample storage in Git
- controlled network policy
- documented sample handling policy
- owner approval

### 6.1 gpt-oss Harmony / Chat Formatting Requirements

The `openai/gpt-oss-20b` model expects inputs and outputs conforming to the **Harmony Response Format**. The formatting helper maps raw dataset records into standard chat-style messages, which are subsequently translated into Harmony format.

#### Harmony Format Structure
* **Hierarchy:** Harmony defines a strict role hierarchy where system instructions, user inputs, and assistant outputs are processed via distinct channel wrappers.
* **Special Tokens:** Harmony wraps messages with control tokens (such as `<|start|>`, `<|message|>`, `<|channel|>`).
* **Multi-channel Output:** The format splits outputs into separate streams like `analysis` (for internal reasoning) and `final` (for user-facing responses).

#### Minimum Implementation Scope
To ensure compatibility and prevent training/inference mismatches:
1. **No Manual Token Wrapping:** The training dataset format must contain standard `messages` lists (using standard roles: `"system"`, `"user"`, `"assistant"`). Special Harmony tokens must **not** be manually hardcoded in the JSONL dataset files.
2. **Tokenizer-Driven Conversion:** During SFT training and local evaluation/inference, the Hugging Face tokenizer's `apply_chat_template` reads the model's `chat_template.jinja` configuration and dynamically formats standard chat messages into the correct Harmony binary/text token structure.
3. **Consistently Serialized Target Output:** The assistant response in SFT datasets must contain the raw JSON string conforming to `OUTPUT_CONTRACT_SCHEMA`, serialized deterministically (pretty-printed with 2-space indentation and sorted keys).

## 7. JSON Output Contract

v0 fine-tuning output is JSON only.

Use this schema as the first training and evaluation contract:

```json
{
  "summary": "string",
  "behavior_explanation": "string",
  "risk_level": "low|medium|high|critical|unknown",
  "malware_like_behaviors": [
    {
      "behavior": "string",
      "evidence": "string",
      "confidence": "low|medium|high"
    }
  ],
  "attack_mapping": [
    {
      "tactic": "string",
      "technique_id": "string",
      "technique_name": "string",
      "evidence": "string"
    }
  ],
  "recommendations": ["string"],
  "limitations": ["string"]
}
```

HTML is out of scope for this fine-tuning track. Future HTML reports should be
generated from JSON output.

## 8. Experiment Environment

The first fine-tuning experiments target a single-GPU Linux workstation.

Hardware:

- CPU: Intel(R) Xeon(R) w5-3435X
- RAM: 125 GiB
- SSD: 1 TB
- GPU: NVIDIA RTX A6000
- VRAM: 48 GB

System:

- OS: Ubuntu 24.04 LTS
- NVIDIA-SMI: 595.71.05
- NVIDIA Driver: 595.71.05
- CUDA reported by NVIDIA-SMI: 13.2
- Python: 3.12
- Python package manager: uv

Current serving / inference stack snapshot:

- vLLM: 0.21.0
- torch: 2.11.0+cu130
- torch CUDA runtime: 13.0
- torch CUDA device: NVIDIA RTX A6000
- torch-c-dlpack-ext: 0.1.5
- torchaudio: 2.11.0+cu130
- torchvision: 0.26.0+cu130

PyTorch and training package versions may be adjusted inside the uv environment
to satisfy Unsloth, TRL, CUDA, and gpt-oss compatibility. Any adjustment must be
recorded in the experiment log before training results are compared.

### 8.1 Shared Development Workstation Runtime Integrity Management

AegisLM fine-tuning is centralized on a single shared GPU workstation. Because multiple team members collaborate on the same system, you must run the following self-verification command whenever starting a new experiment or modifying dependencies to prevent configuration drift or data leaks:

```bash
uv run scripts/verify_gpu.py
```

* **Check Items**:
  * **Dependency Integrity**: Detects whether core packages (PyTorch, CUDA, Unsloth, etc.) have been altered or corrupted by other workloads.
  * **Security Leak Prevention (Git Ignore)**: Prevents large weights, caching directories (`checkpoints/`, `adapters/`, `models/`, `unsloth_compiled_cache/`), and `.env` files from being accidentally staged or committed to Git.
  * **Experiment Metadata Archiving**: Automatically updates [experiments/env_check_report.json](../experiments/env_check_report.json) upon execution. You should copy the `versions` block from this report into the `environment` metadata of your experiment log to maintain a trace of the workstation's runtime configuration history.


### 8.2 SFT Training Configuration Dry-run Check

Before launching actual fine-tuning (which consumes significant GPU resources and time), you must validate your configuration schema, local directory permissions, and dataset formatting eligibility by running the dry-run script:

```bash
uv run scripts/dry_run_training.py --config configs/tiny_sft_config.json
```

Use `--check-model` to verify that the base model tokenizer can be successfully downloaded and loaded into memory:

```bash
uv run scripts/dry_run_training.py --config configs/tiny_sft_config.json --check-model
```

### 8.3 External credentials and `.env`

External credentials are read from the repository-root `.env` file. Create it
from the committed key-only template if it does not already exist, then edit it
locally. Never paste the value into a command, log, issue, or PR.

```bash
if test ! -f .env; then (umask 077 && cp .env.example .env); fi
chmod 600 .env
```

The only supported credential keys are:

- `WANDB_API_KEY`: required only when a command explicitly uses `--wandb`
- `HF_TOKEN`: optional; used when a Hugging Face model requires authenticated
  access
- `AEGISLM_INFERENCE_API_KEY`: optional; sent only to a validated loopback
  OpenAI-compatible inference endpoint; arbitrary remote endpoints are rejected

These are API/access tokens, not OAuth client IDs or client secrets. Shell/CI
environment values take precedence over `.env`. Hugging Face implicit cached
authentication is disabled so a run cannot silently use another workstation
user's login. See the official [W&B environment variable reference](https://docs.wandb.ai/models/track/environment-variables)
and [Hugging Face environment variable reference](https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables).


## 9. Training Stack

Run a small PoC comparison before choosing the long-running training path.

Candidate stacks:

- Unsloth QLoRA
- Hugging Face TRL LoRA

v0 hardware assumption:

- single CUDA GPU server
- enough VRAM for `openai/gpt-oss-20b` QLoRA experiments
- datasets stored on the GPU machine or approved mounted storage

Record for each PoC:

- package versions
- PyTorch / CUDA compatibility note
- GPU type and VRAM
- dataset path on the GPU machine
- dataset size
- training command
- peak VRAM
- training time
- output JSON validity
- inference latency

## 10. Evaluation

Phase D/E evaluation follows `docs/EVALUATION_PLAN.md`. The baseline run is
recorded as the before state; adapter runs are compared against the same
held-out fixture set. Phase D completion and Phase E readiness are judged with
`docs/PHASE_D_EXIT_CRITERIA.md`.

Primary v0 evaluation metrics:

- JSON parse success rate
- JSON Schema validation pass rate
- required field completeness
- behavior explanation usefulness
- ATT&CK technique precision, recall, and F1
- risk_level consistency
- hallucinated TTP rate
- unsafe or overly actionable malware guidance rate
- composite score, 0-100

Evaluation artifacts:

- `evaluation_summary.json` for machine-readable comparison
- `evaluation_report.html` for human review

Evaluation candidates:

- held-out NVD / KEV examples
- held-out ATT&CK technique examples
- CyberSecEval-style security benchmarks
- CyberSOCEval-style malware analysis and CTI reasoning benchmarks
- Project NuriLab synthetic suspicious Python fixtures

Do not treat LLM output as final ground truth. Evaluation should compare model
output against curated labels, deterministic analyzer signals, and human review.

## 11. Safety and Storage Rules

Detailed adapter, checkpoint, model card, and evaluation artifact storage
rules are maintained in `docs/ARTIFACT_STORAGE_POLICY.md`.

- Do not commit real malware samples.
- Do not commit downloaded datasets.
- Do not commit secrets, API keys, private CTI, or private customer data.
- Do not train on private code unless the owner explicitly approves it.
- Do not train outputs that include step-by-step attack execution guidance.
- Do not weaken Project NuriLab's principle that deterministic signals remain
  the decision basis.
- Keep large artifacts, model checkpoints, and raw datasets outside the Git
  repository.

## 12. Initial Experiment Steps

1. Confirm the NVIDIA GPU machine can load `openai/gpt-oss-20b`.
2. Verify vLLM inference on the base model.
3. Create a uv training environment and verify GPU/runtime integrity via the validation script (`uv run scripts/verify_gpu.py`).
4. Prepare a small JSONL dataset from metadata/report-only sources.
5. Run Unsloth QLoRA PoC.
6. Run Hugging Face TRL LoRA PoC on the same small dataset.
7. Compare JSON validity, output quality, VRAM usage, and training time.
8. Choose the v0 training stack.
9. Scale dataset construction only after the PoC path is stable.

## 13. Current Reference Links

- OpenAI gpt-oss help:
  https://help.openai.com/en/articles/11870455-openai-open-weight-models-gpt-oss
- Hugging Face model card:
  https://huggingface.co/openai/gpt-oss-20b
- OpenAI Cookbook gpt-oss fine-tuning:
  https://developers.openai.com/cookbook/articles/gpt-oss/fine-tune-transfomers
- Hugging Face TRL SFTTrainer:
  https://huggingface.co/docs/trl/main/en/sft_trainer
- Hugging Face TRL PEFT integration:
  https://huggingface.co/docs/trl/peft_integration
- Hugging Face PEFT LoRA:
  https://huggingface.co/docs/peft/en/developer_guides/lora
- Unsloth gpt-oss fine-tuning guide:
  https://unsloth.ai/docs/models/gpt-oss-how-to-run-and-fine-tune/tutorial-how-to-fine-tune-gpt-oss
- MITRE ATT&CK data and tools:
  https://attack.mitre.org/resources/attack-data-and-tools/
- NIST NVD:
  https://www.nist.gov/itl/nvd
- CISA KEV catalog:
  https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- MalwareBazaar API:
  https://bazaar.abuse.ch/api/
- VirusTotal API docs:
  https://docs.virustotal.com/docs/api-overview

## 14. Current Source-v2 Experiment

This section is the controlling plan for the current Phase E experiment.
Earlier sections retain the broader and historical Phase E learning track.

### Scope and completion

- Canonical base: `openai/gpt-oss-20b`. The pinned Unsloth QLoRA runtime is
  `unsloth/gpt-oss-20b-unsloth-bnb-4bit` at
  `093fba6992ef5a7152481afec0bdfca1ac486998`.
- Task: assess one requested CWE in one supplied C/C++ function and return
  aegislm.source-vulnerability-assessment.v2.
- Training: phase-f-source-v5-r1 train (10,000) and validation (1,000).
- Primary comparison: its full-report challenge/gold pair (500).
- Secondary comparison: phase-f-source-untouched-blind-480-v1 (480,
  decision-only gold).
- Project NuriLab integration is out of scope.

AegisLM completes when a valid adapter reloads, base and adapter inference run,
and comparison artifacts are written. Improvement is not a completion gate.
The result is labeled improved, equivalent, or regressed, and the valid base
identifier/revision, PEFT adapter, tokenizer/chat template, configs, manifests,
predictions, reports, and limitations are retained in all three cases.

### Frozen output and Harmony loss contract

The exact schema is aegislm.schemas.SOURCE_ASSESSMENT_SCHEMA. It requires:

- fixed schema_version aegislm.source-vulnerability-assessment.v2
- scope.target_cwe and scope.boundary supplied_function
- assessment: present, not_observed, or uncertain
- assessment_basis with exact code spans, relationship, conclusion, confidence
- findings with exact code spans, operation, evidence, confidence
- limitations and recommendations

Evidence lists contain at most eight unique exact substrings from the supplied
function. A present assessment requires a finding; not_observed has no finding.

Frozen JSONL records keep standard system/user/assistant messages and contain no
hand-authored Harmony control tokens. The tokenizer renders the system/user
generation prompt and a full conversation whose assistant has empty thinking
and final-channel JSON content. The prompt token sequence must be an exact
prefix of the full sequence. Prompt labels are -100, and only assistant channel
tokens contribute to loss. Overlength or zero-supervision records fail before
training.

The 2026-09-10 local GPT-OSS tokenizer audit covered all 11,000 train and
validation records. Train maximum was 1,886 tokens, validation maximum was
1,880, and neither split overflowed 2,048.

### Canonical QLoRA configuration

configs/source_v2_qlora.json fixes:

- rank 8, alpha 16, dropout 0.05
- attention targets q_proj, k_proj, v_proj, o_proj
- Unsloth split-module MoE targets gate_up_projs/down_projs in layers 7, 15,
  and 23, matching the three-layer subset used by the GPT-OSS reference recipe
- batch size 2, gradient accumulation 4, one epoch
- learning rate 2e-4, warmup ratio 0.03, cosine schedule
- adamw_8bit, Unsloth gradient checkpointing, seed 3407, no packing

A deterministic, assessment-stratified 1,000-record canary precedes the full
run. The initial 200-record trial covered too few examples per CWE and produced
0/40 contract-valid held-out outputs, so it is retained as a failed diagnostic
rather than used to weaken the gate under
`adapters/source-v2-qlora/diagnostics/canary-200/`. The 1,000-record size also matches the
small-dataset scale in the GPT-OSS reference fine-tuning recipe. The canary
requires finite loss, non-empty assistant supervision, saved expert adapter
tensors, successful adapter reload, and at least 90% schema/grounding pass on a
fixed 40-record validation subset. The reload gate uses deterministic batched
generation with a 512-token ceiling (the audited subset's gold maximum is 450
supervised tokens); `--gate-only` reruns it without training. Raw generations
and validation errors are retained beside the adapter for diagnosis.

For the pinned Unsloth 2026.6.9, unsloth-zoo 2026.6.7, and Transformers 5.5.0
stack, Trainer eval forward is disabled because its patched GPT-OSS
create_causal_mask call is incompatible with Transformers 5.5. Validation is
therefore performed by deterministic generation after persisted-adapter reload,
which also tests the actual handoff path. Full-run checkpoints remain saved at
the configured interval for recovery only. The current implementation promotes
only the final adapter and records checkpoint selection as not performed; it
does not label the final adapter as a metric-selected best checkpoint.
Unsloth exposes each GPT-OSS expert as a plural, per-expert module rather than
the fused Hugging Face parameter name. The training helper therefore builds a
strict regex covering attention modules and only the configured expert layers;
the saved-adapter gate fails if no expert tensors are present.

### Canary status on 2026-09-10

The 1,000-record canary completed one epoch in 882.471 seconds with training
loss 0.132187 and 14.768 GiB peak allocated VRAM. The saved adapter contained
expert tensors and reloaded from disk. Its resolved quantized base was
`unsloth/gpt-oss-20b-unsloth-bnb-4bit` at commit
`093fba6992ef5a7152481afec0bdfca1ac486998`.

The held-out gate failed at 0/40. Thirty-one outputs were not parseable JSON;
the remaining nine violated the source-v2 contract, primarily by appending a
CWE description to `scope.target_cwe`. Raw generations show special-token
repetition as well as ungrounded spans. The failed run remains under
`adapters/source-v2-qlora/canary/`; the earlier 200-record failure is under
`adapters/source-v2-qlora/diagnostics/canary-200/`.

The full 10,000-record run and base/adapter challenge comparison are not run
until this gate passes. The threshold is not lowered to promote the artifact.

Offline and GPU diagnostics on 2026-09-11 separated two failures. The preserved
40 cases contain 31 parse failures and nine parsed-but-invalid responses; 21
never emitted EOS before the 512-token ceiling, and none began with the expected
Harmony analysis prefix. The same fixed eight records under explicit low
reasoning/EOS/padding produced these results:

| Runtime | Batch | Parsed | Final channel | Strict pass |
| --- | ---: | ---: | ---: | ---: |
| base | 1 | 5/8 | 5/8 | 0/8 |
| checkpoint 25 | 1 | 8/8 | 8/8 | 0/8 |
| checkpoint 100 | 1 | 6/8 | 7/8 | 0/8 |
| final/checkpoint 125 | 1 | 2/8 | 7/8 | 0/8 |
| final/checkpoint 125 | 8 | 0/8 | 1/8 | 0/8 |

The batch-dependent divergence confirms a generation/runtime interaction. The
checkpoint trend and near-zero training loss with zero held-out validity also
show semantic overfitting/control-token degeneration. Neither extraction alone
nor a larger generation ceiling can repair this artifact.

New recipes therefore use an explicit protocol (`reasoning_effort=low`, left
padding, pad 200017, EOS 200002/199999, deterministic decoding), a batch-1 gate,
and checkpoints every 25 optimizer steps. `unsloth_v2` retains the Unsloth
adapter helper. `peft_split_control` retains the same Unsloth split-BNB loader
but uses direct `prepare_model_for_kbit_training` and `peft.get_peft_model`.
It is an adapter-injection control, not a vanilla Transformers fused-expert
QLoRA claim. The A6000 load/injection preflight passed with 288 exact 4-bit
targets, 15,040,512 trainable parameters, and 14.931 GiB peak allocated VRAM.

### Recovery canary status on 2026-09-11

Both recovery recipes completed training and fresh persisted-adapter reload,
but neither passed a single held-out record. They used the same assessment-only
1,000-record train selection digest
`e945b83777119d809dd2f9a7c6b638c0e1b2815af1fc1fd1ea8fb741550f155d`,
the same fixed 40-record validation digest
`45989ea9e3a81926f13cfe73a8088d44b8b7817fcb782fd61f3ffd6b3d1b40d0`,
and the same explicit batch-1 generation protocol.

| Recipe | Train loss | Seconds | Peak VRAM | Parsed | EOS | Strict valid | W&B run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `unsloth_v2` | 0.13205 | 863.227 | 14.768 GiB | 16/40 | 24/40 | 0/40 | `mdotwa7l` |
| `peft_split_control` | 0.13091 | 1,216.043 | 18.081 GiB | 5/40 | 9/40 | 0/40 | `4a0wl8na` |

The Unsloth-v2 output had 24 duplicate final markers, 23 tool-call markers, and
16 rows without EOS. The direct PEFT control was worse: 34 duplicate final
markers, 35 tool-call markers, and 31 rows without EOS. Both saved adapters had
exactly 576 finite tensors: 192 attention and 384 expert tensors. Their
different SHA-256 digests, active-adapter checks, and fresh reloads rule out a
missing or accidentally reused adapter as the explanation.

The earliest saved checkpoints also failed the same fixed eight diagnostic
records. Unsloth-v2 checkpoint 25 parsed 0/8 with EOS 4/8; PEFT checkpoint 25
parsed 6/8 with EOS 7/8 but violated the schema/grounding contract on all eight.
The PEFT final regression therefore contains later control-token degeneration,
but semantic validity was already zero at step 25. Additional checkpoints are
not promoted, and diagnostic reports retain `promotion_authority=false`.

Token inspection confirms that supervised targets contain the canonical empty
analysis channel, assistant restart, final JSON channel, and return token. The
observed failure is therefore not caused by omitting EOS from the target. The
current evidence points to autoregressive control-token repetition and a large
teacher-forcing/generation gap; CWE frequency imbalance is not established as
the primary cause.

An opt-in data-distribution ablation is prepared but **NOT_RUN** in
`configs/source_v2_peft_cwe_balanced.json`. Its versioned
`target_cwe_assessment_round_robin_v1` selector covers all 86 observed
`(target_cwe, assessment)` strata without replacement and produces train digest
`b98b65c5d0475ed0c0e29365fa72374303111b524b28f46ba2fffad77baaa8c9`.
Only 105/1,000 records overlap the assessment-only canary, so this is a major
distribution ablation rather than a backend control. The validation fixture,
protocol, hyperparameters, and 90% gate remain unchanged. Run it only after a
separate issue records the hypothesis and accepts rare-CWE oversampling and
memorization risk; do not infer that balancing will repair the observed
Harmony/schema failure.

The canonical OpenAI MXFP4 checkpoint cannot currently be converted into a
vanilla bitsandbytes fused-expert QLoRA control on this 48 GB stack: its expert
parameters are not ordinary quantizable `nn.Linear` modules, and dequantizing
them is outside the available memory budget. Revisit that path only with native
3D expert quantization support or an 80 GB-class fused BF16 LoRA environment.

Primary commands:

    uv run python scripts/audit_source_dataset.py \
      --train data/processed/phase-f-source-v5-r1/train.jsonl \
      --validation data/processed/phase-f-source-v5-r1/validation.jsonl \
      --challenge data/processed/phase-f-source-v5-r1/challenge.jsonl \
      --gold data/processed/phase-f-source-v5-r1/gold.jsonl \
      --output outputs/source-v2/data-audit.json

    uv run python scripts/audit_source_tokens.py \
      --tokenizer adapters/source-v2-qlora/canary/final \
      --train data/processed/phase-f-source-v5-r1/train.jsonl \
      --validation data/processed/phase-f-source-v5-r1/validation.jsonl \
      --reasoning-effort low \
      --output outputs/source-v2/token-audit.json

    uv run python scripts/train_source_unsloth.py \
      --config configs/source_v2_unsloth_v2.json --stage canary

    uv run python scripts/train_source_peft_control.py \
      --config configs/source_v2_peft_control.json --stage canary

    uv run python scripts/train_source_peft_control.py \
      --config configs/source_v2_peft_cwe_balanced.json --stage canary \
      --prepare-only

    uv run python scripts/train_source_unsloth.py \
      --config configs/source_v2_unsloth_v2.json --stage full

`--gate-only` requires a new `--gate-output-dir`; it never overwrites a prior
gate report or prediction file. The resolved output must remain in a
Git-ignored/external location and outside the adapter and checkpoint trees.
Both training entrypoints load the frozen train and validation splits and
reject any cross-split record-ID or canonical source-code digest overlap before
selection, stage reservation, W&B initialization, or promotion checks.
Training stages are exclusively reserved before model loading; an existing,
finalized, or mixed stage is rejected before training can overwrite it. Resume
is explicit and is limited to a direct `checkpoint-N` child of the configured
stage whose reservation has the same config digest. `--gate-only` and
`scripts/run_source_checkpoint_gate.py` create diagnostic-only reports with
`promotion_authority=false`. Such reports cannot open a full stage.
The omitted Unsloth config now resolves to `source_v2_unsloth_v2.json`.
`legacy_unsloth` remains available only for reproduction/diagnostics and cannot
run or authorize a full stage.

Add `--wandb` only to a real canary/full training or `--gate-only` command that
should be tracked online. W&B uses project `aegislm`, group `source-v2`, and job
types `training`, `evaluation`, `comparison`, or `historical-import`. Trainer
always keeps `report_to="none"` so the stock Transformers W&B callback cannot
publish model, PEFT, output-path, or TrainingArguments configuration. When
`--wandb` is selected, a local callback sends only finite loss, learning rate,
gradient norm, and epoch scalars. Without the flag, the existing local execution
path is unchanged. With the flag, a missing `WANDB_API_KEY` fails before model
load and before configuration or dataset files are read. The W&B training
configuration is a separate semantic projection: it accepts only the canonical
source-v2 model IDs and pinned `093fba6992ef5a7152481afec0bdfca1ac486998`
revision, SHA-256 dataset identities, the approved
optimizer/scheduler and attention-module domains, bounded expert-layer indices,
the versioned train-selection strategy, and bounded numeric hyperparameters.
Local paths are never part of that projection.
Training, persisted-adapter gate-only, and checkpoint-diagnostic W&B runs use
digest-derived deterministic IDs and Git-ignored receipts. The receipt is
written in `pending` state before network initialization, resumes only the same
identity after interruption, and becomes `complete` only after W&B finish
succeeds. A completed receipt is checked before immutable stage/output
reservation and makes the same logical command a no-op. A pending diagnostic
receipt can resume the same remote identity while using a fresh local output
directory. Receipt preparation holds an exclusive, non-blocking process lock
through remote logging and finish, so a simultaneous invocation is rejected
before W&B initialization instead of duplicating metrics or tables. Process
exit releases the ownership lock for a subsequent same-identity recovery. If
logging completed but finish failed, the next invocation performs a
finish-only recovery before any stage/output reservation and does not retrain,
regate, or re-upload known-logged data. Error handling keeps the claim until
the active failure-finish call itself returns.

Before W&B initialization or any callback/metric/table upload, the receipt advances from
`pending` to `logging_ambiguous`. Because a process can die after W&B accepts a
payload but before local acknowledgement, this state is never auto-retried.
After inspecting the deterministic W&B run, use exactly one explicit recovery:

```bash
# Remote run has no payload; allow logging to run again.
... --wandb --wandb-reconcile retry-logging

# Remote payload is present; skip logging and recover finish only.
... --wandb --wandb-reconcile finish-only
```

The preserved 2026-09-10 failed canary is imported idempotently with:

```bash
uv run python scripts/import_source_canary_to_wandb.py --wandb
```

The importer deterministically identifies the run from the three local source
file digests, requires those digests and the linked train/validation/config
digests to equal the frozen 2026-09-10 canary, and reads each JSON file once so
the parsed bytes and digest cannot diverge. It uses `resume="never"` on the first attempt, uploads the 125-step
scalar learning curve and aggregate gate outcome, and writes a local receipt
under `outputs/source-v2/wandb/`. A pending receipt is written before network
initialization. Interrupted attempts resume only the same deterministic run
with `resume="allow"`; ambiguous attempts require the same explicit
`--wandb-reconcile` decision; completed receipts make reruns a no-op. The importer
uses the same process-lifetime exclusive receipt claim, and therefore rejects
concurrent imports before remote initialization. A logged-but-unfinished retry
skips the 125 history rows and aggregate summary and only recovers finish. It
does not read or upload
the raw gate predictions. The import completed on
2026-09-11 as run
`source-v2-canary-import-84a709909f53`; its local receipt is the canonical
link. Re-running the command is a no-op after receipt verification.

GPU training and model inference are experiment runs rather than PR unit-test
gates. Record their commands, packages, GPU, elapsed time, peak VRAM, resolved
model revision, and artifact paths.
`--prepare-only` validates frozen file hashes, record shape, and deterministic
split selection but intentionally does not tokenize; the token-audit command is
the mandatory tokenizer/max-length preflight. A full stage also requires a
current canonical promotion report. Promotion requires an authoritative,
versioned report, exact nonzero counts, matching recipe/protocol/config/model,
the selected train and validation record digests, the prediction-file digest,
and a digest of the complete saved adapter directory (weights, adapter config,
tokenizer, and chat template). The full-stage launcher independently reloads
the persisted tokenizer/adapter handoff, verifies the artifact digest is
unchanged across the gate, and re-scores the preserved prediction rows against
the exact selected records;
stored `parsed_output`, error strings, and aggregate assertions do not grant
promotion. Non-finite/out-of-range rates, inconsistent counts, diagnostic
authority, duplicate/missing IDs, and modified prediction bytes are rejected.

The promotion rescorer is bound to the resolved `GenerationContract`, including
the configured `max_new_tokens` ceiling and EOS set. Non-legacy gate rows retain
the bounded generated token IDs, first-EOS result, raw trailing terminator, and
Harmony flags; each field is recomputed or cross-checked during rescore. A
non-legacy row can pass only when it terminates on one of the configured EOS
token IDs; valid JSON ending by length or an unknown reason remains a failed row.
A
well-formed provenance envelope with invalid JSON/schema is a scored held-out
failure. Missing or inconsistent provenance is a run failure and cannot be
reclassified as a model-quality result. Source-v2 JSON/JSONL inputs use bounded
UTF-8 streaming readers that reject JSON constants and recursive non-finite
numbers; generated JSON uses `allow_nan=False`.

These SHA-256 values establish consistency among local files, not authorship.
A principal allowed to rewrite the adapter, predictions, and report can rebuild
unsigned evidence; OS account permissions and human review remain the trust
boundary. Cryptographic attestation is outside the current local PoC.

## 15. Fresh Unsloth Manual Run

### 상태와 실험 조건

`scripts/train_source_unsloth_fresh.py`는 사용자가 직접 실행하는 새 진입점이다.
코드 작성 시 학습·추론·GPU smoke·pytest·W&B 접속을 실행하지 않았다.
정적 분석은 런타임 호환성이나 학습 품질의 검증을 대신하지 않는다.
기존 실패 canary와 현재 full-stage 차단 상태도 그대로 유지한다.

설정은 `configs/source_v2_unsloth_fresh.json`, recipe는 `unsloth_fresh_v1`이다.
기존 pinned Unsloth 4-bit 모델과 source-v2 schema, 데이터셋을 유지하고
학습률은 `2e-4`에서 `5e-5`로 낮춘다. 이는 제어 토큰 반복·출력 품질 악화를
줄여보는 **미검증 가설**이며, 기존 실패를 해결했다고 주장하지 않는다.
batch 2, accumulation 4, 1 epoch, rank 8, alpha 16, dropout 0.05,
길이 2048, seed 3407, attention 및 expert layer 7/15/23을 사용한다.
Unsloth는 모델·QLoRA를, Transformers Trainer는 학습 루프를 담당한다.

새 recipe는 `dataset.challenge_path`와 `dataset.challenge_sha256`을 요구한다.
train/validation/challenge 파일 해시와 서로 간 ID·코드 중복을 확인하고,
train/validation의 정답 schema·근거를 검사한다. challenge는 중복 검사에만
사용하며, challenge 정답(gold)은 학습 진입점에서 읽지 않는다.
이 두 설정 필드는 이전 recipe에는 선택 사항이어서 기존 설정과 호환된다.

### 환경과 모델 캐시

저장소 루트에서 준비된 환경을 사용한다. 패키지를 자동 업그레이드하지 않는다.

```bash
cd /home/remoteuser/Desktop/AegisLM
source experiments/training-loop-debug/activate.sh
python scripts/train_source_unsloth_fresh.py --help
```

모델 가중치는 `model.cache_dir`를 사용한다. 토크나이저는 그 캐시를 먼저 조회하고,
파일이 부족하면 기본 Hugging Face 캐시에서 **동일한 고정 revision**을 조회한다.
`tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`,
`chat_template.jinja`가 한 snapshot에 모두 있어야 하며 서로 다른 캐시나 revision의
파일을 섞지 않는다. 준비 결과의 `tokenizer.snapshot`에 선택한 경로를 기록하고,
학습·재로딩에도 같은 조회 규칙으로 선택한 tokenizer를 명시적으로 전달한다.

Unsloth가 가중치를 `models/cache`에, tokenizer를 기본 HF 캐시에 나눠 저장한 경우가
있다. 가중치만 있는 캐시에 AutoTokenizer를 직접 요청하면 실제 원인은 파일 누락인데도
`sentencepiece or tiktoken` 변환기 오류가 나올 수 있다. 먼저 캐시 파일을 확인한다.

캐시가 없으면 사용자가 아래 명령으로 먼저 다운로드한다. 이 명령은 네트워크와
모델 저장 공간을 사용하며, 코드 작성 과정에서는 실행하지 않았다.

```bash
hf download unsloth/gpt-oss-20b-unsloth-bnb-4bit \
  --revision 093fba6992ef5a7152481afec0bdfca1ac486998 \
  --cache-dir models/cache
```

학습용 환경은 Python 3.12.13, torch 2.10.0, Transformers 5.5.0,
Unsloth 2026.6.9, unsloth-zoo 2026.6.7, PEFT 0.19.1, TRL 0.24.0이다.
기존 전용 환경을 사용하며 루트 `.venv`나 lockfile을 바꾸지 않는다.

### 직접 실행하는 순서

먼저 전체 train/validation을 토큰화해 길이 초과와 assistant-only masking을
검사한다. 이 단계는 로컬 tokenizer만 로드하며 모델 가중치·W&B는 사용하지 않는다.

```bash
python scripts/train_source_unsloth_fresh.py --prepare-only
```

각 명령이 성공한 뒤 다음 명령을 실행한다. `--wandb`를 빼면 로컬 기록만 남긴다.
W&B 사용 시 기존 `.env`의 `WANDB_API_KEY`를 읽으며 원문·코드·console log·모델은
전송하지 않는다. 키를 명령행에 넣거나 `.env`를 shell script로 source하지 않는다.

```bash
python scripts/train_source_unsloth_fresh.py --stage smoke --wandb
```

smoke는 고정 train 32건, 10 optimizer step, 고정 validation 8건이다.
finite loss·실제 nonzero gradient·LoRA 가중치 변화·유한한 expert tensor 저장과
별도 프로세스의 adapter 재로딩을 확인한다. 출력 점수는 진단용이며,
`promotion_authority=false`다. smoke 출력 품질이 낮아도 실행 무결성 검증이
성공했다면 종료 코드는 0일 수 있으므로 JSON 점수와 실행 성공을 구분한다.

```bash
python scripts/train_source_unsloth_fresh.py --stage canary --wandb
```

canary는 기존 assessment 층화 방식의 1,000건을 사용하며 smoke adapter를
이어 학습하지 않는다. base에서 새로 학습한 뒤 별도 프로세스에서 저장 adapter를
로드하고 고정 validation 40건에 대해 Harmony/EOS·schema·근거·안전성 gate를
평가한다. 기본 통과 기준은 36/40이다. 25 optimizer step마다 checkpoint를
저장하고 최근 6개를 유지한다. gate 실패 시 산출물을 보존하고 nonzero로 종료한다.

```bash
python scripts/train_source_unsloth_fresh.py --stage full --wandb
```

full은 동일 config의 canary 보고서, 전체 adapter digest, 고정 40건 prediction을
다시 채점하여 통과한 경우에만 시작한다. base에서 전체 train 10,000건을 1 epoch
학습하며 canary 가중치를 이어 쓰지 않는다. final adapter를 저장·재로딩한 뒤 같은
gate를 실행한다. best checkpoint 선택은 구현하지 않으며 final을 best로 부르지 않는다.
이 명령은 challenge 본 비교를 자동 실행하지 않는다.

Trainer eval forward는 현재 고정 runtime의 mask 호환성 문제 때문에 비활성화한다.
validation 정답 loss를 산출했다고 주장하지 않으며, 저장 후 생성 검증을 사용한다.
모든 단계는 실제 모델 tokenizer로 전체 train/validation 토큰을 다시 확인한다.

### 입력·출력 진단 로그

학습 trace는 해당 stage에서 선택한 학습 레코드를 대상으로,
Trainer Dataset 생성에 사용하는 동일한 토큰화 결과에서 만든다.
다시 토큰화하거나 학습 데이터·프롬프트·labels를 변경하지 않는다.

- `messages` : system/user/assistant 메시지
- `input_ids`, `attention_mask`, `labels` : 배치 구성 전 학습 데이터
- `decoded_input` : 특수 토큰을 보존한 전체 학습 시퀀스
- `decoded_masked_input` : labels가 -100인 위치의 입력 토큰
- `decoded_supervised_labels` : -100을 제외한 정답 토큰
- `masked_token_count`, `supervised_token_count` : 각 구간의 토큰 수

이 기록은 data collator 처리 전이다. 실제 배치 패딩, 매 optimizer
step의 입력 순서, logits 또는 학습 중 생성 답변을 기록한 것은 아니다.
학습 정답과 모델이 자유 생성한 답변을 혼동하지 않는다.

학습 trace는 adapter stage 내부가 아닌 adapter root에 저장한다.
실행 시도마다 UUID가 다른 파일을 만들며, 체크포인트 재개 시에도
이전 파일을 덮어쓰지 않는다. 완료된 학습 manifest의
`training_trace`에 경로, SHA-256, 레코드 수와
`capture_point="before_data_collator"`를 기록한다.
학습 완료 전에 중단되면 trace만 남고 manifest는 없을 수 있다.

평가 prediction은 레코드 ID별로 다음 정보를 연결한다.

- `input` : 원본 prompt 메시지, 지정 CWE, 모델에 전달한 input_ids와
  attention_mask, 특수 토큰을 보존한 decoded_input
- `raw_generation` : 종료 토큰 기준으로 정리한 생성 구간의 원문
- `generation` : 생성 토큰 ID와 종료 사유 등
- `extracted_final` : JSON 파서에 전달한 문자열
- `parsed_output` : 파싱된 JSON 객체. 파싱 실패 시 null
- `validation_errors` : 프로토콜·JSON·스키마·근거 등의 검증 오류

진단 시에는 같은 평가 레코드의 입력 → raw_generation →
extracted_final → parsed_output → validation_errors 순서로 확인한다.
학습 trace는 정답 형식과 masking을 확인하는 별도 자료이며,
학습과 검증 레코드를 같은 샘플이라고 가정하지 않는다.

모든 원문 진단 파일은 Git 제외 로컬 artifact로 보관한다.
W&B에는 프롬프트, 소스 코드, 정답, 생성 원문을 업로드하지 않는다.
새 기록 필드는 기존 gate의 평가 기준이나 승격 조건을 바꾸지 않는다.
기존 실행의 artifact에는 이 필드들이 없을 수 있다.

### 출력과 실패·재개

| 위치 | 내용 |
| --- | --- |
| `adapters/source-v2-unsloth-fresh-v1/<stage>/final/` | adapter, tokenizer, 학습 인자 |
| 같은 stage의 `aegislm_training_manifest.json` | config, 명령, 버전, GPU, digest, loss, 시간·VRAM |
| 같은 stage의 `training_log.json` | 로컬 학습 curve |
| 같은 stage의 `post_training_gate_predictions.jsonl` | 평가 입력·생성 토큰·원문 출력·추출 final·파싱 결과·검증 오류 |
| 같은 stage의 `post_training_gate.json` | 재로딩·엄격 검증 결과 |
| `checkpoints/source-v2-unsloth-fresh-v1/<stage>/checkpoint-N/` | 재개용 checkpoint |
| 완료 checkpoint의 `aegislm-training-evidence.json` | config·데이터·tokenizer 계약, gradient·가중치 변경 검증, adapter·Trainer 상태 해시 |
| adapter root의 `<stage>.wandb.json` | 외부 기록 완료·재시도 상태 |
| adapter root의 `<stage>.training-trace-<uuid>.jsonl` | 선택된 학습 데이터의 메시지·토큰·labels·마스킹 진단 |

위 경로는 모두 Git 제외 대상이다. stage가 이미 있으면 재실행으로 덮어쓰지 않는다.
새 실험은 설정 파일을 복사하고 `output_dir`와 `checkpoint_dir`를 모두 새로운
경로로 바꿔 시작한다. 설정이 달라지면 이전 canary 결과로 full을 시작할 수 없다.

학습 중 중단되었고 adapter stage에 reservation만 남아 있으며 checkpoint가 완전한
경우에만 동일 config로 재개한다. 실제 존재하는 `checkpoint-N`을 지정한다.
예를 들어 canary의 checkpoint-25가 있다면:

```bash
python scripts/train_source_unsloth_fresh.py --stage canary \
  --resume-from-checkpoint checkpoints/source-v2-unsloth-fresh-v1/canary/checkpoint-25
```

`global_step < max_steps`인 checkpoint는 기존 Trainer 재개 경로를 사용한다.
`global_step == max_steps`이면 추가 학습 대신 최종 저장·재로딩·gate로 복구한다.
이때 예약 검증에 더해, 마지막 checkpoint 저장 callback이 남긴
`aegislm-training-evidence.json`이 반드시 있어야 한다. config·stage·학습 데이터,
adapter/config 파일 및 Trainer 상태 해시, 유한한 step별 loss 기록,
gradient 검증과 가중치 변화 근거를 확인한다. 실제 runtime의 총 step 수와
tokenizer 계약도 일치해야 하며, 복원한 trainable 가중치의 해시를 다시 대조한다.
완료 checkpoint 복구에서는 `Trainer.train()`을 호출하지 않는다.

복구 manifest는 `resume_mode="finalize_completed_checkpoint"`,
`gradient_verification_source="checkpoint_evidence"`로 이전 실행의 검증 근거를
사용했음을 명시한다. `training_loss_source="checkpoint_log_history_mean"`은
저장된 step별 loss의 평균이며, 새 학습의 loss나 validation loss가 아니다.
시간·VRAM은 이번 복구 호출의 측정값이지 원래 학습 전체의 측정값이 아니다.

검증 근거 파일이 없는 기존 완료 checkpoint는 자동 복구하지 않는다.
이 경우 이전의 미완료 checkpoint에서 명시적으로 재개하거나 새 실험 경로를
사용한다. 근거 파일을 손으로 작성하거나 성공 검사를 생략해서 우회하지 않는다.
checkpoint 파일은 있지만 근거 파일 저장 전에 중단된 경우에도 같은 제한이 적용된다.
더 최신 checkpoint에 완료 검증 근거 파일이 있으면 이전 checkpoint부터의 재학습은
거부한다. Trainer가 최신 checkpoint와 근거를 덮어쓰지 않도록, 완료 checkpoint를
복구하거나 새로운 실험 경로를 사용한다. 손상된 근거 파일도 임의로 덮어쓰지 않는다.
이번 복구 변경의 CPU/mock 회귀 테스트 결과는 아래 코드 인계 검증에 기록한다.
실제 GPU에서의 완료 checkpoint 복구는 아직 실행하지 않았다.

완성되거나 일부 저장된 `final/`, manifest 또는 gate가 있는 stage는 학습 resume
대상이 아니다. 삭제해서 재사용하지 않는다. 재로딩 중단으로 **gate와 prediction이
둘 다 아직 없는 경우**에는 학습을 다시 하지 않고 아래 명령으로 저장 adapter만
검증할 수 있다. 이 내부 복구 모드는 W&B를 사용하지 않는다.

```bash
python scripts/train_source_unsloth_fresh.py --stage canary --reload-only
```

prediction만 남은 중단이나 이미 완료된 gate의 재진단에는 기존
`run_source_checkpoint_gate.py`의 별도 진단 출력 경로를 사용한다. 완료된 stage를
덮어쓰거나 진단 결과를 full 승격 증거로 재사용하지 않는다.

```bash
python scripts/run_source_checkpoint_gate.py \
  --config configs/source_v2_unsloth_fresh.json \
  --adapter adapters/source-v2-unsloth-fresh-v1/canary/final \
  --output-dir outputs/source-v2-unsloth-fresh-v1/canary-diagnostic-01 \
  --limit 40 --batch-size 1
```

W&B 네트워크 실패는 로컬 학습 결과와 구분한다. `logging_ambiguous` receipt이면
기존 W&B 복구 규칙에 따라 원격 반영 여부를 확인한다. 미완료 학습 재개와 함께
로그 기록을 재시도할 때는 `--wandb --wandb-reconcile retry-logging`을 사용한다.
이미 원격에 기록된 run을 finish만 복구할 때는
`--wandb --wandb-reconcile finish-only`를 사용한다. finish-only는 학습을 재개하지
않는다. receipt 완료는 모델 품질 통과를 의미하지 않으며 로컬 gate를 확인해야 한다.

### 본 학습 이후 base·adapter 비교

full이 성공한 뒤 아래 명령을 별도로 실행한다. 주 평가 500건과 판단 전용 480건을
각각 처리하며 결과를 합치지 않는다. 출력이 이미 존재하면 새 출력 경로를 사용한다.
괄호 안에서 첫 실패 시 중단하므로 실패한 추론 결과를 다음 채점에 사용하지 않는다.

```bash
(
  set -e
  for AEGISLM_EVAL_SET in phase-f-source-v5-r1 phase-f-source-untouched-blind-480-v1; do
    AEGISLM_EVAL_DATA="data/processed/$AEGISLM_EVAL_SET"
    AEGISLM_EVAL_OUTPUT="outputs/source-v2-unsloth-fresh-v1/$AEGISLM_EVAL_SET"
    python scripts/run_source_inference.py \
      --dataset "$AEGISLM_EVAL_DATA/challenge.jsonl" \
      --predictions "$AEGISLM_EVAL_OUTPUT/base.jsonl" \
      --model-id unsloth/gpt-oss-20b-unsloth-bnb-4bit \
      --model-revision 093fba6992ef5a7152481afec0bdfca1ac486998 \
      --run-id "fresh-base-$AEGISLM_EVAL_SET" --backend unsloth
    python scripts/run_source_inference.py \
      --dataset "$AEGISLM_EVAL_DATA/challenge.jsonl" \
      --predictions "$AEGISLM_EVAL_OUTPUT/adapter.jsonl" \
      --model-id source-v2-unsloth-fresh-v1 \
      --base-model-id unsloth/gpt-oss-20b-unsloth-bnb-4bit \
      --model-revision 093fba6992ef5a7152481afec0bdfca1ac486998 \
      --adapter-path adapters/source-v2-unsloth-fresh-v1/full/final \
      --run-id "fresh-adapter-$AEGISLM_EVAL_SET" --backend unsloth
    for AEGISLM_EVAL_ROLE in base adapter; do
      python scripts/evaluate_source_predictions.py \
        --challenge "$AEGISLM_EVAL_DATA/challenge.jsonl" \
        --gold "$AEGISLM_EVAL_DATA/gold.jsonl" \
        --predictions "$AEGISLM_EVAL_OUTPUT/$AEGISLM_EVAL_ROLE.jsonl" \
        --summary-json "$AEGISLM_EVAL_OUTPUT/$AEGISLM_EVAL_ROLE-summary.json" \
        --report-html "$AEGISLM_EVAL_OUTPUT/$AEGISLM_EVAL_ROLE.html" --wandb
    done
    python scripts/compare_source_runs.py \
      --base-summary "$AEGISLM_EVAL_OUTPUT/base-summary.json" \
      --adapter-summary "$AEGISLM_EVAL_OUTPUT/adapter-summary.json" \
      --output "$AEGISLM_EVAL_OUTPUT/comparison.json" --wandb
  done
)
```

### 코드 인계 검증

초기 작성 시에는 Ruff lint·format, mypy, Python 구문 컴파일, 설정 JSON 문법만
검사했다. 2026-09-26에는 사용자 요청에 따라 CPU/mock 회귀 테스트를 실제 실행했다.
검증 대상은 `f7151fb`에 main.py 기본 실행 복구 및 완료 checkpoint 복구의 로컬
수정분을 더한 작업 트리이며, 테스트 당시 이 수정분은 아직 커밋하지 않은 상태다.
환경은 루트 `.venv`의 Python 3.12.13, pytest 9.1.0이다.

| 검사 범위 | 결과 |
| --- | --- |
| `test_main`, `test_completed_checkpoint`, `test_fresh_training`, `test_source_gate` | 74 passed, 1.23초 |
| 위 4개를 포함한 아래 14개 관련 회귀 테스트 파일 | 300 passed, 1.85초 |

74개는 300개에 포함된다. 저장소 전체 `tests/`를 실행한 결과는 아니다.
모델·tokenizer 실제 로드, GPU 학습·추론, 실제 W&B 접속은 수행하지 않았다.
GPU를 숨기고 Hugging Face를 오프라인으로 설정했으며 pytest 외부 플러그인
자동 로딩을 비활성화했다. 모델·외부 서비스 관련 동작은 모의 객체로 검증했다.

```bash
env CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  WANDB_MODE=disabled PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  .venv/bin/python -m pytest \
  tests/test_main.py \
  tests/test_completed_checkpoint.py \
  tests/test_fresh_training.py \
  tests/test_source_gate.py \
  tests/test_source_training.py \
  tests/test_source_training_config.py \
  tests/test_source_checkpoint_gate.py \
  tests/test_source_peft_control.py \
  tests/test_source_inference.py \
  tests/test_source_evaluation.py \
  tests/test_artifacts.py \
  tests/test_tracking_receipt.py \
  tests/test_wandb_tracking.py \
  tests/test_diagnose_source_canary.py -q
```

이번 실행에서 실패한 테스트는 없었다. 이는 모의 입력에 대한 기록·검증·복구
경로의 회귀 검증이며, 이전 smoke의 출력 품질 문제가 해결됐다는 근거는 아니다.
기존 `adapters/source-v2-unsloth-fresh-v1/smoke/post_training_gate_predictions.jsonl`을
읽기 전용으로 재확인한 결과, 8건 중 파싱 가능한 객체는 7건이며 그 7건 모두
`assessment_basis`가 객체로 출력되고 지정 CWE 불일치 오류가 기록돼 있었다.
이 artifact에는 새 `input` 및 `extracted_final` 필드가 한 건도 없어 실제 모델
입력부터 파싱까지의 전체 경로를 당시 결과만으로 재구성할 수 없다.
다음 GPU 진단은 기존 결과를 보존하는 새 실험 경로에서 입력·출력 기록을 포함해
사용자가 실행한 뒤 분석한다. 학습 전 base 비교와 실제 runtime 복구도 미검증이다.

진단용 `configs/source_v2_unsloth_trace_smoke.json`은 기존 fresh 설정에서
`training.output_dir`와 `training.checkpoint_dir`만 `source-v2-unsloth-trace-v1`
경로로 변경했다. 모델·데이터·학습 조건은 유지한다. 저장소 루트의 Bash에서
아래 준비 명령이 성공한 뒤 smoke 명령을 실행한다. GPU 실행은 사용자가 담당한다.

```bash
source experiments/training-loop-debug/activate.sh
python scripts/train_source_unsloth_fresh.py \
  --config configs/source_v2_unsloth_trace_smoke.json --prepare-only
python scripts/train_source_unsloth_fresh.py \
  --config configs/source_v2_unsloth_trace_smoke.json --stage smoke
```

학습은 32건·10 optimizer step, 평가는 8건이다. 학습 trace는
`adapters/source-v2-unsloth-trace-v1/smoke.training-trace-<uuid>.jsonl`,
평가 입력·출력은 같은 root의 `smoke/post_training_gate_predictions.jsonl`에
남는다. `smoke/post_training_gate.json`의 품질 결과도 함께 확인한다.
동일 경로를 다시 쓰려고 기존 결과를 삭제하지 않는다. 재실험은 설정의 두 저장
경로를 모두 새 경로로 변경하고, 중단 복구는 위의 재개 조건을 따른다.


### 2026-09-27: 전체 데이터 비교 실험 승인

사용자는 AegisLM-B200의 Qwen3 실험과 비교하기 위해 기존 10,000건 train,
1,000건 validation, 500건 challenge 구성을 유지한 본 학습을 명시적으로
요청했다. 이는 기존 canary의 품질 실패를 인정한 탐색 실험이며, canary 통과에
따른 승격이 아니다. Qwen3 실험의 설정·결과는 이 저장소에서 확인하지 않았고,
동일한 데이터 파일 해시나 학습 조건을 사용했다고 주장하지 않는다. 여기서는
기존 고정 source-v5-r1 데이터와 GPT-OSS fresh recipe를 그대로 사용한다.

전용 설정 `configs/source_v2_unsloth_full_comparison.json`은 fresh 설정에서
adapter/checkpoint 경로만 `source-v2-unsloth-full-comparison-20260927-v1`로
변경한다. RTX A6000 48GB 한 장, batch 2 × accumulation 4, 1 epoch,
학습률 5e-5, 약 1,250 optimizer step이다. 기존 B200 두 장과의 차이는
비교 결과의 제한사항으로 남긴다.

```bash
source experiments/training-loop-debug/activate.sh
python scripts/train_source_unsloth_fresh.py \
  --config configs/source_v2_unsloth_full_comparison.json --prepare-only
python scripts/train_source_unsloth_fresh.py \
  --config configs/source_v2_unsloth_full_comparison.json --stage full \
  --exploratory-full-reason 'User authorized full 10000-record comparison after failed small-run quality gates; retain validation 1000 and challenge 500 for analysis against the separate AegisLM-B200 Qwen3 experiment.'
```

이 명시적 옵션이 없으면 기존 full 진입 조건은 그대로 유지된다. 옵션은 full
학습에서만 허용하고 빈 사유·prepare-only·reload-only 조합은 거부한다.
학습 전에 adapter root의 `full.execution-intent.json`에 사유, 설정/데이터 digest와 레코드 수를
보존한다. 같은 실행을 resume할 때 사유와 설정도 일치해야 한다. 완료 manifest에
`execution_mode=exploratory_full`, `canary_promotion_verified=false`를 기록한다.

데이터 해시·분할 중복·정답 contract·토큰 길이·assistant-only masking·유한한
loss/gradient·실제 LoRA update·저장/재로딩 검사와 90% 품질 기준은 유지한다.
학습 후 품질 gate 실패는 그대로 실패로 기록하고 nonzero로 종료한다. 실패를
이유로 유효한 adapter와 예측 결과를 삭제하지 않는다.

현재 Trainer는 runtime mask 호환성 문제로 validation loss 계산을 하지 않는다.
validation 1,000건 전체의 사전검사와 고정 40건의 저장 후 생성 gate를 수행하며,
이를 1,000건 전체 평가라고 부르지 않는다. validation 1,000건 전체 평가와
challenge 500건 base/adapter 비교는 별도의 후속 실행이다. challenge/gold를
학습이나 checkpoint 선택에 사용하지 않는다. 최종 adapter만 비교하며 best
checkpoint를 선택했다고 주장하지 않는다. W&B 업로드는 이번 명령에 포함하지 않는다.


실행 확인: 전체 CPU/mock 회귀 테스트 422개, Ruff lint/format, mypy 및
전용 설정 prepare-only 통과 후 본 학습을 시작했다. 1,250 step 중 162 step
진행과 checkpoint-150 저장을 관측했다. 완료·출력 품질 개선은 아직 미확인이다.
로그·실행 메타데이터·종료 상태는
`outputs/source-v2-unsloth-full-comparison-20260927-v1/`에 보존한다.
실행 사유 파일은 checkpoint resume의 빈 stage 검사와 충돌하지 않도록
adapter stage 밖에 보관한다. 최초 실행의 동일 사유 파일은 내용 변경 없이
해당 위치로 이동했고, 학습 프로세스는 계속 실행 중이다.

## 2026-09-28: Q1R10/Q1R11 two-stage GPT-OSS comparison

The successful B200 reference is independent decision and evidence adapters, not
source-v5-r1 full-report generation. The new `source_two_stage_v1` recipe reuses
frozen decision-v1 (10000/1000), evidence-lines-v1 (9975/996), and the original
Qwen fresh-blind-500 benchmark and contract artifacts. This last set is a reused
comparison benchmark, not newly collected unseen evidence.

`scripts/train_source_two_stage.py --config configs/source_two_stage.json --stage all`
performs preparation, actual GPU forward/padding comparison, base dev100,
decision training/reload gate, independent evidence training/reload gates, then
validation and benchmark evaluation. Other stages are prepare, decision,
evidence, evaluate. Each worker runs in a separate process. Run with the existing
`experiments/training-loop-debug/.venv/bin/python`; no dependency upgrade is needed.

Both adapters start from the pinned Unsloth GPT-OSS BnB4bit base. Each uses 100
optimizer steps, batch1/accumulation32, LR1e-4, warmup0.1, cosine, adamw8bit,
weight decay0.01, seed3407 and LoRA rank8/alpha16/dropout0.05. Attention targets
and expert layers7/15/23 retain the verified local configuration. These differ
from Qwen BF16/all-linear and are reported as cross-model confounders.

The maximum training sequence is4096, without truncation or packing. Training
pads right; generation pads left and uses low reasoning, greedy batch1,
decision128/evidence512 new tokens. The GPT-OSS template clock is frozen to the
run UTC date. Prompt tokens and padding have label -100; Harmony answer boundary
and final JSON remain supervised. Preflight compares actual model logits at
supervised positions, solo versus left/right padded batches, with atol0.5,
rtol0.02 and loss difference <=max(0.05,2%). Failure blocks all training.

Decision emits assessment only. Evidence receives the predicted binary assessment
and numbered original source, emitting source-evidence-lines.v1 ranges and
confidence. Gold assessment is only a training/oracle diagnostic condition;
pipeline inference never falls back to gold. Invalid/uncertain decisions fail the
pipeline without omission. Range validation rejects reverse, overlapping,
duplicate and out-of-bounds ranges. A deterministic resolver and renderer create
the existing source-v2 report using exact input substrings and the requested CWE.

Development uses the original shared100 IDs. Promotion requires decision P>=.90,
R>=.95,FPR<=.05,abstention<=.05,parse/schema>=.99; evidence P/R>=.50,
parse/schema>=.99,renderer=1.00 with complete predictions. Both oracle evidence
and predicted-decision evidence gates must pass. Report the gap to Qwen HF
P/R=.9881/1.0 and evidence F1=.9114; passing minimum gates does not imply matching
Qwen quality. Benchmark results never select checkpoints or change thresholds.

Weights & Biases is required for these training workers. A remotely readable
readiness summary precedes the first optimizer step. Approved scalar metrics
are also journaled locally; raw prompts, code, predictions, diffs and weights
remain local. Evaluation metrics update the same objective run. Checkpoints at
10/25/50/100 and final adapters occupy distinct ignored output roots. Existing
runs cannot be overwritten or silently resumed. A failure stops automatic
continuation; no extra epochs, changed thresholds, merging or vLLM serving occur.

Ported contract/evaluation reference: AegisLM-B200 commit
`a07072698d5747721697480045d7c71dc631b5f6`. Validation includes synthetic contract
and no-gold-fallback tests, complete repository checks, frozen inventory audits,
and dev100 oracle scoring. Actual execution results are recorded under
`outputs/source-two-stage-20260928-v1` and linked to their W&B runs.

### Actual preparation result: blocked by benchmark overlap

The 2026-09-28 implementation passed 439 tests, Ruff check/format and mypy.
The real frozen dev100 gold yields decision/evidence/renderer scores1.0 through
the ported evaluators. All21,971 supervised rows tokenize without truncation;
maximum lengths are decision train/validation1472/1466 and evidence1704/1455.
These are preparation/oracle checks, not trained model quality results.

Actual ID and visible-code comparison contradicts the B200 document's independent
fresh-blind claim for the locally frozen artifacts:

| Comparison | Same ID | Same source code |
|---|---:|---:|
| decision train vs validation | 0 | 0 |
| decision train vs fresh-blind500 | 204 | 206 |
| decision validation vs fresh-blind500 | 292 | 292 |

Thus498/500 benchmark rows reuse training or validation code. The benchmark
manifest names the older `phase-f-sard-grounded-v2/eligible_manifest.parquet` as
its exclusion input, while decision training descends from source-v5-r1. This
is consistent with an obsolete exclusion reference, but the original B200
server training/prediction artifacts have not been re-audited here. No conclusion
about the cause of the earlier GPT-OSS generation failure follows from this.

The preparation stage failed closed and preserved
`outputs/source-two-stage-20260928-v1/preparation-audit.json`. GPU forward,
baseline generation, W&B training runs and optimizer updates did not start.
The unchanged benchmark must not be used to claim independent generalization.
A replacement evaluation set must exclude actual decision/evidence train and
validation code/group identities before the planned run proceeds. Keep this
failed preparation artifact; use a new experiment namespace for a corrected run.

## 2026-10-02: v5 decision-only execution

사용자가 요청한 2단계는 `configs/cc_source_decision_v5.json`과
`scripts/train_cc_decision.py`로 연결한다. 이전 `source_two_stage_v1` 설정은
historical 데이터에 고정된 별도 실험이다. 새 경로는
`data/processed/cc-source-candidates-20260928-v5`만 읽으며 근거 adapter를
학습하지 않는다. 데이터셋을 재생성하거나 검수 상태를 변경하지 않는다.

### 입력·출력과 실험 범위

- train: `decision-candidates/train.jsonl` 10,000건. 이 파일만 Trainer에 전달한다.
- validation: `decision-candidates/validation.jsonl` 1,000건. seed3407의
  결정적 해시로 50/50 구성의 development100을 선택하며, optimizer에 전달하지 않는다.
- test: `decision-candidates/challenge.jsonl` 500건과 분리된 `gold.jsonl`.
  생성 입력은 system/user 메시지만 사용한다. 고정 final adapter 학습이
  완료된 후 동일 ID·순서·프롬프트로 base/adapter를 비교한다.
- 출력 계약: `{"assessment":"present|not_observed|uncertain"}`만 생성한다.
  함수 원문과 요청 CWE가 user 입력이고 판단 JSON이 assistant 학습 정답이다.
  annotation, 출처 메타데이터, test 정답은 생성 입력으로 넣지 않는다.
- 원천 라벨과 CWE는 미검수다. `allow_unreviewed_source_labels=true`는
  원천 라벨 기반 탐색 실험을 명시하는 설정이며, canonical의
  `approved_for_training=false`를 바꾸지 않는다. 결과 점수는 원천 라벨과의
  일치도이며 검수된 취약점 정확도나 production 승격 증거가 아니다.
  근거 데이터 검수·학습은 별도 후속 작업으로 남긴다.

### 고정 비교 예산과 실행 조건

기존 Qwen 비교 계획의 GPT-OSS 예산을 유지한다: max_steps100,
batch1/accumulation32, LR1e-4, warmup0.1, cosine, adamw8bit,
weight_decay0.01, seed3407, LoRA rank8/alpha16/dropout0.05,
attention q/k/v/o와 expert layers7/15/23. 이는 단일 GPU에서 3,200번의
레코드 제시를 사용하는 설정이고 **10,000건 전체 1 epoch가 아니다**.
10,000건 풀의 전체 학습·소스 분포를 모두 소진했다고 보고하지 않는다.
Qwen BF16/all-linear/B200 2장과도 완전히 동일한 조건은 아니며, 새 v5의
점수를 과거 Q1R10/Q1R11 점수와 직접 비교하지 않는다. 같은 v5 test500의
Qwen 평가가 있어야 데이터셋을 맞춘 모델 비교가 가능하다.

기준 모델은 `openai/gpt-oss-20b`, 실행 모델은
`unsloth/gpt-oss-20b-unsloth-bnb-4bit`, revision은
`093fba6992ef5a7152481afec0bdfca1ac486998`다. 기존 로컬 캐시와
`experiments/training-loop-debug/.venv`를 사용하며 별도 다운로드나
패키지 갱신을 수행하지 않는다. 템플릿 날짜는 `2026-10-02`에 고정한다.
max_seq_length4096, truncation/packing 없음, prompt/padding label=-100,
Harmony answer boundary·final JSON supervised, 훈련 right padding,
생성 left padding/low reasoning/greedy/batch1/max_new_tokens128이다.

활성 산출물 폴더는 `outputs/cc-decision-20261002-v7`,
`adapters/cc-decision-20261002-v7`, `checkpoints/cc-decision-20261002-v7`다.
이 v7은 **실행 준비 기록의 버전**이며 데이터셋은 계속 v5다.
기능 진단은 `outputs/cc-unsloth-runtime-20261002-v5`와
`adapters/cc-unsloth-runtime-20261002-v5/final`에 분리한다.
실행 준비 v1/v2는 정적 검토 보완 전 CPU 기록으로 보존한다.
검사 후 코드가 달라진 v2는 `context()`에서 실행을 차단했다.
활성 폴더의 보고서·run·adapter를 자동 덮어쓰거나 재시도하지 않는다.

### 단계별 명령

저장소 루트에서 실행한다. `--stage`는 필수이고 `all`이나 암묵적 학습은 없다.
준비 → 격리된 2-step 학습 → 새 프로세스 재로딩 → 실행 전 검사 순서다.
사용자의 Unsloth 호출 실패 조사 요청에 따라 진단 optimizer 실행을 추가했다.
아래 명령은 이미 완료한 현재 경로를 재현하는 순서이며, 그대로 재실행하면
기존 출력 보호 검사에서 차단된다. 다시 검증할 때는 새 경로를 설정한다.

```bash
experiments/training-loop-debug/.venv/bin/python scripts/train_cc_decision.py --config configs/cc_source_decision_v5.json --stage prepare
experiments/training-loop-debug/.venv/bin/python scripts/diagnose_cc_unsloth.py --config configs/cc_source_decision_v5.json --output outputs/cc-unsloth-runtime-20261002-v5 --stage train
experiments/training-loop-debug/.venv/bin/python scripts/diagnose_cc_unsloth.py --config configs/cc_source_decision_v5.json --output outputs/cc-unsloth-runtime-20261002-v5 --stage reload
experiments/training-loop-debug/.venv/bin/python scripts/train_cc_decision.py --config configs/cc_source_decision_v5.json --stage preflight
```

완료된 prepare/preflight를 같은 폴더에서 다시 실행하지 않는다.
아래 4단계 명령은 GPU preflight가 통과해야 실행할 수 있다.
**현재 v7의 기능 준비 검사는 통과했다.** 아래 본 실험 명령은 아직 실행하지
않았다. 사용자가 정한 순서대로 3단계 commit/push를 거쳐 4단계를 진행한다.

```bash
experiments/training-loop-debug/.venv/bin/python scripts/train_cc_decision.py --config configs/cc_source_decision_v5.json --stage baseline
experiments/training-loop-debug/.venv/bin/python scripts/train_cc_decision.py --config configs/cc_source_decision_v5.json --stage train
experiments/training-loop-debug/.venv/bin/python scripts/train_cc_decision.py --config configs/cc_source_decision_v5.json --stage evaluate
```

baseline은 base/development100만 평가한다. base가 성능 기준에 미달해도
분석을 위해 완전한 100건의 기준선 기록이 있으면 판단 학습을 진행할 수 있다.
훈련 중 validation/test로 체크포인트를 선택하지 않는다. checkpoint10/25/50/100은
진단 보존용이며, 비교는 고정 final100을 재로딩해 수행한다. 이후 evaluate는
base/adapter 각각 development100·validation1000·test500을 평가한다.
기존 판단 기준 P>=.90/R>=.95/FPR<=.05/abstention<=.05/parse·schema>=.99는
원천 라벨 기반 보고용으로 유지하며, gate 실패를 자동 추가 학습·기준 완화로
이어가지 않는다. 별도 근거 학습이나 자동 production 승격도 없다.

prepare는 actual canonical ID/code/group/CVE/commit/function-family와
identifier-normalized 5-gram Jaccard>=.8 분할 겹침을 다시 검사한다.
모든 11,500건을 고정 학습 형식으로 토큰화해 truncation·정답 마스크를 확인한다.
현재 preflight는 `batch1_training_and_reload_v1` 정책을 사용한다.
train에서만 뽑은 64건(32/32, 최단·최장 포함)으로 batch1/accumulation32의
실제 forward/backward와 optimizer2회를 수행한 진단 증명을 확인한다.
warmup의 첫 LR0은 정상으로 허용하되, 양수 LR 단계에서 직전 가중치와의
변경 및 유한·비영 gradient를 확인한다. 저장된 adapter의 digest와 새 프로세스의
활성 adapter/동일 LoRA 값도 대조한다. GPU UUID/driver, 설정·코드·데이터·
토크나이저 SHA, 패키지 버전과 실제 train64 IDs를 준비 기록에 묶고,
변경되면 worker 내부에서도 실행을 막는다. 패키지 기록에는
bitsandbytes/triton/accelerate/tokenizers도 포함한다. preflight 자체의 optimizer는
0회다. 진단 adapter는 본 학습의 초기값으로 사용하지 않으며 본 학습은 base에서
다시 시작한다. 이 검사는 생성 출력·품질·100-step 안정성을 보증하지 않는다.

과거 left/right 단독·batch2 비교의 atol0.5/rtol.02 및 loss 오차
max(.05,단독 loss의2%) 실패는 아래에 그대로 보존한다. 기준을 완화하거나
통과했다고 표시하지 않는다. 현재 batch1 학습의 기능 조건과 다른 배치 크기의
수치 동등성을 구분하며, batch2·serving을 확대할 때 별도 조사가 필요하다.

W&B preflight는 인증·`aegislm` 프로젝트와 해당 진단의 원격 성공 summary를
읽기 전용으로 조회한다. training/reload/receipt/remote run의 ID·path,
진단 namespace·recipe·base revision을 묶어 이전 성공 run을 대체할 수 없게 한다.
진단 run은 recipe=`cc_unsloth_smoke_v1`, objective=`decision-runtime-smoke`,
본 학습 run은 recipe=`cc_decision_v1`, objective=`decision`, group=`source-v2`다.
Trainer 구성과 목적지 검사를 끝낸 뒤 run을 열고, 원격 readiness 기록을
다시 읽어 확인한 뒤 첫 optimizer step을 시작한다. 매 step의 승인된 scalar를
로컬에도 기록하고, 평가 집계는 해당 run에 추가한다. 코드·프롬프트·raw 예측·
가중치는 전송하지 않는다. 현재 사전 검사에는 완료된 진단 run이 필요하지만
본 학습 run은 아직 없다. 본 학습 기록 성공은 4단계에서 실제 run·step·종료
기록으로 별도 확인한다.

### 초기 2단계 검증 기록 — 실행 준비 v3–v5 이력

최종 CPU 준비는 10,000/1,000/500건 모두 통과했다. max_tokens는
4,055/3,772/2,947, supervised token은 16–18개였다. actual split audit가
통과했고 위 유사도 기준의 cross-split near-clone은 0건이었다.
이는 설정한 중복 정의의 결과이며 완전한 의미적·사전학습 독립성 주장이 아니다.
관련 코드 정적 검토에서는 16개 token 제한과 BnB 패키지 기록 누락을 찾아
보완했다. 모델·데이터 실행 검증은 별도로 수행한다.

첫 GPU 검사(v3)는 W&B 조회·모델 로드·tokenizer fingerprint를 통과했지만
Unsloth wrapper의 함수 시그니처 손실로 `create_causal_mask()` 필수 인자가
누락되어 첫 forward에서 중단됐다. `outputs/cc-decision-20261002-v3/preflight.log`와
읽기 전용 W&B 보고서를 보존한다. 설치 파일이나 패키지 버전은 변경하지 않았다.
새 worker에서는 Unsloth import 후 GPT-OSS 패치가 시그니처를 캡처하기 전에,
mask wrapper의 `__signature__`를 저장된 원본에서 복원한다. wrapper dispatch와
mask 계산은 그대로 유지하며 원본 시그니처가 없거나 GPT-OSS가 이미 패치된
프로세스는 거부한다. 인자 필터·전달 보존과 미지 런타임 거부 회귀 테스트를
추가했다. v4는 forward 실행에 성공했지만, 네 left/right·단독/배치
비교 모두 원래 수치 기준을 통과하지 못했다. 최대 logit 차이는
right 1.5/3.4921875, left 3.3125/2.84375이며 결과는
`outputs/cc-decision-20261002-v4/preflight/gpu-preflight.json`에 보존한다.
직접 forward의 기본 arange 위치 번호와 달리, v5의 비교는 attention_mask의
누적합으로 실제 토큰 위치를 0부터 맞춘다. 이는 생성 시 위치 규약과 일치하며
훈련의 right-padding live 위치와도 같다. 기존 `_old_*` mask alias가 남은
미지 프로세스는 추가로 거부한다. 패키지·가중치·허용 오차는 유지한다.
v5의 GPU/W&B 최종 결과는 아래에 기록한다.


당시 v5 실행 결과: **GPU gate 미통과, baseline/학습 시작 차단**.
`outputs/cc-decision-20261002-v5/readiness.json`에 전체 상태를 기록했다.
CPU manifest, 실제 tokenizer fingerprint, W&B 인증·프로젝트 조회는 통과했다.
GPU는 NVIDIA RTX A6000 1장이었고, actual package versions는 torch2.10.0,
transformers5.5.0, unsloth2026.6.9, unsloth-zoo2026.6.7, peft0.19.1,
datasets4.3.0, wandb0.30.0 및 추가 BnB/Triton/Accelerate/tokenizers를
manifest/readiness에 기록했다. base weights는 지정 revision 캐시에서 읽었다.
새 다운로드·패키지 변경·optimizer update·baseline generation·W&B run 생성·
Git commit/push는 수행하지 않았다.

| padding | train 극값 행 | max logit 차이 | 단독 loss | 배치 loss | 결과 |
| --- | --- | --- | --- | --- | --- |
| right | 최단 | 1.5 | 1.630033 | 1.676044 | fail |
| right | 최장 | 3.492188 | 9.091637 | 9.305327 | fail |
| left | 최단 | 2.65625 | 1.661777 | 1.658539 | fail |
| left | 최장 | 2.6875 | 9.091740 | 8.880322 | fail |

모든 비교에서 해당 레코드의 supervised16개 위치 전체를 검사했다.
최장 단독 forward의 left/right loss는 위치 번호 보완 후 거의 일치했으나,
right 단독/배치 결과는 v4와 같고 네 gate는 여전히 실패했다.
따라서 위치 번호만으로 원인을 설명하지 못한다. 현재 관측은 optimizer 전
base runtime의 padding/batch shape에 따른 수치 차이다. 수치 오차인지,
mask/kernel/quantization 처리 결함인지 아직 확정하지 못했고 학습 품질 실패와
같다고 단정하지 않는다. 허용 오차를 완화하거나 receipt를 수동 발급하지 않았다.
성공 receipt가 없어 worker가 다음 단계를 차단하는 것을 별도로 확인했다.

최종 저장소 검사: `uv run --offline --frozen pytest tests/ -q` **481 passed**,
`ruff check .`, `ruff format --check .`, `mypy aegislm/ tests/` 모두 통과했다.
독립 정적 검토에서 전체 supervised 위치·패키지 기록·mask 시그니처 시점과
기존 alias 처리 조건을 점검했다. 검토자는 모델/데이터/테스트 코드를 실행하지
않았고, 실제 GPU/W&B 결과는 위 실행 로그와 보고서에 근거한다.

이 시점에는 학습 설정 연결만 완료했고 GPU 준비 조건은 미충족이었다.
이후 사용자 요청으로 실제 batch1 튜닝을 진단하여 아래 기능 복구를 확인했다.
단독 반복 안정성, 동일 길이 batch1/2, padding 유무와 attention/quantized kernel을
분리하는 수치 차이 조사는 여전히 남는다. 아래 기능 진단의 성공은 이 표의
실패를 해소했다는 의미가 아니다.


### 2026-10-02: 로컬 GPT-OSS 양자화 실물 확인

사용자 요청에 따라 캐시 config뿐 아니라 safetensors 인덱스·헤더·NF4
quantization state, 동일 loader로 읽은 실제 모델 객체를 확인했다.
최근 GPU preflight의 실행 모델은
`unsloth/gpt-oss-20b-unsloth-bnb-4bit@093fba6992ef5a7152481afec0bdfca1ac486998`이며
`is_loaded_in_4bit=true`, `Linear4bit` 1,632개, `Params4bit` 1,632개였다.
attention q/k/v/o와 expert의 실제 weight quant_type은 NF4, 저장 dtype은
uint8(4bit 값을 packing), 해당 linear의 compute_dtype은 모두 BF16이었다.
임베딩은 BF16, 확인한 normalization weight는 FP32로, 모든 파라미터가
4bit인 모델을 뜻하지 않는다. 가중치 4개 shard는 합계 12,525,742,660byte다.
실제 로딩 직후 PyTorch 할당 VRAM은 약 11.68GiB였으며 forward activation은
포함하지 않는 측정이다.

별도 로컬 `openai/gpt-oss-20b@6cee5e81ee83917806bbde320786a8fb61efebee`는
quant_method=mxfp4, expert blocks/scales는 uint8, attention q_proj는 BF16이다.
이 원본 캐시와 최근 사용한 NF4 모델은 다른 양자화 형식·범위를 가진다.
이번 확인은 quantization의 품질 영향이나 앞선 GPU 수치 차이의 원인을
확정하는 실험이 아니다.

Unsloth는 DDP 호환 목적으로 `is_loaded_in_8bit=true`도 설정한다.
따라서 이 표시만으로 8bit 모델이라고 판정하지 않는다. 로딩된 quantization
config는 `load_in_4bit=true/load_in_8bit=false`이며, 위 실제 module/parameter와
quant_state가 NF4 4bit를 입증한다. 설치 source의 `models/vision.py:1321/1329`,
`models/llama.py:2830/2835`에서 해당 호환 플래그 설정을 확인했다.

증거는 `outputs/gpt-local-quantization-check-20261002/on-disk.json`,
`runtime.json`, `interpretation.json`, `runtime-v2.log`에 보존한다.
첫 확인 로그 `runtime.log`는 dtype 객체의 JSON 직렬화 오류로 저장 단계에서
실패한 기록이며, 재확인 시 dtype을 문자열로 저장했다.
모델 다운로드·패키지/가중치 변경·optimizer update·답변 생성은 수행하지 않았다.


### 2026-10-02: Unsloth 진단 학습 복구 및 현재 준비 결과

호출 모델명·revision은 설정과 실제 로딩에서 일치했다.
[공식 NF4 모델 저장소](https://huggingface.co/unsloth/gpt-oss-20b-unsloth-bnb-4bit)와
로컬 실물 확인 결과를 대조했다. 다른 프레임워크로 변경하기 전에 현재
Unsloth 경로의 기능 실패와 검사 코드의 실패를 분리했다.

수정한 원인은 다음과 같다.

- Unsloth mask wrapper의 시그니처 손실 때문에 GPT-OSS의 인자 필터가
  `config`/`inputs_embeds`/`attention_mask`를 누락했다. 패치 캡처 전에 원본
  시그니처를 복원하여 forward를 실행했다. 설치 패키지는 변경하지 않았다.
- warmup 초기 LR0에서 가중치가 그대로인 정상 동작을 학습 실패로 판단했다.
  유한·비영 gradient와 양수 LR 단계의 실제 가중치 변경을 확인하도록 수정했다.
- SDK의 문자열 `run.path`를 문자 단위로 join하여 W&B 경로가 깨졌다.
  문자열과 path components를 구분하고 프로젝트·run ID를 검증한다.
- raw Trainer의 `loss`를 W&B용 `training/loss` 변환 후 찾는 검사가 실제 학습을
  실패로 분류했다. raw loss를 먼저 검증한다. 새 프로세스도 `.env`를 직접
  로딩하여 저장 adapter의 W&B 재로딩 기록을 마무리한다.

최종 동결 후보의 진단은 `cc-unsloth-runtime-20261002-v5`이며, GPU는
NVIDIA RTX A6000 1장, runtime은 torch2.10.0+cu128, transformers5.5.0,
unsloth2026.6.9, unsloth-zoo2026.6.7, peft0.19.1, datasets4.3.0,
wandb0.30.0, bitsandbytes0.49.2, triton3.6.0, accelerate1.14.0,
tokenizers0.22.2다. 모든 버전·설정·소스·GPU·tokenizer 자산 hash는
`inputs.json`에 기록했다. B200에서의 실행 결과를 뜻하지 않는다.

| 확인 항목 | 실제 결과 |
| --- | --- |
| optimizer 입력 | v5 train64만 사용, 두 라벨32/32, 230/4055 token 극값 포함 |
| 설정 | batch1, accumulation32, 2-step; 나머지는 본 학습과 같은 고정 QLoRA 설정 |
| trainable LoRA | 15,040,512 parameters; base weights는 동결 |
| optimizer·gradient | optimizer2회, 유한·비영 gradient2회 |
| 실제 가중치 변경 | step1 LR0: 그대로, step2 LR1e-4: 직전 값에서 변경 |
| training loss | 2.003313183784485; step loss1.9749627113342285 / 2.031663656234741 |
| 시간·최대 torch 할당 VRAM | 109.1956초 / 17,754,068,992bytes(약16.54GiB) |
| 저장·새 프로세스 재로딩 | pass, active adapter=`default`, LoRA fingerprint·adapter digest 일치 |
| W&B | [완료된 진단 run cddnbn8c](https://wandb.ai/erad3254-looking-for-a-job/aegislm/runs/cddnbn8c), training/reload 성공 summary 원격 확인 |
| 공식 준비 검사 | v7 prepare/preflight 및 worker의 require_preflight 통과 |

학습 전 LoRA fingerprint는
`b768a2f3dd44148bf2650ab347fe36ca378101b2dad442e87d34d1fbd8bb5c75`,
학습 후·새 프로세스 fingerprint는
`7e3fcd508835609554f56898473e14d96f57bdfeed5b4e83636257c30dd15f53`다.
저장 adapter digest는
`630201b6b3fe28dfba77e3c18c7cfe0c2d1263924c6bcbad066dd5bce43eb738`다.
증거는 진단 폴더의 `inputs.json`, `observed-training.json`, `diagnostic.json`,
`reload.json`, `wandb.json`과 별도 train/reload 로그에 보존한다.
본 실험 준비 보고서는 `outputs/cc-decision-20261002-v7/preflight/`와
`readiness.json`에 기록한다. 준비 v6 및 진단 v1–v4의 실패·성공 로그도
덮어쓰지 않았다. 진단 v3/v4의 성공 결과는 이후 코드·설정 보완 전 이력이며
현재 receipt를 발급하는 증거로 사용하지 않는다.

독립 정적 검토에서 observed-training 파일 누락, 초기 fingerprint만 비교하는
양수 LR 오판정, 이전 W&B run으로 대체 가능한 바인딩 문제를 발견해 수정했다.
재검토자는 해당 변경에서 추가 material finding을 발견하지 못했으며
모델·테스트를 실행하지 않았다. 실제 GPU·W&B 증명은 위 실행 결과에 근거한다.
저장소 검증은 pytest **509 passed**, Ruff check/format 및 mypy(69 source files)
모두 통과했다. 원천 데이터14개 파일·13개 명시 checksum은 보존했다.

현재 확인한 것은 **Unsloth로 batch1 튜닝·저장·값 보존 재로딩이 가능하다**는
것이다. 새 프로세스 재로딩 후 forward/generation·품질은 이 진단에서 검사하지
않았다. 100-step 본 학습, base 기준선, test500 비교, commit/push는 아직
실행하지 않았다. 원천 라벨/CWE 미검수 및 canonical 승인 상태도 그대로다.
후속 순서는 commit/push → base development100 → base에서 판단100-step 학습
및 W&B 기록 → 동일 test500의 base/final-adapter 비교다. 기능 성공만으로
출력 품질이나 원천 라벨의 신뢰도를 주장하지 않는다.


### 2026-10-03: v5 base 평가 및 본 학습 실행

사용자가 커밋·푸시 → base 평가 → 본 학습 및 기록을 명시적으로 요청했다.
현재 상태는 진행 중이다. GPU는 RTX A6000 1장이고 고정 설정과 v5 분할은
앞 절의 계약을 그대로 사용한다. 먼저 기존 변경을 실험 브랜치
`experiment/training-loop-debug`에 커밋·푸시한 뒤 아래 두 명령을 순차 실행한다.

```bash
experiments/training-loop-debug/.venv/bin/python scripts/train_cc_decision.py --config configs/cc_source_decision_v5.json --stage baseline
experiments/training-loop-debug/.venv/bin/python scripts/train_cc_decision.py --config configs/cc_source_decision_v5.json --stage train
```

base 평가는 validation에서 고정한 development100이고 test500을 열지 않는다.
본 학습은 v5 train10000 풀만 사용하며 max_steps100/batch1/accumulation32의
3,200 presentations 예산이다. 진단 adapter에서 이어 학습하지 않는다.
평가 품질에 따라 예산·분할·정답을 변경하지 않고 고정 최종100-step adapter를
저장한다. W&B에는 승인된 scalar만 기록하며 원문·예측·가중치는 전송하지 않는다.
모델/패키지 다운로드와 test500 비교는 이 요청의 실행 범위에 넣지 않는다.

반복 제출 전 검증은 사용자가 지정한 tester `gpt-6-luna`/`xhigh`로 위임한다.
전용 verifier agent type이 런타임에서 제공되지 않아 default agent에 verify-only
계약을 적용했다. GPU와 코드·설정·문서·Git 쓰기는 메인이 담당한다.
최종 검사 로그는 `/tmp/aegislm-cc-training-tester-20261003/`에 기록한다.
실행 로그는 `outputs/cc-decision-20261002-v7/baseline.log`, `train.log`,
단계별 보고서는 같은 폴더의 `baseline/`과 `decision/`에 보관한다.
현재 이 절은 실행 계획·허가 기록이고 완료·품질 성공을 뜻하지 않는다.
실제 commit SHA, base 지표, 완료 step, W&B run, 시간·VRAM·adapter digest와
제한사항은 실행 후 이어 기록한다.
