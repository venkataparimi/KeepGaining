"""
REALISTIC F&O Backtest - Using ACTUAL Option Prices from Database
This version uses real historical option data instead of simulation
"""
import asyncio
import asyncpg
from datetime import datetime, timedelta, time as dt_time
import pandas as pd
import json
from collections import defaultdict

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

class RealDataBacktest:
    """
    Backtest using REAL option prices from database
    No simulation - only actual market data
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
    
    async def get_underlying_stocks(self):
        """Get list of F&O underlying stocks"""
        async with self.pool.acquire() as conn:
            stocks = await conn.fetch("""
                SELECT DISTINCT underlying
                FROM instrument_master
                WHERE instrument_type IN ('CE', 'PE')
                AND underlying IS NOT NULL
                AND underlying != ''
                ORDER BY underlying
            """)
            return [s['underlying'] for s in stocks]
    
    async def get_spot_data(self, underlying, date):
        """Get spot/equity data for underlying"""
        async with self.pool.acquire() as conn:
            # Get equity instrument
            inst = await conn.fetchrow("""
                SELECT instrument_id FROM instrument_master
                WHERE trading_symbol = $1 AND instrument_type = 'EQUITY'
            """, underlying)
            
            if not inst:
                return None
            
            start = datetime.combine(date, datetime.min.time())
            end = datetime.combine(date, datetime.max.time())
            
            candles = await conn.fetch("""
                SELECT timestamp, open, high, low, close, volume
                FROM candle_data
                WHERE instrument_id = $1
                AND timestamp >= $2 AND timestamp <= $3
                AND timeframe = '1m'
                ORDER BY timestamp ASC
            """, inst['instrument_id'], start, end)
            
            if candles:
                df = pd.DataFrame([dict(c) for c in candles])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                return df
            return None
    
    async def find_atm_option(self, underlying, date, spot_price, option_type='CE'):
        """Find ATM option instrument for the date"""
        async with self.pool.acquire() as conn:
            # Determine strike interval
            if underlying in ['NIFTY', 'BANKNIFTY', 'FINNIFTY']:
                strike_interval = 50
            elif spot_price < 500:
                strike_interval = 10
            elif spot_price < 1000:
                strike_interval = 25
            elif spot_price < 2000:
                strike_interval = 50
            else:
                strike_interval = 100
            
            atm_strike = round(spot_price / strike_interval) * strike_interval
            
            # Find option with this strike that was active on this date
            option = await conn.fetchrow("""
                SELECT instrument_id, trading_symbol, strike, expiry
                FROM instrument_master
                WHERE underlying = $1
                AND instrument_type = $2
                AND strike = $3
                AND expiry >= $4
                ORDER BY expiry ASC
                LIMIT 1
            """, underlying, option_type, atm_strike, date)
            
            return option
    
    async def get_option_prices(self, instrument_id, date):
        """Get actual option prices for the day"""
        async with self.pool.acquire() as conn:
            start = datetime.combine(date, datetime.min.time())
            end = datetime.combine(date, datetime.max.time())
            
            candles = await conn.fetch("""
                SELECT timestamp, open, high, low, close, volume
                FROM candle_data
                WHERE instrument_id = $1
                AND timestamp >= $2 AND timestamp <= $3
                AND timeframe = '1m'
                ORDER BY timestamp ASC
            """, instrument_id, start, end)
            
            if candles:
                df = pd.DataFrame([dict(c) for c in candles])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                return df
            return None
    
    def check_entry_signal(self, spot_df):
        """Check if entry conditions are met"""
        if spot_df is None or spot_df.empty or len(spot_df) < 15:
            return False, None
        
        day_open = spot_df['open'].iloc[0]
        
        # Get price at 9:30 AM
        morning_time = dt_time(9, 30)
        morning_candles = spot_df[spot_df['timestamp'].dt.time <= morning_time]
        
        if morning_candles.empty:
            return False, None
        
        price_930 = morning_candles['close'].iloc[-1]
        
        # Check early momentum
        early_momentum = ((price_930 - day_open) / day_open) * 100
        
        # Determine option type
        if early_momentum > 0.5:
            option_type = 'CE'
        elif early_momentum < -0.5:
            option_type = 'PE'
        else:
            return False, None
        
        return True, option_type
    
    async def execute_trade(self, spot_df, option_df, option_type, strike):
        """Execute trade using real option prices"""
        
        # Entry at 9:30 AM (index ~15)
        entry_idx = min(15, len(option_df) - 1)
        entry_time = option_df['timestamp'].iloc[entry_idx]
        entry_spot = spot_df['close'].iloc[entry_idx]
        entry_premium = option_df['close'].iloc[entry_idx]
        
        if pd.isna(entry_premium) or entry_premium <= 0:
            return None
        
        # Track throughout the day
        max_profit_pct = 0
        max_loss_pct = 0
        exit_idx = len(option_df) - 1
        exit_reason = 'Time Stop'
        
        for i in range(entry_idx, len(option_df)):
            current_premium = option_df['close'].iloc[i]
            current_time = option_df['timestamp'].iloc[i]
            
            if pd.isna(current_premium):
                continue
            
            pnl_pct = ((current_premium - entry_premium) / entry_premium) * 100
            
            if pnl_pct > max_profit_pct:
                max_profit_pct = pnl_pct
            if pnl_pct < max_loss_pct:
                max_loss_pct = pnl_pct
            
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
        exit_time = option_df['timestamp'].iloc[exit_idx]
        exit_spot = spot_df['close'].iloc[min(exit_idx, len(spot_df)-1)]
        exit_premium = option_df['close'].iloc[exit_idx]
        
        if pd.isna(exit_premium):
            return None
        
        option_pnl_pct = ((exit_premium - entry_premium) / entry_premium) * 100
        option_pnl_amount = (exit_premium - entry_premium) * 3750  # Standard lot
        
        stock_pnl_pct = ((exit_spot - entry_spot) / entry_spot) * 100
        
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
            'max_profit_pct': max_profit_pct,
            'max_loss_pct': max_loss_pct
        }
    
    async def backtest_stock_date(self, underlying, date):
        """Backtest a single stock for a single date using real data"""
        
        # Get spot data
        spot_df = await self.get_spot_data(underlying, date)
        if spot_df is None:
            return None
        
        # Check entry signal
        enter, option_type = self.check_entry_signal(spot_df)
        if not enter:
            return None
        
        # Find ATM option
        day_open = spot_df['open'].iloc[0]
        option_inst = await self.find_atm_option(underlying, date, day_open, option_type)
        
        if not option_inst:
            return None
        
        # Get REAL option prices
        option_df = await self.get_option_prices(option_inst['instrument_id'], date)
        if option_df is None or option_df.empty:
            return None
        
        # Execute trade with real prices
        result = await self.execute_trade(spot_df, option_df, option_type, option_inst['strike'])
        
        if result is None:
            return None
        
        # Compile trade record
        trade = {
            'date': date,
            'stock': underlying,
            'strike': option_inst['strike'],
            'option_type': option_type,
            'option_symbol': option_inst['trading_symbol'],
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
            'max_profit_pct': result['max_profit_pct'],
            'max_loss_pct': result['max_loss_pct']
        }
        
        return trade
    
    async def run_backtest(self):
        """Run realistic backtest on all stocks"""
        
        print("=" * 100)
        print("REALISTIC F&O BACKTEST - Using ACTUAL Option Prices")
        print("=" * 100)
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Data Source: Real option candles from database")
        print()
        
        # Get stocks
        stocks = await self.get_underlying_stocks()
        print(f"📊 Found {len(stocks)} F&O underlying stocks")
        print(f"Stocks: {', '.join(stocks[:10])}{'...' if len(stocks) > 10 else ''}")
        print()
        
        # Generate dates
        current_date = self.start_date
        dates = []
        while current_date <= self.end_date:
            if current_date.weekday() < 5:
                dates.append(current_date)
            current_date += timedelta(days=1)
        
        print(f"📅 Testing {len(dates)} trading days")
        print()
        print("Running backtest with REAL option prices...")
        print("-" * 100)
        
        # Backtest
        processed = 0
        total = len(stocks) * len(dates)
        
        for stock in stocks:
            for date in dates:
                trade = await self.backtest_stock_date(stock, date)
                
                if trade:
                    self.all_trades.append(trade)
                    status = "✅" if trade['option_pnl_pct'] > 0 else "❌"
                    print(f"{status} {trade['date']} | {trade['stock']:12} | "
                          f"{trade['option_type']} {trade['strike']:6.0f} | "
                          f"Entry: ₹{trade['entry_premium']:7.2f} | "
                          f"Exit: ₹{trade['exit_premium']:7.2f} | "
                          f"PnL: {trade['option_pnl_pct']:+6.1f}% | "
                          f"₹{trade['option_pnl_amount']:+10,.0f} | "
                          f"{trade['exit_reason']}")
                
                processed += 1
                if processed % 50 == 0:
                    print(f"Progress: {processed}/{total} ({processed/total*100:.1f}%)")
        
        print("-" * 100)
        print(f"\n✅ Backtest complete! Found {len(self.all_trades)} trades with real data")
        
        return self.all_trades
    
    def generate_report(self):
        """Generate comprehensive report"""
        
        if not self.all_trades:
            print("\n⚠️  No trades found")
            return None
        
        df = pd.DataFrame(self.all_trades)
        
        print("\n" + "=" * 100)
        print("REALISTIC BACKTEST RESULTS (Using Real Option Prices)")
        print("=" * 100)
        
        # Statistics
        total_trades = len(df)
        winning_trades = len(df[df['option_pnl_pct'] > 0])
        losing_trades = len(df[df['option_pnl_pct'] < 0])
        
        win_rate = (winning_trades / total_trades) * 100
        
        total_pnl = df['option_pnl_amount'].sum()
        avg_pnl = df['option_pnl_amount'].mean()
        
        avg_win_pct = df[df['option_pnl_pct'] > 0]['option_pnl_pct'].mean() if winning_trades > 0 else 0
        avg_loss_pct = df[df['option_pnl_pct'] < 0]['option_pnl_pct'].mean() if losing_trades > 0 else 0
        
        max_win = df['option_pnl_amount'].max()
        max_loss = df['option_pnl_amount'].min()
        
        print(f"\n📊 TRADE STATISTICS:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Winning Trades: {winning_trades} ({win_rate:.1f}%)")
        print(f"   Losing Trades: {losing_trades}")
        print(f"   Win Rate: {win_rate:.1f}%")
        
        print(f"\n💰 PERFORMANCE (REAL DATA):")
        print(f"   Total P&L: ₹{total_pnl:+,.0f}")
        print(f"   Average P&L per Trade: ₹{avg_pnl:+,.0f}")
        print(f"   Average Win: {avg_win_pct:+.1f}%")
        print(f"   Average Loss: {avg_loss_pct:+.1f}%")
        print(f"   Best Trade: ₹{max_win:+,.0f}")
        print(f"   Worst Trade: ₹{max_loss:+,.0f}")
        
        if losing_trades > 0 and avg_loss_pct != 0:
            profit_factor = abs((winning_trades * avg_win_pct) / (losing_trades * avg_loss_pct))
            print(f"   Profit Factor: {profit_factor:.2f}")
        
        # Top performers
        print(f"\n📈 TOP PERFORMERS:")
        stock_pnl = df.groupby('stock')['option_pnl_amount'].agg(['sum', 'count', 'mean']).sort_values('sum', ascending=False)
        for idx, (stock, row) in enumerate(stock_pnl.head(10).iterrows(), 1):
            print(f"   {idx}. {stock:12} | Trades: {int(row['count']):3} | "
                  f"Total: ₹{row['sum']:+10,.0f} | Avg: ₹{row['mean']:+8,.0f}")
        
        # Save
        output_file = f'realistic_backtest_{self.start_date}_{self.end_date}.csv'
        df.to_csv(output_file, index=False)
        print(f"\n💾 Detailed report saved to: {output_file}")
        
        summary = {
            'period': f"{self.start_date} to {self.end_date}",
            'data_source': 'Real option prices from database',
            'total_trades': int(total_trades),
            'winning_trades': int(winning_trades),
            'win_rate': float(win_rate),
            'total_pnl': float(total_pnl),
            'avg_pnl': float(avg_pnl),
            'avg_win_pct': float(avg_win_pct),
            'avg_loss_pct': float(avg_loss_pct)
        }
        
        with open(f'realistic_summary_{self.start_date}_{self.end_date}.json', 'w') as f:
            json.dump(summary, f, indent=2)
        
        return df

async def main():
    """Run realistic backtest"""
    
    start_date = datetime(2025, 12, 1).date()
    end_date = datetime(2025, 12, 15).date()
    
    backtest = RealDataBacktest(start_date, end_date)
    await backtest.connect()
    
    trades = await backtest.run_backtest()
    
    if trades:
        backtest.generate_report()
    
    await backtest.close()
    
    print("\n" + "=" * 100)
    print("✅ REALISTIC BACKTEST COMPLETE!")
    print("=" * 100)
    print("\nThis backtest used REAL option prices from your database.")
    print("Results are based on actual market data, not simulation.")

if __name__ == "__main__":
    asyncio.run(main())
