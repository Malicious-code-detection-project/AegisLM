"""AegisLM Hugging Face TRL & PEFT LoRA/QLoRA SFT training script."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
import torch

# Ensure aegislm package can be imported from root
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Standard HF imports
from transformers import (  # type: ignore[import-not-found] # noqa: E402
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import (  # type: ignore[import-not-found] # noqa: E402
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
)
from trl import SFTTrainer  # type: ignore[import-not-found] # noqa: E402
from datasets import Dataset  # type: ignore[import-not-found] # noqa: E402

from aegislm.training.config import load_config, validate_paths  # noqa: E402
from aegislm.datasets import format_sft_dataset  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hugging Face TRL LoRA/QLoRA fine-tuning script."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/tiny_sft_config.json",
        help="Path to the training configuration JSON file",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    print(f"[INFO] Loading configuration from: {config_path}")
    config = load_config(str(config_path))
    validate_paths(config)

    # Load datasets
    train_path = Path(config["dataset"]["train_path"])
    val_path = Path(config["dataset"]["val_path"])
    print(f"[INFO] Loading training dataset from: {train_path}")
    raw_train = load_jsonl(train_path)
    print(f"[INFO] Loading validation dataset from: {val_path}")
    raw_val = load_jsonl(val_path)

    # Format datasets to SFT chat format
    print("[INFO] Formatting datasets...")
    formatted_train = format_sft_dataset(raw_train)
    formatted_val = format_sft_dataset(raw_val)

    train_dataset = Dataset.from_list(formatted_train)
    val_dataset = Dataset.from_list(formatted_val)

    # Load tokenizer
    model_id = config["model"]["base_model_id"]
    cache_dir = config["model"]["cache_dir"]
    max_seq_length = config["training"]["max_seq_length"]

    print(f"[INFO] Loading tokenizer for: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Setup BitsAndBytes configuration for QLoRA
    print("[INFO] Configuring BitsAndBytes for 4-bit QLoRA...")
    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )

    from transformers import AutoConfig  # type: ignore[import-not-found]

    # Load and modify config to avoid BitsAndBytesConfig vs Mxfp4Config conflict
    print(
        "[INFO] Loading and modifying model configuration to bypass quantization conflict..."
    )
    model_config = AutoConfig.from_pretrained(model_id, cache_dir=cache_dir)
    if hasattr(model_config, "quantization_config"):
        delattr(model_config, "quantization_config")

    # Load base model in 4-bit
    print(f"[INFO] Loading base model '{model_id}' in 4-bit with Transformers...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        config=model_config,
        quantization_config=bnb_config,
        cache_dir=cache_dir,
        device_map={"": 0},  # Place on GPU 0
        torch_dtype=compute_dtype,
    )

    # Prepare model for kbit training
    print("[INFO] Preparing model for kbit training...")
    model = prepare_model_for_kbit_training(model)

    # Setup PEFT/LoRA adapter
    print("[INFO] Setting up LoRA adapter config...")
    peft_config = LoraConfig(
        r=config["training"]["lora_r"],
        lora_alpha=config["training"]["lora_alpha"],
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_dropout=config["training"]["lora_dropout"],
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)

    # Format prompts function for tokenizer template application
    def formatting_prompts_func(examples):
        texts = []
        for messages in examples["messages"]:
            text = tokenizer.apply_chat_template(messages, tokenize=False)
            texts.append(text)
        return {"text": texts}

    train_dataset = train_dataset.map(formatting_prompts_func, batched=True)
    val_dataset = val_dataset.map(formatting_prompts_func, batched=True)

    print("[INFO] Initializing SFTTrainer...")

    # Dynamic adjustment for tiny SFT dataset
    num_samples = len(train_dataset)
    batch_size = config["training"]["batch_size"]
    grad_accum = config["training"]["gradient_accumulation_steps"]

    if num_samples < batch_size * grad_accum:
        print(
            f"[WARN] Training samples ({num_samples}) is less than batch_size * gradient_accumulation_steps ({batch_size * grad_accum})."
        )
        print(
            "[WARN] Temporarily setting gradient_accumulation_steps=1 for this tiny SFT PoC run."
        )
        grad_accum = 1

    training_args = TrainingArguments(
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        warmup_steps=1,
        num_train_epochs=config["training"]["epochs"],
        learning_rate=config["training"]["learning_rate"],
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=3407,
        output_dir=config["training"]["checkpoint_dir"],
        save_strategy="no",
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        dataset_num_proc=2,
        packing=False,
        args=training_args,
    )

    # Start training
    print("[INFO] Starting SFT training...")
    start_time = time.time()

    # Clear CUDA cache before training starts
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    trainer.train()

    end_time = time.time()
    elapsed_time = end_time - start_time

    # Get peak VRAM usage
    peak_vram_gb = torch.cuda.max_memory_allocated() / (1024**3)
    print("=" * 60)
    print("TRL Training Completed Successfully!")
    print(f"Elapsed Time: {elapsed_time:.2f} seconds")
    print(f"Peak VRAM Usage: {peak_vram_gb:.2f} GB")
    print("=" * 60)

    # Save final adapter weights
    # We output to a separate subdirectory 'trl-sft-poc' to keep it distinct from unsloth-sft-poc
    output_dir = Path(config["training"]["output_dir"]).parent / "trl-sft-poc"
    print(f"[INFO] Saving fine-tuned adapter to: {output_dir}")
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print("[SUCCESS] Adapter saved.")


if __name__ == "__main__":
    main()
