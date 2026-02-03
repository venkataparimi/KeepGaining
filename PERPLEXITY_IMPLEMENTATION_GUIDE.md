# Perplexity Pro Implementation Guide

## 🚀 Quick Start - Leverage Your Perplexity Pro

Your Perplexity Pro subscription gives you access to powerful AI capabilities. Here's how to integrate it with KeepGaining for trading intelligence.

---

## 📋 Step 1: Get Your Perplexity API Key

1. **Visit:** https://www.perplexity.ai/settings/api
2. **Generate API Key** (requires Pro subscription)
3. **Copy the key** - you'll need it in the next step

---

## 🔧 Step 2: Configure Environment

Add your Perplexity API key to `.env` file:

```bash
# Navigate to backend directory
cd C:\code\KeepGaining\backend

# Edit .env file
notepad .env
```

Add this line to your `.env`:

```env
# Perplexity API (Comet AI)
PERPLEXITY_API_KEY=pplx-your-api-key-here
```

**Save the file.**

---

## 🎯 Step 3: Update Comet Client for Perplexity

The current `mcp_client.py` uses Anthropic. Let's add Perplexity support:

### Option A: Quick Integration (Recommended)

Perplexity API is **OpenAI-compatible**, so we can use it with minimal changes:

```python
# In mcp_client.py
import os
from openai import OpenAI

class CometMCP:
    def __init__(self):
        perplexity_key = os.getenv("PERPLEXITY_API_KEY")
        if perplexity_key:
            # Use Perplexity with OpenAI SDK
            self.client = OpenAI(
                api_key=perplexity_key,
                base_url="https://api.perplexity.ai"
            )
            self.model = "sonar-pro"  # Best for your Pro subscription
        else:
            logger.warning("No PERPLEXITY_API_KEY found")
            self.client = None
```

### Option B: Direct HTTP Integration

If you prefer direct API calls:

```python
import httpx

async def analyze_with_perplexity(self, prompt: str) -> Dict:
    """Direct Perplexity API call"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('PERPLEXITY_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "sonar-pro",
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 2000
            }
        )
        return response.json()
```

---

## 💡 Step 4: Choose Your Perplexity Models

With Perplexity Pro, you have access to multiple models:

| Model | Best For | Use Case |
|-------|----------|----------|
| **sonar-pro** | Real-time market data | News analysis, sentiment, breaking events |
| **sonar** | General queries | Technical analysis support |
| **sonar-reasoning** | Complex analysis | Multi-factor decision making |

**Recommendation:** Start with `sonar-pro` for real-time market intelligence.

---

## 🎨 Step 5: Leverage Perplexity's Unique Features

### Feature 1: Real-Time Web Access
Perplexity searches the internet in real-time. Perfect for:

```python
# Example: Get latest news impact
prompt = """
Analyze the impact of today's news on {symbol}:
- Recent price action: {price_data}
- Technical signals: {indicators}
- Current market sentiment

What's the latest news affecting this stock today?
Provide actionable trading insights.
"""
```

### Feature 2: Citations
Perplexity provides source citations. Use this to:
- Verify news authenticity
- Track sentiment sources
- Build confidence scores

```python
result = await comet.analyze(context)
# Perplexity returns: result['citations'] = [list of URLs]
```

### Feature 3: Follow-up Queries
Maintain conversation context:

```python
# Initial query
analysis1 = await comet.analyze({
    "query": "What's the sentiment on banking stocks today?"
}, conversation_id="session_1")

# Follow-up
analysis2 = await comet.analyze({
    "query": "How does this affect HDFCBANK specifically?"
}, conversation_id="session_1")  # Same ID = context maintained
```

---

## 🔥 Step 6: Implement Key Use Cases

### Use Case 1: Pre-Market Intelligence

