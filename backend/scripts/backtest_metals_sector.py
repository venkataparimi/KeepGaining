"""
METALS SECTOR STRATEGY BACKTEST
Hypothesis: When metals sector is strong, buy CE on metal stocks

Logic:
1. Check if HINDZINC is UP in the morning (sector leader)
2. If yes, buy CE on HINDZINC and VEDL at 14:00
3. Exit at EOD or 50% target / 40% stop

Using fast Parquet files
"""
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta, time as dt_time
from pathlib import Path
import json

class MetalsSectorBacktest:
    """Backtest metals sector momentum strategy"""
    
    def __init__(self, parquet_dir: str = 'backend/data/strategy_dataset'):
        self.parquet_dir = Path(parquet_dir)
        self.metal_stocks = ['HINDZINC', 'VEDL', 'NATIONALUM', 'NMDC', 'JSWSTEEL', 'TATASTEEL', 'SAIL', 'JINDALSTEL']
        self.sector_leader = 'HINDZINC'
        self.stocks_data = {}
    
    def load_stocks(self):
        """Load metal stocks from Parquet"""
        print("   Loading metal stocks...")
        for stock in self.metal_stocks:
            pf = self.parquet_dir / f"{stock}_EQUITY.parquet"
            if pf.exists():
                df = pd.read_parquet(pf)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                if df['timestamp'].dt.tz is not None:
                    df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')
                else:
                    df['timestamp'] = df['timestamp'] + pd.Timedelta(hours=5, minutes=30)
                self.stocks_data[stock] = df
                print(f"      ✓ {stock}: {len(df)} rows")
            else:
                print(f"      ✗ {stock}: not found")
    
    def check_sector_strength(self, trade_date: date, entry_time: dt_time = dt_time(14, 0)) -> dict:
        """Check if sector leader (HINDZINC) is strong"""
        if self.sector_leader not in self.stocks_data:
            return None
        
        df = self.stocks_data[self.sector_leader]
        day_data = df[df['timestamp'].dt.date == trade_date].copy()
        
        if len(day_data) < 20:
            return None
        
        day_data['time'] = day_data['timestamp'].dt.time
        morning_data = day_data[day_data['time'] <= entry_time]
        
        if len(morning_data) < 10:
            return None
        
        morning_open = float(morning_data.iloc[0]['open'])
        current_price = float(morning_data.iloc[-1]['close'])
        morning_change = ((current_price - morning_open) / morning_open) * 100
        
        # Also check RSI and trend
        rsi = morning_data.iloc[-1].get('rsi_14')
        supertrend_dir = morning_data.iloc[-1].get('supertrend_dir')
        
        return {
            'leader_price': current_price,
            'morning_change': morning_change,
            'is_strong': morning_change > 0.5,  # At least 0.5% up
            'rsi': float(rsi) if pd.notna(rsi) else 50,
            'supertrend_bullish': supertrend_dir == 1 if pd.notna(supertrend_dir) else None
        }
    
    def analyze_metal_stock(self, stock: str, trade_date: date, entry_time: dt_time = dt_time(14, 0)) -> dict:
        """Analyze a metal stock for trading"""
        if stock not in self.stocks_data:
            return None
        
        df = self.stocks_data[stock]
        day_data = df[df['timestamp'].dt.date == trade_date].copy()
        
        if len(day_data) < 20:
            return None
        
        day_data['time'] = day_data['timestamp'].dt.time
        morning_data = day_data[day_data['time'] <= entry_time]
        
        if len(morning_data) < 10:
            return None
        
        entry_row = morning_data.iloc[-1]
        entry_price = float(entry_row['close'])
        morning_open = float(morning_data.iloc[0]['open'])
        morning_change = ((entry_price - morning_open) / morning_open) * 100
        
        return {
            'stock': stock,
            'entry_price': entry_price,
            'morning_change': morning_change,
            'rsi': float(entry_row.get('rsi_14')) if pd.notna(entry_row.get('rsi_14')) else 50,
            'day_data': day_data,
            'entry_idx': len(morning_data) - 1
        }
    
    def simulate_ce_trade(self, analysis: dict, target_pct: float = 50, stop_pct: float = -40) -> dict:
        """Simulate CE trade"""
        day_data = analysis['day_data']
        entry_idx = analysis['entry_idx']
        entry_price = analysis['entry_price']
        
        post_entry = day_data.iloc[entry_idx + 1:]
        
        if len(post_entry) == 0:
            return {'pnl': 0, 'exit_reason': 'NO_DATA', 'exit_pct': 0}
        
        max_price = post_entry['high'].max()
        min_price = post_entry['low'].min()
        close_price = post_entry.iloc[-1]['close']
        
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
    
    def backtest(self, start_date: date, end_date: date) -> list:
        """Run sector strategy backtest"""
        trades = []
        
        current_date = start_date
        day_count = 0
        
        while current_date <= end_date:
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            day_count += 1
            
            # Check sector strength
            sector = self.check_sector_strength(current_date)
            
            if sector and sector['is_strong']:
                if day_count % 5 == 0:
                    print(f"   {current_date}: Sector STRONG ({sector['morning_change']:+.2f}%)")
                
                # Trade all metal stocks that are also strong
                for stock in self.metal_stocks:
                    if stock not in self.stocks_data:
                        continue
                    
                    analysis = self.analyze_metal_stock(stock, current_date)
                    if analysis is None:
                        continue
                    
                    # Only trade if individual stock is also up
                    if analysis['morning_change'] > 0:
                        result = self.simulate_ce_trade(analysis)
                        
                        trades.append({
                            'date': str(current_date),
                            'stock': stock,
                            'sector_change': sector['morning_change'],
                            'stock_change': analysis['morning_change'],
                            'rsi': analysis['rsi'],
                            **result
                        })
            
            current_date += timedelta(days=1)
        
        return trades


