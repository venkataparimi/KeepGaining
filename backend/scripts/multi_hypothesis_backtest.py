"""
Multi-Hypothesis Strategy Backtester
Tests 4 different 14:00 entry strategies to find which pattern works best
"""
import pandas as pd
import asyncio
import asyncpg
from datetime import datetime, date, time as dt_time, timedelta
import numpy as np

class AfternoonStrategyTester:
    def __init__(self, db_url):
        self.db_url = db_url
        self.pool = None
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
        
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def test_all_strategies(self, start_date, end_date):
        """Test all 4 hypothesis strategies"""
        
        print("=" * 80)
        print("🧪 MULTI-HYPOTHESIS STRATEGY BACKTEST")
        print("=" * 80)
        print(f"Period: {start_date} to {end_date}")
        print()
        
        # Get all F&O stocks
        stocks = await self.get_fo_stocks()
        print(f"Testing on {len(stocks)} F&O stocks")
        print()
        
        strategies = {
            "1. Post-Lunch Breakout": self.test_breakout_strategy,
            "2. Afternoon Momentum": self.test_momentum_strategy,
            "3. Afternoon Reversal": self.test_reversal_strategy,
            "4. Time-Based Entry": self.test_time_based_strategy
        }
        
        results = {}
        
        for strategy_name, strategy_func in strategies.items():
            print(f"\n{'=' * 80}")
            print(f"Testing: {strategy_name}")
            print(f"{'=' * 80}")
            
            result = await strategy_func(stocks, start_date, end_date)
            results[strategy_name] = result
            
            print(f"\n✅ {strategy_name} Results:")
            print(f"   Trades: {result['trades']}")
            print(f"   Win Rate: {result['win_rate']:.1f}%")
            print(f"   Total P&L: ₹{result['total_pnl']:,.0f}")
            print(f"   Avg P&L per Trade: ₹{result['avg_pnl']:,.0f}")
        
        # Compare all strategies
        print(f"\n{'=' * 80}")
        print("📊 STRATEGY COMPARISON")
        print(f"{'=' * 80}\n")
        
        comparison_df = pd.DataFrame(results).T
        comparison_df = comparison_df.sort_values('total_pnl', ascending=False)
        
        print(comparison_df.to_string())
        
        # Identify best strategy
        best_strategy = comparison_df.index[0]
        best_result = results[best_strategy]
        
        print(f"\n{'=' * 80}")
        print(f"🏆 BEST STRATEGY: {best_strategy}")
        print(f"{'=' * 80}")
        print(f"Win Rate: {best_result['win_rate']:.1f}%")
        print(f"Total P&L: ₹{best_result['total_pnl']:,.0f}")
        print(f"Avg Trade: ₹{best_result['avg_pnl']:,.0f}")
        print(f"Total Trades: {best_result['trades']}")
        print()
        
        return results
    
    async def get_fo_stocks(self):
        """Get list of F&O stocks"""
        async with self.pool.acquire() as conn:
            result = await conn.fetch("""
                SELECT DISTINCT underlying
                FROM instrument_master
                WHERE instrument_type IN ('CE', 'PE')
                AND underlying NOT IN ('NIFTY', 'BANKNIFTY', 'FINNIFTY')
                ORDER BY underlying
                LIMIT 50
            """)
            return [r['underlying'] for r in result]
    
    async def test_breakout_strategy(self, stocks, start_date, end_date):
        """
        Strategy 1: Post-Lunch Breakout
        Entry: 14:00 if price > morning high
        """
        trades = []
        
        # Simulate backtest (placeholder - would need actual data)
        # For demonstration, return mock results
        
        return {
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'description': 'Enter at 14:00 if price breaks morning high'
        }
    
    async def test_momentum_strategy(self, stocks, start_date, end_date):
        """
        Strategy 2: Afternoon Momentum
        Entry: 14:00 if morning move > +1%
        """
        return {
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'description': 'Enter at 14:00 if morning momentum > +1%'
        }
    
    async def test_reversal_strategy(self, stocks, start_date, end_date):
        """
        Strategy 3: Afternoon Reversal
        Entry: 14:00 if stock dipped in morning but shows reversal
        """
        return {
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'description': 'Enter at 14:00 if morning dip + reversal signal'
        }
    
    async def test_time_based_strategy(self, stocks, start_date, end_date):
        """
        Strategy 4: Time-Based Entry
        Entry: Always at 14:00, no other condition
        """
        return {
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'description': 'Enter at 14:00 every day (statistical edge)'
        }

async def main():
    tester = AfternoonStrategyTester('postgresql://user:password@127.0.0.1:5432/keepgaining')
    await tester.connect()
    
    # Test on Oct-Dec 2025
    results = await tester.test_all_strategies(
        date(2025, 10, 1),
        date(2025, 12, 15)
    )
    
    await tester.close()
    
    print("\n" + "=" * 80)
    print("💡 NEXT STEPS")
    print("=" * 80)
    print()
    print("Since we don't have the actual candle data yet, here's what we can do:")
    print()
    print("Option 1: Use your local AI to analyze patterns")
    print("  → Feed it your trade examples")
    print("  → Let it identify common factors")
    print("  → Generate strategy rules")
    print()
    print("Option 2: Provide more trade examples")
    print("  → Give me 5-10 more similar trades")
    print("  → I'll find the pattern manually")
    print("  → Create backtest based on pattern")
    print()
    print("Option 3: Tell me the logic")
    print("  → Explain why you entered at 14:00")
    print("  → Explain how you chose 500 CE")
    print("  → I'll codify it into a strategy")
    print()
    print("Option 4: Backfill the data")
    print("  → Run data backfill for HINDZINC")
    print("  → Then I can analyze Dec 1, 2025 precisely")
    print("  → Reverse-engineer from actual data")
    print()

if __name__ == "__main__":
    asyncio.run(main())
