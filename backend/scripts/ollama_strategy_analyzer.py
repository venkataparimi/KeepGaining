"""
AI Strategy Discovery Engine - Ollama Integration
Uses local Ollama LLM to identify patterns in trade data

Implements RAG approach with market context.
"""
import asyncio
import aiohttp
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass 
class StrategyHypothesis:
    """A discovered strategy pattern"""
    name: str
    description: str
    entry_rules: List[str]
    exit_rules: List[str]
    common_features: Dict[str, Any]
    confidence: float
    source_trades: List[str]


class OllamaStrategyAnalyzer:
    """Uses Ollama LLM to discover trading strategies from trade data"""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url
        self.model = model
    
    async def check_connection(self) -> bool:
        """Check if Ollama is running"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m['name'] for m in data.get('models', [])]
                        print(f"✅ Connected to Ollama. Available models: {models}")
                        return True
        except Exception as e:
            print(f"❌ Failed to connect to Ollama: {e}")
        return False
    
    async def generate(self, prompt: str, system: str = None) -> str:
        """Generate response from Ollama"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }
        if system:
            payload["system"] = system
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('response', '')
                    else:
                        return f"Error: {resp.status}"
        except Exception as e:
            return f"Error: {e}"
    
    def format_trade_for_llm(self, analysis: Dict) -> str:
        """Format trade analysis for LLM consumption"""
        lines = []
        lines.append(f"Trade: {analysis.get('stock')} {analysis.get('strike')} {analysis.get('option_type')}")
        lines.append(f"Date: {analysis.get('trade_date')}")
        lines.append(f"Entry Time: {analysis.get('entry_time')}")
        lines.append(f"Entry Premium: ₹{analysis.get('entry_premium')}")
        
        if analysis.get('exit_premium'):
            lines.append(f"Exit Premium: ₹{analysis.get('exit_premium')}")
        if analysis.get('pnl'):
            lines.append(f"P&L: ₹{analysis.get('pnl')}")
        
        lines.append(f"\nPrice Features:")
        if analysis.get('spot_price'):
            lines.append(f"  - Spot Price: ₹{analysis.get('spot_price'):.2f}")
        if analysis.get('range_position'):
            lines.append(f"  - Position in Morning Range: {analysis.get('range_position'):.1f}%")
        if analysis.get('morning_range_pct'):
            lines.append(f"  - Morning Range: {analysis.get('morning_range_pct'):.2f}%")
        
        lines.append(f"\nTechnical Indicators:")
        if analysis.get('rsi_14'):
            lines.append(f"  - RSI(14): {analysis.get('rsi_14'):.2f}")
        if analysis.get('macd'):
            lines.append(f"  - MACD: {analysis.get('macd'):.2f}")
        if analysis.get('macd_signal'):
            lines.append(f"  - MACD Signal: {analysis.get('macd_signal'):.2f}")
        if analysis.get('bollinger_position'):
            lines.append(f"  - Bollinger Position: {analysis.get('bollinger_position'):.1f}%")
        
        if analysis.get('volume_ratio'):
            lines.append(f"\nVolume:")
            lines.append(f"  - Volume Ratio: {analysis.get('volume_ratio'):.2f}x")
        
        if analysis.get('moneyness'):
            lines.append(f"\nStrike:")
            lines.append(f"  - Moneyness: {analysis.get('moneyness')}")
            if analysis.get('strike_distance_pct'):
                lines.append(f"  - Distance: {analysis.get('strike_distance_pct'):.2f}%")
        
        return "\n".join(lines)
    
    async def discover_patterns(self, trade_analyses: List[Dict]) -> str:
        """Ask LLM to discover patterns in multiple trades"""
        
        system_prompt = """You are a quantitative trading strategy analyst. Your job is to analyze 
successful trades and identify the underlying trading strategies or patterns.

Key principles:
1. Don't force-fit trades into a single strategy - there may be multiple strategies
2. Look for natural patterns and clusters
3. Identify common entry conditions (time, price, indicators)
4. Note any outliers that don't fit patterns
5. Be specific about the rules that could replicate these trades

Output format:
- List each discovered pattern/strategy
- Explain the entry rules clearly
- Note the confidence level
- List which trades belong to each pattern"""

        # Format all trades
        trade_texts = []
        for i, analysis in enumerate(trade_analyses, 1):
            trade_texts.append(f"=== TRADE {i} ===\n{self.format_trade_for_llm(analysis)}")
        
        prompt = f"""Analyze these successful option trades and identify the underlying trading patterns or strategies.

{chr(10).join(trade_texts)}

Please:
1. Identify any common patterns across these trades
2. Look at entry times, technical indicators, price levels
3. Don't force all trades into one strategy - there may be multiple
4. Be specific about what conditions triggered each trade
5. Suggest rules that could replicate these trades

What patterns do you see?"""

        response = await self.generate(prompt, system_prompt)
        return response
    
    async def analyze_single_trade(self, trade_analysis: Dict) -> str:
        """Ask LLM to analyze a single trade in depth"""
        
        system_prompt = """You are a quantitative trading analyst. Analyze this successful trade 
and identify what conditions made it a good entry. Be specific and quantitative."""

        trade_text = self.format_trade_for_llm(trade_analysis)
        
        prompt = f"""Analyze this successful option trade:

{trade_text}

Questions to answer:
1. What made this a good entry point?
2. What technical/price conditions supported the trade?
3. Was the 14:00 entry time significant?
4. What strategy category does this trade fit?
5. What rules could replicate this trade?"""

        response = await self.generate(prompt, system_prompt)
        return response
    
    async def suggest_strategy_rules(self, pattern_description: str, trade_analyses: List[Dict]) -> str:
        """Ask LLM to formalize strategy rules from discovered patterns"""
        
        system_prompt = """You are a trading system designer. Convert observed patterns 
into formal, testable trading rules. Be specific and quantitative."""

        # Summarize trades
        trade_summary = []
        for a in trade_analyses:
            trade_summary.append(f"- {a.get('stock')} {a.get('strike')} {a.get('option_type')} at {a.get('entry_time')}")
        
        prompt = f"""Based on this pattern analysis:

{pattern_description}

Observed trades:
{chr(10).join(trade_summary)}

Create formal trading rules:

1. ENTRY RULES (be specific with numbers):
   - Time condition: ?
   - Price condition: ?
   - Technical indicators: ?
   - Volume condition: ?

2. STRIKE SELECTION:
   - How to pick the strike?
   - ATM/OTM preference?

3. EXIT RULES:
   - Target %: ?
   - Stop Loss %: ?
   - Time exit: ?

4. FILTERS:
   - Stock universe: ?
   - Days to avoid: ?

Please provide concrete, testable rules."""

        response = await self.generate(prompt, system_prompt)
        return response


