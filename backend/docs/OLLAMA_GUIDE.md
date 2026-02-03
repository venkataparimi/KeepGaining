# Complete Guide to Using Ollama for Trading Strategy Analysis

## What is Ollama?

Ollama is a tool that lets you run **large language models (LLMs) locally** on your computer without needing cloud APIs or tokens. It's perfect for:
- Strategy analysis
- Pattern recognition
- Trade explanation
- Market insights
- **No API costs, no rate limits, fully private**

---

## Installation & Setup

### Step 1: Install Ollama

**Windows:**
```powershell
winget install Ollama.Ollama
```

**Or download from:** https://ollama.com/download

### Step 2: Verify Installation
```powershell
ollama --version
```

### Step 3: Start Ollama Server
```powershell
ollama serve
```
*Keep this terminal open - the server runs in the background*

### Step 4: Pull a Model
```powershell
# Recommended models for trading analysis:

# Llama 3 (8B) - Fast, good for quick analysis
ollama pull llama3

# Llama 3.1 (8B) - Better reasoning
ollama pull llama3.1

# Mistral (7B) - Excellent for technical analysis
ollama pull mistral

# Mixtral (47B) - Most powerful, slower
ollama pull mixtral

# DeepSeek Coder - Great for code generation
ollama pull deepseek-coder
```

---

## Basic Usage

### 1. Command Line Interface

**Simple query:**
```powershell
ollama run llama3 "Explain what a bull flag pattern is"
```

**Interactive chat:**
```powershell
ollama run llama3
>>> Analyze this trade: Bought NIFTY 24000 CE when price broke above 24050
>>> /bye  # to exit
```

**Useful commands:**
```powershell
ollama list              # Show installed models
ollama ps                # Show running models
ollama rm llama3         # Remove a model
ollama stop llama3       # Stop a running model
```

---

## Python Integration

### 2. Using Ollama with Python (Recommended)

**Install Python client:**
```powershell
pip install ollama
```

**Basic Python usage:**
```python
import ollama

# Simple query
response = ollama.chat(
    model='llama3',
    messages=[{
        'role': 'user',
        'content': 'What is a breakout trade?'
    }]
)

print(response['message']['content'])
```

**Streaming response:**
```python
import ollama

stream = ollama.chat(
    model='llama3',
    messages=[{'role': 'user', 'content': 'Explain RSI indicator'}],
    stream=True
)

for chunk in stream:
    print(chunk['message']['content'], end='', flush=True)
```

---

## Trading Strategy Use Cases

### 3. Strategy Analysis

**Analyze a trade:**
```python
import ollama

def analyze_trade(trade_details):
    prompt = f"""
    You are a quantitative trading expert. Analyze this trade:
    
    {trade_details}
    
    Provide:
    1. Entry logic
    2. Exit criteria
    3. Risk management
    4. Similar patterns to look for
    """
    
    response = ollama.chat(
        model='llama3',
        messages=[{'role': 'user', 'content': prompt}]
    )
    
    return response['message']['content']

# Example
trade = """
Symbol: NIFTY 24000 CE
Entry: 150
Exit: 200
Entry Time: 9:30 AM when NIFTY broke 24050
Exit Time: 11:00 AM when RSI hit 75
"""

analysis = analyze_trade(trade)
print(analysis)
```

### 4. Pattern Recognition

**Identify patterns from candle data:**
```python
import ollama
import pandas as pd

def identify_pattern(candles_df):
    # Get last 20 candles
    recent = candles_df.tail(20)
    
    # Format for AI
    candle_summary = ""
    for idx, row in recent.iterrows():
        candle_summary += f"{row['timestamp']}: O={row['open']}, H={row['high']}, L={row['low']}, C={row['close']}\n"
    
    prompt = f"""
    Analyze these candles and identify any chart patterns:
    
    {candle_summary}
    
    Look for: Head & Shoulders, Double Top/Bottom, Triangles, Flags, etc.
    """
    
    response = ollama.chat(
        model='llama3',
        messages=[{'role': 'user', 'content': prompt}]
    )
    
    return response['message']['content']
```