```python
from app.comet.mcp_client import CometMCP
from app.comet.prompt_manager import PromptManager

async def get_premarket_intelligence():
    """Get market intelligence before trading starts"""
    comet = CometMCP()
    pm = PromptManager()
    
    # Use market_context template
    prompt = pm.format_prompt(
        "market_context",
        market_indices="NIFTY: 22000 (+0.5%), BANKNIFTY: 47500 (+0.8%)",
        global_markets="US: S&P +0.3%, Asia: Mixed",
        news_headlines="RBI policy decision today, Q3 earnings season starts",
        sector_performance="IT: Strong, Banking: Moderate, Auto: Weak",
        market_breadth="Advances: 1200, Declines: 800"
    )
    
    result = await comet.analyze({
        "query": prompt,
        "focus": "trading_opportunities"
    })
    
    return result
```

### Use Case 2: Signal Validation

```python
async def validate_trading_signal(signal: dict):
    """Validate technical signal with fundamental/news data"""
    comet = CometMCP()
    pm = PromptManager()
    
    prompt = pm.format_prompt(
        "signal_analysis",
        symbol=signal['symbol'],
        signal_type=signal['type'],  # BULLISH/BEARISH
        entry_price=signal['entry'],
        current_price=signal['current'],
        timeframe=signal['timeframe'],
        indicators=signal['technical_summary'],
        market_context=signal.get('market_state', 'Unknown')
    )
    
    analysis = await comet.analyze({
        "query": prompt,
        "require_citations": True  # Get news sources
    })
    
    # Decision logic
    if analysis['sentiment'] > 0.7 and analysis['confidence'] > 0.6:
        return "STRONG_BUY"
    elif analysis['sentiment'] > 0.5:
        return "BUY"
    else:
        return "SKIP"
```

### Use Case 3: Real-Time News Monitoring

```python
async def monitor_stock_news(symbol: str):
    """Monitor real-time news for a stock"""
    comet = CometMCP()
    
    result = await comet.analyze({
        "query": f"""
        Latest breaking news and sentiment for {symbol}:
        - What happened in the last 1 hour?
        - Is it material for stock price?
        - Immediate trading implications?
        
        Be specific and cite sources.
        """,
        "require_real_time": True
    })
    
    return {
        "symbol": symbol,
        "sentiment": result['sentiment'],
        "news": result['key_insights'],
        "action": result['trading_signals'][0] if result['trading_signals'] else None,
        "sources": result.get('citations', [])
    }
```

### Use Case 4: Risk Assessment

```python
async def assess_portfolio_risk(positions: list):
    """Assess portfolio risk with current market conditions"""
    comet = CometMCP()
    pm = PromptManager()
    
    positions_str = "\n".join([
        f"- {p['symbol']}: {p['quantity']} shares @ ₹{p['entry_price']} "
        f"(Current: ₹{p['current_price']}, P&L: {p['pnl']:.1f}%)"
        for p in positions
    ])
    
    prompt = pm.format_prompt(
        "risk_assessment",
        position_details=positions_str,
        portfolio_metrics=f"Total Value: ₹{sum(p['value'] for p in positions):,.0f}",
        market_conditions="Volatile, High VIX",
        current_exposure=f"{len(positions)} positions",
        time_horizon="Intraday"
    )
    
    risk_analysis = await comet.analyze({
        "query": prompt,
        "focus": "risk_mitigation"
    })
    
    return risk_analysis
```

---

## 🔄 Step 7: Integration Points

### A. Strategy Signal Enhancement

Add Comet validation to your strategies:

```python
# In app/strategies/base_strategy.py or specific strategy
from app.comet.mcp_client import CometMCP

class EnhancedStrategy(BaseStrategy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.comet = CometMCP()
    
    async def generate_signal(self, df, symbol):
        # Your existing technical signal
        technical_signal = super().generate_signal(df, symbol)
        
        if technical_signal['action'] in ['BUY', 'SELL']:
            # Validate with Comet
            validation = await self.validate_with_comet(technical_signal)
            
            # Adjust confidence based on AI analysis
            if validation['sentiment'] < 0.3:  # Negative sentiment
                technical_signal['confidence'] *= 0.5  # Reduce confidence
            elif validation['sentiment'] > 0.7:  # Positive sentiment
                technical_signal['confidence'] *= 1.2  # Increase confidence
            
            technical_signal['ai_validation'] = validation
        
        return technical_signal
```

### B. Pre-Trade Checklist

