# Comet AI Integration Examples

Complete examples showing how to leverage Perplexity Pro subscription in your trading workflows.

---

## 📋 Table of Contents

1. [Strategy Signal Validation](#1-strategy-signal-validation)
2. [Real-Time News Monitoring](#2-real-time-news-monitoring)
3. [Pre-Market Analysis](#3-pre-market-analysis)
4. [Risk Assessment](#4-risk-assessment)
5. [Sector Rotation Detection](#5-sector-rotation-detection)
6. [Position Review](#6-position-review)
7. [Notebook Usage](#7-notebook-usage)
8. [FastAPI Integration](#8-fastapi-integration)

---

## 1. Strategy Signal Validation

**Use Case:** Before entering a trade based on technical signals, validate with real-time fundamental/news context.

```python
from app.comet.mcp_client_perplexity import CometMCP
import asyncio

async def validate_trade_signal():
    comet = CometMCP()
    
    # Your strategy generated a signal
    signal = {
        "symbol": "RELIANCE",
        "action": "BUY",
        "entry": 2500,
        "technical": "MACD bullish crossover, RSI 58, above 20 EMA"
    }
    
    # Validate with Comet
    result = await comet.analyze_with_template(
        "signal_analysis",
        {
            "symbol": signal["symbol"],
            "signal_type": "BULLISH_CROSSOVER",
            "entry_price": signal["entry"],
            "current_price": 2505,
            "timeframe": "1h",
            "indicators": signal["technical"],
            "market_context": "Nifty trending up, banking sector strong"
        }
    )
    
    # Check if fundamentals/news support the signal
    if result["sentiment"] > 0.6 and result["confidence"] > 0.7:
        print(f"✅ CONFIRMED: {signal['symbol']} signal validated")
        print(f"Sentiment: {result['sentiment']}")
        print(f"Key Insights: {result['key_insights'][:2]}")
        
        # Check for contradictory signals
        if result["risks"]:
            print(f"⚠️ Risks detected: {result['risks']}")
        
        return "PROCEED"
    else:
        print(f"❌ REJECTED: Weak fundamental support")
        return "SKIP"

# Run
asyncio.run(validate_trade_signal())
```

---

## 2. Real-Time News Monitoring

**Use Case:** Monitor breaking news that could affect your positions or watchlist.

```python
from app.comet.mcp_client_perplexity import CometMCP
import asyncio
from datetime import datetime

async def monitor_market_news(watchlist: list[str]):
    comet = CometMCP()
    
    # Check general market sentiment
    market_result = await comet.query(
        "What are the top 3 breaking news affecting Indian stock market in the last 2 hours?"
    )
    
    print(f"\n🌍 Market News ({datetime.now().strftime('%H:%M')})")
    print("=" * 60)
    for insight in market_result["key_insights"][:3]:
        print(f"• {insight}")
    
    if market_result["citations"]:
        print(f"\n📰 Sources: {len(market_result['citations'])} articles")
    
    # Check specific stocks in watchlist
    for symbol in watchlist:
        result = await comet.analyze({
            "query": f"Any breaking news or developments on {symbol} in last 4 hours?",
            "symbols": [symbol],
            "focus": "news_impact"
        })
        
        if result["sentiment"] != 0.5:  # Non-neutral
            print(f"\n🔔 ALERT: {symbol}")
            print(f"Sentiment: {result['sentiment']} | Confidence: {result['confidence']}")
            for insight in result["key_insights"][:2]:
                print(f"  • {insight}")
    
    return market_result

# Monitor your positions
watchlist = ["RELIANCE", "HDFCBANK", "TCS", "INFY"]
asyncio.run(monitor_market_news(watchlist))
```

---

## 3. Pre-Market Analysis

**Use Case:** Get AI-powered market overview before trading hours.

```python
from app.comet.mcp_client_perplexity import CometMCP
import asyncio
from datetime import datetime

async def pre_market_briefing():
    comet = CometMCP()
    
    print(f"\n📊 Pre-Market Briefing - {datetime.now().strftime('%d %b %Y')}")
    print("=" * 60)
    
    # Global cues
    global_result = await comet.query(
        "What happened in global markets overnight (US, Europe, Asia)? "
        "How might this affect Indian markets today?"
    )
    
    print("\n🌐 Global Market Cues:")
    for i, insight in enumerate(global_result["key_insights"][:3], 1):
        print(f"{i}. {insight}")
    
    # Sector outlook
    sector_result = await comet.query(
        "Which sectors in Indian stock market are likely to perform well today? "
        "Any sector-specific news or events?"
    )
    
    print("\n📈 Sector Outlook:")
    for signal in sector_result.get("trading_signals", []):
        print(f"• {signal['action']}: {signal.get('reasoning', '')[:100]}")
    
    # Key events
    events_result = await comet.query(
        "Any important economic data releases, corporate results, or policy decisions "
        "scheduled for Indian market today?"
    )
    
    print("\n📅 Key Events Today:")
    for i, insight in enumerate(events_result["key_insights"][:3], 1):
        print(f"{i}. {insight}")
    
    # Trading plan recommendation
    print(f"\n💡 Overall Market Sentiment: {global_result['sentiment']:.2f}")
    print(f"Confidence: {global_result['confidence']:.2f}")
    
    return {
        "global_cues": global_result,
        "sector_outlook": sector_result,
        "events": events_result
    }

# Run before market open (9:15 AM)
asyncio.run(pre_market_briefing())
```

---

## 4. Risk Assessment

**Use Case:** Evaluate risk before adding to position or entering high-risk trade.

```python
from app.comet.mcp_client_perplexity import CometMCP
import asyncio

async def assess_trade_risk(trade_plan: dict):
    comet = CometMCP()
    
    result = await comet.analyze_with_template(
        "risk_assessment",
        {
            "position_details": f"{trade_plan['quantity']} shares of {trade_plan['symbol']} at ₹{trade_plan['entry']}",
            "portfolio_value": trade_plan['portfolio_value'],
            "position_size": trade_plan['position_size_pct'],
            "stop_loss": trade_plan['stop_loss'],
            "target": trade_plan['target'],
            "holding_period": trade_plan['holding_period'],
            "market_conditions": trade_plan['market_context']
        }
    )
    
    print(f"\n🎯 Risk Assessment: {trade_plan['symbol']}")
    print("=" * 60)
    print(f"Position Size: {trade_plan['position_size_pct']}% of portfolio")
    print(f"Risk/Reward: 1:{trade_plan['rr_ratio']}")
    
    print(f"\n🔍 AI Risk Analysis:")
    print(f"Risk Score: {result['sentiment']:.2f} (lower = higher risk)")
    print(f"Confidence: {result['confidence']:.2f}")
    
    print(f"\n⚠️ Key Risks:")
    for i, risk in enumerate(result['risks'][:5], 1):
        print(f"{i}. {risk}")
    
    print(f"\n💡 Recommendations:")
    for insight in result['key_insights'][:3]:
        print(f"• {insight}")
    
    # Decision
    if result['sentiment'] < 0.4:
        print(f"\n❌ HIGH RISK - Consider reducing position size or skipping")
    elif result['sentiment'] < 0.6:
        print(f"\n⚠️ MODERATE RISK - Proceed with caution and tight stops")
    else:
        print(f"\n✅ ACCEPTABLE RISK - Can proceed as planned")
    
    return result

# Example trade
trade = {
    "symbol": "NIFTY50",
    "quantity": 50,
    "entry": 22000,
    "stop_loss": 21800,
    "target": 22400,
    "position_size_pct": 15,
    "portfolio_value": 1000000,
    "rr_ratio": 2,
    "holding_period": "intraday",
    "market_context": "Choppy market, high volatility"
}

asyncio.run(assess_trade_risk(trade))
```

---

## 5. Sector Rotation Detection

**Use Case:** Identify sector rotation trends early for momentum trading.

```python
from app.comet.mcp_client_perplexity import CometMCP
import asyncio

async def detect_sector_rotation():
    comet = CometMCP()
    
    # Use reasoning model for complex analysis
    result = await comet.analyze(
        {
            "query": """Analyze current sector rotation in Indian stock market:
            1. Which sectors are showing OUTPERFORMANCE in last 5 trading days?
            2. Which sectors are UNDERPERFORMING or losing momentum?
            3. Is there money rotating FROM one sector TO another?
            4. What's driving this rotation (FII flows, earnings, policy, global factors)?
            
            Provide specific sectors and actionable recommendations.""",
            "focus": "sector_momentum",
            "timeframe": "short_term"
        },
        model="reasoning"  # Use reasoning model for deep analysis
    )
    
    print("\n🔄 Sector Rotation Analysis")
    print("=" * 60)
    
    print("\n📈 Strong Sectors (Accumulation):")
    strong_sectors = [s for s in result.get("trading_signals", []) 
                      if s.get("action") in ["BUY", "WATCH"]]
    for signal in strong_sectors:
        print(f"• {signal.get('symbol', 'SECTOR')}: {signal.get('reasoning', '')[:120]}")
    
    print("\n📉 Weak Sectors (Distribution):")
    weak_sectors = [s for s in result.get("trading_signals", []) 
                    if s.get("action") in ["SELL", "AVOID"]]
    for signal in weak_sectors:
        print(f"• {signal.get('symbol', 'SECTOR')}: {signal.get('reasoning', '')[:120]}")
    
    print("\n💡 Key Rotation Drivers:")
    for insight in result["key_insights"][:4]:
        print(f"• {insight}")
    
    print(f"\n📊 Confidence: {result['confidence']:.2f}")
    print(f"Sources: {len(result.get('citations', []))} references")
    
    return result

# Run daily or weekly
asyncio.run(detect_sector_rotation())
```

---

## 6. Position Review

**Use Case:** Review open positions with current market context.

```python
from app.comet.mcp_client_perplexity import CometMCP
import asyncio

async def review_open_positions(positions: list):
    comet = CometMCP()
    
    print("\n📊 Position Review with AI Intelligence")
    print("=" * 60)
    
    for pos in positions:
        pnl_pct = ((pos['current_price'] - pos['entry_price']) / pos['entry_price']) * 100
        
        print(f"\n{pos['symbol']} | Entry: ₹{pos['entry_price']} | Current: ₹{pos['current_price']} | P&L: {pnl_pct:.2f}%")
        print("-" * 60)
        
        # Get AI perspective on this position
        result = await comet.analyze({
            "query": f"""Analyze my position in {pos['symbol']}:
            - Entry: ₹{pos['entry_price']} ({pos['days_held']} days ago)
            - Current: ₹{pos['current_price']}
            - P&L: {pnl_pct:.2f}%
            
            Should I HOLD, ADD, TRIM, or EXIT? Consider recent news, technical outlook, and market conditions.""",
            "symbols": [pos['symbol']],
            "focus": "position_management"
        })
        
        # Show recommendation
        if result.get("trading_signals"):
            action = result["trading_signals"][0].get("action", "HOLD")
            reasoning = result["trading_signals"][0].get("reasoning", "")
            print(f"🤖 AI Recommendation: {action}")
            print(f"   Reasoning: {reasoning[:150]}...")
        
        # Show key insights
        if result["key_insights"]:
            print(f"💡 Key Points:")
            for insight in result["key_insights"][:2]:
                print(f"   • {insight[:120]}...")
        
        # Show risks
        if result["risks"]:
            print(f"⚠️ Risks: {', '.join(result['risks'][:2])}")
    
    return True

# Example positions
my_positions = [
    {"symbol": "RELIANCE", "entry_price": 2450, "current_price": 2510, "days_held": 5},
    {"symbol": "HDFCBANK", "entry_price": 1680, "current_price": 1655, "days_held": 12},
    {"symbol": "TCS", "entry_price": 3800, "current_price": 3850, "days_held": 8}
]

asyncio.run(review_open_positions(my_positions))
```

---

## 7. Notebook Usage

**Use Case:** Interactive analysis in Jupyter notebooks.

```python
# In Jupyter notebook
from app.comet.mcp_client_perplexity import MCPClient

# Initialize synchronous client (works in notebooks)
comet = MCPClient()

# Simple query
result = comet.query("What's the sentiment on IT stocks today?")

print(f"Sentiment: {result['sentiment']}")
print(f"Confidence: {result['confidence']}")
print("\nInsights:")
for insight in result['key_insights']:
    print(f"• {insight}")

# Visualize sentiment
import matplotlib.pyplot as plt

sentiment_score = result['sentiment']
confidence = result['confidence']

fig, ax = plt.subplots(1, 2, figsize=(12, 4))

# Sentiment gauge
ax[0].barh(['Sentiment'], [sentiment_score], color='green' if sentiment_score > 0.5 else 'red')
ax[0].set_xlim(0, 1)
ax[0].set_title('Market Sentiment')
ax[0].axvline(0.5, color='gray', linestyle='--', label='Neutral')

# Confidence
ax[1].barh(['Confidence'], [confidence], color='blue')
ax[1].set_xlim(0, 1)
ax[1].set_title('AI Confidence')

plt.tight_layout()
plt.show()

# Analysis with template
signal_result = comet.analyze_with_template(
    "signal_analysis",
    {
        "symbol": "NIFTY",
        "signal_type": "BULLISH",
        "entry_price": 22000,
        "current_price": 22050,
        "timeframe": "15m",
        "indicators": "RSI: 65, MACD: Bullish",
        "market_context": "Strong uptrend"
    }
)

# Display results in dataframe
import pandas as pd

if signal_result.get('trading_signals'):
    df = pd.DataFrame(signal_result['trading_signals'])
    display(df)
```

---

## 8. FastAPI Integration

**Use Case:** Call Comet from your backend API.

```python
# In your strategy execution code
from app.comet.mcp_client_perplexity import CometMCP

class EnhancedTradingStrategy:
    def __init__(self):
        self.comet = CometMCP()
    
    async def should_enter_trade(self, signal: dict) -> bool:
        """Validate technical signal with AI intelligence"""
        
        # Get AI validation
        result = await self.comet.analyze_with_template(
            "signal_analysis",
            {
                "symbol": signal["symbol"],
                "signal_type": signal["type"],
                "entry_price": signal["entry"],
                "current_price": signal["current"],
                "timeframe": signal["timeframe"],
                "indicators": signal["indicators"],
                "market_context": signal["context"]
            }
        )
        
        # Combine technical + AI score
        technical_score = signal.get("score", 0.5)
        ai_sentiment = result["sentiment"]
        ai_confidence = result["confidence"]
        
        # Weighted combination
        final_score = (technical_score * 0.6) + (ai_sentiment * 0.3) + (ai_confidence * 0.1)
        
        # Check for red flags
        has_major_risks = any("major" in risk.lower() or "high" in risk.lower() 
                             for risk in result.get("risks", []))
        
        if has_major_risks:
            logger.warning(f"Comet flagged major risks for {signal['symbol']}")
            return False
        
        # Decision threshold
        return final_score > 0.65
    
    async def manage_position(self, position: dict) -> str:
        """Get AI recommendation for position management"""
        
        result = await self.comet.analyze({
            "query": f"I'm holding {position['symbol']} with {position['pnl_pct']}% P&L. "
                    f"Current market: {position['market_context']}. Should I hold, add, or exit?",
            "symbols": [position['symbol']],
            "focus": "position_management"
        })
        
        if result.get("trading_signals"):
            return result["trading_signals"][0].get("action", "HOLD")
        
        return "HOLD"
```

**API Endpoint Usage:**

```python
# From frontend or external service
import httpx

async def validate_signal_via_api(signal: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/comet/validate-signal",
            json={
                "symbol": signal["symbol"],
                "signal_type": signal["type"],
                "entry_price": signal["entry"],
                "current_price": signal["current"],
                "timeframe": signal["timeframe"],
                "indicators": signal["indicators"],
                "market_context": signal["context"]
            }
        )
        return response.json()

# Usage
signal = {
    "symbol": "RELIANCE",
    "type": "BULLISH_BREAKOUT",
    "entry": 2500,
    "current": 2515,
    "timeframe": "1h",
    "indicators": "MACD bullish, RSI 62",
    "context": "Strong sector momentum"
}

result = await validate_signal_via_api(signal)
print(f"AI Validation: {result['sentiment']}")
```

---

## 💡 Best Practices

### 1. **Use Appropriate Models**
- **`pro`**: Real-time market data, news, current events (default)
- **`standard`**: General queries, historical analysis
- **`reasoning`**: Complex analysis requiring deep thinking

### 2. **Manage Token Usage**
- Perplexity Pro: ~$20/month for 300 queries/day
- Each query ~1000-2000 tokens
- Monitor usage via `result['usage']`

### 3. **Cache Results**
```python
# Cache expensive queries
from functools import lru_cache
from datetime import datetime

@lru_cache(maxsize=100)
def get_market_sentiment(date: str, time_hour: int):
    # Only query once per hour
    comet = MCPClient()
    return comet.query("Current market sentiment?")

# Use
sentiment = get_market_sentiment(datetime.now().strftime("%Y-%m-%d"), datetime.now().hour)
```

### 4. **Handle Errors Gracefully**
```python
async def safe_comet_query(question: str, fallback_sentiment=0.5):
    try:
        comet = CometMCP()
        result = await comet.query(question)
        return result
    except Exception as e:
        logger.error(f"Comet query failed: {e}")
        return {
            "sentiment": fallback_sentiment,
            "confidence": 0.0,
            "key_insights": ["AI unavailable, using default sentiment"],
            "error": str(e)
        }
```

### 5. **Combine with Technical Analysis**
Don't replace technical analysis—augment it:
```python
# Technical says BUY + AI confirms = Strong signal
# Technical says BUY + AI warns = Weak signal, skip
# Technical says neutral + AI suggests opportunity = Research more
```

---

## 🎯 Integration Checklist

- [ ] Add `PERPLEXITY_API_KEY` to `.env`
- [ ] Test basic query with `test_comet_perplexity.py`
- [ ] Create prompt templates for your use cases
- [ ] Add Comet validation to strategy entry logic
- [ ] Set up pre-market briefing automation
- [ ] Monitor token usage and costs
- [ ] Add error handling and fallbacks
- [ ] Create dashboard to display AI insights
- [ ] Log AI recommendations for review
- [ ] A/B test signals with vs without AI validation

---

**Next:** See `PERPLEXITY_PRO_IMPLEMENTATION.md` for detailed setup and cost optimization strategies.
