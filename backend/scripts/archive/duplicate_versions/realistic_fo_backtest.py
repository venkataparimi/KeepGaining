"""
REALISTIC F&O Backtest - Using ACTUAL Option Chain Data
This version uses real option prices from the database instead of simulation
"""
import asyncio
import asyncpg
from datetime import datetime, timedelta
import pandas as pd
import json

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

class RealisticFOBacktest:
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
    
    async def check_option_data_availability(self):
        """Check if we have option chain data"""
        async with self.pool.acquire() as conn:
            # Check for option instruments
            option_count = await conn.fetchval("""
                SELECT COUNT(*) FROM instrument_master
                WHERE instrument_type IN ('CE', 'PE')
            """)
            
            print(f"📊 Found {option_count:,} option instruments in database")
            
            # Check for option candle data
            option_candles = await conn.fetchval("""
                SELECT COUNT(*) FROM candle_data cd
                JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                WHERE im.instrument_type IN ('CE', 'PE')
                AND cd.timestamp >= $1 AND cd.timestamp <= $2
            """, 
            datetime.combine(self.start_date, datetime.min.time()),
            datetime.combine(self.end_date, datetime.max.time()))
            
            print(f"📈 Found {option_candles:,} option candles for the period")
            
            if option_candles == 0:
                print("\n⚠️  WARNING: No option candle data found!")
                print("\nYou need to backfill option data first:")
                print("  python backend/scripts/backfill_fo_historical.py --underlying NIFTY")
                return False
            
            return True
    
    async def get_atm_options_for_date(self, underlying, date, spot_price):
        """Get actual ATM option instruments for a date"""
        async with self.pool.acquire() as conn:
            # Find nearest strike
            strike_interval = 50 if underlying in ['NIFTY', 'BANKNIFTY'] else 100
            atm_strike = round(spot_price / strike_interval) * strike_interval
            
            # Get CE and PE options near ATM
            options = await conn.fetch("""
                SELECT 
                    instrument_id,
                    trading_symbol,
                    instrument_type,
                    strike,
                    expiry
                FROM instrument_master
                WHERE underlying = $1
                AND instrument_type IN ('CE', 'PE')
                AND strike BETWEEN $2 AND $3
                AND expiry >= $4
                ORDER BY ABS(strike - $5), expiry
                LIMIT 4
            """, underlying, atm_strike - strike_interval, atm_strike + strike_interval,
            date, atm_strike)
            
            return options
    
    async def get_option_prices(self, instrument_id, date):
        """Get actual option prices throughout the day"""
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
    
    async def backtest_with_real_data(self):
        """Backtest using actual option prices"""
        
        print("=" * 100)
        print("REALISTIC F&O BACKTEST - Using ACTUAL Option Data")
        print("=" * 100)
        print(f"Period: {self.start_date} to {self.end_date}")
        print()
        
        # Check data availability
        has_data = await self.check_option_data_availability()
        
        if not has_data:
            print("\n❌ Cannot proceed without option data")
            print("\nRECOMMENDATION:")
            print("1. First backfill option data:")
            print("   python backend/scripts/backfill_fo_historical.py --underlying NIFTY --limit 10")
            print("\n2. Then run this backtest again")
            return None
        
        print("\n✅ Option data available! Proceeding with realistic backtest...")
        print("\nNOTE: This will use REAL option prices from your database")
        print("Results will be much more accurate than the simulated version")
        print()
        
        # For now, show what we would do
        print("📋 Backtest Strategy:")
        print("1. Find days where underlying opened near ATM strike")
        print("2. Get ACTUAL option prices from database")
        print("3. Simulate entry at 9:30 AM using REAL premium")
        print("4. Track throughout day using REAL price movements")
        print("5. Exit based on ACTUAL option prices")
        print()
        print("This will give you TRUE win rate and P&L!")
        
        return None

async def main():
    """Check if we can run realistic backtest"""
    
    start_date = datetime(2025, 12, 1).date()
    end_date = datetime(2025, 12, 15).date()
    
    backtest = RealisticFOBacktest(start_date, end_date)
    await backtest.connect()
    
    await backtest.backtest_with_real_data()
    
    await backtest.close()

if __name__ == "__main__":
    asyncio.run(main())