def main():
    """Run metals sector strategy backtest"""
    
    print("=" * 80)
    print("🏭 METALS SECTOR MOMENTUM STRATEGY")
    print("=" * 80)
    print("\nStrategy Logic:")
    print("   1. Check if HINDZINC (sector leader) is UP > 0.5% by 14:00")
    print("   2. If yes, buy CE on ALL metal stocks that are also UP")
    print("   3. Exit: 50% target / 40% stop / EOD")
    print("")
    
    backtester = MetalsSectorBacktest()
    backtester.load_stocks()
    
    print(f"\n   Loaded {len(backtester.stocks_data)} metal stocks")
    
    # Test on October 2025
    start_date = date(2025, 10, 1)
    end_date = date(2025, 10, 31)
    
    print(f"\n📅 Period: {start_date} to {end_date}")
    print("-" * 80)
    
    trades = backtester.backtest(start_date, end_date)
    
    print(f"\n📊 RESULTS:")
    print("-" * 80)
    
    if trades:
        df = pd.DataFrame(trades)
        
        total = len(df)
        winners = len(df[df['pnl'] > 0])
        win_rate = winners / total * 100 if total > 0 else 0
        total_pnl = df['pnl'].sum()
        
        print(f"   Total Trades: {total}")
        print(f"   Winners: {winners} ({win_rate:.1f}%)")
        print(f"   Losers: {total - winners}")
        print(f"   Total P&L: ₹{total_pnl:+,.0f}")
        print(f"   Avg P&L: ₹{df['pnl'].mean():+,.0f}")
        
        if winners > 0:
            print(f"   Avg Win: ₹{df[df['pnl'] > 0]['pnl'].mean():+,.0f}")
        if total - winners > 0:
            print(f"   Avg Loss: ₹{df[df['pnl'] <= 0]['pnl'].mean():+,.0f}")
        
        print(f"\n   Exit Reasons:")
        for reason, count in df['exit_reason'].value_counts().items():
            print(f"      {reason}: {count}")
        
        print(f"\n   Stock Performance:")
        stock_perf = df.groupby('stock').agg({
            'pnl': ['count', 'sum', 'mean']
        }).round(0)
        stock_perf.columns = ['trades', 'total_pnl', 'avg_pnl']
        stock_perf = stock_perf.sort_values('total_pnl', ascending=False)
        for stock, row in stock_perf.iterrows():
            print(f"      {stock}: {int(row['trades'])} trades, ₹{row['total_pnl']:+,.0f}")
        
        # Save results
        df.to_csv('backend/data/metals_sector_october.csv', index=False)
        
        results = {
            'strategy': 'Metals Sector Momentum',
            'period': f'{start_date} to {end_date}',
            'trades': total,
            'win_rate': win_rate,
            'total_pnl': total_pnl
        }
        with open('backend/data/metals_sector_summary.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📄 Saved: backend/data/metals_sector_october.csv")
        
        print("\n" + "=" * 80)
        if win_rate >= 50 and total_pnl > 0:
            print("✅ Strategy PROFITABLE!")
        elif win_rate >= 45:
            print("⚠️ Strategy MARGINAL")
        else:
            print("❌ Strategy UNPROFITABLE")
        print("=" * 80)
    else:
        print("   No trades found - sector may not have been strong enough")
    
    print("\n✅ Complete!")


if __name__ == "__main__":
    main()
