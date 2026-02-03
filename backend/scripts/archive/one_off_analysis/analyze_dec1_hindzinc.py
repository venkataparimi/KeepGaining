"""
Analyze HINDZINC on December 1, 2025 to reverse-engineer the strategy
Using futures data as proxy for spot movement
"""
import asyncio
import asyncpg
import pandas as pd
from datetime import datetime, date, time as dt_time

async def analyze_dec1_hindzinc():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    print("=" * 80)
    print("🔍 ANALYZING HINDZINC - DECEMBER 1, 2025")
    print("=" * 80)
    print()
    
    # Get HINDZINC futures data for Dec 1
    # Use nearest expiry futures as proxy for spot
    query = """
        SELECT 
            cd.timestamp,
            cd.open,
            cd.high,
            cd.low,
            cd.close,
            cd.volume,
            im.trading_symbol
        FROM candle_data cd
        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
        WHERE im.underlying = 'HINDZINC'
        AND im.instrument_type = 'FUTURES'
        AND DATE(cd.timestamp) = '2025-12-01'
        AND im.trading_symbol = 'HINDZINC FUT 30 DEC 25'
        ORDER BY cd.timestamp
    """
    
    data = await conn.fetch(query)
    
    if not data:
        print("❌ No data found for Dec 1, 2025")
        await conn.close()
        return
    
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'trading_symbol'])
    
    # Convert timestamp to IST
    df['timestamp'] = pd.to_datetime(df['timestamp']) + pd.Timedelta(hours=5, minutes=30)
    df['time'] = df['timestamp'].dt.time
    
    print(f"✅ Found {len(df)} candles for HINDZINC FUT 30 DEC 25")
    print()
    
    # Market open (9:15 AM)
    market_open = df.iloc[0]
    print("📊 MARKET OPEN (9:15 AM)")
    print(f"   Price: ₹{market_open['close']:.2f}")
    print()
    
    # Price at 14:00 (2:00 PM) - Entry time
    entry_time = dt_time(14, 0)
    entry_candles = df[df['time'] >= entry_time]
    
    if len(entry_candles) > 0:
        entry_candle = entry_candles.iloc[0]
        entry_price = entry_candle['close']
        
        print("⏰ AT 14:00 (ENTRY TIME)")
        print(f"   Price: ₹{entry_price:.2f}")
        print(f"   Volume: {entry_candle['volume']:,}")
        print()
        
        # Calculate morning movement
        morning_move = ((entry_price - market_open['close']) / market_open['close']) * 100
        
        print("📈 MORNING MOVEMENT (9:15 to 14:00)")
        print(f"   Change: {morning_move:+.2f}%")
        print(f"   From: ₹{market_open['close']:.2f} → ₹{entry_price:.2f}")
        print()
        
        # Morning high/low
        morning_df = df[df['time'] < entry_time]
        morning_high = morning_df['high'].max()
        morning_low = morning_df['low'].min()
        
        print("📊 MORNING RANGE")
        print(f"   High: ₹{morning_high:.2f}")
        print(f"   Low: ₹{morning_low:.2f}")
        print(f"   Range: ₹{morning_high - morning_low:.2f} ({((morning_high - morning_low) / morning_low * 100):.2f}%)")
        print()
        
        # Check if breakout
        is_breakout = entry_price > morning_high
        print(f"   Breakout at 14:00? {'✅ YES' if is_breakout else '❌ NO'}")
        if is_breakout:
            print(f"   Broke above morning high by ₹{entry_price - morning_high:.2f}")
        print()
        
        # Post-entry movement
        post_entry_df = df[df['time'] >= entry_time]
        
        if len(post_entry_df) > 1:
            max_price = post_entry_df['high'].max()
            min_price = post_entry_df['low'].min()
            close_price = post_entry_df.iloc[-1]['close']
            
            print("📊 POST-ENTRY MOVEMENT (14:00 to Close)")
            print(f"   Max: ₹{max_price:.2f} (+{((max_price - entry_price) / entry_price * 100):.2f}%)")
            print(f"   Min: ₹{min_price:.2f} ({((min_price - entry_price) / entry_price * 100):.2f}%)")
            print(f"   Close: ₹{close_price:.2f} ({((close_price - entry_price) / entry_price * 100):.2f}%)")
            print()
            
            # Estimate option P&L
            # If 500 CE premium was ₹14, and spot moved X%, option would move ~2X%
            spot_move_pct = ((float(close_price) - float(entry_price)) / float(entry_price)) * 100
            estimated_option_move = spot_move_pct * 2  # Rough delta estimate
            
            print("💰 ESTIMATED OPTION PERFORMANCE")
            print(f"   Entry Premium: ₹14.0")
            print(f"   Spot Move: {spot_move_pct:+.2f}%")
            print(f"   Estimated Option Move: {estimated_option_move:+.2f}%")
            print(f"   Estimated Exit Premium: ₹{14.0 * (1 + estimated_option_move/100):.2f}")
            print(f"   Estimated P&L: ₹{(14.0 * estimated_option_move/100) * 1225:+,.0f}")
            print()
        
        # Volume analysis
        avg_volume = df['volume'].mean()
        entry_volume = entry_candle['volume']
        
        print("📊 VOLUME ANALYSIS")
        print(f"   Average Volume: {avg_volume:,.0f}")
        print(f"   Volume at 14:00: {entry_volume:,.0f}")
        print(f"   Volume Ratio: {entry_volume / avg_volume:.2f}x")
        print()
        
        # Identify the strategy pattern
        print("=" * 80)
        print("🎯 STRATEGY PATTERN IDENTIFICATION")
        print("=" * 80)
        print()
        
        if is_breakout and morning_move > 0:
            print("✅ PATTERN MATCH: POST-LUNCH BREAKOUT")
            print()
            print("Strategy Rules:")
            print("  1. Wait until 14:00 (2:00 PM)")
            print("  2. Check if price > morning high")
            print("  3. Check if morning move > 0%")
            print("  4. Enter ATM CE option")
            print("  5. Target: 50-100% | Stop: -40%")
            
        elif morning_move > 1.0:
            print("✅ PATTERN MATCH: AFTERNOON MOMENTUM")
            print()
            print("Strategy Rules:")
            print("  1. Calculate morning move (9:15 to 14:00)")
            print(f"  2. If move > +1% (was {morning_move:+.2f}%)")
            print("  3. Enter ATM CE at 14:00")
            print("  4. Target: 50% | Stop: -40%")
            
        elif morning_move < 0 and entry_price > morning_low:
            print("✅ PATTERN MATCH: AFTERNOON REVERSAL")
            print()
            print("Strategy Rules:")
            print("  1. Stock dips in morning (negative move)")
            print("  2. At 14:00, check if reversing")
            print("  3. Enter CE if price > morning low")
            print("  4. Target: 50% | Stop: -40%")
            
        else:
            print("✅ PATTERN MATCH: TIME-BASED ENTRY")
            print()
            print("Strategy Rules:")
            print("  1. Always enter at 14:00")
            print("  2. No other conditions")
            print("  3. Statistical edge at this time")
            print("  4. Target: 50% | Stop: -40%")
        
        print()
        
    await conn.close()
    
    print("=" * 80)
    print("✅ Analysis Complete!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(analyze_dec1_hindzinc())
