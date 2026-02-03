"""
Fine-tuning Pipeline for Trading Strategy Discovery
Prepares training data and manages QLoRA fine-tuning with Unsloth

Process:
1. Generate training examples from successful trades
2. Format for instruction tuning
3. Train with QLoRA using Unsloth
4. Export to GGUF for Ollama
"""
import asyncio
import asyncpg
import json
import os
from datetime import datetime, date
from typing import Dict, List, Any
from pathlib import Path


class TrainingDataGenerator:
    """Generates training data from trades and market context"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None
        self.output_dir = Path("training_data")
        self.output_dir.mkdir(exist_ok=True)
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    def create_instruction_example(self, context: str, trade: Dict, analysis: str) -> Dict:
        """Create a single training example in instruction format"""
        
        instruction = f"""Analyze this market data and trading situation:

{context}

The trader entered a {trade.get('option_type', 'CE')} option at strike {trade.get('strike')} with premium ₹{trade.get('entry_premium')}.

Questions:
1. What pattern or setup justified this entry?
2. What were the key technical and price conditions?
3. What strategy rules could replicate this trade?"""

        response = f"""Based on the market data, here is my analysis:

{analysis}

Entry Justification:
- Entry Time: {trade.get('entry_time')} 
- Strike: {trade.get('strike')} ({trade.get('moneyness', 'ATM')})
- Premium: ₹{trade.get('entry_premium')}

This appears to be a {trade.get('pattern', 'time-based entry')} strategy.

Trade Result: {'Profitable' if trade.get('pnl', 0) > 0 else 'Details pending'}"""

        return {
            "instruction": instruction,
            "input": "",
            "output": response
        }
    
    def create_pattern_recognition_example(self, trades: List[Dict]) -> Dict:
        """Create example for pattern recognition across multiple trades"""
        
        # Format trades for input
        trade_descriptions = []
        for i, t in enumerate(trades, 1):
            trade_descriptions.append(f"""Trade {i}:
- Stock: {t.get('stock')}
- Date: {t.get('trade_date')}
- Entry Time: {t.get('entry_time')}
- Strike: {t.get('strike')} {t.get('option_type')}
- Entry Premium: ₹{t.get('entry_premium')}
- RSI: {t.get('rsi_14', 'N/A')}
- MACD: {t.get('macd', 'N/A')}
- Range Position: {t.get('range_position', 'N/A')}%""")
        
        instruction = f"""Analyze these successful trades and identify common patterns:

{chr(10).join(trade_descriptions)}

Find:
1. Common entry conditions
2. Similar technical setups
3. Strategy rules that fit these trades"""

        # Generate expected response based on common features
        common_time = trades[0].get('entry_time') if trades else '14:00'
        common_type = trades[0].get('option_type') if trades else 'CE'
        
        response = f"""Pattern Analysis:

**Common Features Identified:**
1. Entry Time: All trades entered at {common_time}
2. Option Type: All trades are {common_type} (bullish)
3. Strike Selection: In-The-Money (ITM) options

**Suggested Strategy Rules:**

Entry Rules:
- Time: {common_time} (fixed)
- Option: {common_type} at nearest strike
- Check: RSI in 45-55 range (neutral)

Exit Rules:
- Target: 50% profit on premium
- Stop: 40% loss on premium
- Time: Same day exit

This pattern represents a "Time-Based ITM Entry" strategy."""

        return {
            "instruction": instruction,
            "input": "",
            "output": response
        }
    
    async def generate_training_dataset(self, trades: List[Dict], output_file: str = "training_data.json"):
        """Generate full training dataset from trades"""
        
        print(f"📝 Generating training data from {len(trades)} trades...")
        
        training_examples = []
        
        # Create individual trade examples
        for trade in trades:
            # Simple context for now
            context = f"""Stock: {trade.get('stock')}
Date: {trade.get('trade_date')}
Entry Time: {trade.get('entry_time')}
Spot Price: ₹{trade.get('spot_price', 'N/A')}
RSI(14): {trade.get('rsi_14', 'N/A')}
MACD: {trade.get('macd', 'N/A')}
Volume Ratio: {trade.get('volume_ratio', 'N/A')}x
Morning Range Position: {trade.get('range_position', 'N/A')}%"""

            analysis = f"""The entry at {trade.get('entry_time')} shows:
- RSI at {trade.get('rsi_14', 50):.1f} (neutral territory)
- Price at {trade.get('range_position', 50):.1f}% of morning range
- Volume ratio of {trade.get('volume_ratio', 1):.2f}x average"""

            example = self.create_instruction_example(context, trade, analysis)
            training_examples.append(example)
        
        # Create pattern recognition example
        if len(trades) >= 2:
            pattern_example = self.create_pattern_recognition_example(trades)
            training_examples.append(pattern_example)
        
        # Save to file
        output_path = self.output_dir / output_file
        with open(output_path, 'w') as f:
            json.dump(training_examples, f, indent=2)
        
        print(f"✅ Generated {len(training_examples)} training examples")
        print(f"📄 Saved to: {output_path}")
        
        return training_examples
    
    def create_unsloth_training_script(self) -> str:
        """Generate Python script for Unsloth fine-tuning"""
        
        script = '''"""
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
'''
        
        script_path = self.output_dir / "train_with_unsloth.py"
        with open(script_path, 'w') as f:
            f.write(script)
        
        print(f"📄 Training script saved to: {script_path}")
        return str(script_path)
    
    def create_ollama_modelfile(self) -> str:
        """Create Ollama Modelfile for importing fine-tuned model"""
        
        modelfile = '''# Ollama Modelfile for Trading Strategy Model
FROM ./trading_strategy_gguf/unsloth.Q4_K_M.gguf

# Set parameters
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER stop "### Instruction:"
PARAMETER stop "### Response:"

# System prompt
SYSTEM """You are an expert quantitative trading analyst specializing in Indian equity and F&O markets. 
Your role is to:
1. Analyze trading patterns and market data
2. Identify repeatable trading strategies
3. Provide specific, actionable trading rules
4. Focus on technical indicators (RSI, MACD, Volume) and price action

Always be quantitative and specific. Avoid vague advice."""

# Template for instruction format
TEMPLATE """{{ if .System }}{{ .System }}{{ end }}

### Instruction:
{{ .Prompt }}

### Response:
"""
'''
        
        modelfile_path = self.output_dir / "Modelfile"
        with open(modelfile_path, 'w') as f:
            f.write(modelfile)
        
        print(f"📄 Ollama Modelfile saved to: {modelfile_path}")
        return str(modelfile_path)


async def main():
    """Test training data generation"""
    
    print("=" * 80)
    print("🎯 FINE-TUNING PIPELINE - Training Data Generator")
    print("=" * 80)
    
    generator = TrainingDataGenerator('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Sample trades (would come from trade_analyzer in production)
    sample_trades = [
        {
            "stock": "HINDZINC",
            "trade_date": "2025-12-01",
            "entry_time": "14:00",
            "strike": 500,
            "option_type": "CE",
            "entry_premium": 14.0,
            "exit_premium": 23.0,
            "pnl": 11025,
            "spot_price": 503.65,
            "rsi_14": 46.08,
            "macd": -0.43,
            "volume_ratio": 0.41,
            "range_position": 51.2,
            "moneyness": "ITM"
        },
        {
            "stock": "HEROMOTOCO",
            "trade_date": "2025-12-01",
            "entry_time": "14:00",
            "strike": 6200,
            "option_type": "CE",
            "entry_premium": 195.0,
            "spot_price": 6321.0,
            "rsi_14": 51.38,
            "macd": 0.22,
            "volume_ratio": 2.22,
            "range_position": 54.9,
            "moneyness": "ITM"
        }
    ]
    
    # Generate training data
    print("\n📝 Step 1: Generating training dataset...")
    examples = await generator.generate_training_dataset(sample_trades)
    
    # Create training script
    print("\n📝 Step 2: Creating Unsloth training script...")
    generator.create_unsloth_training_script()
    
    # Create Ollama Modelfile
    print("\n📝 Step 3: Creating Ollama Modelfile...")
    generator.create_ollama_modelfile()
    
    print("\n" + "=" * 80)
    print("✅ FINE-TUNING PIPELINE READY")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Add more trades to training_data/training_data.json")
    print("2. Run: python training_data/train_with_unsloth.py")
    print("3. Import to Ollama: ollama create trading-strategy -f training_data/Modelfile")
    print("")


if __name__ == "__main__":
    asyncio.run(main())
