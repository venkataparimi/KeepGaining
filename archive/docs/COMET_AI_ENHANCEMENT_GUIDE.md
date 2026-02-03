# Comet AI Integration Enhancement - Complete Guide

## 🎯 Overview

This enhancement adds **structured prompt templates** and **Jupyter notebooks** to the KeepGaining trading system for better Comet AI (Perplexity) integration, following best practices from the Generative AI Project Structure template.

**Status:** ✅ **Complete - Zero Breaking Changes**

---

## 📂 What Was Added

### 1. Prompt Templates (`backend/prompts/templates/`)

Four structured templates for consistent Comet AI queries:

- **`signal_analysis.txt`** - Analyze trading signals with strength ratings
- **`risk_assessment.txt`** - Assess position and portfolio risk
- **`market_context.txt`** - Get broader market analysis
- **`trade_plan.txt`** - Generate complete trade execution plans

### 2. Prompt Manager (`backend/app/comet/prompt_manager.py`)

New utility class for loading and formatting prompt templates:

```python
from app.comet.prompt_manager import PromptManager

pm = PromptManager()
prompt = pm.format_prompt(
    "signal_analysis",
    symbol="NIFTY",
    signal_type="BULLISH",
    entry_price=22000,
    current_price=22050,
    timeframe="15m",
    indicators="RSI: 65, MACD: Bullish",
    market_context="Strong uptrend"
)
```

### 3. Enhanced Comet Client

Added new methods to `backend/app/comet/mcp_client.py`:

- **`analyze_with_template()`** - Use prompt templates (async)
- **`query()`** - Simple query method (async)
- **`MCPClient` class** - Synchronous wrapper for notebooks

### 4. Jupyter Notebooks (`backend/notebooks/`)

Two analysis notebooks:

- **`01_strategy_backtest_analysis.ipynb`** - Analyze backtest results
- **`02_comet_signal_validation.ipynb`** - Validate signals with Comet AI

### 5. Configuration (`backend/config/comet_config.yaml`)

Comprehensive Comet AI configuration including:
- Model settings (temperature, max_tokens)
- Caching and rate limiting
- Cost management
- Feature flags

---

## 🚀 Quick Start

### Option 1: Use in Production Code

```python
from app.comet.mcp_client import comet_client

# Use with templates (async)
analysis = await comet_client.analyze_with_template(
    "signal_analysis",
    symbol="NSE:NIFTY50-INDEX",
    signal_type="BULLISH",
    entry_price=22000,
    current_price=22050,
    timeframe="15m",
    indicators="RSI: 65, MACD: Bullish Crossover, Volume: Above Average",
    market_context="Strong uptrend, above all EMAs"
)

print(f"Signal Strength: {analysis.get('sentiment')}")
print(f"Confidence: {analysis.get('confidence')}")
```

### Option 2: Use in Jupyter Notebooks

```python
from app.comet.mcp_client import MCPClient

# Synchronous wrapper - no async/await needed!
comet = MCPClient()

analysis = comet.analyze_with_template(
    "signal_analysis",
    symbol="NIFTY",
    signal_type="BULLISH",
    entry_price=22000,
    current_price=22050,
    timeframe="15m",
    indicators="RSI: 65",
    market_context="Uptrend"
)

print(analysis)
```

### Option 3: Direct Prompt Usage

```python
from app.comet.mcp_client import MCPClient

comet = MCPClient()

# Simple query
response = comet.query("What's the sentiment for NIFTY today?")
print(response.get('content'))
```

---

## 📖 Detailed Usage Guide

### Using Prompt Templates

#### 1. Signal Analysis

```python
from app.comet.mcp_client import MCPClient

comet = MCPClient()

analysis = comet.analyze_with_template(
    "signal_analysis",
    symbol="NSE:BANKNIFTY-INDEX",
    signal_type="BEARISH",
    entry_price=45000,
    current_price=44950,
    timeframe="5m",
    indicators="RSI: 72 (Overbought), MACD: Bearish Divergence",
    market_context="Resistance rejection, weakening momentum"
)

# Extract key information
signal_strength = analysis.get('sentiment', 0.5)  # 0.0-1.0
confidence = analysis.get('confidence', 0.0)       # 0.0-1.0
insights = analysis.get('key_insights', [])
risks = analysis.get('risks', [])

print(f"Signal Strength: {signal_strength:.2f}")
print(f"Confidence: {confidence:.2f}")
print(f"Insights: {', '.join(insights)}")
```

#### 2. Risk Assessment