```python
# In app/execution/trade_executor.py
async def pre_trade_check(self, trade_plan: dict):
    """Run AI-powered pre-trade validation"""
    comet = CometMCP()
    
    # Check 1: News sentiment
    news_check = await comet.analyze({
        "query": f"Any breaking news on {trade_plan['symbol']} in last 30 minutes?"
    })
    
    if news_check['sentiment'] < 0.3:
        logger.warning(f"Negative news detected for {trade_plan['symbol']}")
        return {"approved": False, "reason": "Adverse news"}
    
    # Check 2: Market conditions
    market_check = await comet.analyze({
        "query": "Current market sentiment and volatility - suitable for trading?"
    })
    
    if market_check['risks']:
        logger.info(f"Market risks identified: {market_check['risks']}")
    
    return {
        "approved": True,
        "confidence": news_check['confidence'],
        "risks": market_check['risks']
    }
```

### C. Post-Trade Analysis

```python
async def analyze_trade_performance(trade_result: dict):
    """Analyze why trade succeeded or failed"""
    comet = CometMCP()
    
    analysis = await comet.analyze({
        "query": f"""
        Trade Analysis:
        - Symbol: {trade_result['symbol']}
        - Entry: ₹{trade_result['entry']}, Exit: ₹{trade_result['exit']}
        - P&L: {trade_result['pnl']:.1f}%
        - Duration: {trade_result['duration']}
        - Entry reason: {trade_result['entry_reason']}
        
        What market factors influenced this outcome?
        What can we learn for future trades?
        """
    })
    
    return analysis
```

---

## 📊 Step 8: Build a Trading Dashboard

Create a FastAPI endpoint for real-time AI insights:

```python
# In app/api/routes/comet.py
from fastapi import APIRouter, HTTPException
from app.comet.mcp_client import CometMCP

router = APIRouter(prefix="/api/comet", tags=["comet"])

@router.get("/market-pulse")
async def get_market_pulse():
    """Get real-time market intelligence"""
    comet = CometMCP()
    
    pulse = await comet.analyze({
        "query": """
        Current market pulse:
        1. Top 3 trending stocks on NSE
        2. Major news/events affecting Indian markets
        3. Sector rotation signals
        4. Key levels to watch
        
        Provide actionable insights for intraday trading.
        """
    })
    
    return pulse

@router.post("/validate-signal")
async def validate_signal(signal: dict):
    """Validate a trading signal with AI"""
    comet = CometMCP()
    pm = PromptManager()
    
    prompt = pm.format_prompt("signal_analysis", **signal)
    validation = await comet.analyze({"query": prompt})
    
    return {
        "signal": signal,
        "ai_validation": validation,
        "recommendation": "TAKE" if validation['confidence'] > 0.6 else "SKIP"
    }

@router.get("/news/{symbol}")
async def get_stock_news(symbol: str):
    """Get latest news and sentiment for a stock"""
    comet = CometMCP()
    
    news = await comet.analyze({
        "query": f"Latest news and sentiment for {symbol}. Trading implications?"
    })
    
    return news
```

---

## 🎯 Step 9: Advanced Features

### Feature: Multi-Timeframe Analysis

```python
async def multi_timeframe_analysis(symbol: str):
    """Analyze across multiple timeframes"""
    comet = CometMCP()
    
    # Parallel queries for efficiency
    short_term = comet.analyze({
        "query": f"{symbol} - Intraday (5min/15min) trading opportunities"
    })
    
    medium_term = comet.analyze({
        "query": f"{symbol} - Swing trading (1-5 days) outlook"
    })
    
    long_term = comet.analyze({
        "query": f"{symbol} - Investment (weeks/months) perspective"
    })
    
    results = await asyncio.gather(short_term, medium_term, long_term)
    
    return {
        "intraday": results[0],
        "swing": results[1],
        "investment": results[2]
    }
```

### Feature: Sector Rotation Detection

```python
async def detect_sector_rotation():
    """Detect sector rotation using AI"""
    comet = CometMCP()
    
    rotation = await comet.analyze({
        "query": """
        Analyze current sector rotation in Indian markets:
        - Which sectors are gaining momentum?
        - Which sectors are losing steam?
        - What's driving these moves?
        - Top 3 stocks in emerging strong sectors
        
        Provide specific actionable insights.
        """
    })
    
    return rotation
```

