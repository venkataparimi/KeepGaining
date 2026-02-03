"""
Analyze SPOT PRICE movements of HINDZINC and HEROMOTOCO on Dec 1, 2025
to identify what triggered the 14:00 option entries
"""
import asyncio
import asyncpg
import pandas as pd
from datetime import datetime, date, time as dt_time

async def analyze_spot_movements():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    print("=" * 80)
    print("🔍 ANALYZING SPOT PRICE MOVEMENTS - DECEMBER 1, 2025")
    print("=" * 80)
    print("\nFocus: What happened in the EQUITY stocks that triggered option entries?")
    print()
    
    stocks = ['HINDZINC', 'HEROMOTOCO']
    
    for stock in stocks:
        print("\n" + "=" * 80)
        print(f"📊 {stock} SPOT ANALYSIS")
        print("=" * 80)
        print()
        
        # Get futures data (proxy for spot)
        query = """
            SELECT 
                cd.timestamp,
                cd.open,
                cd.high,
                cd.low,
                cd.close,
                cd.volume
            FROM candle_data cd
            JOIN instrument_master im ON cd.instrument_id = im.instrument_id
            WHERE im.underlying = $1
            AND im.instrument_type = 'FUTURES'
            AND DATE(cd.timestamp) = '2025-12-01'
            ORDER BY cd.timestamp
        """
        
        data = await conn.fetch(query, stock)
        
        if not data:
            print(f"❌ No data for {stock}")
            continue
        
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp']) + pd.Timedelta(hours=5, minutes=30)
        df['time'] = df['timestamp'].dt.time
        
        # Key time points
        market_open = df.iloc[0]
        
        # Find 14:00 candle
        entry_time = dt_time(14, 0)
        entry_idx = df[df['time'] >= entry_time].index[0] if len(df[df['time'] >= entry_time]) > 0 else None
        
        if entry_idx is None:
            print(f"❌ No 14:00 data")
            continue
        
        entry_candle = df.loc[entry_idx]
        
        # Morning data (9:15 to 14:00)
        morning_df = df[df.index < entry_idx]
        
        # Calculate key metrics
        open_price = float(market_open['close'])
        entry_price = float(entry_candle['close'])
        morning_high = float(morning_df['high'].max())
        morning_low = float(morning_df['low'].min())
        morning_range = morning_high - morning_low
        
        # Movement metrics
        morning_move = ((entry_price - open_price) / open_price) * 100
        from_high = ((entry_price - morning_high) / morning_high) * 100
        from_low = ((entry_price - morning_low) / morning_low) * 100
        
        print(f"📈 PRICE LEVELS:")
        print(f"   Open (9:15):     ₹{open_price:.2f}")
        print(f"   Morning High:    ₹{morning_high:.2f}")
        print(f"   Morning Low:     ₹{morning_low:.2f}")
        print(f"   Morning Range:   ₹{morning_range:.2f} ({(morning_range/morning_low*100):.2f}%)")
        print(f"   Price at 14:00:  ₹{entry_price:.2f}")
        print()
        
        print(f"📊 MOVEMENT ANALYSIS:")
        print(f"   From Open:       {morning_move:+.2f}%")
        print(f"   From High:       {from_high:+.2f}%")
        print(f"   From Low:        {from_low:+.2f}%")
        print()
        
        # Check for breakout
        is_breakout = entry_price > morning_high
        is_breakdown = entry_price < morning_low
        is_consolidating = morning_low < entry_price < morning_high
        
        print(f"🎯 PATTERN IDENTIFICATION:")
        if is_breakout:
            print(f"   ✅ BREAKOUT - Price above morning high")
            print(f"      Breakout amount: ₹{entry_price - morning_high:.2f}")
        elif is_breakdown:
            print(f"   ⚠️  BREAKDOWN - Price below morning low")
            print(f"      Breakdown amount: ₹{morning_low - entry_price:.2f}")
        else:
            print(f"   📊 CONSOLIDATION - Price within morning range")
            position_in_range = ((entry_price - morning_low) / morning_range) * 100
            print(f"      Position in range: {position_in_range:.1f}%")
        print()
        
        # Volume analysis
        avg_morning_vol = morning_df['volume'].mean()
        entry_vol = float(entry_candle['volume'])
        vol_ratio = entry_vol / avg_morning_vol if avg_morning_vol > 0 else 0
        
        print(f"📊 VOLUME ANALYSIS:")
        print(f"   Avg Morning Vol: {avg_morning_vol:,.0f}")
        print(f"   Volume at 14:00: {entry_vol:,.0f}")
        print(f"   Volume Ratio:    {vol_ratio:.2f}x")
        if vol_ratio > 1.5:
            print(f"   ✅ HIGH VOLUME SPIKE")
        elif vol_ratio > 1.0:
            print(f"   📊 ABOVE AVERAGE")
        else:
            print(f"   📉 BELOW AVERAGE")
        print()
        
        # Momentum analysis (last 30 min before entry)
        last_30min = df[(df.index >= entry_idx - 30) & (df.index < entry_idx)]
        if len(last_30min) > 0:
            momentum_start = float(last_30min.iloc[0]['close'])
            momentum_move = ((entry_price - momentum_start) / momentum_start) * 100
            
            print(f"⚡ MOMENTUM (Last 30 min):")
            print(f"   From 13:30:      {momentum_move:+.2f}%")
            if abs(momentum_move) > 0.5:
                print(f"   ✅ STRONG MOMENTUM")
            else:
                print(f"   📊 WEAK MOMENTUM")
        print()
        
        # Post-entry movement (to understand if entry was good)
        post_entry = df[df.index > entry_idx]
        if len(post_entry) > 0:
            max_after = float(post_entry['high'].max())
            min_after = float(post_entry['low'].min())
            close_price = float(post_entry.iloc[-1]['close'])
            
            max_gain = ((max_after - entry_price) / entry_price) * 100
            max_loss = ((min_after - entry_price) / entry_price) * 100
            final_move = ((close_price - entry_price) / entry_price) * 100
            
            print(f"📈 POST-ENTRY MOVEMENT:")
            print(f"   Max Gain:        +{max_gain:.2f}%")
            print(f"   Max Loss:        {max_loss:.2f}%")
            print(f"   Close Move:      {final_move:+.2f}%")
            print()
    
    await conn.close()
    
    # Summary and pattern identification
    print("\n" + "=" * 80)
    print("🎯 STRATEGY PATTERN IDENTIFICATION")
    print("=" * 80)
    print()
    
    print("Based on spot price analysis, the entry trigger could be:")
    print()
    print("1️⃣  BREAKOUT STRATEGY:")
    print("   • Wait until 14:00")
    print("   • Check if price > morning high")
    print("   • If yes, enter ATM CE")
    print()
    print("2️⃣  MOMENTUM STRATEGY:")
    print("   • Calculate morning move (9:15 to 14:00)")
    print("   • If move > +X%, enter CE at 14:00")
    print("   • Ride the momentum")
    print()
    print("3️⃣  RANGE BREAKOUT:")
    print("   • Identify morning range")
    print("   • At 14:00, check if breaking out")
    print("   • Enter on breakout confirmation")
    print()
    print("4️⃣  TIME + VOLUME:")
    print("   • Fixed 14:00 entry")
    print("   • Check for volume spike")
    print("   • Enter if volume > 1.5x average")
    print()
    print("5️⃣  CONSOLIDATION BREAKOUT:")
    print("   • Morning consolidation")
    print("   • 14:00 breakout from range")
    print("   • Enter CE on upside break")
    print()

if __name__ == "__main__":
    asyncio.run(analyze_spot_movements())
