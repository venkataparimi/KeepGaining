"""
FINAL REALISTIC BACKTEST - Using Real Option Data
Fixed version with proper symbol parsing
Tests on NIFTY first for speed
"""
import asyncio
import asyncpg
from datetime import datetime, timedelta, time as dt_time
import pandas as pd
import json

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

def parse_trading_symbol(trading_symbol):
    """Parse: 'NIFTY 27000 CE 30 DEC 25' -> (27000, date, 'CE')"""
    try:
        parts = trading_symbol.strip().split()
        if len(parts) < 6:
            return None, None, None
        
        strike = int(parts[1])
        option_type = parts[2]
        day = int(parts[3])
        month_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                     'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
        month = month_map.get(parts[4].upper())
        year = 2000 + int(parts[5])
        
        if month:
            expiry = datetime(year, month, day).date()
            return strike, expiry, option_type
    except:
        pass
    return None, None, None

class FinalRealisticBacktest:
    def __init__(self, start_date, end_date, test_symbols=['NIFTY']):
        self.pool = None
        self.start_date = start_date
        self.end_date = end_date
        self.test_symbols = test_symbols
        self.all_trades = []
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(DB_URL)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def get_spot_data(self, symbol, date):
        """Get equity data"""
        async with self.pool.acquire() as conn:
            inst = await conn.fetchrow("""
                SELECT instrument_id FROM instrument_master
                WHERE trading_symbol = $1 AND instrument_type = 'EQUITY'
            """, symbol)
            
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
                df['timestamp'] = df['timestamp'] + timedelta(hours=5, minutes=30)  # Convert to IST
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                return df
            return None
    
    async def find_atm_option(self, underlying, date, spot_price, option_type):
        """Find ATM option using real data"""
        async with self.pool.acquire() as conn:
            # Determine strike interval
            strike_interval = 50 if underlying in ['NIFTY', 'BANKNIFTY'] else 100
            atm_strike = round(spot_price / strike_interval) * strike_interval
            
            # Find options near ATM
            options = await conn.fetch("""
                SELECT instrument_id, trading_symbol, lot_size
                FROM instrument_master
                WHERE underlying = $1
                AND instrument_type = $2
                ORDER BY trading_symbol
            """, underlying, option_type)
            
            # Parse and find best match
            best_option = None
            min_diff = float('inf')
            
            for opt in options:
                strike, expiry, opt_type = parse_trading_symbol(opt['trading_symbol'])
                if strike and expiry and expiry >= date:
                    diff = abs(strike - atm_strike)
                    if diff < min_diff:
                        min_diff = diff
                        best_option = (opt['instrument_id'], opt['trading_symbol'], strike, expiry, opt['lot_size'])
            
            return best_option
    
    async def get_option_prices(self, instrument_id, date):
        """Get real option prices"""
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
                df['timestamp'] = df['timestamp'] + timedelta(hours=5, minutes=30)  # Convert to IST
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                return df
            return None
    
    def check_entry_signal(self, spot_df):
        """Check entry conditions"""
        if spot_df is None or spot_df.empty or len(spot_df) < 15:
            return False, None
        
        day_open = spot_df['open'].iloc[0]
        morning_time = dt_time(9, 30)
        morning_candles = spot_df[spot_df['timestamp'].dt.time <= morning_time]
        
        if morning_candles.empty:
            return False, None
        
        price_930 = morning_candles['close'].iloc[-1]
        early_momentum = ((price_930 - day_open) / day_open) * 100
        
        if early_momentum > 0.5:
            return True, 'CE'
        elif early_momentum < -0.5:
            return True, 'PE'
        return False, None
    
    async def execute_trade(self, spot_df, option_df, strike, lot_size):
        """Execute using REAL prices"""
        if not lot_size: lot_size = 1
        
        entry_idx = min(15, len(option_df) - 1)
        entry_time = option_df['timestamp'].iloc[entry_idx]
        entry_spot = spot_df['close'].iloc[entry_idx]
        entry_premium = option_df['close'].iloc[entry_idx]
        
        if pd.isna(entry_premium) or entry_premium <= 0:
            return None
        
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
            
            if pnl_pct >= 50:
                exit_idx = i
                exit_reason = 'Target (50%)'
                break
            if pnl_pct <= -40:
                exit_idx = i
                exit_reason = 'Stop (-40%)'
                break
            if current_time.hour >= 14 and current_time.minute >= 30:
                exit_idx = i
                exit_reason = 'Time (2:30PM)'
                break
        
        exit_time = option_df['timestamp'].iloc[exit_idx]
        exit_spot = spot_df['close'].iloc[min(exit_idx, len(spot_df)-1)]
        exit_premium = option_df['close'].iloc[exit_idx]
        
        if pd.isna(exit_premium):
            return None
        
        option_pnl_pct = ((exit_premium - entry_premium) / entry_premium) * 100
        option_pnl_amount = (exit_premium - entry_premium) * lot_size
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
            'max_loss_pct': max_loss_pct,
            'strike': strike
        }
    
    async def backtest_date(self, symbol, date):
        """Backtest one day"""
        spot_df = await self.get_spot_data(symbol, date)
        if spot_df is None:
            return None
        
        enter, option_type = self.check_entry_signal(spot_df)
        if not enter:
            return None
        
        day_open = spot_df['open'].iloc[0]
        option_data = await self.find_atm_option(symbol, date, day_open, option_type)
        
        if not option_data:
            return None
        
        inst_id, trading_symbol, strike, expiry, lot_size = option_data
        
        option_df = await self.get_option_prices(inst_id, date)
        if option_df is None or option_df.empty:
            return None
        
        result = await self.execute_trade(spot_df, option_df, strike, lot_size)
        if result is None:
            return None
        
        return {
            'date': date,
            'stock': symbol,
            'strike': result['strike'],
            'option_type': option_type,
            'option_symbol': trading_symbol,
            **result
        }
    
    async def run(self):
        """Run backtest"""
        print("=" * 100)
        print("FINAL REALISTIC BACKTEST - Using REAL Option Prices")
        print("=" * 100)
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Symbols: {', '.join(self.test_symbols)}")
        print()
        
        dates = []
        current = self.start_date
        while current <= self.end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        print(f"Testing {len(dates)} days on {len(self.test_symbols)} symbols")
        print("-" * 100)
        
        for symbol in self.test_symbols:
            for date in dates:
                trade = await self.backtest_date(symbol, date)
                if trade:
                    self.all_trades.append(trade)
                    status = "✅" if trade['option_pnl_pct'] > 0 else "❌"
                    print(f"{status} {date} | {symbol:10} | {trade['option_type']} {trade['strike']:6.0f} | "
                          f"₹{trade['entry_premium']:7.2f} → ₹{trade['exit_premium']:7.2f} | "
                          f"{trade['option_pnl_pct']:+6.1f}% | ₹{trade['option_pnl_amount']:+10,.0f} | "
                          f"{trade['exit_reason']}")
        
        print("-" * 100)
        print(f"\n✅ Found {len(self.all_trades)} trades")
        
        if self.all_trades:
            df = pd.DataFrame(self.all_trades)
            
            total = len(df)
            wins = len(df[df['option_pnl_pct'] > 0])
            win_rate = (wins / total) * 100
            total_pnl = df['option_pnl_amount'].sum()
            avg_win = df[df['option_pnl_pct'] > 0]['option_pnl_pct'].mean() if wins > 0 else 0
            avg_loss = df[df['option_pnl_pct'] < 0]['option_pnl_pct'].mean() if wins < total else 0
            
            print("\n" + "=" * 100)
            print("RESULTS (REAL DATA)")
            print("=" * 100)
            print(f"Total Trades: {total}")
            print(f"Wins: {wins} ({win_rate:.1f}%)")
            print(f"Total P&L: ₹{total_pnl:+,.0f}")
            print(f"Avg Win: {avg_win:+.1f}%")
            print(f"Avg Loss: {avg_loss:+.1f}%")
            
            import time
            timestamp = int(time.time())
            df.to_csv(f'final_realistic_{timestamp}.csv', index=False)
            print(f"\n💾 Saved to: final_realistic_{timestamp}.csv")

async def main():
    # Get all F&O stocks from database
    conn = await asyncpg.connect(DB_URL)
    stocks = await conn.fetch("""
        SELECT DISTINCT underlying FROM instrument_master
        WHERE instrument_type IN ('CE', 'PE')
        AND underlying IS NOT NULL
        AND underlying != ''
        AND underlying NOT IN ('NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY')  -- Exclude indices
        ORDER BY underlying
    """)
    test_symbols = [s['underlying'] for s in stocks]
    await conn.close()
    
    print(f"Testing on {len(test_symbols)} F&O stocks")
    
    backtest = FinalRealisticBacktest(
        start_date=datetime(2025, 11, 1).date(),
        end_date=datetime(2025, 11, 30).date(),
        test_symbols=test_symbols  # All F&O stocks
    )
    
    await backtest.connect()
    await backtest.run()
    await backtest.close()

if __name__ == "__main__":
    asyncio.run(main())
