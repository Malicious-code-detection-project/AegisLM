from unsloth import FastLanguageModel
import torch
max_seq_length = 1024
dtype = None
fourbit_models = ['unsloth/gpt-oss-20b-unsloth-bnb-4bit', 'unsloth/gpt-oss-120b-unsloth-bnb-4bit', 'unsloth/gpt-oss-20b', 'unsloth/gpt-oss-120b']
model, tokenizer = FastLanguageModel.from_pretrained(model_name='unsloth/gpt-oss-20b', dtype=dtype, max_seq_length=max_seq_length, load_in_4bit=True, full_finetuning=False)
model = FastLanguageModel.get_peft_model(model, r=8, target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'], lora_alpha=16, lora_dropout=0, bias='none', use_gradient_checkpointing='unsloth', random_state=3407, use_rslora=False, loftq_config=None)

def formatting_prompts_func(examples):
    convos = examples['messages']
    texts = [tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=False) for convo in convos]
    return {'text': texts}
from datasets import load_dataset
dataset = load_dataset('json', data_files={'train': '/home/remoteuser/Desktop/AegisLM/outputs/cc-official-tutorial-v5-token-caps-20261004-v1/training-messages.jsonl'}, split='train')
dataset
from unsloth.chat_templates import standardize_sharegpt
dataset = standardize_sharegpt(dataset)
dataset = dataset.map(formatting_prompts_func, batched=True)
print(dataset[0]['text'])
from trl import SFTConfig, SFTTrainer
trainer = SFTTrainer(model=model, tokenizer=tokenizer, train_dataset=dataset, args=SFTConfig(per_device_train_batch_size=1, gradient_accumulation_steps=4, warmup_steps=5, max_steps=30, learning_rate=0.0002, logging_steps=1, optim='adamw_8bit', weight_decay=0.001, lr_scheduler_type='linear', seed=3407, output_dir='outputs', report_to='none'))
from unsloth.chat_templates import train_on_responses_only
gpt_oss_kwargs = dict(instruction_part='<|start|>user<|message|>', response_part='<|start|>assistant<|channel|>final<|message|>')
trainer = train_on_responses_only(trainer, **gpt_oss_kwargs)
tokenizer.decode(trainer.train_dataset[100]['input_ids'])
tokenizer.decode([tokenizer.pad_token_id if x == -100 else x for x in trainer.train_dataset[100]['labels']]).replace(tokenizer.pad_token, ' ')
gpu_stats = torch.cuda.get_device_properties(0)
start_gpu_memory = round(torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3)
max_memory = round(gpu_stats.total_memory / 1024 / 1024 / 1024, 3)
print(f'GPU = {gpu_stats.name}. Max memory = {max_memory} GB.')
print(f'{start_gpu_memory} GB of memory reserved.')
trainer_stats = trainer.train()
used_memory = round(torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3)
used_memory_for_lora = round(used_memory - start_gpu_memory, 3)
used_percentage = round(used_memory / max_memory * 100, 3)
lora_percentage = round(used_memory_for_lora / max_memory * 100, 3)
print(f"{trainer_stats.metrics['train_runtime']} seconds used for training.")
print(f"{round(trainer_stats.metrics['train_runtime'] / 60, 2)} minutes used for training.")
print(f'Peak reserved memory = {used_memory} GB.')
print(f'Peak reserved memory for training = {used_memory_for_lora} GB.')
print(f'Peak reserved memory % of max memory = {used_percentage} %.')
print(f'Peak reserved memory for training % of max memory = {lora_percentage} %.')
model.save_pretrained('gpt_oss_lora')
