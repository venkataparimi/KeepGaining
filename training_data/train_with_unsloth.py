"""
Unsloth QLoRA Fine-tuning Script for Trading Strategy Model
Run this in a Python environment with Unsloth installed

Requirements:
- pip install unsloth
- GPU with 16GB+ VRAM (or use free Colab GPU)
"""
from unsloth import FastLanguageModel
import torch
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

# Configuration
MODEL_NAME = "unsloth/llama-3-8b-bnb-4bit"  # 4-bit quantized for memory efficiency
MAX_SEQ_LENGTH = 2048
LOAD_IN_4BIT = True

# Load model with Unsloth
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
    dtype=None,  # Auto-detect
    load_in_4bit=LOAD_IN_4BIT,
)

# Add LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r=16,  # LoRA rank
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

# Load training data
dataset = load_dataset("json", data_files="training_data/training_data.json", split="train")

# Format prompt
def formatting_func(example):
    text = f"""### Instruction:
{example['instruction']}

### Response:
{example['output']}"""
    return {"text": text}

dataset = dataset.map(formatting_func)

# Training configuration
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=5,
        max_steps=60,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=1,
        output_dir="outputs",
        optim="adamw_8bit",
        seed=42,
    ),
)

# Train
print("Starting training...")
trainer.train()

# Save model
print("Saving model...")
model.save_pretrained("trading_strategy_lora")
tokenizer.save_pretrained("trading_strategy_lora")

# Save as GGUF for Ollama
print("Exporting to GGUF...")
model.save_pretrained_gguf("trading_strategy_gguf", tokenizer, quantization_method="q4_k_m")

print("Done! Import to Ollama with:")
print("ollama create trading-strategy -f Modelfile")
