# GPT-OSS-20B Fine-Tuning Experiment Plan

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

작성 시 수행 범위는 Ruff lint·format, mypy, Python 구문 컴파일, 설정 JSON 문법
검사다. 추가한 CPU/mock 회귀 테스트는 실행하지 않았다. 사용자가 테스트도 확인하려면
전용 환경에서 `python -m pytest tests/`를 별도로 실행한다. 새 recipe의 실제 학습,
GPU runtime, 저장·재로딩 및 성능 비교 결과는 사용자의 실행 후 기록한다.