### Feature: Earnings Intelligence

```python
async def earnings_intelligence(symbols: list):
    """Get earnings-related intelligence"""
    comet = CometMCP()
    
    queries = [
        f"{symbol} - Recent earnings, analyst sentiment, price targets?"
        for symbol in symbols
    ]
    
    results = await asyncio.gather(*[
        comet.analyze({"query": q}) for q in queries
    ])
    
    return dict(zip(symbols, results))
```

---

## 💰 Cost Optimization

### Perplexity Pro Limits
- **API Calls:** Generous limits with Pro
- **Rate Limits:** ~60 requests/minute
- **Cost:** Included in your Pro subscription

### Best Practices

1. **Cache Results**
   ```python
   from functools import lru_cache
   import time
   
   @lru_cache(maxsize=100)
   def cached_analysis(query: str, timestamp: int):
       # timestamp = int(time.time() / 300)  # 5-minute cache
       return await comet.analyze({"query": query})
   ```

2. **Batch Queries**
   ```python
   # Instead of 10 separate calls
   result = await comet.analyze({
       "query": f"Analyze these stocks: {', '.join(symbols)}"
   })
   ```

3. **Smart Triggers**
   ```python
   # Only call Comet when needed
   if signal['confidence'] < 0.7:  # Low confidence
       validation = await comet.analyze(...)  # Get AI opinion
   ```

---

## 📝 Step 10: Testing & Validation

### Test 1: Basic Connection

```python
# backend/scripts/test_comet_perplexity.py
import asyncio
from app.comet.mcp_client import CometMCP

async def test_connection():
    comet = CometMCP()
    
    result = await comet.analyze({
        "query": "What's the current sentiment on NIFTY 50?"
    })
    
    print("✅ Connection successful!")
    print(f"Sentiment: {result['sentiment']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Insights: {result['key_insights']}")

if __name__ == "__main__":
    asyncio.run(test_connection())
```

Run:
```bash
cd backend
python scripts/test_comet_perplexity.py
```

### Test 2: Template Integration

```python
from app.comet.prompt_manager import PromptManager
from app.comet.mcp_client import CometMCP

async def test_templates():
    pm = PromptManager()
    comet = CometMCP()
    
    # Test signal analysis template
    prompt = pm.format_prompt(
        "signal_analysis",
        symbol="RELIANCE",
        signal_type="BULLISH",
        entry_price=2800,
        current_price=2850,
        timeframe="15m",
        indicators="RSI: 65, MACD: Bullish crossover",
        market_context="Strong market, IT sector leading"
    )
    
    result = await comet.analyze({"query": prompt})
    print(f"✅ Template test passed!")
    print(f"Recommendation: {result['trading_signals'][0]['action']}")

asyncio.run(test_templates())
```

---

## 🚀 Quick Win: Implement Today

**Minimal Viable Integration (30 minutes):**

1. **Add API key** to `.env`
2. **Update `mcp_client.py`** with Perplexity support
3. **Create test script** to validate connection
4. **Add one endpoint** to your API for market pulse

**Example endpoint:**
```python
@router.get("/market-now")
async def market_now():
    comet = CometMCP()
    pulse = await comet.analyze({
        "query": "Top 3 things happening in Indian markets RIGHT NOW"
    })
    return pulse
```

**Test it:**
```bash
curl http://localhost:8000/api/comet/market-now
```

---

## 📚 Resources

- **Perplexity API Docs:** https://docs.perplexity.ai/
- **Model Comparison:** https://docs.perplexity.ai/guides/model-cards
- **OpenAI SDK Compatibility:** https://docs.perplexity.ai/guides/openai-sdk-migration

---

## 🎯 Next Steps

1. ✅ Add `PERPLEXITY_API_KEY` to `.env`
2. ✅ Update `mcp_client.py` for Perplexity
3. ✅ Test connection with simple query
4. ✅ Integrate into one strategy as proof-of-concept
5. ✅ Build dashboard endpoint for market intelligence
6. ✅ Expand to all strategies based on results

---

**Ready to implement? Let me know which part you want to start with!**
