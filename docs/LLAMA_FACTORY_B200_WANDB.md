# LLaMA-Factory B200 Training and W&B Logging

This document defines the first AegisLM multi-GPU SFT path using
LLaMA-Factory, DeepSpeed ZeRO-3, and Weights & Biases logging.

## Recommendation

Use **LLaMA-Factory** as the default B200 fine-tuning framework.

Why:

- YAML-driven training runs are easier for the team to review than custom
  trainer code.
- It supports standard SFT LoRA workflows, DeepSpeed configuration, dataset
  registration, and Transformers logging integrations.
- It fits the current AegisLM boundary: AegisLM owns dataset safety and
  evaluation, while LLaMA-Factory owns the training loop.

Secondary choices:

- **Axolotl**: good fallback if an experiment needs more detailed low-level
  training config control.
- **TRL / PEFT**: use for custom research code after the LLaMA-Factory path is
  stable.
- **Unsloth**: keep for single-GPU PoC and compatibility checks.

## Files

```text
configs/deepspeed/ds_z3_b200.json
configs/llamafactory/aegislm_security_lora_b200.yaml
configs/llamafactory/dataset_info.aegislm_security_sft.json
scripts/export_llamafactory_dataset.py
scripts/run_llamafactory_b200.sh
aegislm/training/llamafactory.py
```

## Dataset Export

If the existing dataset is still in legacy `instruction/input/output` format,
first convert it into AegisLM canonical JSONL and split it:

```bash
uv run python scripts/build_security_dataset.py \
  --legacy-alpaca /data/security_sft_dataset.json \
  --output-dir data/processed \
  --split-ratios 0.8,0.1,0.1 \
  --seed 42
```

The exporter then converts AegisLM JSONL records into LLaMA-Factory Alpaca-style
columns. It reuses the existing AegisLM SFT formatter, so safety, split, schema,
and unsafe-guidance checks remain centralized.

```bash
uv run python scripts/export_llamafactory_dataset.py \
  --input data/processed/aegislm_security_train.jsonl \
  --output data/aegislm_security_sft_train.json \
  --dataset-info-output configs/llamafactory/dataset_info.aegislm_security_sft.json \
  --ignore-errors
```

The output columns are:

```json
{
  "system": "system prompt",
  "instruction": "user prompt",
  "input": "",
  "output": "assistant JSON string"
}
```

Copy or merge the generated dataset info entry into the LLaMA-Factory
`data/dataset_info.json` file when running from a LLaMA-Factory checkout.

## W&B Logging

The training YAML enables:

```yaml
report_to: wandb
run_name: aegislm-security-sft-qwen2_5-coder-72b-b200-lora
logging_steps: 10
plot_loss: true
```

Set secrets only through the runtime environment:

```bash
export WANDB_API_KEY="<set outside git>"
export WANDB_PROJECT="aegislm-security-sft"
export WANDB_ENTITY="<optional-team-or-user>"
```

For an offline smoke test:

```bash
export WANDB_MODE=offline
```

Do not commit W&B API keys, `.env` files, `wandb/`, `runs/`, adapters, or
checkpoints.

## Run

From the AegisLM repo:

```bash
export CUDA_VISIBLE_DEVICES=0,1,2,3
bash scripts/run_llamafactory_b200.sh
```

The default config targets:

```text
base model: /models/qwen/Qwen2.5-Coder-72B-Instruct
template: qwen
GPUs: 4 x B200
method: LoRA SFT
DeepSpeed: ZeRO-3
```

If the experiment uses `openai/gpt-oss-20b`, change `model_name_or_path` and
`template` according to the LLaMA-Factory GPT-OSS guide after confirming the
installed server version and dependencies. Keep the exported dataset format
unchanged unless the target tokenizer requires a different chat-template path.

## Validation

Before a real B200 run:

```bash
uv run pytest tests/test_llamafactory_export.py
uv run python scripts/export_llamafactory_dataset.py \
  --input data/tiny_sft_train.jsonl \
  --output data/aegislm_security_sft.json \
  --ignore-errors
```

Record each run in the experiment log with:

- Git commit
- base model and adapter method
- dataset version and exported file path
- exact LLaMA-Factory YAML
- W&B run URL
- peak VRAM and training time
- eval result before and after adapter
- safety notes
