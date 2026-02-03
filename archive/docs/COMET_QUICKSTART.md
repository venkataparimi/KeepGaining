# Comet AI - Quick Start Guide

Get Comet (Perplexity Pro AI) up and running in 5 minutes.

---

## ✅ Prerequisites

- Perplexity Pro subscription ($20/month)
- Python 3.10+
- KeepGaining backend setup

---

## 🚀 Setup Steps

### 1. Get Your Perplexity API Key

1. Go to https://www.perplexity.ai/settings/api
2. Click "Generate API Key"
3. Copy the key (starts with `pplx-...`)

### 2. Add API Key to Environment

Open `backend/.env` and add:

```bash
PERPLEXITY_API_KEY=pplx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. Install Dependencies

```bash
cd backend
pip install openai loguru  # Already in requirements.txt
```

### 4. Test the Connection

```bash
cd backend
python test_comet_perplexity.py
```

Expected output:
```
🚀 Comet Perplexity Pro Test Suite
============================================================

Testing Async CometMCP Client
============================================================

Test 1: Simple Market Query
------------------------------------------------------------
Sentiment: 0.65
Confidence: 0.80
Key Insights: ['Banking stocks showing strength...', ...]
Citations: 4 sources
Model: sonar-pro
Tokens used: 1234

✅ All tests passed! Comet is ready to use.
```

---

## 📊 Quick Usage Examples

### From Python Script

```python
from app.comet.mcp_client_perplexity import CometMCP
import asyncio

async def main():
    comet = CometMCP()
    
    # Simple query
    result = await comet.query(
        "What's the sentiment on Indian banking stocks today?"
    )
    
    print(f"Sentiment: {result['sentiment']}")
    print(f"Insights: {result['key_insights']}")

asyncio.run(main())
```

### From Jupyter Notebook

```python
from app.comet.mcp_client_perplexity import MCPClient

# Synchronous client for notebooks
comet = MCPClient()

result = comet.query("What's happening with RELIANCE today?")
print(result['key_insights'])
```

### From FastAPI (API Call)

```bash
curl -X POST "http://localhost:8000/api/comet/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Market sentiment on IT stocks?",
    "model": "pro"
  }'
```

---

## 🎯 Common Use Cases

### 1. **Validate Trading Signals**

Before entering a trade based on technical signals:

```python
comet = CometMCP()

result = await comet.analyze_with_template(
    "signal_analysis",
    {
        "symbol": "RELIANCE",
        "signal_type": "BULLISH",
        "entry_price": 2500,
        "current_price": 2510,
        "timeframe": "1h",
        "indicators": "RSI: 65, MACD bullish",
        "market_context": "Strong uptrend"
    }
)

if result['sentiment'] > 0.6 and result['confidence'] > 0.7:
    print("✅ Signal validated by AI")
else:
    print("⚠️ Weak fundamental support")
```

### 2. **Pre-Market Briefing**

Get market overview before trading:

```python
result = await comet.query(
    "What happened in global markets overnight? "
    "How might this affect Indian markets today?"
)
```

### 3. **Real-Time News Monitoring**

Check for breaking news on your positions:

```python
for symbol in ["RELIANCE", "HDFCBANK", "TCS"]:
    result = await comet.query(
        f"Any breaking news on {symbol} in last 4 hours?"
    )
    if result['sentiment'] != 0.5:  # Non-neutral
        print(f"🔔 Alert on {symbol}")
```

### 4. **Position Review**

Get AI perspective on open positions:

```python
result = await comet.analyze({
    "query": f"I'm holding RELIANCE at ₹2450, now at ₹2510 (5 days). "
             f"Should I hold, add, or exit?",
    "symbols": ["RELIANCE"],
    "focus": "position_management"
})
```

---

## 💰 Cost Management

### Perplexity Pro Limits
- **$20/month subscription**
- **~300 queries/day** (600 if using standard model)
- **Each query:** ~1000-2000 tokens

### Token Usage Tips

1. **Check usage:**
```python
result = await comet.query("...")
print(f"Tokens used: {result['usage']['total_tokens']}")
```

2. **Use appropriate models:**
   - `pro`: Real-time news/data (default, more tokens)
   - `standard`: General queries (fewer tokens)
   - `reasoning`: Complex analysis (most tokens)

3. **Cache results:**
```python
# Don't query same thing repeatedly
# Cache market sentiment for 1 hour
@lru_cache(maxsize=100)
def get_cached_sentiment(date_hour: str):
    return comet.query("Market sentiment?")
```

4. **Batch queries when possible:**
```python
# Instead of 5 separate queries, ask one comprehensive question
result = await comet.query(
    "Analyze sentiment and outlook for RELIANCE, TCS, HDFCBANK, ICICIBANK, and INFY"
)
```

---

## 🔧 Configuration

### Models Available

```python
# In your code
result = await comet.query("...", model="pro")  # Default
result = await comet.query("...", model="standard")  # Faster
result = await comet.query("...", model="reasoning")  # Deep analysis
```

### Conversation Context

Maintain context across multiple queries:

```python
conv_id = "my_session_123"

# First query
await comet.analyze(
    {"query": "What's happening with NIFTY?"}, 
    conversation_id=conv_id
)

# Follow-up (remembers context)
await comet.analyze(
    {"query": "Should I buy or wait?"},  # Knows you're asking about NIFTY
    conversation_id=conv_id
)
```

### Custom System Prompt

Edit `backend/app/comet/mcp_client_perplexity.py` → `_load_system_prompt()` to customize Comet's behavior.

---

## 📁 Files Reference

| File | Purpose |
|------|---------|
| `app/comet/mcp_client_perplexity.py` | Main Comet client |
| `app/api/comet.py` | FastAPI routes |
| `test_comet_perplexity.py` | Test script |
| `prompts/templates/*.txt` | Prompt templates |
| `COMET_USAGE_EXAMPLES.md` | Detailed examples |
| `PERPLEXITY_PRO_IMPLEMENTATION.md` | Complete guide |

---

## 🐛 Troubleshooting

### "PERPLEXITY_API_KEY not found"

- Check `.env` file has the key
- Restart your application
- Verify key is valid at https://www.perplexity.ai/settings/api

### "Rate limit exceeded"

- You've used 300 queries today
- Wait until next day or upgrade to higher tier
- Use `standard` model for non-critical queries

### "Connection error"

- Check internet connection
- Verify Perplexity API status
- Check firewall/proxy settings

### Import errors

```bash
pip install openai loguru python-dotenv
```

---

## 📚 Next Steps

1. ✅ **Test basic functionality** - Run `test_comet_perplexity.py`
2. 📖 **Review examples** - Check `COMET_USAGE_EXAMPLES.md`
3. 🔧 **Customize prompts** - Edit templates in `prompts/templates/`
4. 🚀 **Integrate into strategy** - Add validation to your entry logic
5. 📊 **Monitor usage** - Track token consumption
6. 🎯 **Optimize** - Cache results, batch queries

---

## ✨ Key Benefits

- **Real-time intelligence**: Get current news and sentiment
- **Validation**: Confirm technical signals with fundamental context
- **Risk assessment**: Identify risks you might have missed
- **Sector rotation**: Spot trends early
- **Time-saving**: AI does research in seconds

---

**Ready to use!** Start with the test script, then integrate into your trading workflow.

For detailed examples, see `COMET_USAGE_EXAMPLES.md`  
For implementation details, see `PERPLEXITY_PRO_IMPLEMENTATION.md`