```python
risk_analysis = comet.analyze_with_template(
    "risk_assessment",
    symbol="NSE:RELIANCE-EQ",
    position_type="LONG",
    entry_price=2450,
    current_price=2455,
    position_size=50,
    unrealized_pnl=250,
    total_capital=1000000,
    position_percentage=12.3,
    current_drawdown=2.5,
    open_positions_count=5,
    market_conditions="High volatility, sector underperforming",
    technical_indicators="RSI: 58, MACD: Neutral"
)

# Get risk recommendations
risk_level = risk_analysis.get('risks', [])
action_items = risk_analysis.get('trading_signals', [])
```

#### 3. Market Context

```python
from datetime import datetime

market_analysis = comet.analyze_with_template(
    "market_context",
    symbol="NSE:NIFTY50-INDEX",
    current_price=22000,
    day_high=22100,
    day_low=21950,
    volume=5000000,
    avg_volume=3500000,
    atr=150,
    index_performance="NIFTY: +0.8%, SENSEX: +0.6%, BANKNIFTY: +1.2%",
    recent_events="US Fed comments positive, FII buying continues",
    technical_context="Consolidating near ATH, strong support at 21800",
    current_time=datetime.now().strftime("%I:%M %p IST"),
    market_session="Pre-noon",
    day_of_week=datetime.now().strftime("%A")
)
```

#### 4. Trade Plan Generation

```python
trade_plan = comet.analyze_with_template(
    "trade_plan",
    symbol="NSE:TCS-EQ",
    strategy_name="Volume Rocket",
    signal_time="2025-12-06 09:45:00",
    signal_type="BULLISH_BREAKOUT",
    entry_price=3500,
    current_price=3505,
    entry_confidence=8,
    technical_setup="Volume spike + breakout above resistance",
    max_risk_percent=2,
    account_size=1000000,
    max_position_size=50000,
    market_conditions="Strong market, low volatility"
)

# Extract trade plan components
entry_strategy = trade_plan.get('key_insights', [])
position_sizing = trade_plan.get('trading_signals', [])
```

---

## 📊 Jupyter Notebook Workflows

### Workflow 1: Backtest Analysis

```bash
# Start Jupyter
cd backend/notebooks
jupyter notebook 01_strategy_backtest_analysis.ipynb
```

**What it does:**
1. Loads backtest results from CSV
2. Calculates performance metrics
3. Visualizes P&L and distributions
4. Uses Comet AI to analyze best/worst trades
5. Generates optimization recommendations

### Workflow 2: Signal Validation

```bash
jupyter notebook 02_comet_signal_validation.ipynb
```

**What it does:**
1. Loads recent trading signals
2. Validates each signal with Comet AI
3. Assigns confidence scores
4. Generates trade plans
5. Decides which signals to execute

---

## 🔧 Configuration

### Comet Settings (`backend/config/comet_config.yaml`)

Key settings you can adjust:

```yaml
comet:
  model: "sonar-pro"          # Perplexity model
  temperature: 0.7            # Creativity (0.0-1.0)
  max_tokens: 2000            # Max response length

cache:
  enabled: true               # Cache similar queries
  ttl: 3600                   # Cache duration (seconds)

rate_limit:
  max_requests_per_minute: 30
  max_requests_per_hour: 500

cost_management:
  daily_limit_usd: 10.0
  monthly_limit_usd: 200.0
```

---

## 🎯 Integration Examples

### Example 1: Pre-Trade Signal Validation

```python
from app.comet.mcp_client import MCPClient
from app.comet.prompt_manager import PromptManager

def validate_signal_before_execution(signal_data: dict) -> tuple[bool, str]:
    """Validate a trading signal with Comet AI before executing"""
    
    comet = MCPClient()
    
    # Get Comet analysis
    analysis = comet.analyze_with_template("signal_analysis", **signal_data)
    
    # Extract confidence
    confidence = analysis.get('confidence', 0.0)
    sentiment = analysis.get('sentiment', 0.5)
    
    # Decision logic
    if confidence >= 0.7 and sentiment >= 0.6:
        return True, "High confidence - Execute full size"
    elif confidence >= 0.5 and sentiment >= 0.5:
        return True, "Medium confidence - Execute 50% size"
    else:
        return False, "Low confidence - Skip trade"

# Usage in strategy
signal = {
    "symbol": "NIFTY",
    "signal_type": "BULLISH",
    "entry_price": 22000,
    # ... other fields
}

should_trade, reason = validate_signal_before_execution(signal)
if should_trade:
    execute_order(signal)
```

### Example 2: Risk Monitoring

```python
def monitor_position_risk(position: dict) -> dict:
    """Monitor position risk in real-time"""
    
    comet = MCPClient()
    
    risk_data = {
        "symbol": position['symbol'],
        "position_type": "LONG" if position['quantity'] > 0 else "SHORT",
        "entry_price": position['avg_price'],
        "current_price": position['ltp'],
        "position_size": abs(position['quantity']),
        "unrealized_pnl": position['pnl'],
        # ... portfolio context
    }
    
    risk_assessment = comet.analyze_with_template("risk_assessment", **risk_data)
    
    return {
        "risk_level": risk_assessment.get('sentiment'),
        "action_required": len(risk_assessment.get('risks', [])) > 0,
        "recommendations": risk_assessment.get('key_insights', [])
    }
```