async def main():
    """Test the Ollama strategy analyzer"""
    
    print("=" * 80)
    print("🤖 OLLAMA STRATEGY ANALYZER TEST")
    print("=" * 80)
    
    analyzer = OllamaStrategyAnalyzer(model="mistral")
    
    # Check connection
    connected = await analyzer.check_connection()
    if not connected:
        print("\n⚠️  Ollama not running. Please start Ollama first.")
        print("   Run: ollama serve")
        return
    
    # Test with sample trade analyses
    sample_analyses = [
        {
            "stock": "HINDZINC",
            "strike": 500,
            "option_type": "CE",
            "trade_date": "2025-12-01",
            "entry_time": "14:00",
            "entry_premium": 14.0,
            "exit_premium": 23.0,
            "pnl": 11025,
            "spot_price": 503.65,
            "morning_open": 502.50,
            "morning_high": 512.00,
            "morning_low": 494.90,
            "morning_range_pct": 3.46,
            "range_position": 51.2,
            "rsi_14": 46.62,
            "macd": -0.43,
            "macd_signal": -0.12,
            "bollinger_position": 18.5,
            "volume_ratio": 0.41,
            "moneyness": "ITM",
            "strike_distance_pct": 0.73
        },
        {
            "stock": "HEROMOTOCO",
            "strike": 6200,
            "option_type": "CE",
            "trade_date": "2025-12-01",
            "entry_time": "14:00",
            "entry_premium": 195.0,
            "spot_price": 6321.00,
            "morning_open": 6289.50,
            "morning_high": 6390.00,
            "morning_low": 6237.00,
            "morning_range_pct": 2.45,
            "range_position": 54.9,
            "rsi_14": 52.11,
            "macd": 0.22,
            "macd_signal": -0.11,
            "bollinger_position": 37.5,
            "volume_ratio": 2.22,
            "moneyness": "ITM",
            "strike_distance_pct": 1.95
        }
    ]
    
    print("\n📊 Analyzing trades for patterns...\n")
    patterns = await analyzer.discover_patterns(sample_analyses)
    
    print("🎯 DISCOVERED PATTERNS:")
    print("-" * 80)
    print(patterns)
    print("-" * 80)
    
    print("\n✅ Analysis Complete!")


if __name__ == "__main__":
    asyncio.run(main())
