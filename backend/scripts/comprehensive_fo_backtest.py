"""
Comprehensive F&O Strategy Backtest
Runs ATM Breakout strategy on all F&O stocks for a specified period
Generates detailed trade log with all metrics
"""
import asyncio
import asyncpg
from datetime import datetime, timedelta
import pandas as pd
import json
from pathlib import Path

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

class ComprehensiveFOBacktest:
    """
    Backtest ATM Breakout strategy on all F&O stocks
    Generate detailed trade log with comprehensive metrics
    """
    
    def __init__(self, start_date, end_date):
        self.pool = None
        self.start_date = start_date
        self.end_date = end_date
        self.all_trades = []
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(DB_URL)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def get_fo_stocks(self):
        """Get all F&O underlying stocks"""
        async with self.pool.acquire() as conn:
            stocks = await conn.fetch("""
                SELECT DISTINCT underlying as symbol
                FROM instrument_master
                WHERE instrument_type IN ('FUTURES', 'CE', 'PE')
                AND underlying IS NOT NULL
                AND underlying != ''
                ORDER BY underlying
            """)
            return [s['symbol'] for s in stocks]
    
    async def get_stock_data(self, symbol, date):
        """Get intraday stock data for a specific date"""
        async with self.pool.acquire() as conn:
            # Get equity instrument
            inst = await conn.fetchrow("""
                SELECT instrument_id FROM instrument_master
                WHERE trading_symbol = $1 AND instrument_type = 'EQUITY'
            """, symbol)
            
            if not inst:
                return None
            
            inst_id = inst['instrument_id']
            
            # Get intraday candles
            start = datetime.combine(date, datetime.min.time())
            end = datetime.combine(date, datetime.max.time())
            
            candles = await conn.fetch("""
                SELECT timestamp, open, high, low, close, volume
                FROM candle_data
                WHERE instrument_id = $1
                AND timestamp >= $2 AND timestamp <= $3
                AND timeframe = '1m'
                ORDER BY timestamp ASC
            """, inst_id, start, end)
            
            if not candles:
                return None
            
            df = pd.DataFrame([dict(c) for c in candles])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
    
    def find_nearest_strike(self, price, strike_interval=None):
        """Find nearest ATM strike"""
        if strike_interval is None:
            # Auto-determine interval based on price
            if price < 100:
                strike_interval = 5
            elif price < 500:
                strike_interval = 10
            elif price < 1000:
                strike_interval = 25
            elif price < 2000:
                strike_interval = 50
            else:
                strike_interval = 100
        
        return round(price / strike_interval) * strike_interval
    
    def check_entry_signal(self, df):
        """Check if entry conditions are met"""
        if df is None or df.empty or len(df) < 15:
            return False, None, None, None
        
        day_open = df['open'].iloc[0]
        
        # Get price at 9:30 AM (first 15 mins)
        morning_candles = df[df['timestamp'].dt.time <= datetime.strptime('09:30', '%H:%M').time()]
        if morning_candles.empty:
            return False, None, None, None
        
        price_930 = morning_candles['close'].iloc[-1]
        
        # Find nearest strike
        strike = self.find_nearest_strike(day_open)
        
        # Check if price is within 2% of strike
        price_diff_pct = abs(day_open - strike) / strike * 100
        if price_diff_pct > 2:
            return False, None, None, None
        
        # Check early momentum (first 15 mins)
        early_momentum = ((price_930 - day_open) / day_open) * 100
        
        # Determine option type based on momentum
        if early_momentum > 0.5:  # Bullish
            option_type = 'CE'
        elif early_momentum < -0.5:  # Bearish
            option_type = 'PE'
        else:
            return False, None, None, None
        
        # Estimate premium (6% of strike for ATM)
        premium = strike * 0.06
        
        return True, strike, option_type, premium
    
    def simulate_option_trade(self, df, strike, option_type, entry_premium, entry_time_idx=15):
        """
        Simulate option trade throughout the day
        Returns detailed trade metrics
        """
        # Entry at 9:30 AM (after first 15 mins)
        entry_spot = df['close'].iloc[entry_time_idx]
        entry_time = df['timestamp'].iloc[entry_time_idx]
        
        # Track price throughout day
        day_high = df['high'].max()
        day_low = df['low'].min()
        day_close = df['close'].iloc[-1]
        
        # Simulate option prices at different times
        max_profit_pct = 0
        max_loss_pct = 0
        exit_idx = len(df) - 1  # Default to close
        exit_reason = 'Time Stop'
        
        # Scan through the day
        for i in range(entry_time_idx, len(df)):
            current_spot = df['close'].iloc[i]
            current_time = df['timestamp'].iloc[i]
            
            # Calculate option value (simplified)
            if option_type == 'CE':
                intrinsic = max(0, current_spot - strike)
            else:  # PE
                intrinsic = max(0, strike - current_spot)
            
            # Time decay factor (decreases throughout day)
            time_factor = 1 - ((i - entry_time_idx) / (len(df) - entry_time_idx)) * 0.7
            time_value = entry_premium * time_factor * 0.5
            
            option_value = intrinsic + time_value
            pnl_pct = ((option_value - entry_premium) / entry_premium) * 100
            
            # Track max profit/loss
            if pnl_pct > max_profit_pct:
                max_profit_pct = pnl_pct
            if pnl_pct < max_loss_pct:
                max_loss_pct = pnl_pct
            
            # Check exit conditions
            # Target: 50% profit
            if pnl_pct >= 50:
                exit_idx = i
                exit_reason = 'Target Hit (50%)'
                break
            
            # Stop loss: 40% loss
            if pnl_pct <= -40:
                exit_idx = i
                exit_reason = 'Stop Loss (-40%)'
                break
            
            # Time stop: 2:30 PM
            if current_time.hour >= 14 and current_time.minute >= 30:
                exit_idx = i
                exit_reason = 'Time Stop (2:30 PM)'
                break
        
        # Calculate exit values
        exit_spot = df['close'].iloc[exit_idx]
        exit_time = df['timestamp'].iloc[exit_idx]
        
        if option_type == 'CE':
            exit_intrinsic = max(0, exit_spot - strike)
        else:
            exit_intrinsic = max(0, strike - exit_spot)
        
        exit_time_factor = 1 - ((exit_idx - entry_time_idx) / (len(df) - entry_time_idx)) * 0.7
        exit_time_value = entry_premium * exit_time_factor * 0.5
        exit_premium = exit_intrinsic + exit_time_value
        
        option_pnl_pct = ((exit_premium - entry_premium) / entry_premium) * 100
        option_pnl_amount = (exit_premium - entry_premium) * 3750  # Standard lot
        
        # Stock movement
        stock_pnl_pct = ((exit_spot - entry_spot) / entry_spot) * 100
        stock_day_pnl_pct = ((day_close - df['open'].iloc[0]) / df['open'].iloc[0]) * 100
        
        return {
            'entry_time': entry_time,
            'entry_spot': entry_spot,
            'entry_premium': entry_premium,
            'exit_time': exit_time,
            'exit_spot': exit_spot,
            'exit_premium': exit_premium,
            'exit_reason': exit_reason,
            'option_pnl_pct': option_pnl_pct,
            'option_pnl_amount': option_pnl_amount,
            'stock_pnl_pct': stock_pnl_pct,
            'stock_day_pnl_pct': stock_day_pnl_pct,
            'max_profit_pct': max_profit_pct,
            'max_loss_pct': max_loss_pct,
            'day_high': day_high,
            'day_low': day_low,
            'day_close': day_close
        }
    
    async def backtest_stock_date(self, symbol, date):
        """Backtest a single stock for a single date"""
        df = await self.get_stock_data(symbol, date)
        
        if df is None:
            return None
        
        # Check entry signal
        enter, strike, option_type, premium = self.check_entry_signal(df)
        
        if not enter:
            return None
        
        # Simulate trade
        result = self.simulate_option_trade(df, strike, option_type, premium)
        
        # Compile trade record
        trade = {
            'date': date,
            'stock': symbol,
            'strike': strike,
            'option_type': option_type,
            'entry_time': result['entry_time'],
            'entry_spot': result['entry_spot'],
            'entry_premium': result['entry_premium'],
            'exit_time': result['exit_time'],
            'exit_spot': result['exit_spot'],
            'exit_premium': result['exit_premium'],
            'exit_reason': result['exit_reason'],
            'option_pnl_pct': result['option_pnl_pct'],
            'option_pnl_amount': result['option_pnl_amount'],
            'stock_pnl_pct': result['stock_pnl_pct'],
            'stock_day_pnl_pct': result['stock_day_pnl_pct'],
            'max_profit_pct': result['max_profit_pct'],
            'max_loss_pct': result['max_loss_pct'],
            'day_high': result['day_high'],
            'day_low': result['day_low'],
            'day_close': result['day_close']
        }
        
        return trade
    
    async def run_backtest(self):
        """Run backtest on all F&O stocks for the period"""
        
        print("=" * 100)
        print("COMPREHENSIVE F&O STRATEGY BACKTEST")
        print("=" * 100)
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Strategy: ATM Breakout Momentum")
        print()
        
        # Get all F&O stocks
        stocks = await self.get_fo_stocks()
        print(f"📊 Found {len(stocks)} F&O stocks")
        print(f"Stocks: {', '.join(stocks[:10])}{'...' if len(stocks) > 10 else ''}")
        print()
        
        # Generate date range
        current_date = self.start_date
        dates = []
        while current_date <= self.end_date:
            # Skip weekends
            if current_date.weekday() < 5:
                dates.append(current_date)
            current_date += timedelta(days=1)
        
        print(f"📅 Testing {len(dates)} trading days")
        print()
        print("Running backtest...")
        print("-" * 100)
        
        # Backtest each stock for each date
        total_combinations = len(stocks) * len(dates)
        processed = 0
        
        for stock in stocks:
            for date in dates:
                trade = await self.backtest_stock_date(stock, date)
                
                if trade:
                    self.all_trades.append(trade)
                    status = "✅" if trade['option_pnl_pct'] > 0 else "❌"
                    print(f"{status} {trade['date']} | {trade['stock']:12} | "
                          f"{trade['option_type']} {trade['strike']:6.0f} | "
                          f"Entry: ₹{trade['entry_premium']:6.2f} | "
                          f"Exit: ₹{trade['exit_premium']:6.2f} | "
                          f"PnL: {trade['option_pnl_pct']:+6.1f}% | "
                          f"₹{trade['option_pnl_amount']:+10,.0f} | "
                          f"{trade['exit_reason']}")
                
                processed += 1
                if processed % 50 == 0:
                    print(f"Progress: {processed}/{total_combinations} ({processed/total_combinations*100:.1f}%)")
        
        print("-" * 100)
        print(f"\n✅ Backtest complete! Found {len(self.all_trades)} trades")
        
        return self.all_trades
    
    def generate_report(self):
        """Generate comprehensive report"""
        
        if not self.all_trades:
            print("\n⚠️  No trades found")
            return None
        
        df = pd.DataFrame(self.all_trades)
        
        print("\n" + "=" * 100)
        print("BACKTEST RESULTS SUMMARY")
        print("=" * 100)
        
        # Overall statistics
        total_trades = len(df)
        winning_trades = len(df[df['option_pnl_pct'] > 0])
        losing_trades = len(df[df['option_pnl_pct'] < 0])
        breakeven_trades = len(df[df['option_pnl_pct'] == 0])
        
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        total_pnl = df['option_pnl_amount'].sum()
        avg_pnl = df['option_pnl_amount'].mean()
        
        avg_win_pct = df[df['option_pnl_pct'] > 0]['option_pnl_pct'].mean() if winning_trades > 0 else 0
        avg_loss_pct = df[df['option_pnl_pct'] < 0]['option_pnl_pct'].mean() if losing_trades > 0 else 0
        
        max_win = df['option_pnl_amount'].max()
        max_loss = df['option_pnl_amount'].min()
        
        print(f"\n📊 TRADE STATISTICS:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Winning Trades: {winning_trades} ({winning_trades/total_trades*100:.1f}%)")
        print(f"   Losing Trades: {losing_trades} ({losing_trades/total_trades*100:.1f}%)")
        print(f"   Breakeven Trades: {breakeven_trades}")
        print(f"   Win Rate: {win_rate:.1f}%")
        
        print(f"\n💰 PERFORMANCE:")
        print(f"   Total P&L: ₹{total_pnl:+,.0f}")
        print(f"   Average P&L per Trade: ₹{avg_pnl:+,.0f}")
        print(f"   Average Win: {avg_win_pct:+.1f}%")
        print(f"   Average Loss: {avg_loss_pct:+.1f}%")
        print(f"   Best Trade: ₹{max_win:+,.0f}")
        print(f"   Worst Trade: ₹{max_loss:+,.0f}")
        
        if losing_trades > 0 and avg_loss_pct != 0:
            profit_factor = abs((winning_trades * avg_win_pct) / (losing_trades * avg_loss_pct))
            print(f"   Profit Factor: {profit_factor:.2f}")
        
        # By stock
        print(f"\n📈 TOP PERFORMERS (by total P&L):")
        stock_pnl = df.groupby('stock')['option_pnl_amount'].agg(['sum', 'count', 'mean']).sort_values('sum', ascending=False)
        for idx, (stock, row) in enumerate(stock_pnl.head(10).iterrows(), 1):
            print(f"   {idx}. {stock:12} | Trades: {int(row['count']):3} | "
                  f"Total: ₹{row['sum']:+10,.0f} | Avg: ₹{row['mean']:+8,.0f}")
        
        # By option type
        print(f"\n📊 BY OPTION TYPE:")
        for opt_type in ['CE', 'PE']:
            type_df = df[df['option_type'] == opt_type]
            if not type_df.empty:
                type_win_rate = len(type_df[type_df['option_pnl_pct'] > 0]) / len(type_df) * 100
                type_pnl = type_df['option_pnl_amount'].sum()
                print(f"   {opt_type}: {len(type_df)} trades | Win Rate: {type_win_rate:.1f}% | P&L: ₹{type_pnl:+,.0f}")
        
        # Save detailed report
        output_file = f'backtest_report_{self.start_date}_{self.end_date}.csv'
        df.to_csv(output_file, index=False)
        print(f"\n💾 Detailed report saved to: {output_file}")
        
        # Save summary
        summary = {
            'period': f"{self.start_date} to {self.end_date}",
            'total_trades': int(total_trades),
            'winning_trades': int(winning_trades),
            'losing_trades': int(losing_trades),
            'win_rate': float(win_rate),
            'total_pnl': float(total_pnl),
            'avg_pnl': float(avg_pnl),
            'avg_win_pct': float(avg_win_pct),
            'avg_loss_pct': float(avg_loss_pct),
            'max_win': float(max_win),
            'max_loss': float(max_loss)
        }
        
        with open(f'backtest_summary_{self.start_date}_{self.end_date}.json', 'w') as f:
            json.dump(summary, f, indent=2)
        
        return df

async def main():
    """Run comprehensive backtest"""
    
    # Backtest for December 2025
    start_date = datetime(2025, 12, 1).date()
    end_date = datetime(2025, 12, 15).date()  # Up to latest data
    
    backtest = ComprehensiveFOBacktest(start_date, end_date)
    await backtest.connect()
    
    # Run backtest
    trades = await backtest.run_backtest()
    
    # Generate report
    if trades:
        backtest.generate_report()
    
    await backtest.close()
    
    print("\n" + "=" * 100)
    print("✅ BACKTEST COMPLETE!")
    print("=" * 100)

if __name__ == "__main__":
    asyncio.run(main())