### Example 3: Daily Market Context

```python
from datetime import datetime

def get_morning_market_brief() -> dict:
    """Get market context before trading starts"""
    
    comet = MCPClient()
    
    context_data = {
        "symbol": "NSE:NIFTY50-INDEX",
        "current_price": get_nifty_price(),
        "day_high": get_day_high(),
        "day_low": get_day_low(),
        "volume": get_volume(),
        "avg_volume": get_avg_volume(),
        # ... other market data
        "current_time": datetime.now().strftime("%I:%M %p IST"),
        "market_session": "Pre-open",
        "day_of_week": datetime.now().strftime("%A")
    }
    
    return comet.analyze_with_template("market_context", **context_data)

# Use before market open
morning_brief = get_morning_market_brief()
print(f"Market Sentiment: {morning_brief.get('sentiment')}")
print(f"Key Insights: {morning_brief.get('key_insights')}")
```

---

## 🧪 Testing

### Test Prompt Manager

```python
from app.comet.prompt_manager import PromptManager

pm = PromptManager()

# List available templates
templates = pm.list_templates()
print(f"Available templates: {templates}")

# Get template parameters
params = pm.get_template_params("signal_analysis")
print(f"Required parameters: {params}")

# Validate template
valid, missing = pm.validate_template(
    "signal_analysis",
    ["symbol", "signal_type", "entry_price"]
)
print(f"Valid: {valid}, Missing: {missing}")
```

### Test MCPClient

```python
from app.comet.mcp_client import MCPClient

comet = MCPClient()

# Simple query test
response = comet.query("What is 2+2?")
print(response)

# Template test
analysis = comet.analyze_with_template(
    "signal_analysis",
    symbol="TEST",
    signal_type="BULLISH",
    entry_price=100,
    current_price=105,
    timeframe="1h",
    indicators="Test indicators",
    market_context="Test context"
)
print(analysis)
```

---

## 📝 Adding New Templates

### Step 1: Create Template File

Create `backend/prompts/templates/my_template.txt`:

```
Analyze {symbol} for {analysis_type}:

Current Price: {current_price}
Target: {target_price}

Provide:
1. Analysis
2. Recommendation
3. Risk factors
```

### Step 2: Document Parameters

Add to `backend/prompts/README.md`:

```markdown
### 5. `my_template.txt`
Custom analysis template

**Usage:**
\```python
analysis = comet.analyze_with_template(
    "my_template",
    symbol="NIFTY",
    analysis_type="breakout",
    current_price=22000,
    target_price=22500
)
\```
```

### Step 3: Use in Code

```python
result = comet.analyze_with_template(
    "my_template",
    symbol="NIFTY",
    analysis_type="breakout",
    current_price=22000,
    target_price=22500
)
```

---

## 🚨 Important Notes

### 1. Zero Breaking Changes
- All existing code continues to work
- New features are additions only
- No import paths changed

### 2. API Key Required
Set in `.env`:
```bash
ANTHROPIC_API_KEY=your_perplexity_api_key
```

### 3. Cost Management
- Monitor API usage via config
- Set daily/monthly limits
- Use caching to reduce calls

### 4. Fallback Behavior
If Comet API fails:
- Returns safe fallback response
- System continues working
- Logs error for debugging

---

## 📚 Documentation

- **Prompts:** `backend/prompts/README.md`
- **Notebooks:** `backend/notebooks/README.md`
- **Config:** `backend/config/comet_config.yaml`

---

## ✅ Verification

Run these commands to verify everything works:

```bash
cd backend

# Test PromptManager
python -c "from app.comet.prompt_manager import PromptManager; pm = PromptManager(); print('✓ Templates:', pm.list_templates())"

# Test MCPClient
python -c "from app.comet.mcp_client import MCPClient; comet = MCPClient(); print('✓ MCPClient ready')"

# Start Jupyter
cd notebooks
jupyter notebook
```

---

## 🎉 Summary

**What You Can Do Now:**

1. ✅ Use structured prompt templates for consistent Comet AI queries
2. ✅ Validate trading signals before execution
3. ✅ Assess risk for positions and portfolio
4. ✅ Get market context analysis
5. ✅ Generate complete trade plans
6. ✅ Analyze backtest results in Jupyter notebooks
7. ✅ Build signal confidence scoring systems

**All without breaking any existing code!**

---

**Created:** December 6, 2025  
**Status:** ✅ Production Ready
