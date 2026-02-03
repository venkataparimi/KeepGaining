"""
Backtest Cluster 1 Strategy - October 2025
Strategy: Morning Up + High Volume + Extreme Oversold

Cluster 1 Rules:
- Morning Change: > 0 (up)
- RSI: 36-56
- Williams %R: < -75 (extreme oversold)
- Volume: > 2x average
- Type: CE (Call)
"""
import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta, time as dt_time
from typing import Dict, List, Optional
import json

class ClusterBacktester:
    """Backtests cluster strategies"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
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
    
    async def analyze_stock(self, stock: str, trade_date: date, entry_time: dt_time = dt_time(14, 0)) -> Optional[Dict]:
        """Analyze stock at entry time (no lookahead)"""
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
            
            entry_candles = df[df['time'] >= entry_time]
            if len(entry_candles) == 0:
                return None
            
            entry_idx = entry_candles.index[0]
            data_till_entry = df.loc[:entry_idx]
            
            o = data_till_entry['open'].values.astype(float)
            h = data_till_entry['high'].values.astype(float)
            l = data_till_entry['low'].values.astype(float)
            c = data_till_entry['close'].values.astype(float)
            v = data_till_entry['volume'].values.astype(float)
            
            entry_price = float(c[-1])
            morning_open = float(o[0])
            
            # Calculate features
            morning_change_pct = ((entry_price - morning_open) / morning_open) * 100
            
            # RSI
            if len(c) >= 15:
                deltas = np.diff(c)
                gains = np.where(deltas > 0, deltas, 0)
                losses = np.where(deltas < 0, -deltas, 0)
                avg_gain = np.mean(gains[-14:])
                avg_loss = np.mean(losses[-14:])
                if avg_loss > 0:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                else:
                    rsi = 100
            else:
                rsi = 50
            
            # Williams %R
            if len(c) >= 14:
                hh = max(h[-14:])
                ll = min(l[-14:])
                williams_r = -100 * (hh - c[-1]) / (hh - ll) if (hh - ll) > 0 else -50
            else:
                williams_r = -50
            
            # Volume ratio
            if len(v) >= 20:
                avg_vol = np.mean(v[-20:])
                volume_ratio = v[-1] / avg_vol if avg_vol > 0 else 1
            else:
                volume_ratio = 1
            
            return {
                'stock': stock,
                'date': trade_date,
                'entry_price': entry_price,
                'morning_change_pct': morning_change_pct,
                'rsi': rsi,
                'williams_r': williams_r,
                'volume_ratio': volume_ratio,
                'df': df,
                'entry_idx': entry_idx
            }
    
    def check_cluster1_conditions(self, analysis: Dict) -> bool:
        """Check if Cluster 1 conditions are met"""
        # Cluster 1: Morning Up + RSI 36-56 + Williams < -75 + Volume > 2x
        return (
            analysis['morning_change_pct'] > 0 and  # Morning up
            36 <= analysis['rsi'] <= 56 and          # RSI in range
            analysis['williams_r'] < -75 and         # Extreme oversold
            analysis['volume_ratio'] > 2.0           # High volume
        )
    
    async def simulate_ce_trade(self, analysis: Dict, target_pct: float = 50, stop_pct: float = -40) -> Dict:
        """Simulate CE option trade"""
        df = analysis['df']
        entry_idx = analysis['entry_idx']
        entry_price = analysis['entry_price']
        
        post_entry = df.loc[entry_idx+1:]
        if len(post_entry) == 0:
            return {'pnl': 0, 'exit_reason': 'NO_DATA', 'exit_pct': 0}
        
        # For CE: profit when underlying goes up
        max_price = float(post_entry['high'].max())
        min_price = float(post_entry['low'].min())
        close_price = float(post_entry.iloc[-1]['close'])
        
        max_gain_pct = ((max_price - entry_price) / entry_price) * 100 * 2  # 2x leverage approximation
        max_loss_pct = ((min_price - entry_price) / entry_price) * 100 * 2
        final_pct = ((close_price - entry_price) / entry_price) * 100 * 2
        
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
    
    async def backtest_cluster1(self, start_date: date, end_date: date) -> List[Dict]:
        """Backtest Cluster 1 strategy"""
        stocks = await self.get_fo_stocks()
        trades = []
        
        total_days = (end_date - start_date).days
        
        current_date = start_date
        day_count = 0
        
        while current_date <= end_date:
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            day_count += 1
            if day_count % 5 == 0:
                print(f"   Processing: {current_date} ({day_count} trading days)")
            
            daily_signals = 0
            
            for stock in stocks:
                analysis = await self.analyze_stock(stock, current_date)
                if not analysis:
                    continue
                
                # Check Cluster 1 conditions
                if self.check_cluster1_conditions(analysis):
                    result = await self.simulate_ce_trade(analysis)
                    daily_signals += 1
                    
                    trades.append({
                        'date': str(current_date),
                        'stock': stock,
                        'morning_change_pct': analysis['morning_change_pct'],
                        'rsi': analysis['rsi'],
                        'williams_r': analysis['williams_r'],
                        'volume_ratio': analysis['volume_ratio'],
                        **result
                    })
            
            current_date += timedelta(days=1)
        
        return trades


async def main():
    """Run Cluster 1 backtest on October 2025"""
    
    print("=" * 80)
    print("🧪 CLUSTER 1 BACKTEST - OCTOBER 2025")
    print("=" * 80)
    print("\nStrategy Rules:")
    print("   - Morning Change: > 0% (stock up in morning)")
    print("   - RSI(14): 36-56 (neutral/slightly oversold)")
    print("   - Williams %R: < -75 (extreme oversold)")
    print("   - Volume: > 2x average (high volume)")
    print("   - Trade Type: CE (Call)")
    print("")
    
    backtester = ClusterBacktester('postgresql://user:password@127.0.0.1:5432/keepgaining')
    await backtester.connect()
    
    # October 2025
    start_date = date(2025, 10, 1)
    end_date = date(2025, 10, 31)
    
    print(f"📅 Period: {start_date} to {end_date}")
    print("-" * 80)
    
    trades = await backtester.backtest_cluster1(start_date, end_date)
    
    print(f"\n📊 RESULTS:")
    print("-" * 80)
    
    if trades:
        df = pd.DataFrame(trades)
        
        total = len(df)
        winners = len(df[df['pnl'] > 0])
        losers = len(df[df['pnl'] <= 0])
        win_rate = winners / total * 100
        
        total_pnl = df['pnl'].sum()
        avg_pnl = df['pnl'].mean()
        avg_win = df[df['pnl'] > 0]['pnl'].mean() if winners > 0 else 0
        avg_loss = df[df['pnl'] <= 0]['pnl'].mean() if losers > 0 else 0
        
        print(f"   Total Trades: {total}")
        print(f"   Winners: {winners} ({win_rate:.1f}%)")
        print(f"   Losers: {losers}")
        print(f"   Total P&L: ₹{total_pnl:+,.0f}")
        print(f"   Avg P&L: ₹{avg_pnl:+,.0f}")
        print(f"   Avg Win: ₹{avg_win:+,.0f}")
        print(f"   Avg Loss: ₹{avg_loss:+,.0f}")
        
        # Exit reasons
        print(f"\n   Exit Reasons:")
        for reason, count in df['exit_reason'].value_counts().items():
            print(f"      {reason}: {count}")
        
        # Top stocks
        print(f"\n   Most Active Stocks:")
        stock_counts = df['stock'].value_counts().head(5)
        for stock, count in stock_counts.items():
            stock_pnl = df[df['stock'] == stock]['pnl'].sum()
            print(f"      {stock}: {count} trades, ₹{stock_pnl:+,.0f}")
        
        # Save results
        df.to_csv('backend/data/cluster1_october_results.csv', index=False)
        
        results = {
            'period': f'{start_date} to {end_date}',
            'strategy': 'Cluster 1: Morning Up + Oversold + High Volume',
            'total_trades': total,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl
        }
        
        with open('backend/data/cluster1_october_summary.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📄 Saved to:")
        print(f"   - backend/data/cluster1_october_results.csv")
        print(f"   - backend/data/cluster1_october_summary.json")
        
        # Verdict
        print("\n" + "=" * 80)
        if win_rate >= 50 and total_pnl > 0:
            print("✅ Strategy is PROFITABLE in October!")
        elif win_rate >= 45:
            print("⚠️ Strategy is MARGINAL - needs refinement")
        else:
            print("❌ Strategy is UNPROFITABLE in October")
        print("=" * 80)
    else:
        print("   No trades found matching conditions")
    
    await backtester.close()
    print("\n✅ Backtest Complete!")


if __name__ == "__main__":
    asyncio.run(main())
