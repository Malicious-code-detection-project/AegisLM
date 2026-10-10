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
현재 실행은 완료했다. 아래는 실행에 사용한 순서와 조건이다.
GPU는 RTX A6000 1장이고 고정 설정과 v5 분할은
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
아래 완료 기록은 실제 실행 결과에 근거한다. 본 학습 완료와 품질 성공을
구분하며 test500 비교·근거 학습·production 승격은 이번에 실행하지 않았다.


#### 완료 결과와 검증 근거

- 커밋·푸시: 하네스 `68b682d`, 학습 코드·설정·데이터 계보·실행 문서
  `975366a`를 `origin/experiment/training-loop-debug`에 먼저 푸시했다.
  base와 본 학습은 `975366a`의 소스에서 실행했다. prepare의 Git HEAD
  `6845515`는 커밋 전 기록이고, source60/config hash는 실행 시 그대로였다.
- tester 제출 전 검사: pytest509, Ruff check/format, mypy69 source files,
  diff whitespace 검사 모두 통과. 모델·추론 설정은 `gpt-6-luna`/`xhigh`로
  요청해 도구 호출이 수락됐지만 tester 자체 런타임에서는 실제 engine 설정을
  확인할 수 없었다. source/config를 수정하지 않은 verify-only 작업이었다.
- base: validation의 고정 development100을 모두 생성했다. unique ID100,
  manifest/report/JSONL의 ID 일치, missing/extra0을 확인했다.
  parse/schema pass0%, abstention100%, precision/recall0이었다.
  p50/p95 latency는 14,019.711/14,989.8829ms, 생성 latency 합계 약1,414.6초다.
  100건 모두 생성128 tokens=한도128, analysis marker 있음, final marker·
  terminal EOS·추출된 판단 JSON 없음이었다. 이는 해당 생성 예산의 출력 실패다.
  이 결과만으로 모델의 취약점 판단 능력 자체가 0이라고 해석하지 않는다.
  학습 조건은 변경하지 않았으며 품질 비교 시 생성 예산 제약을 따로 검토해야 한다.
- 본 학습: train10000 풀만 전달, batch1/accumulation32, max_steps100,
  Trainer epoch0.32. 3,200 presentations이고 전체10000 1 epoch가 아니다.
  첫 gradient 실제 확인과 100개 finite loss/gradient norm 로그를 확인했다.
  LoRA 가중치 fingerprint가 실제 변경됐다. 평균 training loss
  **0.20977129628881813**, 마지막 step loss **0.02821057289838791**.
  학습·최종 저장 manifest 기준 시간은 **4,411.0657초(약73분31초)**다.
- 저장: `checkpoints/cc-decision-20261002-v7/decision/checkpoint-{10,25,50,100}`,
  최종 `adapters/cc-decision-20261002-v7/decision/final`. 최종 adapter digest는
  `a143733f717b03f8c68d4a5ab79e6fc1a347d2d453d2a928abddd917566fde99`다.
- 새 프로세스 재로딩: active adapter=`default`, 저장된 576개 tensor와
  15,040,512개 parameter가 로딩 값과 정확히 일치했다. 논리값 hash는 양쪽 모두
  `483e30f161650a710e65e31f8fc7456c724f8db3ee1652a558b293a3f1240e93`.
  이 검사는 추가 optimizer0회이며 forward/generation 또는 품질 평가를 하지 않았다.
