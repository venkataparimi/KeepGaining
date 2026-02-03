"""
FAST Cluster 1 Backtest - Using Parquet Files
Uses pre-computed indicators from Parquet files for speed

Cluster 1 Rules:
- Morning Change: > 0% (stock up in morning)
- RSI(14): 36-56 (neutral/slightly oversold)  [FROM PARQUET]
- Williams %R: < -75 (extreme oversold)       [CALCULATED]
- Volume: > 2x average (high volume)
- Type: CE (Call)
"""
import pandas as pd
import numpy as np
from datetime import datetime, date, time as dt_time, timedelta
from pathlib import Path
import json
from glob import glob

class FastParquetBacktester:
    """Fast backtester using pre-computed Parquet indicators"""
    
    def __init__(self, parquet_dir: str = 'backend/data/strategy_dataset'):
        self.parquet_dir = Path(parquet_dir)
        self.stocks_data = {}
    
    def load_all_stocks(self):
        """Load all Parquet files into memory"""
        parquet_files = list(self.parquet_dir.glob('*_EQUITY.parquet'))
        print(f"   Found {len(parquet_files)} Parquet files")
        
        for pf in parquet_files:
            stock = pf.stem.replace('_EQUITY', '')
            try:
                df = pd.read_parquet(pf)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                # Convert to IST
                if df['timestamp'].dt.tz is not None:
                    df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')
                else:
                    df['timestamp'] = df['timestamp'] + pd.Timedelta(hours=5, minutes=30)
                self.stocks_data[stock] = df
            except Exception as e:
                print(f"   ⚠️  Error loading {stock}: {e}")
    
    def calculate_williams_r(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Williams %R"""
        highest_high = high.rolling(period).max()
        lowest_low = low.rolling(period).min()
        wr = -100 * (highest_high - close) / (highest_high - lowest_low)
        return wr
    
    def analyze_stock_day(self, df: pd.DataFrame, trade_date: date, entry_time: dt_time = dt_time(14, 0)) -> dict:
        """Analyze a single stock on a single day up to entry time (no lookahead)"""
        
        # Filter to trade date
        day_data = df[df['timestamp'].dt.date == trade_date].copy()
        
        if len(day_data) < 50:
            return None
        
        # Get data up to entry time (no lookahead!)
        day_data['time'] = day_data['timestamp'].dt.time
        morning_data = day_data[day_data['time'] <= entry_time]
        
        if len(morning_data) < 20:
            return None
        
        entry_row = morning_data.iloc[-1]
        
        # Features from Parquet (pre-computed)
        rsi = entry_row.get('rsi_14')
        if pd.isna(rsi):
            return None
        
        # Calculate Williams %R (not pre-computed)
        high = morning_data['high'].values
        low = morning_data['low'].values
        close = morning_data['close'].values
        
        if len(close) >= 14:
            hh = max(high[-14:])
            ll = min(low[-14:])
            if hh > ll:
                williams_r = -100 * (hh - close[-1]) / (hh - ll)
            else:
                williams_r = -50
        else:
            williams_r = -50
        
        # Morning change (no lookahead)
        morning_open = float(morning_data.iloc[0]['open'])
        entry_price = float(entry_row['close'])
        morning_change_pct = ((entry_price - morning_open) / morning_open) * 100
        
        # Volume ratio
        volumes = morning_data['volume'].values
        if len(volumes) >= 20:
            avg_vol = np.mean(volumes[-20:])
            volume_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1
        else:
            volume_ratio = 1
        
        return {
            'entry_price': entry_price,
            'morning_change_pct': morning_change_pct,
            'rsi': float(rsi),
            'williams_r': williams_r,
            'volume_ratio': volume_ratio,
            'day_data': day_data,
            'entry_idx': len(morning_data) - 1
        }
    
    def check_cluster1_conditions(self, analysis: dict) -> bool:
        """Check Cluster 1 conditions"""
        return (
            analysis['morning_change_pct'] > 0 and     # Morning up
            36 <= analysis['rsi'] <= 56 and            # RSI in range
            analysis['williams_r'] < -75 and           # Extreme oversold
            analysis['volume_ratio'] > 2.0             # High volume
        )
    
    def simulate_ce_trade(self, analysis: dict, target_pct: float = 50, stop_pct: float = -40) -> dict:
        """Simulate CE trade using post-entry data"""
        day_data = analysis['day_data']
        entry_idx = analysis['entry_idx']
        entry_price = analysis['entry_price']
        
        # Get post-entry data
        post_entry = day_data.iloc[entry_idx + 1:]
        
        if len(post_entry) == 0:
            return {'pnl': 0, 'exit_reason': 'NO_DATA', 'exit_pct': 0}
        
        max_price = post_entry['high'].max()
        min_price = post_entry['low'].min()
        close_price = post_entry.iloc[-1]['close']
        
        # 2x leverage approximation for options
        max_gain_pct = ((max_price - entry_price) / entry_price) * 100 * 2
        max_loss_pct = ((min_price - entry_price) / entry_price) * 100 * 2
        final_pct = ((close_price - entry_price) / entry_price) * 100 * 2
        
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
        
        return {'pnl': pnl, 'exit_reason': exit_reason, 'exit_pct': exit_pct}
    
    def backtest_cluster1(self, start_date: date, end_date: date) -> list:
        """Run Cluster 1 backtest on date range"""
        
        trades = []
        current_date = start_date
        day_count = 0
        
        while current_date <= end_date:
            if current_date.weekday() >= 5:  # Skip weekends
                current_date += timedelta(days=1)
                continue
            
            day_count += 1
            if day_count % 5 == 0:
                print(f"   Processing: {current_date} (day {day_count})")
            
            for stock, df in self.stocks_data.items():
                analysis = self.analyze_stock_day(df, current_date)
                
                if analysis is None:
                    continue
                
                if self.check_cluster1_conditions(analysis):
                    result = self.simulate_ce_trade(analysis)
                    
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


def main():
    """Run fast Cluster 1 backtest on October 2025"""
    
    print("=" * 80)
    print("🚀 FAST CLUSTER 1 BACKTEST - USING PARQUET FILES")
    print("=" * 80)
    print("\nCluster 1 Strategy Rules:")
    print("   - Morning Change: > 0% (stock up)")
    print("   - RSI(14): 36-56")
    print("   - Williams %R: < -75 (oversold)")
    print("   - Volume: > 2x average")
    print("   - Trade: CE (Call)")
    print("")
    
    backtester = FastParquetBacktester()
    
    print("📂 Loading Parquet files...")
    backtester.load_all_stocks()
    print(f"   Loaded {len(backtester.stocks_data)} stocks\n")
    
    # October 2025
    start_date = date(2025, 10, 1)
    end_date = date(2025, 10, 31)
    
    print(f"📅 Period: {start_date} to {end_date}")
    print("-" * 80)
    
    trades = backtester.backtest_cluster1(start_date, end_date)
    
    print(f"\n📊 RESULTS:")
    print("-" * 80)
    
    if trades:
        df = pd.DataFrame(trades)
        
        total = len(df)
        winners = len(df[df['pnl'] > 0])
        win_rate = winners / total * 100 if total > 0 else 0
        total_pnl = df['pnl'].sum()
        avg_pnl = df['pnl'].mean()
        
        print(f"   Total Trades: {total}")
        print(f"   Winners: {winners} ({win_rate:.1f}%)")
        print(f"   Losers: {total - winners}")
        print(f"   Total P&L: ₹{total_pnl:+,.0f}")
        print(f"   Avg P&L: ₹{avg_pnl:+,.0f}")
        
        if winners > 0:
            avg_win = df[df['pnl'] > 0]['pnl'].mean()
            print(f"   Avg Win: ₹{avg_win:+,.0f}")
        if total - winners > 0:
            avg_loss = df[df['pnl'] <= 0]['pnl'].mean()
            print(f"   Avg Loss: ₹{avg_loss:+,.0f}")
        
        print(f"\n   Exit Reasons:")
        for reason, count in df['exit_reason'].value_counts().items():
            print(f"      {reason}: {count}")
        
        print(f"\n   Top Stocks:")
        for stock, count in df['stock'].value_counts().head(5).items():
            stock_pnl = df[df['stock'] == stock]['pnl'].sum()
            print(f"      {stock}: {count} trades, ₹{stock_pnl:+,.0f}")
        
        # Save results
        df.to_csv('backend/data/cluster1_october_fast.csv', index=False)
        
        results = {
            'strategy': 'Cluster 1 (Fast Parquet)',
            'period': f'{start_date} to {end_date}',
            'trades': total,
            'win_rate': win_rate,
            'total_pnl': total_pnl
        }
        with open('backend/data/cluster1_october_fast_summary.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📄 Saved: backend/data/cluster1_october_fast.csv")
        
        print("\n" + "=" * 80)
        if win_rate >= 50 and total_pnl > 0:
            print("✅ Strategy PROFITABLE!")
        elif win_rate >= 45:
            print("⚠️ Strategy MARGINAL")
        else:
            print("❌ Strategy UNPROFITABLE")
        print("=" * 80)
    else:
        print("   No trades found matching conditions")
    
    print("\n✅ Complete!")


if __name__ == "__main__":
    main()
