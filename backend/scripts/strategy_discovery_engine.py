"""
AI Strategy Discovery Engine - Main Orchestrator
Coordinates trade analysis, pattern discovery, and strategy validation

This is the primary entry point for discovering strategies from trades.
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trade_analyzer import TradeAnalyzer, TradeAnalysis
from ollama_strategy_analyzer import OllamaStrategyAnalyzer


@dataclass
class DiscoveredStrategy:
    """A strategy discovered from trade analysis"""
    name: str
    description: str
    entry_rules: Dict[str, Any]
    exit_rules: Dict[str, Any]
    source_trades: List[str]
    confidence: str
    created_at: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


class StrategyDiscoveryEngine:
    """
    Main engine for discovering trading strategies from successful trades.
    
    Process:
    1. Input: List of successful trades
    2. Analyze: Extract features using market data
    3. Discover: Use LLM to find patterns
    4. Validate: Backtest discovered strategies
    5. Output: Formalized strategy rules
    """
    
    def __init__(self, db_url: str = 'postgresql://user:password@127.0.0.1:5432/keepgaining'):
        self.db_url = db_url
        self.trade_analyzer = TradeAnalyzer(db_url)
        self.ollama_analyzer = OllamaStrategyAnalyzer(model="llama3")
        self.analyzed_trades: List[Dict] = []
        self.discovered_strategies: List[DiscoveredStrategy] = []
    
    async def initialize(self):
        """Initialize connections"""
        await self.trade_analyzer.connect()
        
        # Check Ollama
        connected = await self.ollama_analyzer.check_connection()
        if not connected:
            print("⚠️  Ollama not running. AI analysis will be limited.")
            return False
        return True
    
    async def close(self):
        """Close connections"""
        await self.trade_analyzer.close()
    
    async def add_trade(self, trade: Dict) -> Dict:
        """Add a trade and analyze it"""
        print(f"\n📊 Analyzing trade: {trade.get('stock', trade.get('stockName'))}")
        
        analysis = await self.trade_analyzer.analyze_trade(trade)
        analysis_dict = analysis.to_dict()
        self.analyzed_trades.append(analysis_dict)
        
        return analysis_dict
    
    async def add_trades(self, trades: List[Dict]) -> List[Dict]:
        """Add multiple trades"""
        results = []
        for trade in trades:
            result = await self.add_trade(trade)
            results.append(result)
        return results
    
    async def discover_patterns(self) -> str:
        """Use LLM to discover patterns in analyzed trades"""
        if not self.analyzed_trades:
            return "No trades to analyze. Add trades first."
        
        print(f"\n🤖 Sending {len(self.analyzed_trades)} trades to LLM for pattern discovery...")
        
        patterns = await self.ollama_analyzer.discover_patterns(self.analyzed_trades)
        return patterns
    
    async def get_strategy_rules(self, pattern_description: str) -> str:
        """Convert discovered patterns to formal rules"""
        rules = await self.ollama_analyzer.suggest_strategy_rules(
            pattern_description, 
            self.analyzed_trades
        )
        return rules
    
    def summarize_trades(self) -> Dict:
        """Get summary statistics of analyzed trades"""
        if not self.analyzed_trades:
            return {}
        
        summary = {
            "total_trades": len(self.analyzed_trades),
            "stocks": list(set(t.get('stock') for t in self.analyzed_trades)),
            "dates": list(set(t.get('trade_date') for t in self.analyzed_trades)),
            "entry_times": list(set(t.get('entry_time') for t in self.analyzed_trades)),
            "option_types": list(set(t.get('option_type') for t in self.analyzed_trades)),
        }
        
        # Common features
        common = {}
        
        # Check entry time pattern
        entry_hours = [t.get('entry_hour') for t in self.analyzed_trades if t.get('entry_hour')]
        if entry_hours and len(set(entry_hours)) == 1:
            common['entry_hour'] = entry_hours[0]
        
        # Check option type pattern
        option_types = [t.get('option_type') for t in self.analyzed_trades if t.get('option_type')]
        if option_types and len(set(option_types)) == 1:
            common['option_type'] = option_types[0]
        
        # Check moneyness pattern
        moneyness = [t.get('moneyness') for t in self.analyzed_trades if t.get('moneyness')]
        if moneyness and len(set(moneyness)) == 1:
            common['moneyness'] = moneyness[0]
        
        summary['common_features'] = common
        
        return summary
    
    async def run_full_discovery(self, trades: List[Dict]) -> Dict:
        """Run the complete discovery pipeline"""
        
        print("=" * 80)
        print("🚀 AI STRATEGY DISCOVERY ENGINE")
        print("=" * 80)
        
        # Step 1: Initialize
        print("\n📡 Step 1: Initializing...")
        await self.initialize()
        
        # Step 2: Analyze trades
        print("\n📊 Step 2: Analyzing trades...")
        await self.add_trades(trades)
        
        # Step 3: Summarize findings
        print("\n📋 Step 3: Summarizing...")
        summary = self.summarize_trades()
        print(f"   Trades analyzed: {summary.get('total_trades')}")
        print(f"   Stocks: {summary.get('stocks')}")
        print(f"   Entry times: {summary.get('entry_times')}")
        if summary.get('common_features'):
            print(f"   Common features: {summary.get('common_features')}")
        
        # Step 4: Discover patterns
        print("\n🤖 Step 4: Discovering patterns with AI...")
        patterns = await self.discover_patterns()
        
        # Step 5: Generate rules
        print("\n📝 Step 5: Generating strategy rules...")
        rules = await self.get_strategy_rules(patterns)
        
        # Close
        await self.close()
        
        result = {
            "summary": summary,
            "patterns": patterns,
            "rules": rules,
            "analyzed_trades": self.analyzed_trades
        }
        
        print("\n" + "=" * 80)
        print("✅ DISCOVERY COMPLETE")
        print("=" * 80)
        
        return result


async def main():
    """Run the strategy discovery engine with sample trades"""
    
    # Sample trades from user
    trades = [
        {
            "date": "2025-12-01",
            "stockName": "HINDZINC",
            "strike": 500,
            "optionType": "CE",
            "entryTime": "14:00",
            "entryPremium": 14.0,
            "exitPremium": 23.0,
            "pnl": 11025
        },
        {
            "date": "2025-12-01",
            "stockName": "Hero Motors",
            "strike": 6200,
            "optionType": "CE",
            "entryTime": "14:00",
            "entryPremium": 195.0
        }
    ]
    
    engine = StrategyDiscoveryEngine()
    result = await engine.run_full_discovery(trades)
    
    # Print results
    print("\n" + "=" * 80)
    print("🎯 DISCOVERED PATTERNS")
    print("=" * 80)
    print(result.get('patterns', 'No patterns found'))
    
    print("\n" + "=" * 80)
    print("📋 STRATEGY RULES")
    print("=" * 80)
    print(result.get('rules', 'No rules generated'))
    
    # Save results
    output_file = 'strategy_discovery_results.json'
    with open(output_file, 'w') as f:
        # Can't serialize the full result due to complex objects
        json.dump({
            "summary": result.get('summary'),
            "patterns": result.get('patterns'),
            "rules": result.get('rules')
        }, f, indent=2, default=str)
    
    print(f"\n📄 Results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