- W&B: [본 학습 run t32zum0i](https://wandb.ai/erad3254-looking-for-a-job/aegislm/runs/t32zum0i).
  실제 API 조회에서 state=`finished`, training_complete=true,
  optimizer_steps100, loss·gradient_norm의 step1–100 원격 history100개를 확인했다.
  평균 train_loss도 로컬 manifest와 일치했다. 학습 run은 진단 run과 별도다.
- GPU: NVIDIA RTX A6000 1장(총49,140MiB). 10초 간격 nvidia-smi 표본에서
  학습 시작–adapter 재로딩 완료 구간의 최대 관측 memory.used는 **17,797MiB**.
  이는 외부 표본 최대이며 정확한 torch peak/순간 최대를 뜻하지 않는다.
  runtime package 버전은 앞 절의 고정 manifest와 동일했다.

실행 원장은 `outputs/cc-decision-20261002-v7/execution-20261003.json`이다.
base의 `baseline/development.{json,jsonl}`, 학습의 `decision/{training,wandb}.json`
및 `metrics.jsonl`, `wandb-completion-20261003.json`,
`adapter-reload-20261003.{json,log}`, `gpu-samples-20261003.jsonl`과
`baseline.log`/`train.log`를 함께 보존한다. tester 검증 로그와 aggregate audit는
`verification-20261003/`에 복사해 임시 폴더에만 남지 않도록 했다.
실행 중지 marker는 GPU sampler만 종료하며 학습 결과를 바꾸지 않는다.

최종 실행 산출물은 Git 제외 경로이고, 결과 요약 문서만 추가 커밋·푸시한다.
현재 완료 판정은 커밋·푸시, base 기준선 생성, 고정 본 학습 및 저장/기록에
한정한다. test500은 optimizer/평가에 사용하지 않았으며 원천 라벨/CWE의
미검수 상태와 evidence 미학습 상태를 유지했다. 학습 loss나 재로딩 성공을
JSON 유효성·held-out 취약점 정확도·production 승인으로 해석하지 않는다.

### 2026-10-03: max-new-tokens-65536 — 생성 한도 비교 실험

base development100에서 100건 모두 생성128 token을 소진하고 final 채널이
없었다. 사용자가 최대 생성 토큰 수를 원인 가설로 두고 2**16 설정을 포함한
실험표 작성과 실행을 요청했다. `2**16`은 **65,536**이고, 공식 모델과 로컬 pinned
snapshot의 `max_position_embeddings`는 **131,072**다.
[공식 모델 설정](https://huggingface.co/openai/gpt-oss-20b/blob/main/config.json)의
문맥 한도는 입력과 출력을 합한 값이다. 65,536을 모델의 공식 최대치로
기록하지 않고 이번 실험의 `max_new_tokens`로 사용한다.

| 모델 | 생성 상한 | validation 표본 | 비교 목적 |
| --- | ---: | ---: | --- |
| base / final adapter | 128 | 동일2건, 라벨별1건 | 기존 한도 재현 |
| base / final adapter | 512 | 동일2건 | 소폭 확장 시 final 생성 여부 |
| base / final adapter | 2,048 | 동일2건 | reasoning에 충분한 여유를 주는 비교 |
| base / final adapter | 65,536 | 동일2건 | 요청한 큰 생성 상한 적용 |

실험 ID는 `cc-max-new-tokens-65536-20261003-v1`, 제목은
`max-new-tokens-65536 (context-window-131072)`다.
설정은 `configs/cc_max_new_tokens_65536_v1.json`, 실행은
`scripts/run_cc_max_new_tokens_65536.py`다. 기존 학습 설정·코드·adapter·데이터의
hash 바인딩을 그대로 확인하고, 새 결과만
`outputs/cc-max-new-tokens-65536-20261003-v1/`에 저장한다.
validation1000의 기존 development100에서 결정적인 순서로 라벨별1건을
선택한 뒤 모든 모델·한도에 같은 ID와 gold-free system/user 입력을 사용한다.
test500은 표본 선택·generation·평가에 쓰지 않는다.

기존 학습4096과 구분해 **추론 runtime context만131,072**로 로딩한다.
모든 실험 행에서 입력 token+요청한 생성 상한이 문맥 한도 안에 있는지
검사한다. tokenizer/date/low reasoning/greedy/4bit revision은 동일하게 유지한다.
EOS가 나오면 일찍 종료하며65,536개를 강제로 출력하지 않는다.
건당 `max_time=300`초 보호 한도를 둔다. 실제로 출력한 token 수, EOS,
token_limit/time_limit, final 채널, JSON parse/schema와 peak CUDA allocated/
reserved memory를 기록해 시간 초과를 생성 상한 도달과 혼동하지 않는다.
이 시간 한도는 decode step 경계에서 검사하며 정확한300초 강제 종료가 아니다.

```bash
experiments/training-loop-debug/.venv/bin/python scripts/run_cc_max_new_tokens_65536.py --stage prepare
experiments/training-loop-debug/.venv/bin/python scripts/run_cc_max_new_tokens_65536.py --stage run
```

이 실험은 optimizer0회인 원인 진단이다. 표본2건의 정확도·JSON 성공률을
전체 validation 또는 test500의 품질 결과로 해석하지 않는다. 같은 runtime
context에서 한도만 비교하므로 이전4096 context의100건 결과와 직접 합치지
않는다. 큰 한도에서 계속 실패하면 길이 부족만으로 설명하지 못하며
prompt/template/runtime·양자화 등을 별도 가설로 확인한다. 학습 중
`eval_strategy="no"`인 설정이나 validation loss 기록을 바꾸는 작업은 포함하지 않는다.

#### 가설과 반증 조건

- **H1: 생성128 token이 reasoning과 최종 JSON을 함께 담기에 부족하다.**
  관측 근거는 기존 base100의 length128/analysis100/final0이다.
  큰 한도에서 동일 입력의 정상 EOS·final·유효 JSON이 회복되면 이 표본에서
  H1을 지지한다. 길이를 늘려도 반복·시간 초과·잘못된 출력이 계속되면
  H1만으로 실패를 설명할 수 없다. 시간 초과는65,536 token을 실제로 모두
  출력한 실험과 구분하며, 이 경우 그 토큰 한도 자체의 효과는 미검증이다.
- **H2: prompt 또는 Harmony template/채널 전환 문제다.** 첫 base raw output에
  반복 문장과 예상하지 않은 commentary/tool 형태가 보였다. 이는 관측이고
  template 결함의 증명은 아니다. 이번 실험에서는 prompt와 template를
  고정하며, H1로 설명되지 않을 때 별도 비교 후보로 남긴다.
- **H3: 4bit/Unsloth 추론 runtime의 문제다.** 이번에 runtime·양자화는
  바꾸지 않으므로 이 가설을 직접 검증하거나 배제하지 않는다.

입력 형식·checksum·분할 검사는 통과했지만 원천 라벨/CWE는 미검수다.
출력 검사 실패를 곧바로 데이터 라벨 문제로 귀속하지 않고, 형식 회복을
취약점 판단 정확도 또는 근거 설명 품질 회복으로 해석하지 않는다.

#### 과정과 재현 기록

사용자 요청 순서는 검증 실패 원인 확인 → 생성 상한 비교 실험 요청 →
가설에 재사용할 수 있도록 전체 과정 문서화 요청이다. 다음을 함께 보존한다.

- 사전 확인: Git fetch/status, 공식·로컬 context131,072, GPU 유휴 상태,
  원 학습 config/hash와 source60/package/tokenizer/dataset 바인딩.
- 변경 범위: 새 실험 config·실행 script·회귀 테스트와 이 문서. 기존 학습
  config와 실행 소스의 고정 hash는 유지해 원 학습 기록을 덮어쓰지 않는다.
- 실행 전 검사: 생성65,536 전달, 입력+출력 context 검사, gold 제거,
  deterministic 표본 선택, EOS/token_limit/time_limit 분리 테스트.
- 재현 자료: `manifest.json`의 Git HEAD·추가 실행 script hash·UTC 준비 시각,
  config snapshot, `execution-source.py`, 고정 prompts/gold의 hash와 ID,
  기존 학습 provenance, package/GPU 정보, 모델별 `runtime.json`.
- 실행 자료: 모델별 `base.log`/`adapter.log`, 각 한도별
  `predictions.jsonl`·`generation.json`·`evaluation.json`, 최종
  `comparison.json`/`max-new-tokens-65536-comparison.md`. 실패한 실행 로그도 보존한다.

위 계획과 가설은 실행 전에 고정했다. 실행한 검증 명령·종료 코드·실측 결과·
중간 실패·해석은 아래에 추가하며, 미실행 내용을 완료로 기록하지 않는다.

#### 명명과 실행 전 수정 이력

사용자가 파일 제목만으로 주요 변경점을 식별할 수 있도록 요청했다.
이번 실험은 **생성 상한128→65,536**이 주 변수이므로 config/script/test/출력
폴더 이름에 `max_new_tokens_65536` 또는 `max-new-tokens-65536`을 넣었다.
전체 문맥 한도는131,072이므로 `context-window-65536`으로 표기하지 않는다.
앞으로도 실제 변경 변수와 수치를 제목에 넣고, `max`처럼 환경에 따라 뜻이
달라지는 이름보다 수치를 우선한다. config의 제목·변경 변수·기준값·목표값은
manifest와 실험표에도 기록한다.

첫 검사에서 pytest520개와 Ruff check/format은 통과했다. mypy는 새 테스트의
`row["messages"].append(...)`에서 dictionary 값 타입을 넓게 추론해 실패했다.
해당 fixture 변수에 `row: dict[str, Any]`를 명시하는 타입 힌트를 추가했다.
이는 테스트 코드의 타입 표기 수정이며 모델 설정·학습 데이터·생성 동작 변경은
아니다. 최초 검사 로그와 종료 코드는
`/tmp/aegislm-generation-budget-checks-20261003-v1/`에 보존한다.
최초 재검사/prepare 명령은 사용자 중단으로 실행되지 않았고, 이름 변경 전
프로세스·출력 폴더 확인 시점에 GPU 실험은 아직 시작하지 않았다.

#### 새 이름으로 검사·준비·실행

파일명 변경 후 `uv run --offline --frozen`으로 pytest tests/ -q(520 passed,
3.46초), Ruff check(통과), Ruff format --check(94 files), mypy aegislm/ tests/
(70 source files, 통과)를 확인했다. 모든 종료 코드는0이다.
위 prepare 명령도 종료 코드0으로 완료했고, original source60/config/package/
tokenizer/dataset 바인딩은 유지했다. 모델·package를 다운로드하지 않았다.

`2026-10-03T11:57:44.595973+00:00`에 run 명령을 시작했다. 실행 도중에는
완료를 주장하지 않으며 최종 상태는 `execution-result.json`의 종료 코드와
모든16개 generation case·8개 평가 행에 근거한다.
`verification/initial/`에 최초 검사 및 mypy 실패 로그,
`verification/current/`에 이름 변경 후 검사·prepare 로그를 복사했다.
`execution-intent.json`은 명령·UTC 시작 시각·optimizer0/test미사용을 기록하고,
`execution.log`와 모델별 로그는 실패를 포함해 보존한다.
GPU 로딩 로그에는 loaded context131,072가 표시되고, 생성 호출에는
`max_new_tokens`가 `max_length`보다 우선한다는 안내가 있다. 실제 상한과
출력 길이는 각 case의 `generation` 필드로 확인한다.

#### 완료 결과 / max-new-tokens-65536

run은 `2026-10-03T12:35:53.304679+00:00`에 종료 코드0으로 완료했다.
전체 실행 시간은 **2,288.7086초(약38분9초)**다. base/adapter 각2건×4개 한도의
총16개 generation과8개 평가 행을 기록했다. 원 학습의 adapter를 로딩했으며
추가 optimizer는0회다. 두 runtime 모두 실제 `max_seq_length`와
`max_position_embeddings`가131,072였다.

| 모델 | max_new_tokens | final marker | JSON/schema 통과 | 정상 EOS | token_limit | time_limit | 실제 생성 tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| base | 128 | 0/2 | 0/2 | 0/2 | 2/2 | 0/2 | 128, 128 |
| base | 512 | 0/2 | 0/2 | 0/2 | 2/2 | 0/2 | 512, 512 |
| base | 2,048 | 2/2 | 1/2 | 1/2 | 1/2 | 0/2 | 1,579, 2,048 |
| base | 65,536 | 2/2 | 1/2 | 2/2 | 0/2 | 0/2 | 1,579, 2,534 |
| adapter | 128 | 2/2 | 0/2 | 0/2 | 2/2 | 0/2 | 128, 128 |
| adapter | 512 | 2/2 | 0/2 | 0/2 | 2/2 | 0/2 | 512, 512 |
| adapter | 2,048 | 2/2 | 0/2 | 0/2 | 2/2 | 0/2 | 2,048, 2,048 |
| adapter | 65,536 | 2/2 | 0/2 | 0/2 | 0/2 | 2/2 | 2,316, 2,318 |

표의 final marker는 출현 횟수가 아니라 해당 case 수이며, 유효한 최종 답변을
뜻하지 않는다. JSON/schema가 둘 다 통과한 것은base의 동일한present1건뿐이다.
65,536 설정에서 base2건이 EOS까지 도달했다는 사실과 JSON2건이 통과했다는
주장은 구분한다. 실제 JSON 통과는1건이다.

- base의 present case는1,579 token에서 정상 JSON으로 종료했고 원천 라벨과
  일치했다. 128/512에서는 동일 입력에 final이 없었으므로 이 case는 H1을 지지한다.
- base의 not_observed case는65,536 설정에서2,534 token을 생성해 EOS로
  종료했지만, 추출한 final에 문장과 여러 Harmony message/channel/tool 형태가
  섞여 JSON 파싱이 실패했다. 뒤에 JSON처럼 보이는 부분이 있어도 첫 구조적
  final 경계를 바꾸거나 마지막 JSON만 골라 기존 스코어를 개선하지 않았다.
- adapter는8개 case 모두 JSON이 실패했다. final 경계 뒤에도
  `<|end|><|start|>assistant<|channel|>...analysis<|message|>`와 같은
  message/channel token이 반복됐다. 65,536 설정의2건은 약300.08/300.12초에
  time_limit으로 종료했고 실제 생성 길이는2,316/2,318 token이었다.
  이는65,536 token 전체를 소진한 결과가 아니다.

이번 판정은 **생성 상한을 늘리면 base의 일부 출력은 회복되지만, 길이만으로
base의 나머지1건과 adapter 실패를 설명할 수 없다**는 것이다. adapter의
시간 한도 이후 출력은 미검증이며, 아무리 길게 생성해도 반드시 실패한다고
주장하지 않는다. 다음 후보 가설은 Harmony 출력 계약, 학습 타깃의 special
token과 supervised span, adapter 적용 시 추론 동작이다. 반복을 관측한
것만으로 어느 가설도 원인으로 확정하지 않는다. 추가 학습과 test500 비교는
이 진단에 포함하지 않았다.

표본 ID는 `cc-55fa921bc64a64071c4dd1c9`와
`cc-b8bec7f8c250c406ad4ed545`다. base128의 input IDs와 generated128 IDs는
원 development100의 대응2건과 모두 정확히 일치했다. 이번 context 변경은
이2건의128token 재현에 영향을 주지 않았지만 다른 입력에도 일반화하지 않는다.
최대 torch CUDA peak allocated는14,688.0977MiB, peak reserved는14,750MiB다.
각 generate 전에 peak 통계를 reset했고 model 상주분도 포함한다. 이전의
10초 간격 nvidia-smi 관측값과는 측정 방법이 다르다.

최종 실험표는 `outputs/cc-max-new-tokens-65536-20261003-v1/`의
`max-new-tokens-65536-comparison.md`와 `comparison.json`, 종료 기록은
`execution-result.json`이다. 16건의 raw token IDs, 추출 final, 판정 오류,
latency·GPU 통계는 각 모델/상한의 artifact에 보관한다. 표본2건이므로
기존minimum100 평가gate의overall_pass는 충족하지 않으며 품질 합격의 근거로 쓰지 않는다.

2026-10-04 사후 검사에서는 기존 source/config/package/tokenizer/dataset
바인딩, 현재 config·script·보관 source의 hash, 최종 adapter digest 보존을
확인했다. 16건의 동일 ID·입력, 각 생성 상한과 실제 길이, EOS/토큰/시간
종료 조건, 저장 prediction의 재채점 결과를 확인했고 모두 통과했다.
같은 모델의 낮은 한도 출력은 높은 한도 출력의 정확한 token prefix였다.
검증 결과는 `post-run-audit.json`에 보관한다. 이는 메인의 사후 검사이며
독립 검토나 새 GPU 재실행을 했다는 뜻은 아니다. diff whitespace 검사도 통과했다.

### 2026-10-04: unsloth-official-gpt-oss-20b-reference

사용자가 기존 원인 탐색을 중단하고 공식 Unsloth GPT-OSS-20B 튜토리얼부터
다시 시작하기로 했다. 기존 데이터·adapter·실패 결과와 생성 상한 비교 이력은
보존하고, 먼저 공식 원본만 확보했다. 설치나 새 학습을 실행했다는 뜻은 아니다.

- [공식 튜토리얼](https://unsloth.ai/docs/models/gpt-oss-how-to-run-and-fine-tune/tutorial-how-to-fine-tune-gpt-oss)
- [공식 노트북 고정본](https://github.com/unslothai/notebooks/blob/92e38e86308748d18fc4cd4b104c4c6d3db1d67e/nb/gpt-oss-%2820B%29-Fine-tuning.ipynb)
- [공식 Python 예제 고정본](https://github.com/unslothai/notebooks/blob/92e38e86308748d18fc4cd4b104c4c6d3db1d67e/python_scripts/gpt-oss-%2820B%29-Fine-tuning.py)

원본 저장소는 `unslothai/notebooks`, 고정 commit은
`92e38e86308748d18fc4cd4b104c4c6d3db1d67e`(commit date2026-09-27)다.
수집 시각은 `2026-10-03T15:45:26.935028+00:00`(KST2026-10-04)이며,
`outputs/unsloth-official-gpt-oss-20b-tutorial-20261004-v1/`에 notebook221,115 bytes,
Python 예제16,960 bytes와 저장소 LICENSE를 내려받았다.
notebook SHA256은 `4e7057b11fa491adaaa2084547eff5cb7ed41f214578a9031a969220b5ec1b2b`,
Python SHA256은 `74ff47bb9212f482f7378d86f27bc088973e924ae427cc84891d87663131895a`다.
45개 notebook 셀 중20개 code cell을 별도 JSON으로 추출했고 실행한 셀은0개다.
`receipt.json`에 URL·commit·수집 시각·파일별 크기와 hash를 기록했으며,
`unsloth-official-gpt-oss-20b-finetuning-reference.md`에 요약과 비교를 남겼다.

확보한 코드의 주요 값은 max_seq_length1024, r8/alpha16/dropout0,
SFTTrainer, batch1/accumulation4/max_steps30, lr2e-4/linear다.
데이터는 Multilingual-Thinking이며 chat template로 text 열을 만들고
`train_on_responses_only`를 사용한다. response 경계는
`<|start|>assistant<|channel|>final<|message|>`다.
기존 경로는 plain Trainer와 직접 만든 label을 사용하며 빈 analysis 메시지와
final header도 supervised span에 포함될 수 있다. 마스킹이 같다고 가정하지
않고 실제 token/label을 비교해야 한다. 이것을 실패 원인으로 확정하지 않는다.

설치 셀의 Transformers4.56.2/TRL0.22.2는 현재5.5.0/0.24.0과 다르다.
공식 튜토리얼의 prose와 notebook 값도 일부 달라, 예를 들어 학습 step은
문장상60이지만 확보한 실행 셀은30이다. 재현에서는 이 고정 notebook의
실행 셀을 기준으로 하고 환경 변경·데이터 변경·기존 코드 재사용을 각각
기록한다. 모델 호출명은 alias이므로 실제 resolved model/revision/template를
확인하기 전에는 기존 bnb-4bit 가중치와 같거나 다르다고 단정하지 않는다.

다음 재현은 **공식 예제 기준 정상 학습·출력 확인 → C/C++ 데이터만 교체 →
동일 validation 확인** 순서로 준비한다. notebook의64-token 생성 시연을
완전한 최종 답변 검증으로 간주하지 않는다. 이번 단계는 자료 확보와 정적
비교까지이며 package 설치, 모델·튜토리얼 dataset 다운로드, GPU 학습·추론,
원천 데이터 포맷 변경은 아직 실행하지 않았다.

### 2026-10-04: final-only-mask-vs-empty-analysis-code-review

사용자가 팀원 작성 코드에서 실제 오류가 있는지 확인하기 위해 공식 예제와
기존 학습 코드의 비교 분석을 요청했다. 비교 대상은 실제 v5/v7 학습에 사용한
commit `975366a9e7ae0d56161097f7e558990d424b2b89`의 코드와 위에서 확보한
공식 commit `92e38e86308748d18fc4cd4b104c4c6d3db1d67e`의 실행 셀이다.
개인에게 귀속되는 오류나 Unsloth 자체의 실패로 단정하지 않는다.

상세 보고서는
`outputs/unsloth-official-gpt-oss-20b-code-review-20261004-v1/`의
`final-only-mask-vs-empty-analysis-code-review.md`에 보관한다. 파일명은 실제
비교 변수인 final-only mask와 빈 analysis 타깃을 표시한다. raw record와
token IDs, audit script·실패 로그는 Git 제외 artifact로 보존한다.

#### 확인된 설정 문제와 미확정 원인

| 항목 | 확인 근거 | 판정 |
| --- | --- | --- |
| decision 생성 상한128 | `two_stage_runtime.py:205`; 원 base100건 모두128 tokens, EOS0/final0 | 해당 평가가 답변을 자른 설정 문제. JSON0%만으로 판단 능력/데이터 오류를 단정할 수 없음 |
| 학습 중 validation 미실행 | Trainer에 eval_dataset 없음, `eval_strategy="no"` | validation 데이터 손상 근거가 아니라 실행을 분리한 설정. 별도 `--stage evaluate` 필요 |
| baseline 승격 조건 | count100·missing/extra0·ID/config 일치 검사 | quality 통과 조건이 아님. 당시 탐색 학습은 사용자 승인 범위 |
| 기존/공식 mask 차이 | 실제 cached tokenizer와 설치된 Unsloth mask로 train32건 재현 | 차이는 확정, adapter 반복 출력의 인과는 미확정 |

공식 예제도 eval_dataset을 연결하지 않는 소규모 시연이다. 따라서 validation
항목은 공식 기능 누락이라는 주장 대신 현재 품질 검증 목적과 실행 설정의
차이로 기록한다. max_new_tokens는 analysis를 포함한 전체 생성 예산이다.

비활성화 이유를 후속 확인하니 초기 source-v2 기록에는 Unsloth2026.6.9 /
unsloth-zoo2026.6.7 / Transformers5.5.0 조합의 GPT-OSS eval forward에서
create_causal_mask 호출 호환성 문제가 있어 Trainer의 validation loss를 끄고,
저장 adapter를 재로딩한 뒤 생성 gate로 검증하도록 했다고 명시돼 있다.
근거는 이 문서의 Canonical QLoRA configuration 및 fresh recipe 절,
`scripts/train_source_unsloth.py`의 trainer_eval_loss_disabled와
`scripts/train_source_unsloth_fresh.py`의
trainer_eval_loss=disabled_due_to_pinned_runtime_mask_incompatibility 기록이다.
v5/v7도 eval_strategy=no와 별도 evaluate 구조를 유지했다. 이는 문서에 남은
초기 우회 사유이며, 같은 오류가 v7에서 다시 발생했는지는 이번 조회로 새로
재현하지 않았다. validation을 중간 모니터링하는 것과 그 결과로 checkpoint를
선택하는 것은 별개다. 새 SFTTrainer recipe에서는 development100 loss를
25step마다 실제로 계산했으므로 그 경로의 중간 validation은 동작한다.

현 loader는 protocol128을 고정하고 변경을 거부하므로 config만 고치면
생성 호출이 바뀐다는 설명도 잘못이다. 다음 recipe에서 값과 호출을 함께
연결해야 하며, 기존 run의 불변 config를 임의로 변경하지 않는다.

앞선 길이 실험은 동일2건 중 base1건에서 JSON 회복을 확인했지만 adapter는
실패했다. adapter의65,536 설정은 약300초 시간 한도에서 종료했으므로
65,536 tokens 전체를 사용했다거나 길이가 전체 원인이라고 주장하지 않는다.

#### CPU 마스킹 재현

train10,000건의 assistant content를 집계하니 두 JSON 문자열이 각5,000건이다.
클래스별 첫16건, 총32건에 기존 helper를 적용하고, 동일 input_ids에 공식
response header로 설치된 Unsloth Zoo2026.6.7 마스크를 적용했다.
Unsloth 본체를 import하지 않고 검토한 함수3개만 AST로 추출했다.
그 결과는 다음과 같다.

| 클래스 | 기존 supervised tokens | 공식 final-only tokens | 추가 header tokens |
| --- | ---: | ---: | ---: |
| present | 16 | 7 | 9 |
| not_observed | 18 | 9 | 9 |

기존 labels에는
`<|channel|>analysis<|message|><|end|><|start|>assistant<|channel|>final<|message|>`
9토큰이 JSON 앞에 포함된다. 공식 mask를 같은 serialization에 적용하면
JSON과 `<|return|>`만 학습한다. 기존 label의50–56.25%가 답변 앞 형식이므로
loss 하락을 판단 성능 개선으로 읽지 않는다. header 학습 자체는 유효한 SFT
설계일 수 있으며, 이것이 adapter 실패 원인이라는 결론은 아직 없다.

32건 모두 prompt 부분이 -100이었고 종료 토큰200002가 supervised span에
포함됐다. 실제 DataCollatorForSeq2Seq에서도 labels가 보존되고 padding만
-100으로 마스킹됐다. 이 표본에서 입력 마스킹 손상이나 EOS 학습 누락은
재현되지 않았다.

현재 cached template에서는 assistant의 thinking 필드를 제거하면 final
channel 없이 `<|start|>assistant<|message|>`가 렌더된다. 이 role/content
문자열에 공식 final-only mask만 적용하면32건 모두 supervised tokens0이다.
이는 다음 포맷 변경 시 발생하는 재현된 오류이며 기존 학습이 그 방식으로
진행됐다는 뜻이 아니다. 함수 이름만 교체하지 말고 실제 header, label>0,
EOS를 함께 검사해야 한다.

CPU 실행 명령은 다음과 같다.

```bash
experiments/training-loop-debug/.venv/bin/python \
  outputs/unsloth-official-gpt-oss-20b-code-review-20261004-v1/mask-comparison-audit.py
```

최종 실행은 종료 코드0, CUDA initialized=false, model load=false,
optimizer0이며 test split은 사용하지 않았다. 기존 source/config/dataset/
tokenizer의 전후 hash는 같았다. 결과는 `cpu-audit-summary.json`,
`mask-comparison.json`, `cpu-audit-attempt-2.log`로 보존한다.
최초 audit는 새 감사 script가 apply_chat_template 반환을 list로 가정해
IndexError로 실패했다. `return_dict=False`를 명시해 재실행했고 성공했다.
최초 실패는 `cpu-audit.log`에 보존하며 팀 코드의 오류로 집계하지 않는다.

#### 기타 비교와 다음 수정 후보

plain Trainer와 SFTTrainer, LoRA target 범위/dropout, LR/scheduler/decay,
Transformers5.5.0/TRL0.24.0과 공식 설치 셀4.56.2/0.22.2는 차이가 있다.
현재 근거로 이 차이 자체를 버그로 분류하지 않는다. 공식 로드 dtype=None과
설명상의float32 주장은 구분하며 기존 bf16=True를 실패 원인으로 단정하지
않는다. alias와 pinned runtime 이름도 resolved weights 확인 전에는 다른
모델을 잘못 불렀다고 판단하지 않는다.

checkpoint100의 epoch는0.32다. batch1×accumulation32×100 updates의
3,200 presentations이며 train pool10,000건을 한 번씩 학습한 결과가 아니다.
고정 예산으로 이미 기록된 조건이고 실제 step 수가 잘못된 것은 아니다.

다음 후보는 공식 출력 동작을 먼저 확인하고 C/C++ serialization/mask의
CPU 검사를 거친 뒤, 동일 모델·표본·학습 예산에서 mask만 변경하는 비교다.
Trainer/package/LoRA/mask를 동시에 바꾸면 원인을 분리할 수 없다.
초기 품질 측정은 validation에서 EOS/final/JSON/판단 일치율을 함께 기록하고
test500은 최종 비교용으로 보존한다. 이번 리뷰에서는 production 학습 코드
수정, 새 GPU 실행, package 설치, 새 학습, 팀원 메시지 전송을 하지 않았다.

#### 팀원 전달용 요약과 현재 코드 재확인

후속 요청에 따라 현재 코드가 실제 학습에 사용한 버전과 같은지 다시 확인했다.
원 학습 manifest의 소스60개, CPU 감사의 입력·자산14개와 결과7개,
공식 원본3개의 hash가 모두 일치했다. 기존32건의 마스크 재현 결과도 대조했다.
추가 GPU 학습을 수행한 검증은 아니며 원 결과를 덮어쓰지 않았다.
재확인 receipt는 같은 출력 폴더의
`followup-current-code-verification-20261004-v1.json`이다.

팀원에게는 다음과 같이 전달할 수 있다.
“기존 평가에서 base100건 모두 생성 상한128에 도달해 final/EOS가 없었습니다.
학습 중 validation도 꺼져 있어서 낮은 train loss만으로 품질을 확인할 수
없었습니다. 공식 예제와 달리 빈 analysis 및 final header9토큰까지 loss에
포함하지만, 그 차이가 출력 반복의 원인인지는 아직 확인되지 않았습니다.
확인한32건의 입력 마스킹과 종료 토큰은 정상이었습니다.”

현재 확인된 평가 설정 문제와 학습 설계 차이를 구분해서 전달한다.
특정 작성자의 실수, 데이터 손상, Unsloth 결함으로 귀속하지 않는다.
공식 helper를 적용할 때는 final header와 label>0을 확인해야 하며,
role/content만 직렬화한 데이터에 helper를 단순 교체하면 label0이 되는
재현 결과도 함께 전달한다.

후속 결과 검사를 준비하며 평가 코드의 별도 예외 처리 오류도 CPU에서
확인했다. `aegislm/evaluation/source_decision.py`의 `_case`는 assessment를
문자열인지 확인하기 전에 허용 문자열 set에 포함되는지 검사한다.
`{"assessment":["present"]}` 또는
`{"assessment":{"value":"present"}}`는 TypeError(unhashable type)를 내어
스키마 실패 집계 대신 평가를 중단한다. null/정수는 스키마 실패로 집계된다.
이는 **재현된 평가 코드 오류**지만 과거 실제 모델 출력에서 이 형태가 나와
실패했음을 확인한 것은 아니다. 재현 입력은 모두 합성이며 receipt는 같은
비교 출력 폴더의 `schema-type-error-reproduction.json`에 보존했다.
실행 중인 학습의 source hash를 유지하기 위해 기존 평가 코드는 수정하지
않았고, 새 결과의 원문을 독립 집계할 때는 문자열 타입을 먼저 확인한다.

### 2026-10-04: sfttrainer-final-only-mask-eos-return

사용자는 확보한 공식 튜토리얼 소스로 학습을 시작하고 기존 생성 한도 실험표를
확장하되 토큰 길이를 유지하며 답변 종료 토큰까지 생성하는 방식을 검토하도록
요청했다. 새 설정은 `configs/cc_tutorial_final_only_eos_v1.json`, 진입점은
`scripts/train_cc_tutorial_final_only_eos.py`, helper는
`aegislm/training/tutorial.py`다. 원 v5/v7 source60/config/데이터/adapter와
완료된 생성 한도 실험은 보존한다.

#### EOS 검토와 길이 해석

GPT-OSS 답변의 native 종료는 `<|return|>`(200002)다.
`<|endoftext|>`(199999)는 엔진 종료로 별도 집계하고,
`<|end|>`(200007)는 analysis 메시지도 끝낼 수 있으므로 답변 종료에 쓰지 않는다.
기존 경로에도 `eos_token_id=[200002,199999]`가 이미 있었다. 따라서 이번 결과를
새 종료 토큰을 추가한 효과라고 해석할 수 없다.
[Transformers 생성 설정](https://huggingface.co/docs/transformers/main/en/main_classes/text_generation)은
EOS에 도달하면 상한보다 먼저 멈출 수 있도록 한다. max_new_tokens는 총 생성
예산이며 종료 토큰이 항상 그 안에서 생성된다는 보장은 없다. EOS까지 무한히
생성하거나 상한에서 강제로 EOS를 붙이면 정상 종료와 잘린 답변을 구분하기
어려워진다. 새 경로는 forced EOS를 끄고 answer_end/endoftext/token_limit/
time_limit을 따로 기록한다. 종료만으로 JSON/판단 품질을 합격 처리하지 않는다.

“길이 유지”는 직전 진단의 생성 상한65,536·전체 context131,072로 해석해
실행했다. 128을 뜻하는지 선택 질문에는 답변이 없어 직전 진단의 값을 유지했다.
학습 입력 한도는4,096, 진단 시간 한도는 case당300초로 유지한다.
max_time은 현재 decode pass 이후 검사하므로 정확한300초 hard timeout은 아니다.
상한/시간 제한에 먼저 도달하면 종료 토큰을 기다리며 재시작하지 않고 미완결로 남긴다.

실제 Transformers generate loop를 작은 CPU GPT2 테스트 모델에서 확인했다.
4건 모두 통과했으며 return이 상한 전에 종료, message-end 이후에도 생성 지속,
endoftext 종료, EOS 없이 상한 도달을 구분했다. 테스트는 합성 logits를 사용하며
실험 모델에는 적용하지 않는다. CUDA initialized=false이며 결과는
`outputs/cc-tutorial-final-only-eos-20261004-v1/native-eos-cpu-proof.json`이다.

#### 공식 예제의 적용 범위

이번 run은 **공식 text formatting → SFTTrainer → train_on_responses_only 경로를
C/C++ 데이터에 적용한 recipe**다. Colab 원본 환경·데이터의 그대로 재현은 아니다.

| 항목 | 기존 v7 | 새 recipe |
| --- | --- | --- |
| 학습 풀/입력/예산 | 10,000 / 4,096 / batch1×accum32×100steps | 유지, 3,200 presentations |
| Trainer / mask | plain Trainer / empty-analysis 및 header 포함 | SFTTrainer / final JSON+return만 |
| r / alpha / dropout | 8 / 16 / 0.05 | 공식8 / 16 / 0 |
| LR / scheduler / decay / warmup | 1e-4 / cosine / 0.01 / 10steps | 공식2e-4 / linear / 0.001 / 5steps |
| expert 범위 | layers7/15/23 | native linearized MoE의24개 layer 전체 |
| 중간 validation | 없음 | development100 loss를25step마다, batch1/loss-only |
| 추론 | bare assistant 시작 | 동일 bare 시작과 gold-free final-prefill 각각 비교 |

고정 공식 commit은 `92e38e86308748d18fc4cd4b104c4c6d3db1d67e`다.
원본은 max_seq_length1024/batch1/accum4/max_steps30이며 C/C++ 길이와 기존
학습 예산을 위해 위 값으로 바꿨다. pinned 4bit 모델과 현재 package를 재사용하고
새 model 다운로드·package upgrade를 하지 않는다. TRL 버전과 설치된 trainer/
mask/MoE 구현 hash도 새 manifest에 추가한다.

현재 BNB 모델의 expert는 `gate_up_projs/down_projs` ModuleList다. 공식 target
이름으로3D parameter를 자동 선택하면 실제 구조와 달라질 수 있어, attention과
모든 linearized expert를 regex로 명시하고 `target_parameters=[]`로 자동선택을
끈다. 사전 예상은 attention96 + expert1,536이며 실제 적용 이름/shape/
trainable 수와 finite backward는 아래 GPU preflight에서 확인했다.
기존 약15.04M보다 넓은 대상이므로 mask/Trainer만의 인과 실험은 아니다.

#### 시작 prefix와 전수 검사

공식 final-only mask를 사용하면 final header 전까지의 전이는 loss에서 제외된다.
cached template의 add_generation_prompt=True는 bare assistant에서 끝난다.
새 경로는 이를 구분하여 같은2개의 validation prompt를 두 방식으로 생성한다.
final-prefill은 system/user 뒤에 내용과 thinking이 빈 assistant를 렌더하고
맨 끝 return만 제거한다. gold JSON이나 판단 라벨을 입력에 넣지 않는다.
이 prefix가 실제 첫 supervised token 직전과 일치하는지 CPU 전수 검사한다.
prefill에서 final header는 입력에 있었음을 별도 기록하고, 모델이 생성했다고
집계하지 않는다. 모델이 내놓은 raw generation과 추출 JSON은 모두 보존한다.

train10,000/dev100의 CPU audit에서 모든 label이 정확히 JSON+return인 것을
확인했다. supervised tokens는 train7토큰5,000건/9토큰5,000건, dev는각50건이고
max input은 train4,055/dev2,583이었다. 공식 helper가 zero-label 행을 제거할 수
있으므로 실제 SFTTrainer/helper 이후에도 count/ID/order/input IDs/labels를
모두 대조한다. SFT 준비 과정에서 ID 열이 제거되면 전체 token/order 일치부터
검증한 뒤 ID를 재부착하며, tensor collator에는 모델 필드만 전달한다.

독립 계획 검토에서 prefix 불일치와 helper 필터링을 지적받아 이 검사를 추가했다.
독립 코드 검토에서는 preflight collator에 문자열 ID가 들어갈 수 있는 결함과
SFT의 ID 열 제거를 지적받아 모델 필드 분리·순서 검증을 반영했다. 초기 CPU
prepare 후보는 `run/`에 보존하고 validation W&B projection 등을 반영한 당시
후보는 `run-v2/`에 새로 바인딩했다. 리뷰 결과와 초기 검사 실패도 로컬 task에 기록한다.

run-v2의 실제 GPU 사전 검사는 종료 코드1로 실패했다. 수동 preflight가
SFTTrainer.train의 학습 모드 전환 wrapper를 거치지 않고 compute_loss를
호출해 eval attention 경로로 들어갔다. 이 경로의 out=matmul은 gradient가
있는 입력을 지원하지 않아 역전파 전에 오류가 발생했다. 본 학습·optimizer
update·새 W&B run은 시작하지 않았다. 이는 이번에 추가한 수동 사전 검사
코드의 결함이며, 이전 팀원 코드의 품질 실패 원인으로 소급하지 않는다.
실패 로그는 `execution-v2.log`, receipt는 `run-v2/execution-result.json`에
보존했다. 수정 후보는 실제 Trainer 설정으로 model.for_training/model.train을
호출하고 `run-v3/` 및 별도의 adapter/checkpoint attempt 경로에서 검증한다.
모델·데이터·패키지·학습 예산·생성 상한은 바꾸지 않는다.

run-v3의 CPU 검사는 pytest531 passed, Ruff check/format 및 mypy72개 파일
통과다. 수정 후 실제 GPU preflight도 optimizer0으로 통과했다.
가장 짧은230토큰/긴4,055토큰 입력의 loss는 각각1.678049/1.868650이며
두 입력 모두 training_mode=true, 유한한 비영 gradient를 확인했다.
실제 주입 모듈은1,632개, 학습 파라미터는92,454,912개이며 train10,000/
dev100의 토큰·정답 label 보존 검사도 통과했다. 정밀도는 bf16=true,
fp16=false, force_float32=0이었다. peak allocated15,952.75MiB,
reserved16,452MiB이며 결과는 `run-v3/preflight.json`에 보존한다.
본 학습용 새 프로세스에서 실제 step1/100을 확인했다. 첫 training loss는
1.350388, gradient norm은21.050524이며 warmup 첫 학습률은0이었다.
[W&B run c9gsifji](https://wandb.ai/erad3254-looking-for-a-job/aegislm/runs/c9gsifji)의
원격 기록 준비를 학습 전에 확인했다. 첫 step 시점에는 완료 결과와 adapter
품질을 확인하지 않았으며 첫 step loss로 개선을 주장하지 않는다.

25-step에서 development100의 첫 검증 loss는5.234795였다. 같은 step의
training loss0.085675와 차이가 크다. checkpoint-25의 Trainer state는
global_step25/epoch0.08이고 adapter·optimizer·scheduler 저장을 확인했다.
W&B API에서도 step25의 validation/loss5.234795를 동일하게 확인했고,
`run-v3/wandb-observation-first-validation.json`에 receipt를 보존했다.
validation은 학습에 섞이지 않은100건이며 JSON 생성 품질 지표와는 다르다.
높은 검증 loss의 원인은 아직 확정하지 않았다. 실제 일반화 실패 가능성과
GPT-OSS의 train/eval attention 경로·정밀도 차이 가능성을 가설로 기록하며,
어느 쪽도 이번 평균 loss만으로 증명하지 않는다. 고정100-step 예산과
validation25/50/75/100 조건을 유지하고 최종 생성 결과를 함께 확인한다.

50-step의 training loss는0.075435, 두 번째 검증 loss는4.965523이었다.
첫 검증보다 낮아졌지만 train/validation 간 차이는 여전히 크며 JSON 생성
품질 개선으로 해석하지 않는다. checkpoint-50의 global_step50/epoch0.16과
adapter·optimizer·scheduler 저장을 확인했다. 동일 실행 프로세스에서 다음
75/100-step 검증과 학습 후 생성 평가를 이어간다.
W&B API로25/50의 두 검증 값이 로컬과 정확히 일치함을 확인했으며,
`run-v3/wandb-observation-validation-50.json`에 원격 확인 기록을 보존했다.

75-step의 training loss는0.066526, 세 번째 검증 loss는4.961874였다.
50-step 검증4.965523과 거의 같은 수준이다. checkpoint-75의
global_step75/epoch0.24 및 adapter·optimizer·scheduler 저장을 확인했다.
W&B의25/50/75 검증 값도 로컬과 정확히 일치했으며,
`run-v3/wandb-observation-validation-75.json`에 보존했다. 낮은 training
loss를 JSON 생성이나 판단 품질 개선으로 해석하지 않고100-step 완료 후
같은2개 입력의 생성 결과를 확인한다.

100-step 학습은 최종 어댑터 저장까지 완료했다. 평균 training loss는
0.1199569928, elapsed_seconds는6,419.9631이고 epoch는0.32다.
이는 train pool10,000건 중3,200 presentations이며 한 epoch 완료가 아니다.
네 번째 development100 validation loss는4.9810667038로, 50/75-step보다
소폭 높고 training loss와의 큰 차이는 남아 있다. adapter fingerprint가
학습 전후 달라졌고 최종 저장 artifact의 SHA256은
`ca6f564955673f5d819db6a68497b23adb01a363cbbc5a295629674b8acdf32b`다.
완료 기록은 `run-v3/training.json`과 adapter 부모의 `training.json`이다.
새 프로세스에서 저장 adapter를 reload하고 아래 생성 비교를 완료했다.
W&B API에서 state=finished, optimizer_steps=100, training_complete=true와
100개 training loss 및25/50/75/100의 검증4개를 확인했다. 모든 값이 로컬과
일치했으며 `run-v3/wandb-observation-training-complete.json`에 보존했다.

#### 확장 실험표와 실행 결과

기존8행을 그대로 가져오고 다음2행을 추가했다. 같은2건의 결과는 진단 자료이며
100건 품질 gate 통과나 test500 결과로 일반화하지 않는다. test는 사용하지 않았다.

| 새 모델 | 시작 방식 | 생성 상한 | 표본 | 생성 final / 입력 final | JSON / schema | return 종료 | 시간 제한 | 실제 tokens |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| tutorial_adapter | bare-assistant | 65,536 | 2 | 0 / 0 | 0 / 0 | 0 | 2 | 1,272–1,278 |
| tutorial_adapter | final-prefill | 65,536 | 2 | 0 / 2 | 2 / 2 | 2 | 0 | 7–9 |

bare-assistant는 두 건 모두 analysis에서 입력에 없는 예시 함수 등을 언급하고
같은 문구를 반복했다. final header와 EOS가 나오지 않아 각각300.388/300.171초
후 시간 제한으로 멈췄다. 이는 정상 종료된 JSON을 parser가 거부한 결과가 아니라
final 답변을 생성하지 못한 결과다. 실제 생성량은65,536에 도달하지 않았다.

같은 adapter의 final-prefill은 각각
`{"assessment": "present"}<|return|>`와
`{"assessment": "not_observed"}<|return|>`를1.895/2.306초에 생성했다.
두 출력 모두 schema 유효하고 원천 라벨과 일치했다. 입력 prefix에는 정답이
없었으며 final header가 입력에 있었으므로 생성 final 성공으로 세지 않았다.
200002는 모델이 실제 생성한 마지막 토큰이며 forced EOS는 사용하지 않았다.
이미 존재하던 native EOS 설정이 이 두 경우에서 상한 전에 종료하는 것을 확인했다.

동일 adapter 내에서 시작 prefix만 바꾼 비교는 학습의 supervised boundary와
추론 시작 형식의 일치가 출력 동작에 영향을 준다는 근거다. 다만 이전 v7과는
Trainer/mask/LoRA 범위/hyperparameter도 동시에 달라졌으므로 이전 실패의
원인이 mask 하나였다고 결론 내릴 수 없다. 원천 라벨은 미검수이며 두 건의
일치가 보안 판단 정확성을 확정하지 않는다. 표본수 최소20건 gate를 만족하지
못하므로 두 report 모두 overall_pass=false다. 높은 development100 loss의
원인도 여전히 미확정이며, 더 넓은 validation 생성 검증이 후속 과제다.

```bash
experiments/training-loop-debug/.venv/bin/python \
  scripts/train_cc_tutorial_final_only_eos.py --stage prepare
experiments/training-loop-debug/.venv/bin/python \
  scripts/train_cc_tutorial_final_only_eos.py --stage run
```

run은 별도 process의 GPU preflight(optimizer0) → fresh model100step 학습 및
온라인 W&B → fresh adapter reload와2개 시작 방식 평가 순서다. 최종 table은
`run-v3/sfttrainer-final-only-mask-eos-return-comparison.md`, 구조화 표는
`run-v3/comparison.json`, 종료 기록은 `run-v3/execution-result.json`이다.
실제 parent 종료 코드0, steps100/table_rows10/test_used=false를 확인했다.
생성 원문·token IDs·개별 평가는 `run-v3/evaluation/`의 두 시작 방식 폴더에,
actual context/max_seq_length131,072와 provenance는 `run-v3/reload.json`에
보존했다. 원 v5/v7 모델·데이터·소스와 기존8행은 덮어쓰지 않았다.

#### 완료 후 검증과 감사 도구의 실패 이력

CPU-only 사후 감사는 저장 adapter digest와 reload provenance, 원 소스60개와
새 실행 소스·설정·패키지 hash, 학습100step과 네 검증 지점, 실제 생성 token IDs,
gold-free prefix 및 기존 bare 입력 일치, 원문 decode·종료 이유·JSON/schema,
기존8행 보존과 새2행, test 미사용을 대조해 통과했다. W&B state=finished와
100개 학습 loss/4개 검증 loss도 원격에서 다시 읽어 로컬과 일치함을 확인했다.
최종 receipt는 `run-v3/post-run-audit-final-only-mask-eos-return.json`,
성공 로그는 `post-run-audit-attempt-2.log`다. 이는 본 세션의 사후 검증이며
새 GPU 결과에 대한 독립 리뷰를 수행했다는 뜻은 아니다.

첫 사후 감사는 W&B history 반환 형태를 잘못 가정해 실패했다. 완료 run의
API는 요청한 metric이 없는 행도 null 열로 반환해 두 scan 모두101행이었다.
실제 training/loss 값은 step1–100의100개, validation/loss는25/50/75/100의
4개였고 step0 등 나머지 해당 열은 null이었다. 감사 도구에서 null metric 행만
제외하고 캐시 없이 재조회하되, 기대 step 집합과 모든 실제 값의 일치 검사는
유지했다. 재실행은 종료 코드0이다. 최초 script는
`post-run-audit-final-only-mask-eos-return-attempt-1.py`, 실패 로그는
`post-run-audit.log`, 관찰값은 `run-v3/wandb-post-audit-scan-observation.json`에
보존했다. 학습 재시작·metric 수정·원문 덮어쓰기는 하지 않았으며, 이 실패를
기존 팀원 코드나 학습/W&B 기록 실패로 집계하지 않는다.

### 2026-10-04: validation-loss-train-vs-eval-mode-analysis

사용자는 새 학습의25step 간격 validation 결과를 분석하고 결과 보고서만
커밋·푸시하도록 요청했다. 분석 대상은 완료된
`cc-tutorial-final-only-eos-20261004-v1-attempt-v3`의 final100 adapter다.
학습 코드·설정·W&B 원본·모델·데이터는 이번 보고서 커밋의 대상이 아니다.
원 실행과 원격 W&B 기록은 앞 절의 경로 및 run c9gsifji로 연결한다.

#### 대상과 수치 해석

학습 풀은10,000건, 실제 예산은 batch1×accumulation32×100steps의
3,200 presentations/epoch0.32다. 평균 training loss는0.1199569928이다.
중간 validation은 validation1,000건에서 미리 고정한 development100건이며
present/not_observed 각50건이다. 네 번 모두 같은100건을 사용했고 final
JSON+return의7/9토큰만 loss 대상으로 남기는 전수 마스크 검사를 통과했다.
이는 validation1,000건 전체 생성 평가나 test500 결과가 아니다.

| step | epoch | 해당 step train loss | 직전25step train loss 평균 | development100 validation loss |
| ---: | ---: | ---: | ---: | ---: |
| 25 | 0.08 | 0.085675 | 0.268000 | 5.234795 |
| 50 | 0.16 | 0.075435 | 0.078819 | 4.965523 |
| 75 | 0.24 | 0.066526 | 0.067565 | 4.961874 |
| 100 | 0.32 | 0.038503 | 0.065444 | 4.981067 |

validation loss는25→50에서5.1439% 감소했고, 50→75는0.0735% 감소로
거의 정체됐다. 75→100은0.3868% 증가했다. 25→100 전체 감소는4.8470%다.
관측 최솟값은75step이지만50step과의 차이는0.003649에 불과하다.
이 수치로 checkpoint75를 품질상 best로 선택하지 않았으며 비교 대상은
계획대로 final100이다. step0/base의 동일 validation loss는 기록하지 않아
학습 전 대비 개선·악화 여부도 이 곡선만으로 확정할 수 없다.

각 train loss는 당시 서로 다른 학습 batch의 측정이고 validation은 고정100건의
집계다. 직전25step 평균도 그 구간의 여러 가중치 상태에 대한 값이므로 같은
가중치·같은 입력의 train/eval 비교와 동일하지 않다. 아래 추가 검사에서는
입력과 final adapter를 고정했다. 낮은 training loss는 JSON 형식·EOS 예측도
포함하므로 판단 정확도 자체와 같지 않다.

#### 같은 입력·같은 가중치의 forward 비교

높은 validation loss를 과적합으로 단정하기 전에 final adapter를 새 프로세스에
불러왔다. train 최단/최장2건과 앞선 생성 비교의 validation2건을 선택하고
같은 input IDs·labels·padding·BF16 autocast로 두 경로의 model loss를 비교했다.
train 경로는 for_training과 model.train 및 gradient 활성화, trainer-eval
경로는 for_training 이후 model.eval 및 gradient 비활성화다. 두 경로 모두
use_cache=false, num_items_in_batch=None이며 별도 optimizer와 backward는 없다.
이 결과는 직접 model forward이며 전체 SFTTrainer loop의 그대로 재현은 아니다.

| 입력 | 입력 tokens | supervised tokens | train 경로 loss | trainer-eval 경로 loss |
| --- | ---: | ---: | ---: | ---: |
| train 최단 | 230 | 7 | 0.067993 | 0.045780 |
| train 최장 | 4,055 | 7 | 0.010108 | 8.670376 |
| validation 비교1 | 309 | 7 | 0.128509 | 6.291219 |
| validation 비교2 | 253 | 9 | 0.017882 | 0.140493 |

입력·labels가 같고 학습에 속한 샘플에서도 큰 차이가 재현됐다. 따라서
**일부 입력에서 실행 경로가 loss에 큰 영향을 주는 것은 확인됐으며,
원 train/validation 차이를 데이터 분할의 일반화 실패만으로 설명할 수 없다.**
다만 train/eval 및 gradient 상태를 함께 바꿨으므로 차이가 생긴 정확한 kernel,
attention mask, precision 또는 loss 계산 위치를 분리한 결과는 아니다.
어느 경로가 올바른 causal cross-entropy를 산출하는지도 아직 확정하지 않았다.
과적합·원천 분포 차이 가능성은 남아 있으며 데이터 손상이나 특정 작성자의
실수로 귀속하지 않는다. 이4건의 직접 forward 결과를100건 전체 값으로
일반화하지 않는다.

검사 전후 in-memory LoRA fingerprint와 저장 adapter SHA256은 같았고
optimizer_steps=0/backward_calls=0, 종료 코드0이었다. 재현 자료는
`outputs/cc-tutorial-validation-analysis-20261004-v1/`에 보존했다.
곡선 집계는 `validation-curve-analysis.json`, 동일 입력 결과는
`same-input-train-eval-loss.json` 및 `same-input-mode-loss.jsonl`,
실행 script는 `same-input-train-eval-loss.py`, 성공 로그는
`same-input-mode-loss-attempt-2.log`다. 원 metric JSONL의 SHA256은
`ec5f72b5ad7ee39f596d993f043b46021a854344626d132426ba2b4667d8aa02`다.

최초 진단 script는 native model의 logits가3차원 tensor라고 가정해 IndexError로
실패했다. 실제 최적화 forward는 빈 logits tensor를 반환했다. 수정 후 native
model loss를 기록하고 logits가 없으면 수동 cross-entropy·token 정확도는 null로
남겼다. 이번 결과에는 수동 CE로 loss를 검산한 근거가 없다. 최초 script와
`same-input-mode-loss.log`를 보존하며 이 실패를 원 학습 코드 오류로 집계하지 않는다.

#### 생성 결과와 결론

이미 완료된 동일 final100 adapter의 두 시작 방식 결과도 함께 읽어야 한다.
bare-assistant는 validation2건 모두 analysis 반복 후 약300초 시간 제한에
도달해 JSON0/2·EOS0/2였다. gold-free final-prefill은 같은2건에서 JSON/schema
2/2·원천 라벨 일치2/2였고 실제 생성한 return 토큰으로7/9토큰 후 종료했다.
prefill의 final header는 입력에 있었으며 정답 JSON은 입력하지 않았다.
생성 상한65,536/context131,072는 유지했고 forced EOS는 사용하지 않았다.

현재 결론은 **final 시작 형식은 생성에 영향을 주고, validation loss는 실행
경로의 영향을 먼저 확인해야 한다**는 것이다. 두 생성 성공을 전체 품질 합격으로
확대하지 않고 높은 validation loss만으로 학습 실패·과적합을 확정하지 않는다.
원천 라벨은 미검수이며 test500 생성 평가는 아직 실행하지 않았다.

후속 순서는 같은 development 입력에서 train/eval/inference forward의 causal
mask·정밀도·loss 산출을 대조해 비교 가능한 loss를 확보하고, 고정 final-prefill로
더 넓은 validation 생성 평가를 수행하는 것이다. base/adapter에 같은 입력·시작
방식·생성 예산을 적용하고 protocol을 확정한 뒤 test500을 비교한다.
그 결과를 남긴 다음 다른 데이터셋의 학습 비교를 진행한다. 이번 보고서에서
추가 학습·전체 validation 생성·test500 또는 다른 데이터셋 학습을 완료했다고
주장하지 않는다.

### 2026-10-04: raw-input-output-prefix9tokens-review

사용자는 원본 로그와 실제 입력·출력의 차이를 전반적으로 확인하도록 요청했다.
CPU-only로 v5 canonical/export11,500건의 형식, 원 v7 base development100의
저장 예측, 같은 validation2건의 과거16개+새4개 출력 원문을 대조했다.
원 로그와 token count/종료 이유, 추가 forward의 입력 hash/수치도 확인했다.
새 GPU 학습·추론은 수행하지 않았으며 test 파일의 형식 확인을 test 품질 평가로
부르지 않는다. 상세 원문은 Git 제외 경로
`outputs/cc-raw-input-output-review-20261004-v1/`의
`input-output-side-by-side.html`, 요약은 `review.md`, 기계 결과는 `review.json`,
재현 script/log는 `review.py`/`review.log`에 보존한다.

#### 실제로 전달된 입력

11,500건 모두 canonical과 decision export가 일치했다. user 필드는
scope(target_cwe/boundary)와 source_code이며 명시적 정답 필드는 없다.
train/validation은 system/user/assistant, test challenge는 system/user다.
분할 간 ID·동일 코드 겹침은0이었으며 CVE/그룹/near-clone 검사를 새로 한 것은 아니다.
이는 구조·입력 일치 확인이며 미검수 원천 라벨의 의미를 검증한 결과는 아니다.

| 비교 입력 | 원천 정답 | bare prompt | final-prefill prompt | teacher-forcing 전체 | 감독 tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| file_asynch_write / CWE-252 | present | 293 | 302 | 309 | 7 |
| zone_set_layer / CWE-190 | not_observed | 235 | 244 | 253 | 9 |

두 source_code를 JSON으로 파싱하면 실제 개행12/6개이며 literal backslash-n은
0이었다. JSON 직렬화에서 보이는 이스케이프를 코드의 이중 인코딩으로 판정하지
않는다. 두 사례의 함수·CWE는 canonical·user payload·실제 input IDs가 일치했다.
모델이 코드가 없다고 출력했지만 실제 입력에는 해당 C 코드가 있었다.

prefill은 bare 입력에 다음9토큰만 붙인다. 정답 JSON은 붙이지 않는다.

```text
<|channel|>analysis<|message|><|end|><|start|>assistant<|channel|>final<|message|>
```

loss용 전체 시퀀스는 prefill+정답 JSON+return이다. 재생성한309/253개의 input IDs
SHA256이 기존 forward 로그의 입력 hash와 일치했다. validation loss의 teacher-
forcing 입력과 실제 자유 생성 입력을 동일한 것으로 해석하지 않는다.

#### 원문 출력의 실패 유형

25step validation은 prediction_loss_only=true의 loss 계산이었다.
그100건의 자유 생성 답변은 저장하지 않았으며, 새 final100 adapter의 저장된
자유 생성 원문은2입력×2시작 방식의4개다. 이번 검사는 이4개를 모두 읽었지만
validation100건 전체 출력 실패 유형을 확인한 결과는 아니다.

새 bare 출력은 실제 C 코드와 다른 Python 함수/int main을 언급하고, 코드가
제공되지 않았다고 주장하거나 취약성 대신 함수의 존재 여부를 반복했다.
함수가 없다는 동일 문장은 두 사례에서10/23회 반복됐다. 이는 JSON parsing
실패 이전에 관측되는 grounding/작업 의미의 실패다. 생성 원문은1,272/1,278
토큰 존재하며 raw_output만 final 미생성 때문에 비어 있다.

새 final-prefill은 같은2건에서 JSON/schema·원천 라벨 일치2/2, 실제 return으로
7/9토큰에 종료했다. final header는 입력에서 제공했고 모델이 생성한 것으로
집계하지 않는다. 같은 adapter 내의 시작 형식 차이가 출력 동작에 영향을
주는 것은 확인됐으나 두 건만으로 코드 판단 정확성을 일반화하지 않는다.

과거 adapter는65,536 상한에서 analysis275/287회·final82/69회의 제어 구조
반복 후 시간 제한에 도달했다. 새 bare는 analysis marker1회 안에서 본문이
반복되는 형태다. 두 run의 반복 유형도 구분해야 한다. 과거 base 두 번째
사례는 EOS가 나왔어도 final에 설명·후속 message가 섞여 JSON이 유효하지
않았다. 요청과 다른 CWE 및 가짜 tool 호출 텍스트도 있었으며, 실제 inference
도구가 실행된 결과가 아니다. 종료 토큰과 JSON/판단 성공을 별도로 본다.

원 base100건의128token 도달/final0/EOS0, 새 실행 로그의 생성4개 이벤트,
네 validation metric 지점 및 forward 성공 로그/JSON 일치를 재확인했다.
forward 로그는 loss와 빈 logits shape만 남겨 출력 token이나 수동 CE를
검산할 수 없다. 이번 검사는 CUDA initialized=false/model load=false/
optimizer0, 종료 코드0이며 원 파일 hash는 전후 같았다.

### 2026-10-04: generation-failure-vs-runtime-qwen-gptoss-analysis

사용자는 반복·시간 초과를 모델의 생성 품질 한계로 해석할 수 있는지,
confusion matrix로 평가하면 되는지, 더 긴 context 모델이 필요한지,
Qwen3-Coder-Next-80B와 GPT-OSS-20B의 차이가 무엇인지 질문했다.
이번 분석은 앞 두 절의 보존 결과와 아래 공식 모델 자료를 대조한 것이다.
새 GPU 실행·모델 다운로드·재학습·평가 metric 구현은 하지 않았다.

#### 관측과 원인 판정

반복·입력과 무관한 함수 생성·final 미생성은 실제 생성 품질 실패다.
그러나 품질 실패는 학습 objective/추론 시작 경계/런타임 오류가 드러나는
증상이기도 하므로 학습 문제와 생성 품질 문제를 상호 배타적으로 분류하지 않는다.
현상 기록과 원인 판정을 구분한다.

- 실패한 새 bare 입력은235/293토큰이고 생성량은1,278/1,272토큰이다.
  context131,072 또는 생성 상한65,536에 도달한 것이 아니라 약300초의
  wall-clock 제한에 도달했다. 더 긴 context가 이 사례를 해결한다는 근거는 없다.
- 같은 adapter·코드에서 gold-free final 시작 접두부9토큰을 추가하면
  JSON/schema·원천 라벨 일치2/2 및 native return7/9토큰 종료가 관측됐다.
  시작 경계에 대한 민감성은 확인됐지만 판단 정확도의 일반화는 미검증이다.
- 새 학습은 final JSON+return만 감독하고 analysis 본문·final header는
  감독하지 않았다. bare 자유 생성은 analysis 및 채널 전환을 모델이 생성해야
  하므로 학습에서 측정한 응답 조건과 다르다. 이 경계 차이는 원인 후보이며,
  공식 final-only 마스킹 자체를 결함으로 판정한 것은 아니다.
- 동일 가중치·동일 입력의 train/eval forward에서도 일부 loss가 크게 달랐다.
  train 최장 사례는0.010108 대8.670376이다. mode와 gradient 상태를 함께
  바꾼 검사이고 수동 CE 검산이 없어 어느 경로가 맞는지는 아직 모른다.
  따라서 학습/추론 실행 경로가 정상이라는 전제를 아직 확보하지 못했다.

#### 공식 모델 차이와 과거 비교의 제한

| 항목 | GPT-OSS-20B | Qwen3-Coder-Next |
| --- | --- | --- |
| 주된 설계 | 범용 reasoning/agentic 모델 | coding agent·로컬 개발 특화 |
| 총/토큰당 활성 파라미터 | 약21B/3.6B | 약80B/3B |
| 기본 출력 경계 | Harmony analysis/final 및 turn 종료 | non-thinking, ChatML assistant 본문 |
| 모델 context 상한 | 131,072 | 262,144 |
| 레이어/attention | 24, sliding/full 교대 | 48, Gated DeltaNet/Gated Attention 혼합 |

출력 형식과 post-training의 차이는 두 실행의 현상 차이를 설명할 후보다.
공식 Qwen 카드는 non-thinking만 지원한다고 명시하며 공식 template은
`<|im_start|>assistant` 뒤 본문을 생성한다. GPT-OSS는 reasoning low도
지원하지만 그것을 analysis 미생성 보장으로 해석하지 않는다.
총 파라미터 비율이나 context 비율만으로 코드 판단 성능 차이를 설명하지 않는다.

이전 Q1R10/Q1R11은 BF16 LoRA/LLaMA-Factory/qwen3_nothink/B2002장이고
현재 GPT-OSS는 pinned Unsloth BnB4bit QLoRA/RTX A6000 1장이다.
데이터도 이전 decision/evidence 폴더와 현재 v5 판단 후보가 다르다.
이전 blind500 중복 감사 결과 때문에 과거의 높은 판단 점수를 독립적인
일반화 기준으로 사용하지 않는다. 다만 누수 문제만으로 현재 bare의 반복과
final 미생성을 설명할 수 있는 것도 아니다. 과거 보고서는
`outputs/source-v2-unsloth-full-comparison-20260927-v1/framework-comparison-20260928/q1r10-q1r11.md`
및 `outputs/q1r10-q1r11-dataset-audit-20260928/summary.md`로 연결한다.

공식 출처(2026-10-04 열람, 현재 main의 설명이며 설치 버전 변경 없음):

- [OpenAI GPT-OSS 소개·구조](https://openai.com/index/introducing-gpt-oss/)
- [공식 GPT-OSS-20B model card](https://huggingface.co/openai/gpt-oss-20b)
- [공식 GPT-OSS config](https://huggingface.co/openai/gpt-oss-20b/blob/main/config.json)
- [공식 Harmony renderer](https://github.com/openai/harmony)
- [공식 Qwen3-Coder-Next model card](https://huggingface.co/Qwen/Qwen3-Coder-Next)
- [공식 Qwen chat template](https://huggingface.co/Qwen/Qwen3-Coder-Next/raw/main/chat_template.jinja)

#### 평가 방법과 다음 원인 분리

기존 평가 계약은 변경하지 않았다. 후속 보고에는 유효한 판단의 TP/TN/FP/FN과
함께 전체 평가 건수, 판단 성공률, JSON/schema 실패율, timeout 비율,
실제 생성 토큰 수·지연 시간을 보존하는 것이 적절하다. 출력 실패를
not_observed로 강제 변환하거나 실패 건을 분모에서 빠뜨리지 않는다.
실제 라벨2종×예측 present/not_observed/출력 실패의2×3 표는 실패 건수를
보여줄 수 있지만, 이것을 표준 이진 confusion matrix와 동일하게 부르지 않는다.
유효 출력만 계산한 지표에는 coverage와 조건부 계산임을 명시하고,
전체 표본에서 실패를 오답으로 세는 성공률도 함께 보고한다.
현재 두 사례의 결과는 원천 라벨 일치이며 검수된 취약성 정확도가 아니다.

다음 실험의 우선순위는 다음과 같다. 이번에 실행한 결과가 아닌 제안이다.

1. 고정 입력·가중치에서 causal mask/precision/forward/loss 경로의 일관성을
   확인한다. train/eval 차이를 일반화 성능으로 오인하지 않도록 한다.
2. 같은 고정 development 집합으로 base/adapter×bare/final-prefill을 비교한다.
   입력 코드·CWE·출력 계약은 같게 두고 모델별 native 형식을 유지한다.
   생성 cap·시간 cap 및 실패 처리도 동결한다. prefill은 gold를 포함하지 않는다.
3. 정상 출력에서도 판단 오류가 높고 실행 경로 문제가 배제되면 동일 v5의
   protocol을 확정한 test500에서 Qwen과 비교한다. 이때 모델 교체의 이유는
   관측된 코드 판단/종료/형식 성능이며 context 길이 개선으로 단정하지 않는다.

### 2026-10-04: context-window-max-131072-generation-experiment

사용자는 문맥 최대 길이를 확인한 뒤 최대 토큰 길이 실험을 요청했고,
실수로 중단한 turn을 이어서 진행하도록 지시했다. 실험명은
`context-window-max-131072 (max-new-tokens=context-minus-input)`이다.
131,072는 입력과 출력을 합친 문맥 한도이므로 실제 생성 상한은 각 입력을
직렬화한 토큰 수를 뺀 값이다. 기존65,536보다 생성 상한만 늘리며,
runtime context131,072·greedy·batch1·low reasoning·native EOS 및
300초 guard는 그대로 유지한다. 생성 상한 설정과 실제 생성량을 구분한다.

#### 실행 전 계획과 검사

대상은 같은 validation2건에서 pinned base와 최신 final100 tutorial adapter의
bare-assistant/final-prefill 시작이다.2모델×2시작 방식×2입력의8개 생성이며
새 학습·test500·데이터셋 변경·모델 다운로드·패키지 업그레이드는 없다.
이전 comparison10행을 보존하고 새4행을 별도 산출물에서 추가한다.
base/final-prefill은65,536의 이전 저장 비교가 없으므로 신규 대조 조건이다.

| 입력 | 시작 | 입력 tokens | 실제 max_new_tokens |
| --- | --- | ---: | ---: |
| cc-55fa921bc64a64071c4dd1c9 | bare-assistant | 293 | 130,779 |
| cc-b8bec7f8c250c406ad4ed545 | bare-assistant | 235 | 130,837 |
| cc-55fa921bc64a64071c4dd1c9 | final-prefill | 302 | 130,770 |
| cc-b8bec7f8c250c406ad4ed545 | final-prefill | 244 | 130,828 |

원 입력 ID·token IDs 및 최신 학습 config/source/package/GPU/adapter digest를
동결본과 대조했다. 새 예산 계산, 경계 초과·gold 입력 거부 및 실제
model.generate의 인자 전달을 검증한 CPU 검사14건이 통과했고 Ruff check도
통과했다. 사전 GPU는 RTX A6000,49,140MiB 중209MiB 사용,compute process0였다.
설정·script·검사는 Git 제외 경로
`outputs/cc-context-window-max-131072-20261004-v1/`의
`config.json`, `run.py`, `test_context_max.py`에 보존하며 결과는 `run-v1/`이다.
기존 학습 구현과 원 산출물을 수정하지 않는다.

실행 명령:

```bash
experiments/training-loop-debug/.venv/bin/python -u \
  outputs/cc-context-window-max-131072-20261004-v1/run.py --stage prepare
experiments/training-loop-debug/.venv/bin/python -u \
  outputs/cc-context-window-max-131072-20261004-v1/run.py --stage run
```

질문은 생성 상한만 높여 동일 입력의 종료·JSON/schema가 바뀌는지다.
300초에 먼저 도달하면 실제 최대 길이까지 생성할 수 있는지 또는65,536 이후
회복하는지는 미검증으로 남긴다. 같은 실패가 반복돼도 자동으로 시간 제한을
늘리거나 학습을 재시작하지 않는다. 미검수 원천 라벨2건으로 판단 품질을
합격 처리하지 않는다. 실행 결과는 아래에 추가한다.

#### 관측에 따른 추가 base 대조 계획

새 base/bare는68/118토큰에서 native return으로 종료해 이전 저장 결과의
1,579/2,534토큰과 달랐다. 둘 다 기존65,536 상한 미만에서 달라졌으므로
이 차이를 상한 증가로 인한 품질 개선으로 판정하지 않는다.
같은 base를 새 프로세스에 한 번 로드하고 각 동일 입력에서65,536과
context-minus-input을 순차 호출해 model.generate의 max_new_tokens 인자만
변경하는4개 생성 대조를 추가한다.300초 제한과 입력·EOS·그 외 kwargs는 같다.
대조 script는 같은 Git 제외 폴더의 `paired_caps.py`이며, 원 실험 script와
결과를 덮어쓰지 않고 `run-v1/base-paired-caps/`에 저장한다.
인자 하나만 변경하는 CPU 검사를 추가한 총15건과 Ruff check가 통과했다.
이 대조는 base 결과 차이를 설명하기 위한 것이며 어댑터 재학습은 아니다.

#### 완료 결과와 해석

원 최대 상한 실험8개 생성과 추가 base 대조4개 생성이 모두 종료 코드0으로
완료됐다. 모든 요청의 입력+설정된 생성 예산은 정확히131,072다.
실제 생성량은 아래와 같으며 어떤 요청도 토큰 상한에 도달하지 않았다.

| 모델 | 시작 | 실제 생성 cap | JSON/schema | native return | 시간 제한 | 실제 생성 tokens |
| --- | --- | --- | --- | --- | --- | --- |
| base | bare-assistant | 130,779/130,837 | 2/2 | 2/2 | 0/2 | 68/118 |
| base | final-prefill | 130,770/130,828 | 1/2 | 2/2 | 0/2 | 43/7 |
| tutorial final100 adapter | bare-assistant | 130,779/130,837 | 0/2 | 0/2 | 2/2 | 1,277/1,284 |
| tutorial final100 adapter | final-prefill | 130,770/130,828 | 2/2 | 2/2 | 0/2 | 7/9 |

adapter/bare 두 사례의 latency는300,344.596/300,255.856ms였다.
adapter/final-prefill은1,886.022/2,336.491ms로 완료됐다.
bare 생성 ID의 공통 길이까지가 이전65,536 출력과 두 사례 모두 완전히 같았다.
이전1,272/1,278토큰과 새1,277/1,284토큰의 차이는 시간 제한까지 처리한
분량 차이이며, 관측된 공통 구간의 생성 의미·반복 유형은 바뀌지 않았다.
final-prefill의 전체 생성 IDs도 이전65,536 출력과 같다. 정답 JSON을 입력에
넣지 않았고 native return을 실제 생성했다. 원천 라벨 일치2/2는 검수된
보안 정확도 또는 전체 validation/test 품질 합격이 아니다.

base/bare의 최종 판단은 첫 사례uncertain, 둘째not_observed다.
base/final-prefill은 첫 사례에서 final 접두부 뒤 설명문과 새 final header를
생성해 JSON 파싱 실패했고, 둘째는uncertain이다. 따라서 EOS2/2를 판단
성공2/2로 읽으면 안 된다. 첫 final에서 실패한 원문을 뒤의 JSON으로
교체하거나 실패 사례를 평가에서 제외하지 않았다.

추가 base의 동일 프로세스 대조:

| 입력 | cap65,536의 실제 tokens | 최대 cap의 실제 tokens | 최종 JSON 비교 |
| --- | ---: | ---: | --- |
| cc-55fa921bc64a64071c4dd1c9 | 38 | 68 | 둘 다 assessment=uncertain |
| cc-b8bec7f8c250c406ad4ed545 | 114 | 118 | 둘 다 assessment=not_observed |

상한 인자 하나만 바꾼 대조에서 생성 본문의 token IDs는 달랐지만 최종
raw_output은 두 사례 모두 같았다. 이 실험은 각 조건1회라 실행 순서나
수치적 비결정성 등과 cap의 경로 영향을 완전히 분리하지 못한다.
이전 원 base65,536의1,579/2,534토큰은 이번65,536 대조에서 재현되지 않았다.
이번 base worker는 tutorial 경로와 맞춰 forced_eos=None 및 min_new_tokens/
min_length=0을 명시하며 이전 base worker는 이 설정을 별도 명시하지 않았다.
이 점과 실행 경로의 재현 문제를 기록하고 과거 대비 차이를 cap 증가로
인한 품질 개선으로 귀속하지 않는다. 추가 대조 두 조건끼리는 이들을 같게
두고 실제 model.generate의 max_new_tokens만 변경했다.

**이 두 입력과300초 조건에서는 생성 상한을 최대화해도 adapter의 bare
반복/종료 실패가 개선되지 않았다.** context 설정 자체는 이전에도131,072였다.
이번에 늘린 것은 남은 문맥만큼의 max_new_tokens이며 입력 길이나 학습 길이는
늘리지 않았다.65,536 이후까지 실제 생성하지 않았으므로 그 구간의 동작이나
최대 문맥 생성 완주 가능성은 미검증이다. 이 결과만으로 모델 고유 한계 또는
특정 학습 코드 결함을 확정하지 않는다.

#### 재검산과 보존

CPU 감사 `audit.py`가12개 원본 출력의 token decode·input 일치·실제 cap,
최대 상한4조건의 평가 재계산, native EOS/시간 종료 및 원본 해시를 대조했고 종료 코드0,
audit_pass=true/CUDA initialized=false였다. 원 comparison10행은 그대로
유지되고 새4행을 별도 comparison에 추가했다. source bindings와 adapter
SHA256 `ca6f564955673f5d819db6a68497b23adb01a363cbbc5a295629674b8acdf32b`는
전후 같았다. optimizer_steps=0/test_used=false다.

결과 위치는 `outputs/cc-context-window-max-131072-20261004-v1/run-v1/`이다.

- `context-window-max-131072-comparison.md`, `comparison.json`: 새4조건 표와
  기존10행+새4행의 전체 표.
- `base/predictions.jsonl`, `tutorial_adapter/predictions.jsonl`: 최대 상한의
  전체8개 raw generation·입력/출력 IDs·종료·latency/메모리 기록.
- `base.log`, `tutorial_adapter.log`: 실제 상한이 표시된 호출 및 종료 로그.
- `base-paired-caps/`: 추가4개 대조의 원 출력·설정·평가·최종 JSON 비교.
- `base-paired-caps.log`: 추가 대조 실행 원 로그.
- `post-run-audit.json`, `post-run-audit.log`: 재검산 결과와 원문 발췌.

재검산 명령:

```bash
experiments/training-loop-debug/.venv/bin/python -u \
  outputs/cc-context-window-max-131072-20261004-v1/paired_caps.py
experiments/training-loop-debug/.venv/bin/python -u \
  outputs/cc-context-window-max-131072-20261004-v1/audit.py
```

paired_caps.py는 GPU 대조 실행 명령이며 기존 출력 폴더가 있으면 덮어쓰지
않고 중단한다. audit.py만 기존 결과를 읽어 재검산하는 CPU 경로다.

### 2026-10-04: unsloth-original-max-new-tokens-131072-training

**조건 정정(2026-10-04):** 사용자가 승인한 변경은 생성 상한 확대였지만,
에이전트가 사전 동의 없이 외부 600초 제한을 추가했다. v2에는 compiler-off
우회도 적용됐다. 아래 기록은 해당 조건에서 관측한 이력으로 보존하며,
사용자가 요청한 “공식 튜토리얼에서 생성 상한만 변경한 재현”의 결과로
간주하지 않는다. `max_time` 인자를 넣지 않았어도 외부 제한은 별도 조건 변경이다.
이후 사용자는 학습과 생성 길이 모두 공식 튜토리얼 그대로인 새 실행을 요청했다.

사용자는 이전 맞춤 종료 설정·prefill이 영향을 줬을 가능성을 비교하기 위해
공식 튜토리얼을 거의 그대로 사용해 새로 학습하고 실험표 및 결과를 기록하도록
요청했다. 이어서 **학습 길이는 원본 유지, 생성 상한만 최대화**를 선택했다.
따라서 이 실험의 학습 max_seq_length는1,024이며131,072로 바꾸지 않는다.
제목은 `unsloth-original-max-new-tokens-131072 (training-length-1024)`다.

#### 사전 고정과 원본 대조

기준 원본은 위에 보존한 Unsloth notebook commit
`92e38e86308748d18fc4cd4b104c4c6d3db1d67e`의 Python 실행 셀이다.
모델 alias/LoRA/formatter/SFTTrainer/SFTConfig/final-response mask 및
trainer.train 호출은 원본 AST에서 추출했다. 변경은 원본 데이터의 로컬 고정본
로드와 checkpoint/adapter 저장 경로뿐이며, 이를 역변환하면 학습 AST가
정확히 같은지 검사했다. 기존 train/eval mask-signature 보정 helper나
final-prefill·EOS 목록·forced_eos·min_new_tokens·sampling 값을 주입하지 않는다.
native generate의 kwargs는 원본처럼 inputs, max_new_tokens, streamer뿐이다.
관측용 callback/streamer는 로그·원 token IDs를 기록하며 학습 타깃을 바꾸지 않는다.
공식 문서가 선택 사항으로 안내하는 학습 전 low/medium/high64-token 시연은
별도로 실행하지 않고, 아래 동일 French 질문의 base 평가를 먼저 수행한다.

| 항목 | 이번 값 |
| --- | --- |
| 원본 dataset | HuggingFaceH4/Multilingual-Thinking, train1,000 |
| 고정 dataset revision | f423949d2726f5a5633ea10ac45bc1ea1e0de6e7 |
| 학습 길이/steps | 1,024 / 30 |
| batch/accumulation | 1 / 4 |
| LoRA | 원본 r8/alpha16/dropout0, attention+MLP 목록 |
| LR/warmup/optimizer | 원본2e-4/5/adamw_8bit |
| schedule/weight decay/seed | 원본linear/.001/3407 |
| formatter/mask | 원본 standardize_sharegpt/chat template/final response mask |
| validation/W&B | 원본대로 eval dataset 없음/report_to=none |
| 생성 조건 | 원본 French 수학 질문, medium/high, native EOS·sampling |
| 생성 비교 | 원본64 vs131,072에서 실제 input tokens를 뺀 상한 |

새 venv는 `experiments/unsloth-original-max-new-tokens-131072/.venv`이며
원본 설치 셀과 같은 Transformers4.56.2/TRL0.22.2 및 호환
huggingface-hub0.36.0을 설치했다. Torch·Unsloth 등 기존 패키지는 원 기존
site-packages를 .pth로 읽으며 기존 venv를 수정하지 않는다. 이는 Colab OS까지
같은 환경의 완전 재현은 아니다. 실제 package 버전은 새 manifest에 기록했다.
새 컴파일 캐시는 실험 출력 폴더 아래로 분리한다. 원본 alias+load_in_4bit가
설치 mapper에서 캐시된 bnb-4bit로 연결되는 것을 확인했다. 새 대형 모델을
다운로드하거나 이전 adapter에서 계속 학습하지 않는다.

실험 파일은 Git 제외 경로
`outputs/unsloth-original-max-new-tokens-131072-20261004-v1/`에 있으며,
실행 전 계획표는 `unsloth-original-max-new-tokens-131072-results.md`다.
`original-training-cells.py`/`training-cells.py`/`manifest.json`에 원본 및 차이를
보존했다. CPU 원본 대조·학습 길이·생성 인자 검사3건 및 Ruff check가 통과했다.
초기 정적 검사에서 관측 wrapper의 미사용 로컬 변수 하나가 발견돼 제거한 뒤
통과했으며 학습 호출·원본 recipe는 바꾸지 않았다.

#### 실행 및 해석 계약

별도 native base 평가→원본30-step 학습→저장 adapter의 새 프로세스 재로딩
평가→표 갱신 순서다. 두 모델에 medium/high×64/최대의4조건씩 총8개 생성이다.
추론 로딩 길이131,072는 생성 최대 문맥용이며 학습 길이 변경과 구분한다.
decoder max_time 인자도 추가하지 않는다. 대신 각 generate의600초 외부
wall-clock guard로 자원을 제한하고, 발생 시 streamer에 저장된 부분 출력과
external_time_limit을 보존한다. 이를 native EOS 성공으로 집계하지 않는다.

```bash
experiments/unsloth-original-max-new-tokens-131072/.venv/bin/python -u \
  outputs/unsloth-original-max-new-tokens-131072-20261004-v1/pipeline.py
```

이 실험은 원본 multilingual/French 수학 시연의 학습·생성 동작 확인이다.
C/C++ v5 판단 데이터로 학습한 기존 adapter의 confusion matrix와 같은
점수로 비교하지 않는다. 같은 튜토리얼 안의 base/adapter 및64/최대 상한을
비교한다. 종료/final 출현·원문 의미·반복을 구분하며 EOS만으로 정답을
판정하지 않는다. 원본 SFT의1,024-token truncation과 supervised label 수를
기록하고 임의로 dataset을 필터링하거나 학습 길이를 늘려 성공시키지 않는다.
실행 실패와 실제 미검증 범위도 아래 결과 및 표에 기록한다.

#### 실행 중 발견한 로컬 런타임 차이

| 실행 | 도달 지점 | 결과/조치 |
| --- | --- | --- |
| attempt1 | base 가중치 로드 전 | 기본 HF 캐시에 tokenizer만 있고 별도 workspace 캐시에 가중치가 있어 `checkpoint_files[0]`가 None인 로더 오류. optimizer 실행 없음 |
| attempt2 | base 가중치 로드 성공, 첫 generate | GPT-OSS router의 TorchDynamo 컴파일 경로에서 `dict_keys_getitem`의 StopIteration. 출력·optimizer 실행 없음 |
| attempt3 | base4조건 완료, 첫 train backward | TorchDynamo 전체 비활성화 후 uncompiled FlexAttention backward에서 Float/BFloat16 오류. optimizer step0, adapter 없음 |
| 별도v2 | 동일 원본30-step 학습 | Unsloth 지원 compiler-off 경로로 학습 완료. 같은 경로의 base/adapter 비교를 별도 표에 기록 |

원본 alias를 바꾸거나 모델을 추가 다운로드하지 않았다. 기존 두 캐시의
동일 revision `093fba6992ef5a7152481afec0bdfca1ac486998` 파일을 출력 폴더의
`native-hub`에 symlink로 모으고 `HF_HUB_CACHE`만 지정했다.
`native-cache-links.json`에 원본 경로·크기를 남겼으며 가중치를 복제하지 않았다.
attempt3에서는 설치 Torch2.10의 `torch/_dynamo/eval_frame.py`에서 지원하는
`TORCHDYNAMO_DISABLE=1`을 import 전에 적용했다. 모델/LoRA/마스크/optimizer/
EOS/sampler 학습·생성 호출의 AST는 그대로다. 이는 컴파일 실행 경로와 속도가
다른 로컬 런타임 보정이므로 원본 Colab 전체 환경과 동일하다고 주장하지 않는다.

실패 로그 `base.log`/`base-attempt2.log`, 각 pipeline-result, 이전 execution
bindings, `run-attempt2.py` 및 생성된 compiler cache를 보존했다. 실패한
inference 폴더도 별도 이름으로 옮겨 덮어쓰지 않았다. 원본 대조3건은
attempt3 변경 이후에도 통과했다. 실제 재시도 명령은 다음과 같다.

```bash
experiments/unsloth-original-max-new-tokens-131072/.venv/bin/python -u \
  outputs/unsloth-original-max-new-tokens-131072-20261004-v1/pipeline_attempt3.py
```

이는 실행 이력이며 같은 폴더에서 반복 실행하는 resume 명령이 아니다.
기존 검증 기준대로 실패·완료 stage는 새 출력 경로 없이 덮어쓰지 않는다.

attempt3의 base4조건은 원본64의 medium/high가 각각64토큰에서 잘렸고,
최대 상한130,950의 medium은2,258토큰/native EOS/final(455.713초), high는
2,966토큰/외부600초 제한/final 없음이었다. medium의 French 답변은 양의
근만 제시해 실근3개 중 음의 근2개를 누락했다. 이 출력은 아래v2 표와
실행 경로가 다르므로 학습 후 adapter와 직접 묶어 비교하지 않는다.

#### 별도v2: 원본 학습 성공과 같은 런타임 비교

설치 `unsloth_zoo/temporary_patches/gpt_oss.py`의
`patch_GptOssAttention`에는 uncompiled FlexAttention backward의 dtype
문제와 `UNSLOTH_COMPILE_DISABLE`일 때 stock attention으로 남기는 분기가
있다. TorchDynamo만 끄는 대신 Unsloth 지원
`UNSLOTH_COMPILE_DISABLE=1`을 import 전에 지정한 별도v2를 만들었다.
원본 learning 호출의 AST 대조3건은 다시 통과했다. EOS/sampling/prefill과
학습 길이·30step·batch1/accum4는 바꾸지 않았다. 이 compiler-off 경로는
원본 Colab 전체 runtime 재현과 구분한다.

새 경로는 `outputs/unsloth-original-max-new-tokens-131072-20261004-v2/`다.
기존v1의 모든 실패 및 base 출력을 유지하며 원본 dataset 고정본과 모델
캐시만 공유한다. 앞선 base 평가로 학습 전 기준을 마련한 뒤 v2 학습을
먼저 실행하고, 새 프로세스로 v2의 동일 compiler-off base/adapter를
비교한다. dataset과 질문·채점 기준을 결과에 맞춰 바꾸지 않는다.

```bash
experiments/unsloth-original-max-new-tokens-131072/.venv/bin/python -u \
  outputs/unsloth-original-max-new-tokens-131072-20261004-v2/pipeline.py
```

| 학습 결과 | 실제 값 |
| --- | --- |
| 원본 입력/최종 trainer records | 1,000 / 933 |
| native 전처리 제외 | 1,024-token truncation 후 응답 라벨 없는67건 자동 제외 |
| 자체 추가 필터/수동 마스크 보정 | 없음 |
| optimizer steps/epoch | 30 / 0.128617 |
| 평균/마지막 step loss | 1.024378 / 0.6893 |
| trainer runtime/로드·저장 포함 | 147.717 / 175.664초 |
| peak reserved memory | 19,758MiB |
| 실제 trainable parameters | 3,981,312 |
| validation/W&B | 원본대로 없음/report_to=none |
| adapter SHA256 | 071dc22d1351abff59362ec7508d9b2777ccd1d13bdf331848590795ca0627a1 |

`train_on_responses_only` 내부가 67건을 자동 제외했다. 원본 호출 그대로
발생한 동작이며 이를 사용자가 만든 데이터 필터로 숨기지 않는다. 30step은
유효933건 전체1epoch 학습이 아니다. 이 runtime의 실제 LoRA tensor 목록과
trainable 수는 `model-runtime.json`에 보존했다. 원본 target 목록이 같다는
이유만으로 이전92,626,944-parameter adapter와 학습 범위까지 동일하다고
주장하지 않는다. 로컬 BnB legacy MoE에서 실제 연결된 모듈 범위도 해석에
포함한다. adapter 저장 후 새 프로세스에서 원본 loader로 다시 불러온다.

#### v2 최종 생성 결과

8조건과 표 갱신 stage는 모두 exit0으로 실행을 마쳤다. 이는 실험 실행 완료이며
생성 품질 합격이 아니다. 모델의131,072 문맥에서 실제 입력122토큰을 제외해
최대 `max_new_tokens=130950`을 적용했다. 원본64 대조도 함께 남겼다.
추론 kwargs는 inputs/max_new_tokens/관측 streamer뿐이며 native EOS와
sampling을 직접 덮어쓰지 않았다. 두 모델의 실제 generation_config가 같고,
EOS는 `[200002,199999]`, forced_eos는None, do_sample=True,
temperature=1/top_k=50/top_p=1, decoder max_time=None임을 재검증했다.

| 모델 | reasoning | 생성 상한 | 실제 생성 | 종료 | final 채널 | 초 |
| --- | --- | ---: | ---: | --- | --- | ---: |
| base | medium | 64 | 64 | token_limit | 없음 | 7.162 |
| base | medium | 130950 | 3025 | external_time_limit | 없음 | 600.000 |
| base | high | 64 | 64 | token_limit | 없음 | 6.691 |
| base | high | 130950 | 3057 | external_time_limit | 없음 | 600.011 |
| adapter | medium | 64 | 64 | token_limit | 없음 | 6.987 |
| adapter | medium | 130950 | 3008 | external_time_limit | 부분 답변 있음 | 600.000 |
| adapter | high | 64 | 64 | token_limit | 없음 | 7.075 |
| adapter | high | 130950 | 2968 | external_time_limit | 없음 | 600.000 |

원본64는4/4가 추론 도중 길이 제한에 도달했다. 최대 상한은4/4가 외부
600초 제한에 도달했으며 native EOS는0/4다. adapter/medium의 final marker는
있지만 답변 말미가 잘렸고 return/EOS는 없다. final 진입을 완성 답변으로
집계하지 않는다. 최대 상한의 실제 생성 속도는 약5tokens/sec였다.
따라서 이 결과는 **600초 제한 안에서 생성 상한만 확대해도 완성 답변이
확인되지 않았다**는 관찰이다. 130,950토큰을 실제로 소진하거나 그 길이의
KV cache를 유지한 검증은 아니다. 제한 없이 계속 생성했을 때 자연 종료하는지,
모델이 해당 최대 길이를 처리하지 못하는지는 이번 결과로 판단할 수 없다.

#### 원문 품질과 인과 해석

보존8개 출력의 channel/message marker 수는 각각1 또는2다. adapter/medium만
analysis→final의 정상 header 전환이 한 번 있고, 이전 C/C++ adapter의 반복
제어 토큰 루프는 이번 출력에서 관찰되지 않았다. 출력 내용은 영어 수학 추론과
수치 계산 위주였다. 이 관찰은 native EOS 성공이나 정확한 답을 의미하지 않는다.

동일 질문은 `x^5+3x^4-13=0`이며 독립적인 단조 구간·이분법 계산의 실근은
약 `-2.783413`, `-1.823035`, `1.317295`다. adapter/medium의 부분 final에는
`f(1.4)≈0.54`가 있지만 직접 대입한 값은3.90304다. 제시한 음의 근
`-1.814`도 기준값과 다르다. 답변이 잘린 상태이므로 끝까지 생성했다면
음의 근을 추가했을지는 판정하지 않는다. EOS와 수학 정확도를 분리했다.
이는 수학 시연 검토이며 C/C++ 판단의 confusion matrix나 benchmark 점수가
아니다. 원본 train1,000건에서 demo 질문의 정확한 문자열 일치는0건이었지만
의미 중복이나 benchmark 오염 전반을 검증한 결과로 확대하지 않는다.

이번 원본 호출로30-step 학습과 저장·재로딩이 가능함은 확인했다. 로컬
compatibility 실패와 생성 미완료를 구분했고, 원본 학습 AST를 유지한
compiler-off 복구가 유효했다. 다만 실제 연결된 LoRA는 attention의
192tensors/3,981,312parameters이며 **expert LoRA tensor는0개**다.
원본 target 목록과 설치된 legacy BnB MoE의 실물 연결 범위를 구분한다.
이전92,626,944parameter adapter와 같은 학습 범위의 비교가 아니다.

이 실험은 EOS 설정 하나의 ablation이 아니다. 기존 C/C++ 실험과 dataset,
학습 길이·step 수, Transformers/TRL 및 실제 LoRA 범위가 다르고, native
sampling을 그대로 사용해 반복 seed 고정이나 동일 RNG replay도 추가하지
않았다. 이전에 명시한 EOS200002/199999는 이번 native 목록에도 존재한다.
따라서 이전 종료 설정이 문제의 원인이었다거나, 원본 코드로 바꾸면 품질이
회복된다고 확정할 수 없다. 이번 최대 상한의 완료 답변은0/4이며 시간 제한과
실제 생성량을 함께 남기는 것이 결과의 해석 범위다.

#### 최종 산출물 및 검증

v2 출력 폴더의 다음 파일을 보존했다. 모델·dataset·checkpoint·adapter·원본
로그는 Git 제외 경로에 유지하고 이 문서에는 재현 조건과 결과만 기록한다.

- `unsloth-original-max-new-tokens-131072-results.md`, `comparison.json`: 최종8행
- `training-result.json`, `metrics.jsonl`, `mask-and-arguments.json`:30step·loss·native 제외67건
- `manifest.json`, `execution-bindings.json`, `model-runtime.json`:원본·패키지·실제 LoRA 범위
- `adapter/`:원본 save_pretrained 결과와 로컬 재로딩용 tokenizer
- `inference/base/`, `inference/adapter/`:입력·생성 token IDs, 원문, 각 native config, 부분 토큰 로그
- `raw-output-review.md`/`.json`:실근 기준값과 완료/부분 출력 검토
- `post-run-audit.json`:원본 AST3검사, 데이터 hash, 30step 및8행 검증 통과
- `pipeline-v2-result.json`, `train-v2.log`, `base-v2.log`, `adapter-v2.log`:실행 결과와 raw logs

사후 CPU 검사는 데이터1,000건의 hash, 원본 설정, native 제외 후933건,
step1–30의 유한 loss/gradient, 저장 tensor192개·파라미터 수와 adapter SHA,
모든 LoRA B의 초기0 대비 갱신, base/adapter 동일 native generation_config,
실제 token decode·중간 토큰 로그 일치, EOS 무주입 및8개 행을 확인해 통과했다.
실행 전 원본 AST3검사와 Ruff check도 통과했고 완료 후 GPU compute process는
없었다. v1의 학습 실패 결과표는0step/adapter4조건 미실행으로 별도 마감했다.

```bash
experiments/unsloth-original-max-new-tokens-131072/.venv/bin/python \
  outputs/unsloth-original-max-new-tokens-131072-20261004-v2/audit.py
experiments/unsloth-original-max-new-tokens-131072/.venv/bin/python \
  outputs/unsloth-original-max-new-tokens-131072-20261004-v2/review_outputs.py
```

### 2026-10-04: unsloth-official-tutorial-generation-64

사용자의 최신 지시는 **학습과 생성 길이를 모두 공식 튜토리얼 그대로 실행**하고,
실험표에 실제 결과를 기록한 뒤 분석하는 것이다. 이전 adapter를 재사용하지 않는다.
정본은 이미 확보한 Unsloth notebooks commit
`92e38e86308748d18fc4cd4b104c4c6d3db1d67e`의
`gpt-oss-(20B)-Fine-tuning.ipynb`와 Python export다. 웹 설명문과 실행 코드의
값을 섞지 않고, 두 파일의 실행 AST가 일치하는 것을 확인했다.

#### 실행 전 고정표

| 항목 | 원본 조건 |
| --- | --- |
| 학습 데이터 | `load_dataset("HuggingFaceH4/Multilingual-Thinking", split="train")` |
| 모델 | `unsloth/gpt-oss-20b`, `load_in_4bit=True`, `dtype=None` |
| 학습 길이 / steps | 1,024 / 30 |
| LoRA | r8 / alpha16 / dropout0, 원본 attention+MLP target 목록 |
| batch / accumulation | 1 / 4 |
| LR / warmup / optimizer | 2e-4 / 5 / adamw_8bit |
| weight decay / scheduler / seed | .001 / linear / 3407 |
| formatter / mask | 원본 standardize_sharegpt, chat template, final response mask |
| validation / W&B | 원본 eval dataset 없음 / report_to=none |
| 생성 | 원본 TextStreamer, max_new_tokens=64, 그 밖의 생성 옵션 원본 유지 |
| 컴파일·종료 | 추가 compiler-off, 외부 시간 제한, 종료 토큰·prefill 보정 없음 |

| 원본 순서 | 모델 상태 | 프롬프트 | reasoning | 생성 상한 | 실행 전 상태 |
| --- | --- | --- | --- | ---: | --- |
| pre-low | LoRA 초기화 후, 학습 전 | 원본 user-only 수학 질문 | low | 64 | pending |
| pre-medium | LoRA 초기화 후, 학습 전 | 원본 user-only 수학 질문 | medium | 64 | pending |
| pre-high | LoRA 초기화 후, 학습 전 | 원본 user-only 수학 질문 | high | 64 | pending |
| train | 새 adapter 학습 | 원본 dataset | 해당 없음 | 해당 없음 | pending |
| post-medium | 30-step 학습 후 | 원본 French system + 수학 질문 | medium | 64 | pending |
| adapter-save | 학습 모델 저장 | 원본 `gpt_oss_lora` 상대 경로 | 해당 없음 | 해당 없음 | pending |
| post-high | 같은 학습 모델 | 원본 French system + 수학 질문 | high | 64 | pending |

원본의 `if False` 재로딩·merge·push 분기는 활성화하지 않는다. 학습 전후
프롬프트가 다르므로 이 5회를 동일 입력 base/adapter 품질 비교로 집계하지 않는다.
64토큰에서 끝나면 원본 예산 소진인지 native EOS인지 구분하며,
시연의 미완성 답변만으로 학습 프레임워크 실패를 판정하지 않는다.

#### 환경과 실행 방법

Git 제외 경로
`outputs/unsloth-official-tutorial-generation-64-20261004-v1/`에 원본 두 파일,
설치 셀, `manifest.json`, 실행 전 `results.md`/`results.json`을 보존했다.
원본 Python SHA256은
`74ff47bb9212f482f7378d86f27bc088973e924ae427cc84891d87663131895a`다.
`run.py`는 원본 top-level AST를 수정 없이 순서대로 실행하고 반환값을 관측한다.
model/generate/streamer/Trainer를 교체하지 않는다.

새 환경은
`experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv`다.
기존 venv의 site-packages를 `.pth`로 공유하지 않는다. 원본 설치 셀의
torch-missing 첫 분기를 로컬 shell 명령으로 옮겨 실행했으며,
마지막 `--upgrade --no-deps` 및 torchao 설치도 그대로 적용했다.
원본에서 버전을 고정하지 않은 패키지는 이번 설치 시점에 결정된 값을 기록한다.

| 패키지 | 실제 설치 버전 / provenance |
| --- | --- |
| Python | 3.12.13 |
| torch / triton | 2.14.1 / 3.8.0 |
| transformers / trl | 4.56.2 / 0.22.2 |
| Unsloth | 2026.9.14, Git `5971d280d4b645c8d470d6bb3171b082c4d4d2b8` |
| Unsloth Zoo | 2026.9.9, Git `867a86383371ebeb8ab1948d085540d134c07b4c` |
| triton_kernels | 원본 고정 Git `0add68262ab0a2e33b84524346cb27cbb2787356` |
| bitsandbytes / PEFT / torchao | 0.50.2 / 0.21.2 / 0.18.0 |
| huggingface-hub / tokenizers | 0.36.2 / 0.22.2 |

GPU는 RTX A6000 49,140MiB, driver595.84다. 저장 위치만 새 process cwd 및
기존 Hugging Face cache 경로로 지정한다. Colab OS/GPU까지 같다는 뜻은 아니다.
원본 설치 전체 성공, `uv pip check`의 113개 패키지 호환 검사 성공,
notebook/Python 실행 AST 일치, 원본 5회 생성 상한64 확인,
관측 스크립트 Python 구문 검사 성공을 기록했다.

```bash
cd outputs/unsloth-official-tutorial-generation-64-20261004-v1
python3 -u install.py > installation.log 2>&1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u run.py > execution.log 2>&1
```

실행 오류가 발생하면 해당 후보를 실패로 마감하고 원본 오류와 미실행 행을
기록한다. 설정·의존성·compiler 경로를 임의로 수정한 재시도를 같은 결과에
섞지 않는다. 실행 후 결과와 분석은 아래에 추가한다.

#### 실제 실행 결과: completed

2026-10-04 18:01:10–18:07:29 KST에 원본 실행 AST의 64개 top-level 문장을
순서대로 실행해 exit0으로 마감했다. 원본 조건 외의 학습·생성 인자를 추가하지
않았고, compiler-off 및 외부 시간 제한을 적용하지 않았다. 원본의 disabled
재로딩·merge·push 분기도 그대로 비활성 상태였다.

| 학습 지표 | 실제 값 |
| --- | ---: |
| 완료 optimizer steps | 30 / 30 |
| 원본 데이터 / 유효 학습 데이터 | 1,000 / 933 |
| 원본 처리에서 제외된 all-ignored-label record | 67 |
| native 학습 시간 | 275.4449초 |
| 평균 train loss | 1.003214 |
| step1 / step30 loss | 1.0702 / 0.6554 |
| 첫5 / 마지막5스텝 평균 loss | 1.17802 / 0.94244 |
| non-finite loss·grad norm step | 0 |
| 실제 학습 epoch | 0.128617 |
| trainable parameters / tensors | 92,454,912 / 3,264 |
| 그중 expert trainable parameters | 88,473,600 |
| 학습 전후 해시가 바뀐 trainable tensors | 3,264 / 3,264 |
| native peak reserved GPU memory | 19.295GiB |

원본 relative checkpoint와 adapter 경로는 새 process cwd 아래에 생성됐다.
최종 adapter는
`outputs/unsloth-official-tutorial-generation-64-20261004-v1/gpt_oss_lora/adapter_model.safetensors`다.
파일 크기370,291,488 bytes, tensor 수3,264, parameter 수92,454,912이며
저장 파일의 shape 합계와 실제 학습 parameter 합계가 일치했다. SHA256은
`d914cf7fb22e10d3f68fadc39f7c3583cef3b832f550437ae3ebb4300531d9ba`다.
원본대로 저장까지만 검증했으며, 비활성 재로딩 분기를 켠 별도 검증은 하지 않았다.

| 조건 | 입력 토큰 | 상한 | 실제 생성 토큰 | 종료 이유 | final marker | 시간(초) |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| pre-low | 98 | 64 | 64 | token_limit | 없음 | 14.558 |
| pre-medium | 98 | 64 | 64 | token_limit | 없음 | 5.389 |
| pre-high | 98 | 64 | 64 | token_limit | 없음 | 5.451 |
| post-medium | 122 | 64 | 64 | token_limit | 없음 | 5.923 |
| post-high | 122 | 64 | 64 | token_limit | 없음 | 5.538 |

5회 모두 원본 TextStreamer와 생성 상한64로 정상 반환했다. native EOS 종료는0/5,
외부 시간 제한은0/5다. 모든 원문은 `<|channel|>analysis<|message|>`로 시작하고,
64토큰 안에는 final 채널이나 완성된 수학 정답이 없다. 각각 analysis marker는
1개라 이 범위에서 반복되는 channel 접두부 루프는 관측하지 않았다.
수식과 질문을 여러 번 재진술하는 부분은 있지만 64토큰 밖의 반복 여부나
자연 종료 가능성은 이 실행으로 확인하지 않았다.

#### 입력·출력과 실제 mask 분석

원본의 학습 전 입력은 user-only 수학 질문이고, 학습 후 입력은
`reasoning language: French`를 포함하는 system 메시지와 같은 질문이다.
native chat template는 이 system 지시를 developer 영역에 넣었다.
학습 후 medium 출력은 `We have to solve equation: ...`, high 출력은
`We need to solve ...`로 시작했다. **관측한 첫64토큰은 둘 다 영어**였으므로,
이 시연에서 French reasoning 적응 성공을 확인했다고 기록하지 않는다.

실제 native 처리 후 Arrow cache의 input_ids/labels도 모델 재로딩 없이
검사했다. 1,000건의 cached labels에서 확인한 값은 다음과 같다.

| 라벨 검사 | 실제 값 |
| --- | ---: |
| analysis 본문 토큰 | 468,501 |
| 그중 supervised analysis 토큰 | 0 |
| final 본문 토큰 | 226,733 |
| 그중 supervised final 토큰 | 226,733 |
| 모든 labels가 -100인 record | 67 |
| full final header가 없는 record | 65 |
| final header는 있으나 supervised 본문이 없는 record | 2 |

이는 원본 `train_on_responses_only`의 final response mask가 실제로
**final만 직접 학습하고 analysis 본문은 loss에서 제외**했음을 보여준다.
67건은 agent가 새 필터를 만든 결과가 아니라 원본 helper의 자동 처리이며,
65건은 final header가 없고 2건은 header 뒤 학습할 본문이 남지 않았다.
따라서 “공식 예제가 French reasoning 데이터로 학습하니 analysis의 언어도
직접 학습된다”는 해석은 이 설정과 맞지 않는다. 이 mask가 영어 출력의
단독 원인이라고 단정하지는 않는다. 짧은 학습량과 생성 예산 등 다른 조건도
있고, 같은 입력으로 mask만 바꾼 비교를 하지 않았기 때문이다.

#### 해석과 기존 실행과의 차이

이번 환경에서는 공식 설치 처방과 원본 실행 셀로 모델 로딩, 실제30-step
학습, 생성5회, adapter 저장까지 완료됐다. **Unsloth로 학습 자체가 불가능하다는
결론은 이 결과와 맞지 않는다.** 반면 완성된 답변·French reasoning 적응·
C/C++ 판단 성능을 입증한 실험도 아니다. 답변 미완성은 모두 실제 원본
64토큰 예산 소진으로 관측됐으며, 실행 예외·외부 시간 제한과 구분한다.

원본에는 validation dataset과 W&B가 없고 effective 설정은
`eval_strategy=no`, `report_to=[]`다. 30스텝은 유효 데이터 전체1회 학습이 아니라
약0.129epoch이며, train loss 감소만으로 일반화 품질을 판정하지 않는다.
C/C++ test500 평가·혼동행렬은 실행하지 않았다.

이번 원본 설치 셀은 floating Git refs와 torch 하한을 포함한다. 그 처방대로
새로 설치한 실제 환경은 이전 혼합 환경과 달라졌다.

| 항목 | 이전 최대 생성 실험 v2 | 이번 원본64 실행 |
| --- | --- | --- |
| Torch / Unsloth / Zoo | 2.10.0 / 2026.6.9 / 2026.6.7 | 2.14.1 / 2026.9.14 / 2026.9.9 |
| 환경 구성 | 기존 site-packages를 .pth로 공유 | 새 독립 venv, 원본 설치 셀 |
| compiler override | `UNSLOTH_COMPILE_DISABLE=1` | 없음 |
| trainable parameters | 3,981,312 | 92,454,912 |
| expert trainable parameters | 0 | 88,473,600 |
| 원본 생성 호출 | 별도8조건 비교로 대체 | 원본5회 그대로 |
| 외부 generate 제한 | 각600초 | 없음 |

동일한 원본 target 목록이라도 이번 라이브러리는 로그에서 64개 expert
projection module의 LoRA를 활성화했다고 알렸다. 따라서 이전과의 loss·
출력 차이를 종료 토큰이나 생성 길이 하나에만 귀속할 수 없다.

이번 native generation config의 EOS 목록은 `[200002,199999,200012]`다.
마지막 `<|call|>` ID200012는 새 Unsloth가 로딩 중 자동 추가했다는 로그가 있다.
에이전트가 EOS 목록을 주입한 것은 아니며, original.generate kwargs에는
EOS·forced_eos·sampling·prefill·max_time 인자를 추가하지 않았다.
native forced_eos는None, do_sample=True, temperature1.0, top_k50, top_p1.0이다.
모델 alias는 실제로 기존 cache의 `unsloth/gpt-oss-20b-unsloth-bnb-4bit`로
연결됐고 quantization은 BnB NF4, bf16 compute, double quant였다.

#### provenance·산출물·검증

native model cache revision은 `093fba6992ef5a7152481afec0bdfca1ac486998`,
dataset revision은 `f423949d2726f5a5633ea10ac45bc1ea1e0de6e7`이다.
원본 train parquet SHA256은
`db53734e93e43a211c631b460fdfc6c01fa0c919f426046e89360928a6f85e26`,
label cache SHA256은
`a7d94ebd80cb74e9697bf88196667eaa5f60e3386ce69cac1b9c2131bf1db079`다.
source 파일·dataset·model·adapter·raw log는 Git 제외 경로에 남겼다.

새 실험 디렉터리의 결과 파일:

- `results.md` / `results.json`: 최종5조건 실험표와 학습 상태
- `analysis.md` / `analysis.json`: 전체5개 생성 원문과 해석·학습·저장 검증
- `training.json`: native metrics,30step log_history, effective SFTConfig
- `pre-*.json` / `post-*.json`: 실제 input/output token IDs·원문·generation config
- `manifest.json`, `packages.json`, `installation.json` / `.log`: 원본·환경·설치 명령
- `runtime.json` / `execution.log`: 원본64문장 실행 순서와 실제 stdout/stderr
- `cache-provenance.json`, `dataset-cache-files.json`, `label-inspection.json`: cache 계보·실제 labels 검사
- `trainable-parameters.json`: 초기 trainable tensor 형태와 해시
- `audit.json`: 원본 AST·kwargs·순서·실제 토큰 수·완료 상태 대조8항목 통과

Python 구문 검사 및 관측 스크립트 Ruff check를 통과했다. 실제30step의
loss/grad norm이 모두 finite이고, 저장 safetensors의 parameter 수와 학습 전후
3,264개 tensor 변경을 확인했다. 원본을 바꾸는 수정이나 추가 GPU 실험은 하지 않았다.

```bash
cd outputs/unsloth-official-tutorial-generation-64-20261004-v1
python3 audit.py
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  inspect_labels.py
```

### 2026-10-04: official-tutorial-v5-dataset-token-caps

사용자는 공식 튜토리얼에서 데이터셋만 우리 것으로 교체해 새로 학습하고,
생성은 기존 실험표의 토큰 길이 조건으로 진행하도록 요청했다.
새 실험 ID는 `cc-official-tutorial-v5-token-caps-20261004-v1`, 설정은
`configs/cc_official_tutorial_dataset_v5_token_caps_v1.json`이다.
바로 앞 공식 원본64 실험에서 설치·검증한 독립 venv를 그대로 사용하므로
이번 실행 중 패키지를 업데이트하지 않는다.

#### 실행 전 고정 조건

- 학습 입력: `data/processed/cc-source-candidates-20260928-v5/decision-candidates/train.jsonl` 10,000건만 사용.
- validation1,000은 optimizer 입력에 넣지 않는다. 기존 실험표의 동일 validation2건만 생성 진단에 사용한다.
- 기존 test500·gold 파일은 학습·표본 선택·생성 평가에 로딩하지 않는다. 보존된 전체 split audit와 train/validation ID 독립성을 대조한다.
- 공식 학습 AST의 모델·LoRA·formatter·SFTConfig·final response mask·train·save 호출은 그대로다.
- 변경한 학습 AST는 `load_dataset` 1개뿐이다. 로컬 JSONL loader로 역변환 검사 시 그 외 AST가 모두 원본과 같다.
- 학습 길이1,024, steps30, batch1×accumulation4, LR2e-4, warmup5, adamw_8bit, weight decay.001, seed3407은 원본 값이다.
- validation 및 W&B는 원본처럼 비활성이다. 이전 C/C++100-step·4096-token 설정으로 바꾸지 않는다.

#### 데이터 형식 연결과 길이 검사

우리 원본 assistant 메시지는 `role`과 JSON `content`만 가진다. 이 형식을
native chat template에 그대로 넣으면 `<|start|>assistant<|message|>`가 되어
공식 final response mask의 marker와 일치하지 않았다. 따라서 학습용 사본의
assistant에 **`thinking: ""`만 추가**했다. 원본 공식 dataset의 assistant 형식에
맞추기 위한 연결이며 system/user/assistant content와 JSON label은 그대로다.
원본 dataset 폴더를 수정하지 않고 새 실험의 `training-messages.jsonl`에 저장한다.
추가 reasoning 문장·근거·정답 보정은 만들지 않는다.

CPU 준비에서 10,000건 content 보존과 실제 installed Zoo의 masking 함수로
토큰·정답 마스크를 확인했다. 최초 CPU 관측 helper에는 새 Zoo의 내부 helper
추출이 누락돼 NameError가 있었고 `prepare-attempt1.py`/`.log`로 보존했다.
누락된 `_stable_marker_edges`와 상수만 함께 읽도록 고쳤다. 학습 recipe를
우회하거나 바꾸는 수정은 아니며 GPU 학습 전에 준비 검사를 완료했다.

| 길이·라벨 항목 | CPU 사전 검사 |
| --- | ---: |
| 원본 train | 10,000 |
| 원본 present / not_observed | 5,000 / 5,000 |
| 원본1,024토큰을 넘는 record | 1,490 |
| 완전한 JSON+return target이 남는 record | 8,510 |
| supervised target 일부만 남는 record | 15 |
| 모든 target이 잘려 자동 제외될 record | 1,475 |
| 예상 유효 train | 8,525 |
| 예상 유효 present / not_observed | 3,831 / 4,694 |

길이는 user의 요청대로 원본1,024를 유지한다. 이 실험을 train10,000 전체
정답이 온전한4096-token 학습으로 기록하지 않으며, partial target15건도 숨기지
않는다. 실제 SFTTrainer 처리 수와 native mask 결과는 학습 후 대조한다.
원천 취약 여부/CWE는 미검수 후보 라벨이며, 기존에 승인한 판단 학습 실험
범위에서 사용한다. human-reviewed 정답으로 표시하지 않는다.

#### 생성 표와 적용 범위

이전 `max-new-tokens-65536` 표의128/512/2048/65536을 적용하고, 후속
최대 문맥 실험의 `131072 - input_tokens` 조건도 포함한다.
모든 행에 이전 표의 같은 validation ID2건을 쓰며 gold-free system/user만 입력한다.

| 모델 | 생성 상한 조건 | 입력 | 생성 호출 수 |
| --- | --- | --- | ---: |
| base | 128 / 512 / 2,048 / 65,536 / context-minus-input | 동일 validation2건 | 10 |
| 새30-step adapter | 같은5조건 | 동일 validation2건 | 10 |

ID는 `cc-55fa921bc64a64071c4dd1c9`(present)와
`cc-b8bec7f8c250c406ad4ed545`(not_observed)다. first base128 진단을 먼저
실행하고 새 학습을 진행한 뒤 나머지 base/adapter 표를 채운다.
큰 예산의 생성 때문에 새 학습 착수가 밀리지 않도록 실행 순서만 나눴다.
추론 loader의 context131,072는 이 표의 큰 생성 예산용이며 학습1,024와 구분한다.

기존 표는 greedy/low reasoning이지만 공식 tutorial은 native sampling이다.
이 차이에 대해 사용자에게 선택 질문을 보냈고, 독립적인 데이터 준비를 계속했다.
별도 답변 없이 준비가 끝난 시점에는 권장안인 **공식 기본 생성 유지, 길이만 변경**을
적용한다고 안내했고, 학습 도중 사용자가 같은 선택을 명시적으로 회신했다.
회신은 새 실험의 `user-selection.json`에 기록했다.
그 조건은 mode=`official-native-defaults`, native medium
reasoning, native EOS/sampling/pad 설정이다. 별도 `do_sample`, EOS, forced_eos,
final-prefill, 외부 시간 제한, `max_time`을 주입하지 않는다.
표의 길이 조건을 재사용하되 과거 greedy의 동일 protocol이라고 주장하지 않는다.
각 native sampling 호출의 RNG를 새로 고정하거나 rewind하지도 않으므로,
서로 다른 예산의 출력 접두부나 성공률이 단조로 같다고 가정하지 않는다.

원문/token IDs/실제 생성량/종료 이유/final 존재/JSON·판단 schema·원천 라벨 일치를
행별로 기록한다. 동일2건 진단이며 전체 validation/test500 성능으로 일반화하지 않는다.
형식 실패는 오분류와 별도로 집계한다.

#### 명령·저장 위치

실험 실행 코드·원본·임시 데이터·adapter·로그·표는 Git 제외 경로
`outputs/cc-official-tutorial-v5-token-caps-20261004-v1/`에 보존한다.
설정과 요약 문서만 Git 변경 대상으로 두며, 현재 요청에 commit/push는 포함하지 않는다.

```bash
cd outputs/cc-official-tutorial-v5-token-caps-20261004-v1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u prepare.py > prepare.log 2>&1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u generate.py --model base --phase baseline > base-baseline.log 2>&1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u train.py > training.log 2>&1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u generate.py --model base --phase remaining > base-remaining.log 2>&1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u generate.py --model adapter --phase all > adapter-all.log 2>&1
```

설정·CPU 준비의 Python 구문 검사와 Ruff check는 통과했다. 원본 학습 AST,
실제 학습·adapter 재로딩·20개 생성 결과를 아래에 기록했다.

#### 실제 학습 결과와 환경

공식30-step 학습과 adapter 저장을 완료했다. 평균 train loss는
**0.230625**, 마지막 step loss는0.0996, native train runtime은226.963초다.
30개의 loss·grad norm이 모두 finite였고 유효 train 수는 예상과 같은
**8,525건**이었다. native Arrow cache의10,000개 실제 labels를 사전 검사와
행별로 대조해 길이와 supervised token 수가 전부 일치했다.
원본1,024-token truncation으로1,475건이 제외되고15건은 partial target으로
남는 것을 확인했다. full train10,000을 모두 온전히 학습한 결과는 아니다.

batch1×accumulation4의30step은 약120회 표본 제시, epoch0.01408이다.
낮은 train loss로 전체 데이터 학습 완료나 일반화 성능을 주장하지 않는다.
trainable parameter는92,454,912개·3,264개 tensor이며 저장 전후 해시에서
3,162개 tensor 변경을 확인했다. expert LoRA를 포함하는 native 구성으로,
이전 구환경의3,981,312개 parameter 실행과 같은 adapter 구성은 아니다.
native peak reserved GPU memory는19.295GiB다.

환경은 RTX A6000 49,140MiB, NVIDIA driver595.84, Python3.12.13,
Torch2.14.1+cu130, Triton3.8.0, Transformers4.56.2, TRL0.22.2,
Unsloth2026.9.14, Zoo2026.9.9다. Unsloth Git SHA는
`5971d280d4b645c8d470d6bb3171b082c4d4d2b8`, Zoo는
`867a86383371ebeb8ab1948d085540d134c07b4c`다.
이 실험에서 model venv는 변경하지 않았으며 `uv pip check`는113개 package
호환성을 통과했다. 실행 후 package 목록도 별도로 기록했다.
모델 alias `unsloth/gpt-oss-20b`는 기존 BnB NF4·bf16 compute·double quant
cache를 사용한다. cache revision은 `093fba6992ef5a7152481afec0bdfca1ac486998`이다.
저장 adapter SHA256은
`6a5721a752ac49b31485641d1b402ad7529c63b4818e1342a67922f9a09ca827`이다.

#### 평가 파서 누락과 실제 출력 오류 구분

첫 fixed-string 검사는 `<|channel|>final<|message|>`만 인식했다.
그러나 base의 일부 정상 출력은
`<|channel|>final <|constrain|>json<|message|>` 헤더였다.
이 형식에는 실제 final JSON이 있어도 initial matcher가 없는 것으로 집계했다.
Harmony는 채널과 형식 metadata를 함께 표현할 수 있으므로
[공식 Harmony 형식 문서](https://developers.openai.com/cookbook/articles/openai-harmony)와
[공식 parser](https://github.com/openai/harmony)를 기준으로 token IDs를 다시 평가한다.
원래 `results.json`과 raw 생성물은 보존하고, corrected 결과는
`scored-results.json`·`.md`에 분리한다. 학습·생성 설정이나 이미 받은 출력은
수정하지 않는다.

반대로 adapter512의 음성 표본에는 `final` 뒤에 또 `analysis` 채널과
가상의 tool recipient가 붙는 잘못된 헤더가 있다. JSON 내용이 원천 라벨과
같더라도 공식 parser에서 final로 나오지 않으므로 형식 실패로 남긴다.
base512의 음성 표본은 commentary tool request 뒤 `<|call|>`로 종료한다.
이 역시 JSON 판단 final이 아니며 도구 실행은 하지 않았다.
native EOS로 끝났다는 사실과 유효한 최종 답변인지는 서로 다른 지표다.

추가 parser는 model venv와 분리한
`experiments/cc-official-tutorial-v5-score/.venv`의 `openai-harmony0.0.8`이다.
원 token IDs를 읽기만 하며 생성에 영향을 주지 않는다. 실제 constrained final,
analysis 안의 JSON, 실제 tool handoff, 잘못된 중복 channel header,
uncertain, incomplete JSON·trailing text·wrong type·extra field를 검사한
pytest **9건**을 통과했다. 합성 fixture의 special token encoding 허용 누락을
고친 뒤 재검사했고 실제 생성물은 바꾸지 않았다.

```bash
uv venv --python python3 experiments/cc-official-tutorial-v5-score/.venv
uv pip install --python experiments/cc-official-tutorial-v5-score/.venv/bin/python \
  openai-harmony==0.0.8 pytest==8.4.2
experiments/cc-official-tutorial-v5-score/.venv/bin/python -m pytest -q \
  outputs/cc-official-tutorial-v5-token-caps-20261004-v1/test_score.py
```

실제 초기 설치 명령의 parser에는 version pin이 없었고0.0.8로 resolved됐다.
위 명령은 재현용 pin이며 실제 명령과 전체 보조 package version은
`scoring-environment.json`에 별도로 기록했다.

#### 최종 생성 실험표 — 20/20 완료

각 행은 **같은 validation2건**이다. 실제 생성량은 양성/음성 순서다.
원 token IDs를 official Harmony parser로 평가한 `scored-results.json`이
이 표의 정본이며 초기 literal matcher 결과도 별도로 보존했다.
`JSON/schema`는 유효한 판단 final, `라벨 일치`는 원천 후보 라벨과의 일치다.
둘을 동일 지표로 취급하지 않는다.

| 모델 | 생성 상한 | JSON/schema | 라벨 일치 | uncertain | 형식 실패 | EOS / 상한 종료 | 실제 생성 토큰 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| base | 128 | 0/2 | 0/2 | 0 | 2 | 0 / 2 | 128 / 128 |
| adapter | 128 | 0/2 | 0/2 | 0 | 2 | 0 / 2 | 128 / 128 |
| base | 512 | 1/2 | 1/2 | 0 | 1 | 2 / 0 | 451 / 315 |
| adapter | 512 | 0/2 | 0/2 | 0 | 2 | 1 / 1 | 512 / 486 |
| base | 2,048 | 2/2 | 1/2 | 1 | 0 | 2 / 0 | 347 / 464 |
| adapter | 2,048 | 2/2 | 2/2 | 0 | 0 | 2 / 0 | 857 / 524 |
| base | 65,536 | 2/2 | 1/2 | 1 | 0 | 2 / 0 | 308 / 577 |
| adapter | 65,536 | 2/2 | 2/2 | 0 | 0 | 2 / 0 | 904 / 830 |
| base | context-minus-input | 2/2 | 1/2 | 1 | 0 | 2 / 0 | 203 / 517 |
| adapter | context-minus-input | 2/2 | 2/2 | 0 | 0 | 2 / 0 | 549 / 823 |

첫 표본 입력은293token, 둘째는235token이다. 최대 문맥 조건의 실제
`max_new_tokens`는 각각 **130,779 / 130,837**이었다. 최대 조건의 adapter는
549/823token 뒤 native EOS로 끝났으므로13만token을 모두 생성한 실행은 아니다.
외부 시간 제한은 없었고 모든 호출이 native generate에서 정상 반환했다.
EOS로 끝난15호출 중2호출은 유효 final이 없으며, native EOS와 출력 품질을
따로 확인해야 한다. 실제 stop 합계는 base EOS8·상한2,
adapter EOS7·상한3으로 **EOS 총15호출**이다.

이진 confusion matrix로는2,048/65,536/최대 문맥의 각 조건에서 base가
TP1·uncertain1, adapter가TP1·TN1이다. FP/FN은 없지만 짧은 조건의
invalid와 base의 uncertain을 제외하고 전체 품질이100%라고 해석하지 않는다.
조건별 TP/TN/FP/FN·invalid·uncertain은 `analysis.json`·`.md`에 기록했다.

초기 literal matcher가 정상 final을 누락한 것은 **3건**이다.
base512의 양성, base2048의 양성·음성이며 corrected parser에서 복구됐다.
이 세 건은 모델 생성 실패가 아니라 evaluator의 형식 인식 누락이었다.
나머지 짧은 예산의 analysis truncation, tool handoff, 중복 channel header는
실제 출력 문제로 남아 있다. 원문에 정답 JSON이 언급된다고 final로 인정하지 않는다.

#### 해석·다음 판단에 사용할 범위

이번 공식 recipe로 학습·저장·독립 프로세스의 **base+unmerged adapter 로딩**과
생성이 성공했다. Unsloth에서 학습 자체가 불가능하다는 결론은 이 결과로
지지되지 않는다. 이 로더는 Unsloth이며 vLLM adapter 서빙 검증은 아니다.
2,048 이상 조건에서는 두 사례의 출력 형식과 원천 라벨 일치가 확인됐다.
base의 음성 판단은 uncertain, adapter는 not_observed로 달라졌지만
동일2건 반복·native sampling·미검수 후보 라벨이라 일반화 개선을 확정하지 않는다.

128의 예산 소진과512의 형식 실패로 보아 이번 입력에서 모든 문제를
최대 context 부족 하나로 설명할 수 없다. 예산별 RNG가 같지 않으므로
512에서 실패하고2048에서 성공한 차이도 길이만의 인과로 단정하지 않는다.
source train은10,000건이지만 학습은30step·0.01408epoch에 불과하고
1,475건 제외·15건 partial target이라는1024-token 제약이 있다.
실험 요청대로 조건을 유지했으며 이번 결과를 보고 길이·step·EOS·prompt를
추가 수정하거나 test500 평가로 범위를 확장하지 않았다.

#### 최종 산출물·검증

실험 폴더 `outputs/cc-official-tutorial-v5-token-caps-20261004-v1/`의
`analysis.md`·`.json`은 학습·입력/출력·confusion·실패 원인·제한을 정리한
최종 보고서다. `scored-results.md`·`.json`은 corrected 최종 실험표,
`results.md`·`.json`은 original literal matcher 관측 이력이다.
raw20개 JSON/TXT와 각 generate log, 원본/변경 AST, 실제 native mask cache,
저장 adapter, `training.json`, 환경·명령·해시 manifest를 보존했다.
학습 recipe에서는 dataset loader만 변경됐다는 AST 비교와 실제 저장
3,264개 tensor·92,454,912개 parameter 검사를 통과했다.
실험 중113개 model package version과 기록된 Git provenance가 그대로임도
대조했다. 별도 Harmony 평가 환경의 설치는 model venv를 바꾸지 않았다.

```bash
cd outputs/cc-official-tutorial-v5-token-caps-20261004-v1
../../experiments/cc-official-tutorial-v5-score/.venv/bin/python score.py
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python audit.py
../../experiments/cc-official-tutorial-v5-score/.venv/bin/python analyze.py
```

final audit은20호출 완료, 같은 input IDs, 각 요청 예산·실제 token 수·native EOS,
do_sample=True/temperature1/top_k50/top_p1, forced_eos/max_time=None,
실제10,000건 mask 일치 검사를 통과했다. pytest9건, 관측/평가/분석 코드의
Ruff·Python 구문 검사, 설정 JSON 검사와 `git diff --check`도 통과했다.
GPU 종료 후 사용량은209MiB로 복귀했다. 현재 요청에는 commit/push가 없어
설정과 요약 문서 변경은 로컬에 남겼다.

### 2026-10-04: official-tutorial-v5-max-steps-100

사용자는 성공한 직전30-step 실험의 다른 조건을 바꾸지 않고
`max_steps`만100으로 늘려 같은 기록 방식과 생성 실험표로 진행하도록 요청했다.
실험 ID는 `cc-official-tutorial-v5-max-steps-100-20261004-v1`, 설정은
`configs/cc_official_tutorial_dataset_v5_max_steps_100_v1.json`이다.
기준 실험은 `cc-official-tutorial-v5-token-caps-20261004-v1`이며 결과를 보존한다.

#### 고정 조건과 변경 범위

| 항목 | 기준30step | 새100step |
| --- | --- | --- |
| max_steps | 30 | **100** |
| 시작 모델·seed | fresh base / 3407 | 동일 |
| train 파일·assistant 형식·mask | v5 train10,000 / empty thinking / official final-only | 동일 |
| 학습 길이·batch·accumulation | 1,024 / 1 / 4 | 동일 |
| LR·scheduler·warmup·optimizer·decay | 2e-4 / linear / 5 / adamw_8bit / .001 | 동일 |
| LoRA·환경·cache revision | 원본 r8/alpha16/dropout0, 기존 독립 venv와 cache | 동일 |
| validation·W&B | 원본 `eval_strategy=no`, `report_to=[]` | 동일 |
| 생성 표본·상한 | 동일 validation2건 /128·512·2048·65536·context-minus-input | 동일 |
| 생성 sampling·reasoning·EOS | native sampling / medium / native EOS | 동일 |
| 외부 시간 제한·forced EOS·final-prefill·compiler override | 없음 | 동일 |
| optimizer 표본 제시 수 | 약120 / epoch0.01408 | 약400 / epoch0.04692 예정 |

새 run은 같은 base에서 원본 seed로100step을 실행한다. 기존30step adapter를
resume하는 별도 경로는 추가하지 않는다. 기존 linear scheduler는
총 optimizer step 수를 사용하므로 `max_steps=100`에 따라 LR 곡선도 자동으로
100step 기준이 된다. scheduler 종류·초기 LR·warmup을 별도로 변경하지 않았고,
30step run의 첫30step과 가중치 경로가 완전히 같다고 주장하지 않는다.

CPU 준비를 같은 `prepare.py`로 다시 실행했다. 원자료·train10,000·validation1,000
독립성 검사,10,000건 token/mask 결과와 생성용2건 입력을 대조했다.
`training-messages.jsonl`, `dataset-audit.json`, `prompts.json`, `gold.json`,
`frozen-inputs.json`이30step 실험과 byte 단위로 동일하다.
유효8,525·완전 target8,510·partial15·제외1,475도 그대로 유지한다.
길이·표본·라벨을 추가 수정하거나 test500을 로딩하지 않는다.

실행 전 실제 `train.py`의 AST 준비 부분을 CPU-only로 실행해
dataset 경로와 `max_steps`를 제외한 학습 AST가30step과 같음을 검사했다.
새 artifact 경로는 같은 해시의 학습 사본을 가리킨다. 공식 원본과 비교하면
기존의 dataset loader 교체에 `SFTConfig.max_steps`30→100만 추가된다.
`generate.py`와 official Harmony `score.py`도30step과 byte 단위로 같다.
113개 model package version과 기록된 Git provenance를 다시 대조해 일치했다.
보조 parser 환경은 기존 openai-harmony0.0.8을 사용하며 새 설치는 하지 않았다.

실행 기록 helper 복제의 첫 시도는 formatting된 `audit.py`에서 single-line
문자열을 찾는 assertion에 걸렸다. GPU 실행 전의 준비 오류이며
`setup-attempt1.json`에 남겼다. 실제 source block을 확인해 사후 감사 부분만
수정한 뒤 recipe 검사와 CPU 준비를 통과했다. 학습 hyperparameter나
generation의 변경·재시작·결과 덮어쓰기는 없었다.

#### 실행 순서와 저장 위치

기준 실험과 같은 순서로 base128 진단 → fresh100step 학습·저장 → 나머지
base8호출 → 독립 adapter reload·10호출을 실행한다. 총20개 새 생성 결과를
보존하고30step 결과와 같은 공식 Harmony parser로 비교한다.
짧은 예산·형식 실패·uncertain·tool request를 기존과 같은 방식으로 분리한다.
native sampling RNG를 새로 고정하거나 rewind하지 않으므로 한 조건의
두 건 일치 차이를 전체 정확도나 step 수만의 인과로 단정하지 않는다.

원본·실행 source·token IDs·data 사본·adapter·로그·결과표·보고서는
`outputs/cc-official-tutorial-v5-max-steps-100-20261004-v1/`에 저장한다.
설정과 요약 문서만 Git 변경 대상으로 두며 commit/push는 현재 요청에 없다.

```bash
cd outputs/cc-official-tutorial-v5-max-steps-100-20261004-v1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u prepare.py > prepare.log 2>&1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u generate.py --model base --phase baseline > base-baseline.log 2>&1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u train.py > training.log 2>&1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u generate.py --model base --phase remaining > base-remaining.log 2>&1
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python \
  -u generate.py --model adapter --phase all > adapter-all.log 2>&1
```

실행 전 CPU 준비·recipe AST 검사·package provenance 대조·동일 parser의
pytest9건을 통과했다. 학습100step·저장·재로딩·생성20/20을 완료했으며 결과는 아래와 같다.

#### 실제100step 학습 결과

| 항목 | 기준30step | 새100step |
| --- | ---: | ---: |
| optimizer steps | 30 | 100 |
| native 평균 train loss | 0.230625 | 0.130558 |
| 마지막 step loss | 0.0996 | 0.0860 |
| native train runtime(초) | 226.963 | 656.811 |
| epoch | 0.01408 | 0.04692 |
| 변경된 trainable tensor / 전체 | 3,162 / 3,264 | 3,178 / 3,264 |
| trainable parameters | 92,454,912 | 92,454,912 |
| 원본 / 유효 train | 10,000 / 8,525 | 10,000 / 8,525 |

100개의 실제 step loss·gradient norm이 모두 finite였다. 최종 adapter를
저장하고 별도 프로세스에서 unmerged base+adapter 로딩을 완료했다.
초기 trainable tensor3,264개의 해시는30step과 전부 같았다.
native SFTConfig 전체를 대조해 `max_steps`와 동적으로 생성되는
`logging_dir` 외의 모든 항목이 같음을 확인했다. 데이터 사본·실제 native mask
10,000건·생성용 input IDs·생성 코드·parser 코드도 기준 실험과 같았다.
linear scheduler의 전체 예산에 따른 파생 LR 차이는 첫30step 중24개
logged step에서 관측했으며 `step30-vs-step100.json`에 수치를 남겼다.

| 100step 구간 | 평균 train loss | 구간 마지막 loss | 마지막 logged LR |
| --- | ---: | ---: | ---: |
| 1–25 | 0.264692 | 0.1021 | 0.00016000 |
| 26–50 | 0.088124 | 0.0593 | 0.00010737 |
| 51–75 | 0.088280 | 0.0704 | 0.00005474 |
| 76–100 | 0.081148 | 0.0860 | 0.00000211 |

이 표는 학습 loss 구간 집계이며 validation loss가 아니다. 원본과 기준30step의
설정을 유지해 validation 및 W&B를 새로 켜지 않았다.
약400회 표본 제시이며8,525건 전체를 한 epoch 학습한 결과도 아니다.

GPU는 같은 RTX A6000 49,140MiB·driver595.84다. Python3.12.13,
Torch2.14.1+cu130, Triton3.8.0, Transformers4.56.2, TRL0.22.2,
Unsloth2026.9.14와 Zoo2026.9.9를 그대로 사용했다.
113개 package version 및 기록된 Git provenance 대조와 `uv pip check`가
통과했다. native peak reserved memory는19.295GiB이며 종료 후209MiB로 복귀했다.
cache revision은 `093fba6992ef5a7152481afec0bdfca1ac486998`, 저장 adapter SHA256은
`4f0280021be433758f7ee6e1fc8d09f22846286ab6967892bd0cdbae9691b4b9`다.

#### 같은 생성 실험표의 최종 결과 — 20/20

각 행은 같은 validation2건이며 token 수는 양성/음성 순서다.
`판단 schema`는 정확히 assessment 하나만 갖는 유효 final이며,
JSON 문법만 정상인 출력과 원천 라벨 일치를 별도로 평가했다.

| 모델 | 생성 상한 | 판단 schema | 원천 라벨 일치 | TP / TN / FP / FN | invalid / uncertain | EOS / 상한 종료 | 실제 token 수 |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| base | 128 | 0/2 | 0/2 | 0 / 0 / 0 / 0 | 2 / 0 | 0 / 2 | 128 / 128 |
| base | 512 | 1/2 | 0/2 | 0 / 0 / 0 / 0 | 1 / 1 | 1 / 1 | 512 / 479 |
| base | 2,048 | 1/2 | 0/2 | 0 / 0 / 0 / 1 | 1 / 0 | 2 / 0 | 191 / 319 |
| base | 65,536 | 1/2 | 1/2 | 1 / 0 / 0 / 0 | 1 / 0 | 2 / 0 | 566 / 337 |
| base | context-minus-input | 2/2 | 2/2 | 1 / 1 / 0 / 0 | 0 / 0 | 2 / 0 | 464 / 235 |
| adapter100 | 128 | 0/2 | 0/2 | 0 / 0 / 0 / 0 | 2 / 0 | 0 / 2 | 128 / 128 |
| adapter100 | 512 | 2/2 | 2/2 | 1 / 1 / 0 / 0 | 0 / 0 | 2 / 0 | 424 / 250 |
| adapter100 | 2,048 | 1/2 | 0/2 | 0 / 0 / 0 / 1 | 1 / 0 | 2 / 0 | 1,062 / 648 |
| adapter100 | 65,536 | 2/2 | 1/2 | 1 / 0 / 1 / 0 | 0 / 0 | 2 / 0 | 517 / 550 |
| adapter100 | context-minus-input | 1/2 | 1/2 | 1 / 0 / 0 / 0 | 1 / 0 | 2 / 0 | 1,222 / 752 |

최대 문맥은 입력293/235token을 뺀 `max_new_tokens=130779/130837`로
그대로 적용했다. 모든15개 native EOS 종료와5개 token-budget 종료를 확인했다.
외부 timeout·forced EOS는 없었고13만token을 소진한 호출도 없다.
native EOS로 끝났다는 사실만으로 schema·판단 품질을 합격 처리하지 않는다.

#### 30step 대비 결과와 실패 구분

| 생성 상한 | adapter30 schema | adapter100 schema | adapter30 라벨 일치 | adapter100 라벨 일치 |
| --- | ---: | ---: | ---: | ---: |
| 128 | 0/2 | 0/2 | 0/2 | 0/2 |
| 512 | 0/2 | 2/2 | 0/2 | 2/2 |
| 2,048 | 2/2 | 1/2 | 2/2 | 0/2 |
| 65,536 | 2/2 | 2/2 | 2/2 | 1/2 |
| context-minus-input | 2/2 | 1/2 | 2/2 | 1/2 |

이번 반복에서512는 좋아졌지만2,048·65,536·최대 문맥의 원천 라벨 일치는
기준30step보다 낮았다. 100step이 일관된 생성 품질 개선을 보였다고 결론
내리지 않는다. native sampling RNG를 새로 고정하지 않았고, 변경하지 않은
base에서도 schema7→5·라벨 일치4→3이라는 호출 집계 변화가 있었다.
같은2건을5개 예산에서 반복한 합계이므로 독립10건 accuracy로 해석하지 않는다.
이번 차이만으로100step 과적합이나 step 수만의 인과도 확정하지 않는다.

실제 실패는 다음처럼 구분한다.

- adapter128 두 건은 analysis 중 budget을 소진했다.
- adapter2048 양성은 `not_observed`를 반환해 원천 라벨 기준FN이다. 음성은 tool request 후 `<|call|>`로 끝나 판단 final이 없다.
- adapter65536 음성은 `present`를 반환해 원천 라벨 기준FP다.
- adapter 최대 문맥 음성은 JSON 문법이 정상이고 assessment 값도 원천 라벨과 같지만, `target_cwe`·`source_code`를 추가했다. assessment-only 계약 위반이므로 schema 실패이며 유효 라벨 일치에 포함하지 않는다.
- base2048·65536 음성도 tool request로 종료했다. 도구를 실제로 실행하지 않았다.

literal marker 검사가 final을 누락한 것은3건이다. base512 음성,
base2048 양성, adapter 최대 문맥 음성이다. 앞의 두 건은 schema가 유효하고,
마지막은 final을 추출해도 추가 필드 때문에 schema가 무효다.
원문·token IDs·initial matcher 결과를 보존하고 공식 Harmony parser로
final 존재·JSON 문법·schema·라벨 일치를 각각 기록했다.
모든 실패가 parser 문제이거나 토큰 상한 부족이라고 설명하지 않는다.
후보 라벨은 미검수이고 test500은 계속 사용하지 않았으므로 전체 판단 품질은
이2건 진단으로 확정하지 않는다.

#### 보고서·재현·완료 검사

새 실험 폴더의 `analysis.md`·`.json`은100step의 실제 학습·입출력·confusion·
실패·제한 보고서이고, `step30-vs-step100.md`·`.json`은 기준30step과의
같은 조건 비교표 및 LR 파생 차이다. 최종 생성 표는
`scored-results.md`·`.json`이며 raw20개 JSON/TXT,3개 generate log,
원본·실행 AST, native training.json 및 저장 adapter를 보존했다.
`results.md`·`.json`의 literal matcher 관측은 별도로 유지한다.

```bash
cd outputs/cc-official-tutorial-v5-max-steps-100-20261004-v1
../../experiments/cc-official-tutorial-v5-score/.venv/bin/python score.py
../../experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python audit.py
../../experiments/cc-official-tutorial-v5-score/.venv/bin/python analyze.py
../../experiments/cc-official-tutorial-v5-score/.venv/bin/python compare.py
```

`audit.json`은100step·유한한 loss/gradient100건·같은 초기 LoRA 해시·
같은 SFTConfig·native10,000건 mask·saved tensor/parameter 수·20호출 완료·
같은 input IDs·native sampling/EOS·요청 예산/실제 token 수·외부 제한 없음의
대조를 통과했다. 관측/평가/비교 코드의 Ruff·구문 검사와 설정 JSON 검사,
parser pytest9건, `git diff --check`도 통과했다. 환경 및 실행 파일의 해시는
새 manifest로 보존하며 기존30step manifest와 artifact는 수정하지 않는다.

### 2026-10-05: official-tutorial-max-steps-100-error-analysis-serving-comparison

사용자는 vLLM 서빙에서 GPT-OSS-20B가 CWE 기반 분류·선정 이유·추천 사항을
잘 제공했던 관측과, 최근 학습 결과를 “안 됐다”고 표현한 이유의 차이를 설명해
달라고 요청했다. 이론과 원문 증거, 확인된 사실과 가설을
[GPT-OSS 서빙·판단 학습 오류 분석](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md)에 기록했다.
실험 수치와 조건의 정본은 앞의 공식30/100step 실행 기록으로 유지한다.

100step 학습은 완료됐고, 최종 trainable tensor3,264개 중3,178개가 변경됐다.
전체20호출은 고유 validation2건을 반복한 결과다. 오류 분류는 다음과 같다.

| 분류 | base | adapter | 전체 |
| --- | ---: | ---: | ---: |
| 생성 예산 소진, final 없음 | 3 | 2 | 5 |
| tool handoff, final 없음 | 2 | 1 | 3 |
| 추가 필드의 schema 위반 | 0 | 1 | 1 |
| 원천 라벨 기준 FN | 1 | 1 | 2 |
| 원천 라벨 기준 FP | 0 | 1 | 1 |
| 유효한 uncertain 보류 | 1 | 0 | 1 |
| schema 유효 + 원천 라벨 일치 | 3 | 4 | 7 |

literal final 검사의 누락3건은 기존 Harmony 재평가에 이미 반영됐다.
이를 모델의 실행 오류와 섞지 않는다. 원문에서는 CWE-252 의미의 잘못된 회상,
analysis의 결론과 final assessment 불일치도 확인했다. source-label match가
곧 올바른 설명을 생성했다는 뜻은 아니다. v5 target은 판단 한 필드이고
선정 이유·추천 정답 및 지표는 없으므로, vLLM 성공의 목표와 다르다.

CPU tokenizer 검사에서 tools 인자를 주지 않은 기본 호출에도 현재 template가
functions 호출 채널 안내를 렌더링함을 재현했다. 함수 정의는 없는 상태다.
이 안내의 tool handoff 인과, 빈 analysis 학습과 실제 analysis 생성의 분포 차이,
양자화/엔진 차이 및100step 과적합은 미검증 가설로 남겼다.
이전 vLLM 사례의 checkpoint·요청·응답·옵션은 이번 분석에서 확보되지 않았고,
같은 조건의 vLLM 대조를 수행한 것은 아니다.

추가 근거는 Git 제외 경로
`outputs/cc-official-tutorial-step100-error-analysis-20261005-v1/`의
`evidence.json`, `tokenizer-audit.json`, 수집/CPU 검사 스크립트와 로그다.
30step97개·100step104개 원 manifest artifact hash를 재확인했고 모두 일치했다.
새 학습·모델 생성·서빙은 실행하지 않았고, 기존 조건·adapter·원 출력을 보존했다.
문서의 후속 실험표는 제안이며 실행 완료 결과로 표기하지 않는다.

### 2026-10-05: native-step100-forward-and-decision-token-audit

사용자의 원인 재검토 요청에 따라 실행 완료와 실제 학습 정합성을 구분했다.
원 30/100스텝 실험은 보존했으며 새 학습·backward·optimizer·자유 생성은 0회다.
자세한 방법·제한은 [서빙/학습 분석 11절](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md#11-2026-10-05-전체-입출력과-실제-forward-재점검)에 기록한다.

- train10,000/validation1,000의 canonical→decision 연결, train 사본, 실제 두 native
  Arrow cache의 input IDs·labels 모든 위치를 대조했다. 불일치0건, 유효 인덱스8,525건 일치.
- 기존40회 생성은 고유 validation2건이다. 전체 원문·입력·정답·final을 연결한
  `outputs/cc-official-tutorial-v5-input-output-audit-20261005-v1/review.html`을 만들었다.
- 100스텝 종료 hash→저장 파일→재로딩 LoRA3,264tensor 모두 일치하고 finite다.
- 4건×3모드 forward에서 직접 hidden state/LM head로 구한 shifted CE와 model loss가
  최대 약4.5e-8 차이로 일치했다. 과거 구환경의 수십 배 train/eval 차이는 이4건에서
  재현되지 않았다. 구환경 문제가 해결됐다는 소급 판정이나 전체 runtime 정상 판정은 아니다.

**진단 조건:** validation 파일 순서에서 라벨별 첫50건, 전체 렌더링≤1,024토큰,
정답 final 접두사를 이미 제공한 teacher-forced forward, 두 라벨 첫 token의 조건부
logit 비교, 동률→not_observed. 기존 bare-assistant generation table 및 test500과
분리한다. 미검수 원천 라벨이며 통계적 일반화나 자유 생성 성능을 주장하지 않는다.

| 실험 타입 | 모델 | 표본 | 평균 sequence loss | 정답 token 적중 | 조건부 두 라벨 일치 | 양성 재현율 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| native-step100-forward / final-prefix / decision-token-probe | base | 100 | 1.261358 | 601/800 | 47/100 | 7/50 |
| native-step100-forward / final-prefix / decision-token-probe | adapter100 | 100 | 0.089278 | 756/800 | 56/100 | 10/50 |

adapter confusion은 TP10/FN40/FP4/TN46이며 86건을not_observed로 선택했다.
판단 분기100token 이외700token은 전부 맞혔다. 그래서94.5% token 적중과0.089loss가
핵심 판단56%와 동시에 나타난다. base는 무제약 첫 판단 token이98건에서 두 라벨
밖이었으므로47%를 자유 생성 정확도로 해석하지 않는다. adapter는100건 모두
두 라벨 안에 있었고 조건부 선택과 같았다.

정답 이외의 고정 토큰은 완벽하고 두 라벨만0.5/0.5인 가상 기준의 sequence loss는
0.088019다. 계산상 참고값이며 실측 모델이 무작위라는 증명은 아니다. 낮은loss를
판단 학습 성공으로 간주할 수 없다는 해석상의 문제를 직접 수치화했다.

남은 원인 후보는 약400회 표본 제시/0.0469epoch의 학습량, 1,024상한으로 제외된
1,475건과 부분정답15건, 희소CWE(CWE252는 유효train 양성2건), empty-analysis
final-only 학습과 medium-analysis 자유 생성의 조건 차이다. 각각 사실은 확인했으나
오류에 대한 기여도는 통제 실험 전이다. 설정·데이터·생성 조건은 임의로 수정하지 않았다.

추가 미래token 치환 검사에서는 eval 경로의 앞선logit 차이가0이었고 train 경로에서
0.09375~0.140625 차이가 관측됐다. 전체prefix 추적의 최초 차이는 layer5 MLP
4.77e-7이며, 이후 MoE와 attention을 통해 전파됐다. 같은 입력 반복은 정확히 같았고
진단 예의 판단은 유지됐다. MoE 수치 민감도를 분리 검증할 과제로 남기며, 이를
attention mask 누출이나 품질 실패의 주원인으로 확정하지 않는다. 최초 eval+grad
진단은out=matmul의autograd 제약으로 실패했고, 원 학습 실패와 구분해 보존했다.

재현물: `outputs/cc-native-forward-diagnostic-20261005-v1/`의 스크립트·원 로그·
`summary.json`·`probe-inputs.json`·`probe-base.json`·`probe-adapter.json`·
`mode-matrix.json`·`causal-prefix-repeat.json`. 원 native 가상환경/RTX A6000/캐시
NF4 base/원100step adapter를 사용했다. 30step97개·100step104개 manifest artifact
hash가 모두 일치했고 test500은 사용하지 않았다. 별도 보고서11.6에 버전·경로·명령을 기록했다.

#### 2026-10-05: Astra 100스텝 원인 분석 재검토

이전 진단의 원본 JSON을 다른 스크립트로 재집계했다.
`outputs/astra-step100-report-review-20261005-v1/review.json`에 입력 ID와
원천 라벨, loss·토큰·판단 결과 검산을 기록했다. base47/100, adapter56/100,
adapter TP10/FN40/FP4/TN46 및756/800 token은 원자료와 일치한다.
train–validation의 동일 `(CWE, source_code)` 0건, 선정100건의 train 중복0건이다.
쌍별 개선15건·악화6건이며 탐색적 정확 검정 p≈0.0784다.
[분석 보고서 11.7절](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md#117-astra-원인-분석의-2차-확인)에
측정 사실과 아직 입증되지 않은 인과를 분리했다. 새 학습·GPU 추론·test500 사용은 없다.


### 2026-10-05: native-step100-max-new-tokens-130000-confusion-matrices

사용자가 생성 상한별 confusion matrix와13만token 조건 추가를 요청했다.
기존100step native 생성표5조건을 보존하고 `max_new_tokens=130000` 고정 조건을
동일 base/adapter·동일 frozen validation2건에 추가했다. 총4회 새 생성이며 새 학습은0회다.
기존 최대 문맥 조건은131072−입력으로 실제 상한130779/130837이었다.
따라서130000고정은 별도6번째 조건이다. 각 조건은 양성1건·음성1건으로,
앞선 teacher-forced validation100 진단과 다른 자유 생성 평가다. 원천 라벨은 미검수다.

입력IDs·native generation_config가 기존 실행과 정확히 같음을 검사했다.
sampling 기본값·medium reasoning·native EOS를 유지했고 외부timeout/forced EOS는 없다.
RNG를 조건별로 되감지 않았으므로 상한별 출력은 동일 생성문을 잘라 비교한 결과가 아니다.
새13만조건의 실제 생성량/시간은 base485/338token,83.56/57.28초;
adapter1351/366token,259.46/71.66초이며 모두 native EOS로 종료됐다.
13만token 전부를 생성한 실행은 아니다. model runtime 문맥은131072다.

아래는 **final JSON의 assessment 값만 집계한 판단 행렬**이다. 추가 필드가 있어도
판단값은 읽으며, JSON schema 위반은 별도 열에 기록한다. final 없음·도구 요청·
파싱 실패를 not_observed로 변환하지 않고 판단 불가로 남긴다.

| 생성 상한 | TP | FN | FP | TN | uncertain | final 판단 불가 | 읽을 수 있는 판단의 형식 위반 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| 512 | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| 2048 | 0 | 1 | 0 | 0 | 0 | 1 | 0 |
| 65536 | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| 131072 − 입력 (130779/130837) | 1 | 0 | 0 | 1 | 0 | 0 | 1 |
| 130000 | 0 | 1 | 0 | 1 | 0 | 0 | 1 |

최대 문맥의 음성 응답은not_observed를 맞혔지만 추가 필드로 schema에 실패했다.
130000의 양성 응답은not_observed로 틀렸고 potential_vulnerabilities 추가 필드도
포함했다. 엄격한 schema 기준에서는 이 둘을 invalid로 분류하므로 각각의 행렬도
함께 저장했다. 세부 base/adapter2×4행렬과 두 채점 기준을 선택하는 로컬 HTML은
`outputs/cc-step100-max-new-tokens-130000-confusion-matrix-20261005-v1/confusion-matrices.html`이다.
동일 폴더의JSON/Markdown·generate.py·aggregate.py·verify.py·request.json·
packages.json·runtime정보·원 출력·로그가 재현 자료다.

재현 명령은 해당 새 실험 폴더에서 native 가상환경의 `generate.py --model base`,
`generate.py --model adapter`와 scorer 가상환경의 `aggregate.py`, Python3의
`verify.py`다. native환경은 기존tutorial venv이고 scorer는 기존cc-official-tutorial-v5-score venv다.
Unsloth2026.9.14/zoo2026.9.9/Transformers4.56.2/torch2.14.1+cu130/TRL0.22.2/
PEFT0.21.2/bitsandbytes0.50.2/Python3.12.13, RTX A6000을 사용했다.
원30step97개·100step104개 manifest artifact hash, 원adapter hash가 그대로임을 확인했다.
각 행렬의총수2·새조건4회완료·입력과native기본값일치 검증을 통과했다.
HTML의 브라우저 자동 렌더링 검사는 하지 않았으며test500은 사용하지 않았다.

### 2026-10-05: native-step100-validation100-token-caps — 평가 표본 수 정정

사용자가 각 생성 조건에 100건이 있어야 한다고 지적했다. 직전 생성표는 기존
설정의 `sample_ids` 2건을 그대로 사용한 스모크 평가였다. 별도의 100건 판단
진단은 teacher forcing이며, 생성 길이별 100건 평가를 수행한 것이 아니었다.
기존 2건 기록은 그대로 보존하고 아래 새 실행에서 평가 범위를 정정한다.

| 항목 | 새 실행 조건 |
| --- | --- |
| 학습 | 기존 공식 tutorial 데이터 교체·100step adapter 사용, 추가 학습 0회 |
| 입력 | 같은 validation 100건, 원천 라벨 present50 / not_observed50 |
| 선정 | 앞선 probe-inputs.json의 ID만 재사용; 원천 validation 순서에서 전체 학습 렌더링 1024 이하인 라벨별 첫50건 |
| 생성 입력 | 원 system/user만 사용; 정답·teacher-forced tokens·final prefill 제외 |
| 생성 상한 | 128 / 512 / 2048 / 65536 / 130000 / 131072−입력 |
| 모델 | 같은 base와 기존100step adapter, 각600회·총1200회 |
| 기본값 | native sampling·medium reasoning·native EOS 유지, 별도시간제한 없음 |
| 채점 | 공식 Harmony parser; final assessment 행렬 및 엄격한 schema 행렬 병기 |
| 집계 | 각 조건100건, uncertain/invalid/pending 분리; 미완료를 invalid로 세지 않음 |

선정100건은 짧은 입력에 한정된 균형 진단 표본이다. validation1000 전체나
held-out test500 성능으로 일반화하지 않는다. 입력232–980tokens로 고정130000
조건도 전체문맥131072 안에 들어간다. train과 선정 입력의 ID 및 user내용 중복은0이다.
test500은 읽지 않는다. 원천 라벨·CWE는 미검수 상태다.

설정: `configs/cc_native_step100_validation100_token_caps_v1.json`.
실행기: `scripts/run_cc_native_validation100.py`.
출력: `outputs/cc-native-step100-validation100-token-caps-20261005-v1/`.
`prepared.json`에 데이터·선정ID·입력·정답·adapter hash와 계획1200회를 기록했다.
각 출력은 atomic JSON으로 저장하며 `progress.json`과 `confusion-matrices.json/.md`로
진행률을 확인한다. 완료된 출력을 덮어쓰지 않고 미완료분만 재개한다.
Sampling RNG는 조건마다 초기화하지 않는다. 재개 프로세스는 새 native RNG를
사용하며 각 출력의 run_id로 구분한다. 따라서 상한별 결과는 같은 생성열의 접두사가 아니다.

재현 명령:

```bash
experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python scripts/run_cc_native_validation100.py prepare
experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python scripts/run_cc_native_validation100.py run
experiments/cc-official-tutorial-v5-score/.venv/bin/python scripts/run_cc_native_validation100.py score
```

prepare는 최초1회만 실행하며 재시작은 run만 실행한다. 기존 native/scorer환경과
RTX A6000을 사용한다. 라이브러리 버전은 직전130000실험과 동일하며
packages.json 및 model별 runtime JSON으로 기록한다. 자동 채점은 최초1건,
이후10건마다 및 전체 완료 시 갱신한다. **1200회 완료 전에는 100건 결과로 보고하지 않는다.**

#### 2026-10-05: 실행 중인 평가의 W&B 연결

사용자가 W&B 미전송을 지적하여 저장된 평가 결과의 후등록과 이후 자동 기록을
추가했다. 생성 프로세스·학습·입력·예산·기본값은 변경하지 않고 별도 CPU sidecar가
`confusion-matrices.json`을 읽는다. W&B project/group은 기존 `aegislm` / `source-v2`,
job_type은 evaluation이다. 이번 run은 학습loss를 기록한 run이 아니다.
모델/조건별 완료·남은 수, semantic/strict 판단행렬을 기록하며 조건100건 완료 시
안전한 사례 table과 두 기준의 confusion chart를 추가한다. 미완료를 invalid로 세지 않는다.
로컬 raw 코드·생성 원문·token IDs·자유문 오류는 전송하지 않는다.

명령: `uv run python scripts/track_cc_native_validation100.py --wandb`.
기존 .env 인증을 사용하고 tracking lock/receipt를 유지한다.
W&B run ID/URL은 출력 폴더의 `wandb-link.json`, 전송 상태는 `wandb-progress.json`,
SDK로그는 `wandb-sidecar.log`, lifecycle영수증은 `evaluation.wandb.json`에 남긴다.
전송 불확실 상태의 재실행은 원격 확인 후 명시적 `--wandb-reconcile`을 요구한다.
원본 실험 artifact는 Git 제외 경로에 보존한다. 세부 전송 필드는 EVALUATION_PLAN의
native tutorial validation100 generation tracking 절에 정의한다.

실제 online run은
[cc-native-step100-validation100-token-caps](https://wandb.ai/erad3254-looking-for-a-job/aegislm/runs/source-v2-evaluation-9d30dc7ec1290bd4)다.
2026-10-05T13:16:19Z에 sidecar를 시작하여 당시 채점 완료된170회를 후등록했고,
adapter128조건100건의 사례 table·semantic/strict confusion chart를 추가했다.
이후 채점 snapshot 변경을10초마다 확인하여 새 기록을 전송한다. 채점 자체는
기존 생성기의10건마다 갱신 조건을 따른다. 학습 완료시점의 W&B run으로
위장하지 않으며 `recording_mode=saved-evaluation-backfill-and-live-snapshots`를 기록했다.
추가검사: pytest544개 통과, 변경파일ruff/mypy 통과. 생성 PID84337은 유지했고
별도 CPU tracking PID108432를 사용했다. raw 코드·로그·출력의 원격 업로드는 없다.

#### 2026-10-06: native-validation100 OOM 조사

원실행은2026-10-06 00:05:39 KST에 adapter65536 조건의 세 번째 입력에서
CUDA OOM으로 중단됐다. 128/512/2048각100건과655362건,전체302/1200건 완료다.
base와130000·최대문맥 조건은 미실행이다. 새 프로세스에서 같은825token 입력과
65536예산으로 동일OOM을 재현했고 실제StaticCache66360칸을 관찰했다.
prefill의eager attention FP32 임시배열 추정13.0529GiB가 요청13.05GiB와 일치한다.
실제6만token 생성누적, 학습실패 또는타프로세스경합으로 설명할 필요가 없다.

세부는 [원인 보고서11.10절](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md#1110-2026-10-06-validation100-native-생성-oom의-직접-원인)에
기록한다. GPU진단은같은native환경·RTX A6000·원adapter·원frozen token을 쓰며
새학습0회, 생성조건변경0회다. 실패시progress.status가running으로 남는 별도버그를
수정하고 현재상태는failed로 정정했다. OOM입력은완료/invalid로 변환하지 않는다.
마지막10건단위 채점에는300건만 반영되어 원snapshot을 보존한 뒤 실제302건으로
동일Harmony parser를 사용해 로컬평가를 갱신했다. 원출력과error는 보존한다.
W&B의기존run에는history를재생하지 않고302건부분평가·OOM진단 scalar를
summary정정으로 기록한다. sidecar는 generation-failed 상태로 종료됐다.
실험 전체를 완료했다는 의미가 아니다. 상한/시간/EOS를 임의로 줄이지 않았고
재실행 전에는 chunked prefill 등 별도 추론조건을 검증해야 한다.

#### 2026-10-06: fresh-process-per-model-budget-v2 — 생성 상한별 초기화

사용자 확정 조건: 독립변수인 최대 생성 길이가 바뀌면 모델을 처음 GPU에 올리는
상태로 돌아간다. 기존 v1은 모델당 한 번 로드한 뒤 상한을 연속 순회했으므로
이 조건을 충족하지 못했다. 원본 302건은 보존하고 v2와 합산하지 않는다.
코드 감사·검증·제한은 [오류 분석 11.13절](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md#1113-2026-10-06-생성-상한-변경-시-모델-재로딩-여부-감사와-수정)에 기록한다.

| 조건 | 고정하거나 변경하는 값 |
| --- | --- |
| 독립변수 | max_new_tokens 128 / 512 / 2048 / 65536 / 130000 / context-minus-input |
| 초기화 경계 | 모델 × 생성 상한마다 새 spawn 프로세스, 이전 프로세스 종료 후 시작 |
| 조건 내부 | 같은 validation 100건(50:50), 순서 고정, 모델을 유지하며 순차 평가 |
| 학습 산출물 | 기존 공식 recipe의 100-step adapter, 새 학습 없음 |
| 생성 고정값 | native sampling/EOS, runtime context 131072, timeout 없음, 추가 generate kwargs 없음 |
| 실패 / 재개 | 실패 시 순회 중단, 완료 조건만 skip 가능; 부분 조건 이어붙이기는 거부 |
| 감사 당시 상태 | 입력 준비 및 CPU 검증 완료; 이후 GPU 결과는 아래 실행 결과 참조 |

설정: `configs/cc_native_step100_validation100_fresh_process_v2.json`.
출력: `outputs/cc-native-step100-validation100-fresh-process-20261006-v2/`.
기존과 다른 설정 키는 experiment_id/output_dir/execution_protocol뿐이며
동결 입력과 정답·adapter 등 7개 hash는 v1과 같다. 입력 길이 232–980, 계획 1200호출.

실행기는 `scripts/run_cc_native_validation100.py`의 prepare/run/score로 구분한다.
현재 v2 prepare는 완료됐다. 향후 GPU 실행 명령은 아래와 같으며 이번 감사에서는
실행하지 않았다. 원래 native 환경을 사용하고 scorer는 기존 Harmony 전용 환경이다.

```bash
experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python scripts/run_cc_native_validation100.py run --config configs/cc_native_step100_validation100_fresh_process_v2.json
```

W&B sidecar도 동일 v2 config를 지정해야 하며 새 실험 identity로 scalar/표만 기록한다.
runner와 tracker 기본 config는 v2로 일치시켰다. 기존 v1 재채점에는 v1 config를 명시한다.
프로세스 종료는 디스크 캐시나 다른 GPU 사용자를 초기화하지 않으며, 공식 sampling의
seed 정책도 그대로다. 조건 내부 메모리 누적과 seed 통제는 별도 연구 항목이다.
신규 조건별 PID/종료코드/로드 메모리는 conditions 아래에 보존한다.
이 수정으로 기존 단일 요청 OOM이 해결됐다고 주장하지 않는다.

#### 2026-10-06 작업 인계: Astra 수정본 재검토

현재 저장소의 v2 코드는 조건별 프로세스 분리를 구현했고 입력 준비만 완료했다.
사용자가 Astra 수정본으로 지정한 실행 코드와 11.13절 보고서를 대조했다.
[11.14절 인계 기록](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md#1114-2026-10-06-실행-코드-재검토와-작업-세션-인계)에 결과와 한계를 남겼다.
현재 v2 평가 0/1200, GPU 재로딩 실측 및 65536 이상의 OOM 해결은 미검증이다.
이번 재검토에서는 생성 실패 직후 마지막 부분 결과도 채점하도록 보완했다.

#### 2026-10-06: v2 GPU 실행 결과 — 초기화 확인, 302/1200 후 OOM

사용자가 지정한 `gpt-6-luna`/medium tester 1명에게 verify 실행을 위임했다.
실험 후보는 `df6dd7783d05573961c5ad1d09e0e8840fcc9eb0`, runner SHA-256은
`717502ed93ba472936939740d51a91484cc68559eabfe265507184fb3bb149ea`다.
입력·prompt·gold·adapter·train·validation·선정자료의 7개 hash를 확인했다.
메인은 종료 후 원 오류, receipt, 집계와 GPU 프로세스 부재를 대조했다.

RTX A6000 1장, 기존 native 환경에서 위 `run --config` 명령을 실행했다.
환경 기록(`preparation-environment.json`)은 Python 3.12.13, torch 2.14.1,
transformers 4.56.2, unsloth 2026.9.14, unsloth-zoo 2026.9.9,
trl 0.22.2, peft 0.21.2, bitsandbytes 0.50.2다.
데이터는 `data/processed/cc-source-candidates-20260928-v5/decision-candidates/`
아래 train/validation이며, 평가에는 동결된 validation 100건을 사용했다.
학습·test500 사용·생성 설정 변경은 없었다. 원천 라벨은 미검수 상태다.

실행 구간은 2026-10-06 14:48:58–17:47:06 KST다. 조건별 receipt의 시각은 UTC다.

| adapter 상한 | worker PID | 시작 UTC | 종료 UTC | exitcode | 생성 완료 |
| --- | ---: | --- | --- | ---: | ---: |
| 128 | 484755 | 05:48:58.330786 | 06:06:43.497836 | 0 | 100 |
| 512 | 494492 | 06:06:43.505158 | 07:05:48.766071 | 0 | 100 |
| 2048 | 550012 | 07:05:48.772973 | 08:42:35.038615 | 0 | 100 |
| 65536 | 642121 | 08:42:35.045667 | 08:47:05.855018 | 1 | 2 |

네 프로세스 모두 로드 전 PyTorch allocated/reserved는 0이었다.
로드 후 allocated 12,909,326,336 B, reserved 12,947,816,448 B로 동일했다.
이전 worker 종료 후 다음 worker가 시작했으며 실행 구간이 겹치지 않는다.
이는 실행된 네 조건의 모델 재로딩 증거이며 장치 전체 VRAM이 0이라는 뜻은 아니다.

| adapter 상한 | TP | FN | FP | TN | uncertain | invalid | pending |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 0 | 1 | 0 | 0 | 0 | 99 | 0 |
| 512 | 4 | 10 | 2 | 18 | 0 | 66 | 0 |
| 2048 | 19 | 21 | 11 | 33 | 0 | 16 | 0 |
| 65536 | 2 | 0 | 0 | 0 | 0 | 0 | 98 |

strict/semantic 집계는 동일하다. 2048조건의 원천 라벨 일치는 52/100건이다.
65536의 2건은 모두 양성이며 해당 조건의 전체 성능을 나타내지 않는다.
adapter/130000·context-minus-input 및 base의 6조건은 각각 100건 모두 pending이다.
전체는 완료 302건 + OOM 1건 + 미시도 897건이다. OOM은 pending에 포함되며
FN/invalid로 채점하지 않는다. `confusion-matrices.json`의 complete는 false다.

65536조건의 세 번째 입력 `cc-8745b2417b18ebf598e0a8c4`에서
`inplace_eager_attention_forward`의 FP32 softmax가 13.05GiB를 요청했으나
여유는 13.01GiB였다. GPU 총 47.39GiB, 해당 프로세스 사용 34.26GiB로 기록됐다.
기존 v1과 같은 입력·할당 실패가 조건별 새 프로세스에서도 발생했다.
초기화 요구 충족과 OOM 해결은 별개이며, 첫 오류에서 전체 순회를 중단했다.
자동 재시도·조건 건너뛰기·부분 조건 이어붙이기는 하지 않았다.

산출물은 `outputs/cc-native-step100-validation100-fresh-process-20261006-v2/`에
보존했다. `conditions/*-runtime.json`과 receipt, `adapter-65536-error.json`,
`progress.json`, `error.json`, raw 302건, `confusion-matrices.json/.md`,
`gpu-run.stdout.log`, `tracker.stdout.log`, `score-final-after-failure.stdout.log`가 근거다.
최종 scorer는 exit 0이며, 마지막 2건도 집계됐다. v1의 302건과 합산하지 않는다.

[W&B v2 evaluation run](https://wandb.ai/erad3254-looking-for-a-job/aegislm/runs/source-v2-evaluation-b7551d344cea1182)은
로컬 로그에 302/1200 업로드와 Sync 완료, tracker exit 0이 기록됐다.
`evaluation.wandb.json`의 complete는 기록 lifecycle 완료이며,
`wandb-progress.json`은 generation-failed다. 전체 평가 성공을 뜻하지 않는다.
실행 중 사용자가 crashed→running 표시 복구를 보고했지만 그 원인은 확정하지
않았고, 원격 최종 state는 별도로 재조회하지 않았다.

후속 GPU 실험은 미실행이다. 실패 825token 및 최장 980token 입력에 대한
prefill 메모리 분리 검증 등은 별도 조건으로 계획해야 한다.

#### 2026-10-06: base 단독 평가 착수

사용자가 adapter의 OOM 이후 같은 조건으로 base만 우선 실행하도록 지시했다.
설정은 `configs/cc_native_base_validation100_fresh_process_v1.json`, 출력은
`outputs/cc-native-base-validation100-fresh-process-20261006-v1/`이다.
v2와 달라지는 설정 값은 experiment_id, output_dir, models 세 개뿐이다.
같은 100건, 여섯 상한과 순서, native sampling/EOS, timeout 없음,
모델×상한별 새 프로세스, 첫 실행 오류 시 중단 규칙을 유지한다.
계획은 600회이며 새 prepare에서 생성한 동결 입력과 7개 hash를 v2와 대조한다.
기존 adapter 결과를 덮어쓰거나 부분 조건에 이어붙이지 않는다.

동일한 Luna tester에게 verify 실행을 위임한다. 생성기 코드는 변경하지 않고,
W&B tracker가 명시된 모델 집합에 따라 600/1200회를 집계하도록 보완했다.
누락·중복·다른 모델 조건은 계속 거부한다. 아래 명령은 기존 native 환경에서
prepare, 별도 Harmony 환경에서 score, CPU tracker 초기 업로드 확인 후 실행한다.

```bash
experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python scripts/run_cc_native_validation100.py run --config configs/cc_native_base_validation100_fresh_process_v1.json
```

W&B tracker에도 위 base 전용 config와 `--wandb`를 명시한다. 결과와 성공 여부는
실제 실행 산출물로 확인하며, 65,536 이상의 메모리 부족 해결을 가정하지 않는다.

#### 2026-10-07: Unsloth·Axolotl·LLaMA-Factory 비교와 선택 기준

사용자가 공유한 B200 계획 13·14절과 공식 문서를 기준으로 학습 프레임워크의
역할과 비교 기준을 정리했다. 이번 작업은 문서화이며 프레임워크 설치·전환,
새 학습·평가 실행을 포함하지 않는다. B200의 실행 상태는 사용자 제공 기록이며
이 A6000 세션에서 원격 GPU나 실행 산출물을 직접 검증한 결과가 아니다.

Unsloth는 지원 모델의 커널·LoRA 연산·중간값 저장과 재계산을 최적화하므로
메모리가 제한된 단일 GPU에서 유력한 선택이다. FlashAttention 사용 여부만으로
전체 학습 속도나 메모리 사용량을 설명할 수 없다. 그러나 단일 GPU에서 항상
가장 빠르다는 뜻은 아니며, 공식 벤치마크의 개선 배율을 현재 GPT-OSS 설정에
그대로 적용하지 않는다. 로컬에서 확인한 것은 기존 A6000 100-step 학습의
완료이며, 세 프레임워크의 동일조건 성능 비교는 아직 없다.

| 비교 | Unsloth | Axolotl | LLaMA-Factory |
| --- | --- | --- | --- |
| 중심 강점 | 지원 모델의 속도·메모리 최적화 | 설정 파일 기반 학습·분산 실험 구성 | 다양한 모델·학습법을 공통 작업 흐름으로 제공 |
| 사용 방식 | Python 코드·튜토리얼, UI도 제공 | YAML·CLI 중심 | WebUI·CLI·설정 파일 |
| 최적화 접근 | 모델별 커널·패치, LoRA 연산, checkpointing | attention backend·packing·분산 전략 조합 | 여러 학습법과 최적화 backend 통합 |
| 다중 GPU | DDP 지원, 조합별 검증 필요 | DDP·DeepSpeed·FSDP2 | DDP·DeepSpeed·FSDP 계열 |
| 현재 비교의 핵심 | 모델별 패치와 MoE·DDP의 상호작용 | 기존 양자화·expert LoRA·마스킹 재현 | 기존 양자화·expert LoRA·마스킹 재현 |

이는 설계와 사용 방식의 비교이며 성능 순위가 아니다. LLaMA-Factory의
사용량이 가장 많다는 순위도 이 조사로 확정하지 않는다. 또한 LLaMA-Factory는
Unsloth 통합을 제공하므로 프레임워크 이름뿐 아니라 실제 backend를 기록해야
한다. 이 통합이 현재 GPT-OSS·NF4·expert LoRA 조합까지 지원하는지는 미검증이다.

근거: [Unsloth 소개](https://unsloth.ai/docs/get-started),
[checkpointing 최적화](https://unsloth.ai/blog/long-context),
[Unsloth DDP](https://unsloth.ai/docs/basics/multi-gpu-training-with-unsloth/ddp),
[Axolotl 다중 GPU](https://docs.axolotl.ai/docs/multi-gpu.html),
[LLaMA-Factory 저장소](https://github.com/hiyouga/LlamaFactory),
[LLaMA-Factory 분산 학습](https://llamafactory.readthedocs.io/en/latest/advanced/distributed.html).
공식 지원 범위 확인일은2026-10-07이며 실제 실행에는 고정 버전의 호환성 검증이 필요하다.

**학습과 생성 평가의 구분:** Axolotl은 학습 프레임워크, FlashAttention은
학습과 추론에 사용할 수 있는 attention 계산 최적화다. vLLM은 추론·서빙
엔진이며 PagedAttention은 KV cache를 블록으로 관리하고 읽는 기술이다.
일반적인 SFT의 역전파 메모리는 추론용 KV cache 설정만으로 해결되지 않는다.
Paged optimizer도 optimizer 상태를 관리하는 별도 기술이다.
현재 A6000의 문제는 완료된100-step 학습 이후 생성 평가에서 발생한 OOM이며,
동적 cache 진단 결과는
[오류 분석 문서 11.18절](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md#1118-2026-10-07-a6000-메모리-절감-후보-진단--완료)에 기록했다.
이는 학습 프레임워크 전환의 성능 근거로 사용하지 않는다.
기술 근거: [Axolotl attention](https://docs.axolotl.ai/docs/attention.html),
[Transformers 캐시](https://huggingface.co/docs/transformers/v4.56.2/en/cache_explanation),
[PagedAttention](https://vllm.ai/blog/2023-06-20-vllm),
[QLoRA와 paged optimizer](https://arxiv.org/abs/2305.14314).

**사용자 제공 B200 계획의 해석:** B200 두 장의 DDP에서 GPU당batch1,
accumulation2로 전체batch4·100 optimizer step을 유지한다는 계획이다.
v2의 sparse MoE unused-gradient 오류 이후, 설치된 Zoo의 reentrant
checkpointing과 DDP 조합을 피하려고 v3에서는 activation checkpointing을
끄고 `find_unused_parameters=true`를 사용한다고 보고됐다.
[PyTorch DDP 문서](https://docs.pytorch.org/docs/2.14/generated/torch.nn.parallel.DistributedDataParallel.html)의
reentrant checkpointing 제약과 부합하는 대응이지만, 여기서 v3의 완료를
확정하지 않는다. 해당 환경의 `b200-verification.json`과 두 rank 기록으로
판정해야 한다. Unsloth 전체가 다중 GPU에 부적합하다는 증거도 아니다.

checkpointing 해제는 activation 저장량과 재계산량을 바꾼다. 따라서
A6000 대비 속도 차이를 B200 하드웨어 효과만으로 해석하지 않는다.
두 GPU DDP는 모델 복제와 gradient 동기화 방식이며 두 장의 VRAM을 하나의
모델 공간으로 합치지 않는다. 전체batch와step 수가 같아도 sampler·loss
집계·커널 등의 차이 때문에 같은 loss나 adapter SHA를 요구하지 않는다.

**현재 선택 의견과 후속 비교 조건:** A6000에서는 실행 근거가 있는 Unsloth를
기준선으로 유지하고, B200의 기존 두 GPU 재현 확인과 프레임워크 전환 결정을
분리한다. 마스킹·expert LoRA·분산 설정을 코드와 설정 파일로 관리하는 현재
요구에는 Axolotl을 우선 비교 후보로 본다. 팀의 공통 UI와 여러 모델·학습법
운영이 우선이면 LLaMA-Factory를 비교한다. 이는 선택 의견이며 전환 승인이나
성능 우위의 확정이 아니다.

후속 비교에서는 별도 환경·고정 commit/lock·새 실험명을 사용하고 다음을 대조한다.

- 동일 동결 입력의 `input_ids`·`labels`, 날짜·길이·마스킹·제외 기록.
- 모델 revision, NF4/double-quant/BF16 compute, LoRA 대상 이름·개수.
- 전체batch4·100-step, optimizer·scheduler·seed와 checkpointing 전략.
- 동일 평가 입력·scorer·명시된 생성 backend로 측정한 품질.
- 실제 처리 token 기준 학습tokens/s, 최대VRAM, 준비·컴파일 시간,
  실패와 디버깅 비용. 입력 token 처리량과 loss 대상 token 수는 구분한다.

지원상 이유로 양자화·expert 대상·마스킹 등을 바꿔야 하면 변경 조건을 명시하고
프레임워크 효과만으로 해석하지 않는다. 기능의 문서상 지원과 현재 환경의
실측 호환성은 끝까지 구분한다.

#### 2026-10-08: A6000 동적 캐시 validation100 — 실험 전 준비 완료

사용자가 실험 표를 기록하고 GPU 실험 전 단계까지 준비한 뒤 커밋·푸시할
변경 묶음을 점검하도록 요청했다. 이번 단계에서 GPU 학습·생성 및 새로운
온라인 W&B run은 시작하지 않았다. B200의 두 GPU 학습과 별개로 진행한다.

**질문:** 기존 native StaticCache에서65536상한의 세 번째 입력에 발생한
prefill OOM을 DynamicCache로 피하면서, 같은100건을 각 생성 상한에서
완료할 수 있는가? 완료율·생성량·종료 이유·JSON/schema 유효성·strict/semantic
confusion matrix를 함께 관측한다. 길게 생성할수록 좋아진다고 가정하지 않는다.

| 단계 | cache | 모델 | 범위 | 관측·현재 상태 |
| --- | --- | --- | --- | --- |
| 기존 v2 평가 | native StaticCache | adapter | 100건 × 6상한 | 302/1200 전체 계획 중 adapter302건 후 OOM; base 미실행 |
| 기존 base 단독 평가 | native StaticCache | base | 100건 × 6상한 | 302/600 후 같은 입력·softmax OOM |
| 2026-10-07 초기 진단 | native/chunk128/dynamic | base·adapter | 2token 진단6조건 | 5조건 완료, chunk128 shape 오류1조건 |
| 2026-10-07 EOS 진단 | dynamic | base·adapter | 단일 입력3조건 | 515·553·1024token 후 EOS; 전체100건·실제13만token은 미검증 |
| 새 base 평가 | dynamic | base | 100건 × 6상한 | CPU 준비 완료, 생성0/600 |
| 새 adapter 평가 | dynamic | 기존100-step adapter | 100건 × 6상한 | CPU 준비 완료, 생성0/600; base 결과 검토 뒤 별도 착수 |

초기·EOS 진단의 모든9조건 실측 표와 실패 근거는
[오류 분석 11.18절](GPT_OSS_SERVING_TRAINING_ERROR_ANALYSIS.md#1118-2026-10-07-a6000-메모리-절감-후보-진단--완료)에 있다.
새 실험은 전체100건의 동일한 양성50·음성50, 미검수 원천 라벨을 사용한다.

| 생성 상한 | base 계획·완료 | adapter 계획·완료 | 현재 단계 |
| --- | --- | --- | --- |
| 128 | 100 / 0 | 100 / 0 | 준비 |
| 512 | 100 / 0 | 100 / 0 | 준비 |
| 2048 | 100 / 0 | 100 / 0 | 준비 |
| 65536 | 100 / 0 | 100 / 0 | 준비 |
| 130000 | 100 / 0 | 100 / 0 | 준비 |
| context-minus-input | 100 / 0 | 100 / 0 | 준비 |

빈 결과표의0은 아직 관측이 없다는 뜻이며 모든 조건은 pending100이다.
OOM·미시도는 invalid나FN으로 채점하지 않는다. 첫 오류에서 순회를 멈추고
부분 생성 결과까지 채점하며, 자동 재시도·부분 조건 이어붙이기는 하지 않는다.

**고정 조건:** RTX A6000 한 장, runtime context131072, 기존 native 환경과
model revision `093fba6992ef5a7152481afec0bdfca1ac486998`, 4bit 양자화,
동결 날짜2026-10-04, native sampling/EOS, 외부timeout 없음, 새 학습0step.
모델×상한마다 새 프로세스에서 모델을 로딩하고 종료를 기다린 후 다음 조건으로
넘어간다. GPU 작업은 한 실행기만 소유한다. adapter는
`outputs/cc-official-tutorial-v5-max-steps-100-20261004-v1/gpt_oss_lora/`를 사용한다.
패키지 정본은 `configs/environments/cc-native-step100/pyproject.toml`과
`uv.lock`이며 이번 작업에서 패키지를 변경하지 않았다.

**변경 파일과 동작:**

- `scripts/run_cc_native_validation100.py`: 기존 기본값native를 유지하면서
  명시적 `cache_policy: dynamic`을 추가했다. 복사한 generation config와
  `cache_implementation="dynamic"`을 함께 전달한다. 매 generate 호출의 첫
  self-attention 모듈에서 prefill·decode cache class를 검사하고 DynamicCache가
  아니거나 관측되지 않으면 실패한다. raw 결과에 cache 관측과 생성 구간
  peak allocated/reserved를 기록한다. 동적 실험 채점은 이 관측 증거가 없는
  출력을 거부한다. `verify`는 모델을 로딩하지 않고 동결 입력을 검증한다.
- `scripts/track_cc_native_validation100.py`: 캐시 방식과 실행기SHA를 새 W&B
  run identity/config에 반영한다. 기존native run identity는 유지한다.
  기존의 원문·token ID 비전송 규칙과600회 집계를 유지한다. 메모리 세부값은
  로컬 raw 기록에 남기며 이번 변경으로 원격 전송 항목을 추가하지 않았다.
- `configs/cc_dynamic_base_validation100_v1.json`,
  `configs/cc_dynamic_adapter_validation100_v1.json`: 출력과W&B run을 분리한
  각600회 설정이다. 기존native 설정이나B200 레시피를 수정하지 않는다.
- `tests/test_cc_native_validation100.py`, `tests/test_cc_native_wandb.py`:
  wrapper의 config 덮어쓰기, 실제 cache 불일치·관측 누락, hook 정리,
  비교 입력·실행기 변경, 잘못된 출력 채점, 추적 identity·원문 제외를 검증한다.

**실제로 완료한 CPU 준비:** 두 설정 모두 prepare→verify→score를 수행했다.
train·validation·selection·frozen input·prompt·gold·adapter의7개SHA를 기존
`outputs/cc-native-base-validation100-fresh-process-20261006-v1/`과 대조했다.
두 설정 모두 입력232–980token, ID·user content train overlap0이다.
실행기SHA-256은
`c2597d7f1e09aa0f44e32593e3b0a899323b0971ef3c5edc4cf116e4cb28b0e7`이다.
실행기 변경 후에는 기존 준비를 수정하지 않고 새 실험명으로 prepare한다.

아래는 CPU 준비 명령의 base 예시다. adapter는 config 파일명을
`cc_dynamic_adapter_validation100_v1.json`으로 바꾼다. 현재 로컬에서는 이미
완료했으므로 prepare를 다시 실행하지 않는다. Git clone만으로는 Git 제외
동결 자료·모델·기존adapter가 생기지 않으며 위 reference 경로들이 필요하다.

```bash
experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python scripts/run_cc_native_validation100.py prepare --config configs/cc_dynamic_base_validation100_v1.json
experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python scripts/run_cc_native_validation100.py verify --config configs/cc_dynamic_base_validation100_v1.json
experiments/cc-official-tutorial-v5-score/.venv/bin/python scripts/run_cc_native_validation100.py score --config configs/cc_dynamic_base_validation100_v1.json
```

산출물은 `outputs/cc-dynamic-{base,adapter}-validation100-20261008-v1/`의
`prepared.json`, `preflight.json`, `confusion-matrices.json/.md`다.
raw 결과는0건이고 worker receipt도 없다. W&B 전송용 config와 빈 결과표는
로컬에서 validation을 통과했지만 새로운 온라인 연결은 아직 검증하지 않았다.
실험 시작 시 아래tracker를 별도 터미널에서 먼저 실행하고 `wandb-link.json`과
`wandb-progress.json`의 online·0/600을 확인한 뒤 base run을 시작한다.
다음 두 명령은 이번 준비 단계에서는 실행하지 않았다.

```bash
.venv/bin/python scripts/track_cc_native_validation100.py --config configs/cc_dynamic_base_validation100_v1.json --wandb
experiments/unsloth-official-tutorial-generation-64-20261004-v1/.venv/bin/python scripts/run_cc_native_validation100.py run --config configs/cc_dynamic_base_validation100_v1.json
```

단일 입력 진단과 새 정식 실행기는 구분한다. 이전 진단은 GPU에서 검증했지만
이번 통합 실행기의 실제 GPU 동작과 전체100건 완주는 아직 미검증이다.

최종 사전 검증: `uv run pytest tests/` 586건 통과,
`uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy aegislm/ tests/`, `git diff --check` 통과.
준비 브랜치는 `experiment/a6000-dynamic-cache`이며 이 기록 시점에는
커밋·푸시 전이다. 동결 데이터·adapter·generated artifact는 Git에서 제외한다.

#### 2026-10-08: 동적 캐시 평가 착수 승인과 실행 인계

준비 코드는 `b53a84f`로 `experiment/a6000-dynamic-cache`에 커밋·푸시했다.
사용자가 위 표대로 실행하고 단일 `gpt-6-luna` tester에게 GPU 작업을 맡기도록
승인했다. 담당은 `/root/dynamic_cache_tester`, 모드는 verify다. root는 반복
실행·CPU 채점·로그와 기록 작성을 승인하며, 패키지 설치·환경·드라이버·시스템
설정 변경은 사용자 확인을 받는다. 도구의 시스템 권한 승인을 root가 대신할
수 있다는 의미는 아니다. 두 output의 `execution-authorization.json`에
허용 범위와 base→adapter 전환 기준을 기록했다.

base600 완료,6조건 정상 종료와 순차 프로세스·초기 메모리0, 실제DynamicCache,
adapter hash 불변, 최종 채점·W&B 기록 완료와GPU worker 종료를 확인하면
같은 설정의 adapter600 실행은 추가 허락 없이 진행하도록 승인했다.
invalid/uncertain 예측은 관측할 평가 결과이며 실행 오류와 구분한다.
실행 오류·무결성 검사 실패·새 환경 변경 필요 시에는 중단하고 보고한다.

첫 base tracker는 GPU 실행 전 `ServicePollForTokenError`로 종료했다.
로그에 `Operation not permitted`가 있어 sandbox 서비스 시작 제한으로
판단했다. root가 정상 권한의 W&B API로 동일run ID
`source-v2-evaluation-4afe23e80c9d977c`를 조회해 원격run 부재를 확인했다.
초기receipt는 `logging_ambiguous`로 보존하고, root는 같은ID의
`--wandb-reconcile retry-logging` 1회를 정식 권한 요청 경로로 승인했다.
이는 GPU 실험 재시도가 아니며 원 실패로그·영수증을 삭제하지 않는다.
새 온라인 연결과 실제 생성 시작 여부는 이후 link/progress·worker 기록으로
판정하며, 이 인계 기록 자체가 실험 완료 증거는 아니다.

#### 2026-10-09: 동적 캐시 base600 완료 확인과 adapter 인계

root가2026-10-09 10:50 KST에 산출물을 확인했다. base는2026-10-08
23:57:43 KST에600/600을 완료했고 여섯 생성 상한마다100건씩 기록됐다.
모든 raw에 DynamicCache 관측이 있으며 여섯 worker는 서로 다른PID로
순차 실행·exit0 종료했다. 모든 조건의 모델 로딩 전 allocated/reserved는0,
7개 동결해시와adapter는 불변이고 최종 채점·W&B600업로드 영수증도 완료됐다.
오류파일은 없으며 확인 시GPU compute process는 없었다.

종료 이유는 native EOS457건·token limit143건, 실제 최대 생성4936token,
생성 구간 peak allocated 최대13.133GiB다.65536·130000상한의100건 평가도
완료했지만 실제13만token을 생성한 결과는 아니다. 평가 품질은 별도 해석한다.
근거는 base output의 `root-phase-transition-audit.json`, 조건별receipt,
raw·최종confusion matrix 및
[W&B base run](https://wandb.ai/erad3254-looking-for-a-job/aegislm/runs/source-v2-evaluation-4afe23e80c9d977c)이다.

같은 확인 시점에 adapter는0/600, 기존tester는 비활성 상태였다.
adapter로 자동 전환되지 않은 이유는 확인하지 못했다. root는 이미 승인된
전환 조건을 모두 검증하고 새 단일 `gpt-6-luna` tester
`/root/dynamic_adapter_tester`에게 남은adapter600회를 인계했다.
동일 설정·출력 경로를 사용하며 아직생성되지않은adapter의 최초실행이다.
base를 재실행하거나 결과를 덮어쓰지 않는다. adapter 시작·완료 여부는
이후 실제progress와W&B기록으로 판정한다.

<a id="2026-10-10-dynamic-cache-results"></a>

#### 2026-10-10: 동적 캐시 base·adapter 전체 결과 분석

adapter는2026-10-10 00:24:05 KST에 생성·로컬 채점600/600을 완료했다.
root가 양쪽 raw 각600건,12개 조건의 exit0·조건별 서로 다른worker PID,
모델 로딩 전 allocated/reserved0 및 모든 출력의 DynamicCache 관측을 직접
확인했다. 양쪽 frozen-inputs·prompts·gold 파일은 바이트 단위로 동일하다.
확인 시 A6000은 GPU utilization0%, 메모리146MiB로 실행이 끝난 상태였다.
실행 revision·명령·환경·동결해시는 adapter output의
`experiment-result.json`과 앞 절의 준비·실행 기록을 따른다.

생성 상한별 strict schema 결과는 다음과 같다. 각 조건은 동일한 양성50·음성50건이다.
정답은 `(TP+TN)/100`이며 uncertain·invalid를 분모에서 제외하지 않는다.
schema 유효에는 uncertain도 포함한다. 아래 B/A는 base/adapter다.

| 생성 상한 | schema 유효 B/A | 정답 B/A | uncertain B/A | invalid B/A |
| --- | ---: | ---: | ---: | ---: |
| 128 | 0 / 0 | 0 / 0 | 0 / 0 | 100 / 100 |
| 512 | 44 / 35 | 14 / 16 | 19 / 0 | 56 / 65 |
| 2048 | 84 / 79 | 38 / 44 | 25 / 0 | 16 / 21 |
| 65536 | 77 / 87 | 23 / 50 | 39 / 0 | 23 / 13 |
| 130000 | 82 / 92 | 33 / 57 | 30 / 0 | 18 / 8 |
| context-minus-input | 88 / 84 | 34 / 46 | 32 / 0 | 12 / 16 |

기존 `confusion-matrices.md`는 semantic 판정 표이며,130000의adapter는
추가scope필드가 있는1건을FP로 세므로FP9·invalid7이다.
strict는 같은1건을invalid로 세어FP8·invalid8이다. 다른 조건은 두 행렬이 일치한다.

**Confusion matrix로 읽는 결과:** 아래 표는 사용자가 보는 `.md`와 동일한
semantic 기준이다. TP는 실제 present→present, FN은 실제 present→not_observed,
FP는 실제 not_observed→present, TN은 실제 not_observed→not_observed다.
uncertain과 invalid는 FN/FP로 합치지 않고 별도로 표시한다. invalid는 생성
프로세스 실패를 뜻하지 않으며 최종 판정을 읽지 못한 응답을 포함한다.
각 행의 여섯 수 합은 100이다. 라벨은 원천 데이터 기준이며 아직 미검수다.

| 모델 | 생성 상한 | 정탐 TP | 미탐 FN | 오탐 FP | 정상 TN | 판단 유보 | 출력 오류 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 128 | 0 | 0 | 0 | 0 | 0 | 100 |
| adapter | 128 | 0 | 0 | 0 | 0 | 0 | 100 |
| base | 512 | 3 | 9 | 2 | 11 | 19 | 56 |
| adapter | 512 | 1 | 15 | 4 | 15 | 0 | 65 |
| base | 2048 | 10 | 20 | 1 | 28 | 25 | 16 |
| adapter | 2048 | 14 | 26 | 9 | 30 | 0 | 21 |
| base | 65536 | 5 | 14 | 1 | 18 | 39 | 23 |
| adapter | 65536 | 14 | 26 | 11 | 36 | 0 | 13 |
| base | 130000 | 11 | 15 | 4 | 22 | 30 | 18 |
| adapter | 130000 | 20 | 27 | 9 | 37 | 0 | 7 |
| base | context-minus-input | 8 | 19 | 3 | 26 | 32 | 12 |
| adapter | context-minus-input | 16 | 26 | 12 | 30 | 0 | 16 |

130000 조건을 실제 라벨×모델 판정으로 펼치면 다음과 같다.

| 모델·실제 라벨 | 판정 present | 판정 not_observed | 판정 uncertain | 출력 오류 |
| --- | ---: | ---: | ---: | ---: |
| base·present 50건 | 11 | 15 | 14 | 10 |
| base·not_observed 50건 | 4 | 22 | 16 | 8 |
| adapter·present 50건 | 20 | 27 | 0 | 3 |
| adapter·not_observed 50건 | 9 | 37 | 0 | 4 |

adapter의 양성 50건 중 27건(54%)은 음성으로 판정됐고, 출력 오류 3건까지 합하면
30건에서 양성 탐지가 이뤄지지 않았다. 전체 present 판정 29건·not_observed 판정
64건으로 음성 판정이 많지만, 이것만으로 학습 데이터 불균형이나 원인을 확정하지
않는다. 판단 유보·출력 오류가 줄며 정탐과 미탐, 정상 판단과 오탐이 모두 증가했다.
출력 완성률 개선을 탐지 정확도 개선과 동일시하지 않는다.

**実行安定性:** 両モデルとも65536以上の3条件で全件native EOSとなり、
今回の100入力ではOOMが再発しなかった。全条件を通じた実生成最大は
base4936token・adapter3266token、生成区間peak allocated最大はそれぞれ
13.133GiB・13.477GiBだった。高い生成上限で完走した証拠であり、
実際に13万tokenの生成・長い入力を処理できた証拠ではない。

**判断品質:** adapterは600出力でuncertainが0だった。130000条件では
正答33→57件だが、strictのTP11→20・FP4→8でもある。adapterの陽性50件は
TP20・FN27・invalid3に分かれ、検出できた割合は20/50=40%に留まる。
baseがuncertainだった30件はadapterで正答17・誤答10・invalid3となった。
判断を返す割合が増えたことと、判断の信頼性が上がったことは同一ではない。
600件は同じ100入力の6条件であり、独立した600標本として扱わない。

**生成上限の解釈:** 128では両者100件すべてtoken limitで終了し、adapterでは
finalが100件とも無い。512でもbase42・adapter57件がtoken limitとなった。
2048ではbase1・adapter4件に減り、65536以上では0件だった。
一方でnative生成設定はdo_sample=true、temperature1.0、top_k50、top_p1.0、
条件ごとのseed固定なしである。130000条件の57正答を「13万上限の因果効果」や
最適上限と断定しない。130000でのadapter実生成最大は2446tokenだった。
同条件のstrict invalid8件はHarmony parse error7件・schema違反1件であり、
上限不足だけでは残存する出力契約の問題を説明できない。
パーサーが受理しないヘッダーとモデルが壊したヘッダーは原token列で切り分ける。

**追跡の未完了:** baseのW&Bは600/600・complete。adapterはローカル結果が
600/600の一方、W&B進捗590/600・receipt=logging_ambiguousで止まった。
trackerは最後のcontext-minus-input semantic行列のartifact名が128文字を
超えてValueError、exit1となった。生成workerの失敗ではない。今回の分析は
ローカル最終行列を使い、W&Bの全件反映を完了とは記録しない。
原ログ・receiptを保持し、この分析中にGPU再実行・tracker再送はしていない。

次の候補は追跡名の修正と保存済み結果の再送、同一入力の誤答・ヘッダーの監査、
新しい実験名でseedを管理した生成条件の反復比較である。原ラベルは未検収で、
test500は未使用のため、今回のラベル一致率だけで検出性能の確立とはしない。
