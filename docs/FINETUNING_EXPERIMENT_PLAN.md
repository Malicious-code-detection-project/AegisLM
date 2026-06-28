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

### 8.3 Shared Development Workstation Runtime Integrity Management

AegisLM fine-tuning is centralized on a single shared GPU workstation. Because multiple team members collaborate on the same system, you must run the following self-verification command whenever starting a new experiment or modifying dependencies to prevent configuration drift or data leaks:

```bash
uv run scripts/verify_gpu.py
```

* **Check Items**:
  * **Dependency Integrity**: Detects whether core packages (PyTorch, CUDA, Unsloth, etc.) have been altered or corrupted by other workloads.
  * **Security Leak Prevention (Git Ignore)**: Prevents large weights, caching directories (`checkpoints/`, `adapters/`, `models/`, `unsloth_compiled_cache/`), and `.env` files from being accidentally staged or committed to Git.
  * **Experiment Metadata Archiving**: Automatically updates [experiments/env_check_report.json](../experiments/env_check_report.json) upon execution. You should copy the `versions` block from this report into the `environment` metadata of your experiment log to maintain a trace of the workstation's runtime configuration history.


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