### 5. Strategy Generation

**Generate strategy from winning trades:**
```python
import ollama

def reverse_engineer_strategy(winning_trades):
    prompt = f"""
    You are a quantitative analyst. Based on these winning trades, 
    create a systematic trading strategy:
    
    {winning_trades}
    
    Provide:
    1. Entry rules (specific conditions)
    2. Exit rules (profit target, stop loss)
    3. Position sizing
    4. Risk management
    5. Backtestable pseudocode
    
    Format as JSON.
    """
    
    response = ollama.chat(
        model='llama3',
        messages=[{'role': 'user', 'content': prompt}],
        format='json'  # Request JSON output
    )
    
    return response['message']['content']
```

---

## Advanced Features

### 6. Multi-Turn Conversations

**Build context over multiple queries:**
```python
import ollama

conversation = []

def ask_ollama(question):
    conversation.append({
        'role': 'user',
        'content': question
    })
    
    response = ollama.chat(
        model='llama3',
        messages=conversation
    )
    
    # Add AI response to conversation
    conversation.append({
        'role': 'assistant',
        'content': response['message']['content']
    })
    
    return response['message']['content']

# Example conversation
print(ask_ollama("What is a MACD crossover?"))
print(ask_ollama("How can I use it for entry signals?"))
print(ask_ollama("What about exit signals?"))
```

### 7. Custom System Prompts

**Set AI personality/expertise:**
```python
import ollama

def trading_expert_chat(user_query):
    messages = [
        {
            'role': 'system',
            'content': '''You are an expert quantitative trader with 20 years of experience.
            You specialize in:
            - Technical analysis
            - Options trading strategies
            - Risk management
            - Backtesting methodologies
            
            Always provide specific, actionable advice with examples.'''
        },
        {
            'role': 'user',
            'content': user_query
        }
    ]
    
    response = ollama.chat(model='llama3', messages=messages)
    return response['message']['content']
```

### 8. Structured Output (JSON)

**Get structured data:**
```python
import ollama
import json

def analyze_trade_structured(trade_data):
    prompt = f"""
    Analyze this trade and return JSON with this structure:
    {{
        "entry_logic": "string",
        "exit_logic": "string",
        "risk_reward": "number",
        "confidence": "high|medium|low",
        "similar_patterns": ["pattern1", "pattern2"]
    }}
    
    Trade: {trade_data}
    """
    
    response = ollama.chat(
        model='llama3',
        messages=[{'role': 'user', 'content': prompt}],
        format='json'
    )
    
    return json.loads(response['message']['content'])
```

---

## Integration with Your Trading System

### 9. Real-Time Strategy Analysis

**Analyze live trades:**
```python
import ollama
import asyncpg

async def analyze_recent_trades():
    # Get recent trades from DB
    conn = await asyncpg.connect('postgresql://...')
    trades = await conn.fetch("""
        SELECT * FROM trades 
        WHERE timestamp > NOW() - INTERVAL '1 day'
        ORDER BY timestamp DESC
        LIMIT 10
    """)
    
    # Format for AI
    trade_summary = "\n".join([
        f"{t['symbol']}: Entry={t['entry_price']}, Exit={t['exit_price']}, PnL={t['pnl']}"
        for t in trades
    ])
    
    # Ask AI for insights
    response = ollama.chat(
        model='llama3',
        messages=[{
            'role': 'user',
            'content': f"Analyze these trades and identify common winning patterns:\n{trade_summary}"
        }]
    )
    
    print(response['message']['content'])
```

### 10. Indicator Explanation

**Explain indicator values:**
```python
import ollama

def explain_indicators(symbol, indicators):
    prompt = f"""
    For {symbol}, current indicators:
    - RSI: {indicators['rsi']}
    - MACD: {indicators['macd']}
    - Bollinger Bands: Price at {indicators['bb_position']}
    - Volume: {indicators['volume_ratio']}x average
    
    What do these suggest? Should I enter a trade?
    """
    
    response = ollama.chat(
        model='llama3',
        messages=[{'role': 'user', 'content': prompt}]
    )
    
    return response['message']['content']
```

---

## Performance Tips

