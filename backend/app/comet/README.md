# Comet AI - Market Intelligence Module

AI-powered market intelligence using Perplexity Pro for real-time trading insights.

---

## 🎯 Purpose

Comet provides AI-powered market intelligence to enhance trading decisions:
- Validate technical signals with fundamental/news context
- Real-time news monitoring and sentiment analysis
- Risk assessment and opportunity detection
- Pre-market briefings and position reviews

---

## 📁 Files

- **`mcp_client_perplexity.py`** - Main Comet client (async + sync wrapper)
- **`prompt_manager.py`** - Prompt template loader and formatter

---

## 🚀 Quick Start

```python
from app.comet.mcp_client_perplexity import CometMCP

# Async usage (in backend services)
comet = CometMCP()
result = await comet.query("Market sentiment on banking stocks?")
print(result['sentiment'], result['key_insights'])

# Sync usage (in notebooks)
from app.comet.mcp_client_perplexity import MCPClient
comet = MCPClient()
result = comet.query("What's happening with RELIANCE?")
```

---

## 🔧 Configuration

Set your Perplexity API key in `backend/.env`:
```
PERPLEXITY_API_KEY=pplx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Get your key: https://www.perplexity.ai/settings/api

---

## 📖 Documentation

- **Setup:** `../../COMET_QUICKSTART.md`
- **Examples:** `../../COMET_USAGE_EXAMPLES.md`
- **Complete Guide:** `../../PERPLEXITY_PRO_IMPLEMENTATION.md`
- **Summary:** `../../COMET_IMPLEMENTATION_SUMMARY.md`

---

## 🎨 Usage Patterns

### Signal Validation
```python
result = await comet.analyze_with_template(
    "signal_analysis",
    {
        "symbol": "NIFTY",
        "signal_type": "BULLISH",
        "entry_price": 22000,
        "current_price": 22050,
        "timeframe": "15m",
        "indicators": "RSI: 65, MACD bullish",
        "market_context": "Strong uptrend"
    }
)
```

### News Monitoring
```python
result = await comet.query(
    f"Any breaking news affecting {symbol} in last 4 hours?"
)
if result['sentiment'] != 0.5:
    send_alert(symbol, result)
```

### Pre-Market Briefing
```python
result = await comet.query(
    "Global market cues and sector outlook for Indian markets today"
)
```

---

## 🧪 Testing

Run comprehensive tests:
```bash
cd backend
python test_comet_perplexity.py
```

---

## 📊 API Endpoints

- `POST /api/comet/query` - Simple queries
- `POST /api/comet/analyze` - Advanced analysis
- `POST /api/comet/template` - Template-based analysis
- `POST /api/comet/validate-signal` - Signal validation
- `GET /api/comet/health` - Health check

See `../api/comet.py` for details.

---

## 💡 Key Features

- **Real-time web search** - Current news and data
- **Multi-source synthesis** - Combine multiple sources
- **Citations** - Verify information sources
- **Three models** - `pro`, `standard`, `reasoning`
- **Conversation context** - Multi-turn dialogues
- **Template support** - Structured prompts
- **Token tracking** - Monitor usage

---

## 💰 Cost

Perplexity Pro: **$20/month**
- ~300 queries/day with sonar-pro model
- ~600 queries/day with standard model
- Real-time web search included

**Typical usage:** 20-30 queries/day for active trading

---

## 🎯 Integration Points

### Strategy Execution
```python
# In your strategy class
ai_result = await comet.analyze_with_template("signal_analysis", {...})
if ai_result['sentiment'] > 0.6:
    self.execute_trade()
```

### Risk Management
```python
# In risk manager
ai_risks = await comet.analyze_with_template("risk_assessment", {...})
if ai_risks['risks']:
    self.block_trade()
```

### Position Monitoring
```python
# In position manager
for position in positions:
    ai_review = await comet.query(f"Review position: {position}")
    if ai_review['trading_signals'][0]['action'] == 'EXIT':
        self.close_position()
```

---

**Documentation:** See root-level COMET_*.md files  
**Tests:** `../../test_comet_perplexity.py`  
**API Routes:** `../api/comet.py`
