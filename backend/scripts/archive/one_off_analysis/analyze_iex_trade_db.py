"""
Analyze IEX 140 CE trade using actual database data
Fetch market data, indicators, and identify the exact strategy
"""
import asyncio
import asyncpg
from datetime import datetime, timedelta
import pandas as pd

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

async def get_iex_data_on_dec1():
    """Get IEX market data and indicators for December 1, 2025"""
    
    pool = await asyncpg.create_pool(DB_URL)
    
    async with pool.acquire() as conn:
        # Get IEX instrument ID
        iex_inst = await conn.fetchrow("""
            SELECT instrument_id, trading_symbol 
            FROM instrument_master 
            WHERE trading_symbol = 'IEX' AND instrument_type = 'EQUITY'
        """)
        
        if not iex_inst:
            print("❌ IEX not found in database")
            return None
        
        inst_id = iex_inst['instrument_id']
        
        print("=" * 80)
        print("IEX DATA FOR DECEMBER 1, 2025")
        print("=" * 80)
        
        # Get candle data for Dec 1
        dec1_start = datetime(2025, 12, 1, 0, 0, 0)
        dec1_end = datetime(2025, 12, 1, 23, 59, 59)
        
        candles = await conn.fetch("""
            SELECT timestamp, open, high, low, close, volume
            FROM candle_data
            WHERE instrument_id = $1
            AND timestamp >= $2 AND timestamp <= $3
            AND timeframe = '1m'
            ORDER BY timestamp ASC
        """, inst_id, dec1_start, dec1_end)
        
        if not candles:
            print("\n⚠️  No candle data found for December 1, 2025")
            print("Checking available data range...")
            
            date_range = await conn.fetchrow("""
                SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest
                FROM candle_data
                WHERE instrument_id = $1
            """, inst_id)
            
            print(f"Available data: {date_range['earliest']} to {date_range['latest']}")
            
            # Get data from latest available date instead
            latest_date = date_range['latest'].date()
            print(f"\n📊 Using latest available data: {latest_date}")
            
            latest_start = datetime.combine(latest_date, datetime.min.time())
            latest_end = datetime.combine(latest_date, datetime.max.time())
            
            candles = await conn.fetch("""
                SELECT timestamp, open, high, low, close, volume
                FROM candle_data
                WHERE instrument_id = $1
                AND timestamp >= $2 AND timestamp <= $3
                AND timeframe = '1m'
                ORDER BY timestamp ASC
            """, inst_id, latest_start, latest_end)
        
        if candles:
            df = pd.DataFrame([dict(c) for c in candles])
            
            # Convert to numeric
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            print(f"\n📈 Market Data Summary:")
            print(f"   Trading Date: {df['timestamp'].iloc[0].date()}")
            print(f"   Open: ₹{df['open'].iloc[0]:.2f}")
            print(f"   High: ₹{df['high'].max():.2f}")
            print(f"   Low: ₹{df['low'].min():.2f}")
            print(f"   Close: ₹{df['close'].iloc[-1]:.2f}")
            print(f"   Volume: {df['volume'].sum():,.0f}")
            print(f"   Price at 9:30 AM: ₹{df['close'].iloc[0]:.2f}")
            
            # Calculate intraday move
            day_high = df['high'].max()
            day_low = df['low'].min()
            day_range = ((day_high - day_low) / day_low) * 100
            
            print(f"\n📊 Intraday Movement:")
            print(f"   Range: ₹{day_low:.2f} - ₹{day_high:.2f}")
            print(f"   Movement: {day_range:.2f}%")
            
            return df, inst_id
        else:
            print("❌ No data available")
            return None, None
    
    await pool.close()

