"""
Backtest Discovered Strategies - December 2025
Following incremental approach: Dec first, then Nov, then Oct

Strategies:
A) CE Range Entry: RSI 38-55, Range >50%, ITM
B) PE Near-Low Entry: RSI 49-57, Range <40%, OTM
"""
import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta, time as dt_time
from collections import defaultdict
from typing import Dict, List, Optional

class StrategyBacktester:
    """Backtests discovered strategies"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    def calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    async def get_fo_stocks(self) -> List[str]:
        """Get F&O stock list"""
        async with self.pool.acquire() as conn:
            result = await conn.fetch("""
                SELECT DISTINCT underlying
                FROM instrument_master
                WHERE instrument_type = 'FUTURES'
                AND underlying NOT IN ('NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY')
                ORDER BY underlying
            """)
            return [r['underlying'] for r in result]
    
    async def analyze_stock_at_entry(self, stock: str, trade_date: date, entry_time: dt_time = dt_time(14, 0)) -> Optional[Dict]:
        """Analyze stock at entry time"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT cd.timestamp, cd.open, cd.high, cd.low, cd.close, cd.volume
                FROM candle_data cd
                JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                WHERE im.underlying = $1
                AND im.instrument_type = 'FUTURES'
                AND DATE(cd.timestamp) = $2
                ORDER BY cd.timestamp
            """
            data = await conn.fetch(query, stock, trade_date)
            
            if not data or len(data) < 50:
                return None
            
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp']) + pd.Timedelta(hours=5, minutes=30)
            df['time'] = df['timestamp'].dt.time
            
            # Find entry candle
            entry_candles = df[df['time'] >= entry_time]
            if len(entry_candles) == 0:
                return None
            
            entry_idx = entry_candles.index[0]
            entry_candle = df.loc[entry_idx]
            data_till_entry = df.loc[:entry_idx]
            
            prices = data_till_entry['close'].values.astype(float)
            entry_price = float(entry_candle['close'])
            
            # Calculate indicators
            rsi = self.calculate_rsi(prices, 14)
            
            morning_high = float(data_till_entry['high'].max())
            morning_low = float(data_till_entry['low'].min())
            
            if morning_high > morning_low:
                range_position = ((entry_price - morning_low) / (morning_high - morning_low)) * 100
            else:
                range_position = 50
            
            return {
                'stock': stock,
                'date': trade_date,
                'entry_price': entry_price,
                'entry_idx': entry_idx,
                'rsi': rsi,
                'range_position': range_position,
                'morning_high': morning_high,
                'morning_low': morning_low,
                'df': df
            }
    
    async def simulate_trade(self, analysis: Dict, option_type: str, target_pct: float = 50, stop_pct: float = -40) -> Dict:
        """Simulate option trade"""
        df = analysis['df']
        entry_idx = analysis['entry_idx']
        entry_price = analysis['entry_price']
        
        post_entry = df.loc[entry_idx+1:]
        if len(post_entry) == 0:
            return {'pnl': 0, 'exit_reason': 'NO_DATA', 'exit_pct': 0}
        
        # For CE: profit when price goes up
        # For PE: profit when price goes down
        if option_type == 'CE':
            max_price = float(post_entry['high'].max())
            min_price = float(post_entry['low'].min())
            close_price = float(post_entry.iloc[-1]['close'])
            
            max_gain_pct = ((max_price - entry_price) / entry_price) * 100 * 2  # 2x leverage
            max_loss_pct = ((min_price - entry_price) / entry_price) * 100 * 2
            final_pct = ((close_price - entry_price) / entry_price) * 100 * 2
        else:  # PE
            max_price = float(post_entry['high'].max())
            min_price = float(post_entry['low'].min())
            close_price = float(post_entry.iloc[-1]['close'])
            
            # For PE, profit when price drops
            max_gain_pct = ((entry_price - min_price) / entry_price) * 100 * 2
            max_loss_pct = ((entry_price - max_price) / entry_price) * 100 * 2
            final_pct = ((entry_price - close_price) / entry_price) * 100 * 2
        
        # Determine exit
        if max_gain_pct >= target_pct:
            exit_pct = target_pct
            exit_reason = "TARGET"
        elif max_loss_pct <= stop_pct:
            exit_pct = stop_pct
            exit_reason = "STOP"
        else:
            exit_pct = final_pct
            exit_reason = "EOD"
        
        capital = 20000
        pnl = capital * (exit_pct / 100)
        
        return {
            'pnl': pnl,
            'exit_reason': exit_reason,
            'exit_pct': exit_pct
        }
    
    async def backtest_strategy_a(self, start_date: date, end_date: date) -> List[Dict]:
        """Strategy A: CE Range Entry
        - RSI: 38-55
        - Range Position: >50%
        - Type: CE (bullish)
        """
        stocks = await self.get_fo_stocks()
        trades = []
        
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            for stock in stocks:
                analysis = await self.analyze_stock_at_entry(stock, current_date)
                if not analysis:
                    continue
                
                # Strategy A conditions
                if (38 <= analysis['rsi'] <= 55 and 
                    analysis['range_position'] > 50):
                    
                    result = await self.simulate_trade(analysis, 'CE')
                    
                    trades.append({
                        'date': str(current_date),
                        'stock': stock,
                        'strategy': 'A_CE_RANGE',
                        'rsi': analysis['rsi'],
                        'range_position': analysis['range_position'],
                        'entry_price': analysis['entry_price'],
                        'option_type': 'CE',
                        **result
                    })
            
            current_date += timedelta(days=1)
        
        return trades
    
    async def backtest_strategy_b(self, start_date: date, end_date: date) -> List[Dict]:
        """Strategy B: PE Near-Low Entry
        - RSI: 42-58
        - Range Position: <40%
        - Type: PE (bearish)
        """
        stocks = await self.get_fo_stocks()
        trades = []
        
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            for stock in stocks:
                analysis = await self.analyze_stock_at_entry(stock, current_date)
                if not analysis:
                    continue
                
                # Strategy B conditions
                if (42 <= analysis['rsi'] <= 58 and 
                    analysis['range_position'] < 40):
                    
                    result = await self.simulate_trade(analysis, 'PE')
                    
                    trades.append({
                        'date': str(current_date),
                        'stock': stock,
                        'strategy': 'B_PE_LOW',
                        'rsi': analysis['rsi'],
                        'range_position': analysis['range_position'],
                        'entry_price': analysis['entry_price'],
                        'option_type': 'PE',
                        **result
                    })
            
            current_date += timedelta(days=1)
        
        return trades
    
    def print_results(self, trades: List[Dict], strategy_name: str):
        """Print backtest results"""
        if not trades:
            print(f"\n❌ {strategy_name}: No trades found")
            return
        
        df = pd.DataFrame(trades)
        
        total = len(df)
        winners = len(df[df['pnl'] > 0])
        losers = len(df[df['pnl'] <= 0])
        win_rate = winners / total * 100
        
        total_pnl = df['pnl'].sum()
        avg_win = df[df['pnl'] > 0]['pnl'].mean() if winners > 0 else 0
        avg_loss = df[df['pnl'] <= 0]['pnl'].mean() if losers > 0 else 0
        
        print(f"\n📊 {strategy_name}")
        print("-" * 50)
        print(f"   Trades: {total}")
        print(f"   Winners: {winners} ({win_rate:.1f}%)")
        print(f"   Losers: {losers}")
        print(f"   Total P&L: ₹{total_pnl:+,.0f}")
        print(f"   Avg Win: ₹{avg_win:+,.0f}")
        print(f"   Avg Loss: ₹{avg_loss:+,.0f}")
        
        # Exit reason breakdown
        exit_counts = df['exit_reason'].value_counts()
        print(f"\n   Exit Reasons:")
        for reason, count in exit_counts.items():
            print(f"      {reason}: {count}")
        
        return df


async def main():
    """Backtest on December first"""
    
    print("=" * 80)
    print("🧪 BACKTESTING DISCOVERED STRATEGIES - DECEMBER 2025")
    print("=" * 80)
    print("\nFollowing incremental approach:")
    print("  1. Test December first (most recent)")
    print("  2. If profitable, extend to November")
    print("  3. If still good, extend to October")
    print()
    
    backtester = StrategyBacktester('postgresql://user:password@127.0.0.1:5432/keepgaining')
    await backtester.connect()
    
    # December 2025
    start_date = date(2025, 12, 1)
    end_date = date(2025, 12, 17)  # Up to today's data
    
    print(f"📅 Period: {start_date} to {end_date}")
    print("-" * 80)
    
    # Strategy A
    print("\n🎯 Testing Strategy A: CE Range Entry...")
    print("   Rules: RSI 38-55, Range >50%, CE at 14:00")
    trades_a = await backtester.backtest_strategy_a(start_date, end_date)
    df_a = backtester.print_results(trades_a, "Strategy A: CE Range Entry")
    
    # Strategy B
    print("\n🎯 Testing Strategy B: PE Near-Low Entry...")
    print("   Rules: RSI 42-58, Range <40%, PE at 14:00")
    trades_b = await backtester.backtest_strategy_b(start_date, end_date)
    df_b = backtester.print_results(trades_b, "Strategy B: PE Near-Low Entry")
    
    # Combined summary
    all_trades = trades_a + trades_b
    if all_trades:
        total_pnl = sum(t['pnl'] for t in all_trades)
        total_trades = len(all_trades)
        winners = sum(1 for t in all_trades if t['pnl'] > 0)
        
        print("\n" + "=" * 80)
        print("📊 COMBINED RESULTS - DECEMBER 2025")
        print("=" * 80)
        print(f"   Total Trades: {total_trades}")
        print(f"   Win Rate: {winners/total_trades*100:.1f}%")
        print(f"   Total P&L: ₹{total_pnl:+,.0f}")
        
        # Save results
        import json
        results = {
            'period': f"{start_date} to {end_date}",
            'strategy_a_trades': len(trades_a),
            'strategy_a_pnl': sum(t['pnl'] for t in trades_a),
            'strategy_b_trades': len(trades_b),
            'strategy_b_pnl': sum(t['pnl'] for t in trades_b),
            'total_trades': total_trades,
            'total_pnl': total_pnl,
            'win_rate': winners/total_trades*100
        }
        
        with open('backend/data/december_backtest_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        # Save detailed trades
        pd.DataFrame(all_trades).to_csv('backend/data/december_backtest_trades.csv', index=False)
        
        print(f"\n📄 Results saved to:")
        print(f"   - backend/data/december_backtest_results.json")
        print(f"   - backend/data/december_backtest_trades.csv")
        
        # Recommendation
        print("\n" + "=" * 80)
        if total_pnl > 0:
            print("✅ December is PROFITABLE - Proceed to November backtest")
        else:
            print("⚠️ December is UNPROFITABLE - Review strategy rules")
        print("=" * 80)
    
    await backtester.close()
    print("\n✅ Backtest Complete!")


if __name__ == "__main__":
    asyncio.run(main())
