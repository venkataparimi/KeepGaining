"""
Strategy Investigator Service using Local AI (Ollama + Llama 3)
Reverse engineers trading strategies from successful trade examples.
"""

import asyncio
import asyncpg
import json
import requests
import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from decimal import Decimal

# Configuration
DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3"

@dataclass
class TradeExample:
    symbol: str          # Underlying equity symbol (e.g., NIFTY 50, RELIANCE)
    trade_type: str      # CE, PE, or EQUITY
    entry_time: datetime.datetime
    entry_price: float   # Option/Stock price at entry
    strike_price: Optional[float] = None
    expiry_date: Optional[datetime.date] = None

class StrategyInvestigator:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(DB_URL)

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def analyze_trade_example(self, trade: TradeExample) -> Dict[str, Any]:
        """
        Main entry point: Analyzes a specific successful trade to reverse-engineer the strategy.
        """
        await self.connect()
        
        print(f"🔍 Investigating Trade: {trade.trade_type} on {trade.symbol} at {trade.entry_time}")
        
        # 1. Fetch Market Context (Underlying Equity Data)
        # We look at data leading up to the trade (e.g., previous 60 minutes)
        context_data = await self._fetch_market_context(trade)
        
        if not context_data:
            return {"error": "No market data found for this timeframe"}
        
        # 2. Construct Prompt for AI
        prompt = self._construct_analysis_prompt(trade, context_data)
        
        # 3. Query Local AI
        print("🤖 Consulting AI Analyst...")
        ai_response = self._query_ollama(prompt)
        
        # 4. Parse Strategy
        strategy = self._parse_ai_response(ai_response)
        
        return {
            "trade_example": str(trade),
            "derived_strategy": strategy,
            "market_context_summary": f"Analyzed {len(context_data)} candles before entry"
        }

    async def _fetch_market_context(self, trade: TradeExample) -> List[Dict]:
        """
        Fetches candle and indicator data for the underlying asset 
        leading up to the entry time.
        """
        # Look back 2 hours (120 minutes) to see the setup forming
        start_time = trade.entry_time - datetime.timedelta(minutes=120)
        end_time = trade.entry_time
        
        # Find instrument_id for the underlying symbol
        # Note: We look for the INDEX or EQUITY instrument, not the Option contract itself
        # for technical analysis context.
        query_inst = """
            SELECT instrument_id FROM instrument_master 
            WHERE trading_symbol = $1 AND instrument_type IN ('EQUITY', 'INDEX')
            LIMIT 1
        """
        inst_id = await self.pool.fetchval(query_inst, trade.symbol)
        
        if not inst_id:
            print(f"❌ Could not find underlying instrument for {trade.symbol}")
            return []

        # Fetch Indicators + Candlesjoined
        # We prioritize indicator_data but join with price for clarity
        query_data = """
            SELECT 
                i.timestamp,
                c.open, c.high, c.low, c.close, c.volume,
                i.rsi_14, i.sma_20, i.sma_50, 
                i.macd, i.macd_signal, i.macd_histogram,
                i.bb_upper, i.bb_lower,
                i.supertrend, i.supertrend_direction,
                i.adx, i.vwap
            FROM indicator_data i
            JOIN candle_data c ON i.instrument_id = c.instrument_id 
                               AND i.timestamp = c.timestamp
                               AND i.timeframe = c.timeframe
            WHERE i.instrument_id = $1 
            AND i.timeframe = '1m'
            AND i.timestamp >= $2 
            AND i.timestamp <= $3
            ORDER BY i.timestamp ASC
        """
        
        rows = await self.pool.fetch(query_data, inst_id, start_time, end_time)
        
        # Convert to list of dicts for easier processing
        data = []
        for r in rows:
            data.append({
                "time": r['timestamp'].strftime("%H:%M"),
                "price": float(r['close']),
                "rsi": float(r['rsi_14']) if r['rsi_14'] else None,
                "sma20": float(r['sma_20']) if r['sma_20'] else None,
                "macd_hist": float(r['macd_histogram']) if r['macd_histogram'] else None,
                "supertrend": "UP" if r['supertrend_direction'] == 1 else "DOWN",
                "adx": float(r['adx']) if r['adx'] else None,
                "vwap": float(r['vwap']) if r['vwap'] else None
            })
            
        return data

    def _construct_analysis_prompt(self, trade: TradeExample, context: List[Dict]) -> str:
        """
        Creates a detailed prompt for the LLM to analyze the price/indicator action.
        """
        # Summarize the last 5 candles (the immediate entry setup)
        recent_setup = json.dumps(context[-5:], indent=2)
        
        # Describe the trend (first vs last price in the window)
        start_price = context[0]['price']
        end_price = context[-1]['price']
        trend = "UP" if end_price > start_price else "DOWN"
        
        direction = "BOUGHT (Long)" if trade.trade_type in ['CE', 'EQUITY'] else "SOLD/BOUGHT PE (Short)"
        
        return f"""
        You are an expert Algorithmic Trading Strategist.
        
        I executed a successful trade. Help me reverse-engineer the strategy rules based on the technical indicators at the time.
        
        TRADE DETAILS:
        - Asset: {trade.symbol}
        - Action: {direction}
        - Entry Time: {trade.entry_time}
        - Entry Price: {trade.entry_price}
        
        MARKET CONTEXT (Last 5 minutes before entry):
        {recent_setup}
        
        MARKET TREND (Last 2 hours): {trend}
        
        TASK:
        Analyze the indicators (RSI, MACD, Supertrend, VWAP, SMA) effectively.
        Define a clear, rule-based strategy that would trigger this trade.
        
        OUTPUT FORMAT (JSON):
        {{
            "strategy_name": "Creative Name based on analysis",
            "logic_summary": "Why this trade worked",
            "entry_conditions": [
                "Condition 1 (e.g., RSI > 60)",
                "Condition 2 (e.g., Price > VWAP)"
            ],
            "exit_conditions": [
                "Stop Loss rule",
                "Take Profit rule"
            ]
        }}
        """

    def _query_ollama(self, prompt: str) -> Dict:
        """Sends the prompt to the local Ollama instance."""
        try:
            payload = {
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "format": "json"  # Force JSON output if supported by model version
            }
            response = requests.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "{}")
        except Exception as e:
            print(f"Error querying AI: {e}")
            return {}

    def _parse_ai_response(self, response_text: str) -> Dict:
        """Cleans and parses the AI response."""
        try:
            # Attempt to find JSON in the response
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end != -1:
                json_str = response_text[start:end]
                return json.loads(json_str)
            return {"raw_text": response_text}
        except Exception as e:
            return {"error": "Failed to parse AI response", "raw_text": response_text}

# --- usage Example ---
if __name__ == "__main__":
    # Example usage for testing
    async def run_test():
        investigator = StrategyInvestigator()
        
        # Dummy Trade Example (The user will provide real ones)
        example_trade = TradeExample(
            symbol="NIFTY 50",  # We look at the Index data
            trade_type="CE",    # Bullish trade
            entry_time=datetime.datetime(2024, 12, 6, 10, 30), # Example date
            entry_price=150.0   # Option price
        )
        
        result = await investigator.analyze_trade_example(example_trade)
        print("\n=== STRATEGY ANALYSIS RESULT ===")
        print(json.dumps(result, indent=2, default=str))
        
        await investigator.close()

    asyncio.run(run_test())