### 11. Optimization

**Speed up responses:**
```python
import ollama

# Use smaller models for faster responses
response = ollama.chat(
    model='llama3',  # 8B model - fast
    messages=[{'role': 'user', 'content': 'Quick analysis needed'}],
    options={
        'num_predict': 200,  # Limit response length
        'temperature': 0.3,  # More focused responses
        'top_p': 0.9
    }
)
```

**Batch processing:**
```python
import ollama
from concurrent.futures import ThreadPoolExecutor

def analyze_single_trade(trade):
    response = ollama.chat(
        model='llama3',
        messages=[{'role': 'user', 'content': f"Analyze: {trade}"}]
    )
    return response['message']['content']

# Analyze multiple trades in parallel
trades = [...]  # List of trades
with ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(analyze_single_trade, trades))
```

---

## Model Comparison

| Model | Size | Speed | Use Case |
|-------|------|-------|----------|
| **llama3** | 8B | Fast | Quick analysis, chat |
| **llama3.1** | 8B | Fast | Better reasoning |
| **mistral** | 7B | Fast | Technical analysis |
| **mixtral** | 47B | Slow | Deep analysis, complex strategies |
| **deepseek-coder** | 6.7B | Fast | Code generation |
| **phi3** | 3.8B | Very Fast | Simple queries |

---

## Complete Example: Strategy Investigator

```python
import ollama
import asyncpg
import json

class StrategyInvestigator:
    def __init__(self, model='llama3'):
        self.model = model
        self.conversation = []
    
    async def analyze_winning_trades(self, db_conn):
        # Get winning trades
        trades = await db_conn.fetch("""
            SELECT * FROM trades 
            WHERE pnl > 0 
            ORDER BY pnl DESC 
            LIMIT 20
        """)
        
        # Format for AI
        trade_data = json.dumps([dict(t) for t in trades], indent=2)
        
        prompt = f"""
        Analyze these winning trades and identify the common strategy:
        
        {trade_data}
        
        Return JSON with:
        {{
            "strategy_name": "string",
            "entry_conditions": ["condition1", "condition2"],
            "exit_conditions": ["condition1", "condition2"],
            "indicators_used": ["indicator1", "indicator2"],
            "win_rate_estimate": "percentage",
            "risk_reward": "ratio"
        }}
        """
        
        response = ollama.chat(
            model=self.model,
            messages=[{'role': 'user', 'content': prompt}],
            format='json'
        )
        
        return json.loads(response['message']['content'])
    
    def refine_strategy(self, strategy, feedback):
        prompt = f"""
        Current strategy: {json.dumps(strategy, indent=2)}
        
        Feedback: {feedback}
        
        Refine the strategy based on this feedback.
        Return improved strategy in same JSON format.
        """
        
        response = ollama.chat(
            model=self.model,
            messages=[{'role': 'user', 'content': prompt}],
            format='json'
        )
        
        return json.loads(response['message']['content'])

# Usage
investigator = StrategyInvestigator(model='llama3')
# strategy = await investigator.analyze_winning_trades(conn)
# refined = investigator.refine_strategy(strategy, "Add volume confirmation")
```

---

## Troubleshooting

**Ollama not responding:**
```powershell
# Restart Ollama
taskkill /F /IM ollama.exe
ollama serve
```

**Model too slow:**
```powershell
# Use smaller model
ollama pull phi3
```

**Out of memory:**
```powershell
# Use quantized models (smaller)
ollama pull llama3:7b-q4_0
```

---

## Next Steps

1. **Install Ollama** and pull `llama3`
2. **Test basic queries** from command line
3. **Integrate with Python** using the examples above
4. **Build your strategy analyzer** using the StrategyInvestigator template
5. **Experiment with different models** to find the best fit

---

*For more examples, check:*
- `backend/app/services/strategy_investigator.py` - Full implementation
- `backend/notebooks/03_strategy_builder_no_tokens.ipynb` - Interactive examples
- `.agent/workflows/setup_local_ai.md` - Setup guide

---

**Remember**: Ollama runs **100% locally** - no internet needed, no API costs, complete privacy!