async def get_indicators(inst_id, date):
    """Get technical indicators for the date"""
    
    pool = await asyncpg.create_pool(DB_URL)
    
    async with pool.acquire() as conn:
        # Get indicators from indicator_data table
        indicators = await conn.fetch("""
            SELECT timestamp, rsi_14, macd, macd_signal, 
                   sma_20, sma_50, bb_upper, bb_lower, supertrend
            FROM indicator_data
            WHERE instrument_id = $1
            AND DATE(timestamp) = $2
            AND timeframe = '1m'
            ORDER BY timestamp ASC
        """, inst_id, date)
        
        if indicators:
            df = pd.DataFrame([dict(i) for i in indicators])
            
            print("\n📊 Technical Indicators (at market open):")
            first = df.iloc[0]
            print(f"   RSI: {first['rsi_14']:.2f if first['rsi_14'] else 'N/A'}")
            print(f"   MACD: {first['macd']:.2f if first['macd'] else 'N/A'}")
            print(f"   MACD Signal: {first['macd_signal']:.2f if first['macd_signal'] else 'N/A'}")
            print(f"   SMA 20: ₹{first['sma_20']:.2f if first['sma_20'] else 'N/A'}")
            print(f"   SMA 50: ₹{first['sma_50']:.2f if first['sma_50'] else 'N/A'}")
            print(f"   Supertrend: ₹{first['supertrend']:.2f if first['supertrend'] else 'N/A'}")
            
            return df
        else:
            print("\n⚠️  No indicator data found")
            return None
    
    await pool.close()

async def analyze_strategy():
    """Complete strategy analysis"""
    
    result = await get_iex_data_on_dec1()
    
    if result and result[0] is not None:
        df, inst_id = result
        date = df['timestamp'].iloc[0].date()
        
        # Get indicators
        indicators_df = await get_indicators(inst_id, date)
        
        # Analyze the trade
        print("\n" + "=" * 80)
        print("STRATEGY ANALYSIS")
        print("=" * 80)
        
        spot_price = df['close'].iloc[0]  # Price at market open
        strike = 140
        premium = 9
        
        print(f"\n🎯 Trade Setup:")
        print(f"   IEX Spot Price: ₹{spot_price:.2f}")
        print(f"   Strike Price: ₹{strike}")
        print(f"   Premium Paid: ₹{premium}")
        print(f"   Moneyness: {'ITM' if spot_price > strike else 'OTM'} by ₹{abs(spot_price - strike):.2f}")
        
        # Determine strategy based on price action
        if spot_price < strike:
            otm_percent = ((strike - spot_price) / spot_price) * 100
            print(f"\n📈 Strategy Type: BULLISH SPECULATION")
            print(f"   OTM by: {otm_percent:.2f}%")
            print(f"   Expecting: {otm_percent:.2f}% move up to break-even")
        else:
            itm_percent = ((spot_price - strike) / strike) * 100
            print(f"\n📈 Strategy Type: ITM CALL (Lower Risk)")
            print(f"   ITM by: {itm_percent:.2f}%")
        
        # Check for breakout
        day_high = df['high'].max()
        if indicators_df is not None and not indicators_df.empty:
            sma_20 = indicators_df.iloc[0]['sma_20']
            sma_50 = indicators_df.iloc[0]['sma_50']
            rsi = indicators_df.iloc[0]['rsi_14']
            
            print(f"\n🔍 Entry Signals:")
            if sma_20 and sma_50:
                if spot_price > sma_20:
                    print(f"   ✅ Price above SMA 20 (₹{sma_20:.2f}) - Bullish")
                if spot_price > sma_50:
                    print(f"   ✅ Price above SMA 50 (₹{sma_50:.2f}) - Strong trend")
            
            if rsi:
                if 50 < rsi < 70:
                    print(f"   ✅ RSI at {rsi:.2f} - Healthy momentum")
                elif rsi > 70:
                    print(f"   ⚠️  RSI at {rsi:.2f} - Overbought")
        
        print(f"\n💰 Risk/Reward:")
        print(f"   Max Loss: ₹{premium * 3750:,.0f}")
        print(f"   Break-even: ₹{strike + premium}")
        print(f"   Required move: {((strike + premium - spot_price) / spot_price * 100):.2f}%")
        
        return df, indicators_df
    else:
        print("\n❌ Could not retrieve data for analysis")
        return None, None

if __name__ == "__main__":
    asyncio.run(analyze_strategy())
