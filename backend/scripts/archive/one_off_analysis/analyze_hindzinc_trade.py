"""
Analyze HINDZINC 500 CE trade on Dec 1, 2025
Entry at 14:00 (2:00 PM)
"""
import asyncio
import asyncpg
import pandas as pd
from datetime import datetime, date, time as dt_time

async def analyze_hindzinc_trade():
    """Analyze the specific HINDZINC trade"""
    
    # Connect to database
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    trade_date = date(2025, 12, 1)
    
    print("=" * 80)
    print("🔍 ANALYZING HINDZINC 500 CE TRADE")
    print("=" * 80)
    print(f"Date: {trade_date}")
    print(f"Entry Time: 14:00 (2:00 PM)")
    print(f"Strike: 500 CE")
    print()
    
    # 1. Get HINDZINC spot data for Dec 1
    print("📊 FETCHING HINDZINC SPOT DATA...")
    spot_query = """
        SELECT timestamp, open, high, low, close, volume
        FROM equity_candles
        WHERE symbol = 'HINDZINC'
        AND timestamp::date = $1
        ORDER BY timestamp
    """
    spot_data = await conn.fetch(spot_query, trade_date)
    
    if not spot_data:
        print("❌ No spot data found for HINDZINC on Dec 1, 2025")
        await conn.close()
        return
    
    spot_df = pd.DataFrame(spot_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    print(f"✅ Found {len(spot_df)} candles")
    print(f"   Market Open: {spot_df['open'].iloc[0]:.2f}")
    print(f"   Day High: {spot_df['high'].max():.2f}")
    print(f"   Day Low: {spot_df['low'].min():.2f}")
    print(f"   Close: {spot_df['close'].iloc[-1]:.2f}")
    print()
    
    # 2. Find the 500 CE option
    print("🔎 FINDING 500 CE OPTION...")
    option_query = """
        SELECT instrument_id, trading_symbol, lot_size
        FROM instrument_master
        WHERE underlying = 'HINDZINC'
        AND instrument_type = 'CE'
        AND trading_symbol LIKE '%500CE%'
        ORDER BY trading_symbol
        LIMIT 5
    """
    options = await conn.fetch(option_query)
    
    if not options:
        print("❌ No 500 CE options found for HINDZINC")
        await conn.close()
        return
    
    print(f"✅ Found {len(options)} matching options:")
    for opt in options:
        print(f"   {opt['trading_symbol']} (Lot: {opt['lot_size']})")
    
    # Use the first one (likely nearest expiry)
    selected_option = options[0]
    print(f"\n📌 Selected: {selected_option['trading_symbol']}")
    print()
    
    # 3. Get option data for Dec 1
    print("📈 FETCHING OPTION PRICE DATA...")
    option_query = """
        SELECT timestamp, open, high, low, close, volume, oi
        FROM fo_candles
        WHERE instrument_id = $1
        AND timestamp::date = $2
        ORDER BY timestamp
    """
    option_data = await conn.fetch(option_query, selected_option['instrument_id'], trade_date)
    
    if not option_data:
        print("❌ No option data found")
        await conn.close()
        return
    
    option_df = pd.DataFrame(option_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
    
    print(f"✅ Found {len(option_df)} candles")
    print()
    
    # 4. Find entry point at 14:00
    print("⏰ ANALYZING ENTRY AT 14:00...")
    entry_time = datetime.combine(trade_date, dt_time(14, 0))
    
    # Find closest candle to 14:00
    option_df['time_diff'] = abs((option_df['timestamp'] - entry_time).dt.total_seconds())
    entry_idx = option_df['time_diff'].idxmin()
    entry_candle = option_df.loc[entry_idx]
    
    print(f"Entry Timestamp: {entry_candle['timestamp']}")
    print(f"Entry Premium: ₹{entry_candle['close']:.2f}")
    print(f"Entry Volume: {entry_candle['volume']}")
    print(f"Entry OI: {entry_candle['oi']}")
    print()
    
    # Get corresponding spot price
    spot_df['time_diff'] = abs((spot_df['timestamp'] - entry_time).dt.total_seconds())
    spot_entry_idx = spot_df['time_diff'].idxmin()
    entry_spot = spot_df.loc[spot_entry_idx, 'close']
    
    print(f"Spot Price at Entry: ₹{entry_spot:.2f}")
    print(f"Moneyness: {'ITM' if entry_spot > 500 else 'OTM' if entry_spot < 500 else 'ATM'}")
    print(f"Distance from Strike: {abs(entry_spot - 500):.2f} ({abs(entry_spot - 500)/500*100:.2f}%)")
    print()
    
    # 5. Analyze what happened after entry
    print("📊 POST-ENTRY ANALYSIS...")
    remaining_df = option_df[option_df.index >= entry_idx].copy()
    
    if len(remaining_df) > 1:
        max_premium = remaining_df['high'].max()
        min_premium = remaining_df['low'].min()
        exit_premium = remaining_df['close'].iloc[-1]
        
        max_gain_pct = ((max_premium - entry_candle['close']) / entry_candle['close']) * 100
        max_loss_pct = ((min_premium - entry_candle['close']) / entry_candle['close']) * 100
        actual_pnl_pct = ((exit_premium - entry_candle['close']) / entry_candle['close']) * 100
        
        print(f"Max Premium Reached: ₹{max_premium:.2f} (+{max_gain_pct:.2f}%)")
        print(f"Min Premium Reached: ₹{min_premium:.2f} ({max_loss_pct:.2f}%)")
        print(f"Close Premium: ₹{exit_premium:.2f} ({actual_pnl_pct:+.2f}%)")
        print()
        
        # Calculate P&L with lot size
        lot_size = selected_option['lot_size']
        pnl_amount = (exit_premium - entry_candle['close']) * lot_size
        
        print(f"💰 P&L CALCULATION (Lot Size: {lot_size})")
        print(f"Entry Cost: ₹{entry_candle['close'] * lot_size:,.2f}")
        print(f"Exit Value: ₹{exit_premium * lot_size:,.2f}")
        print(f"P&L: ₹{pnl_amount:+,.2f} ({actual_pnl_pct:+.2f}%)")
        print()
    
    # 6. Analyze market context
    print("🔍 MARKET CONTEXT ANALYSIS...")
    
    # Morning to entry movement
    morning_open = spot_df['open'].iloc[0]
    entry_spot_price = entry_spot
    morning_to_entry_move = ((entry_spot_price - morning_open) / morning_open) * 100
    
    print(f"Morning Open: ₹{morning_open:.2f}")
    print(f"Price at 14:00: ₹{entry_spot_price:.2f}")
    print(f"Move till Entry: {morning_to_entry_move:+.2f}%")
    print()
    
    # Volume analysis
    avg_volume = spot_df['volume'].mean()
    entry_volume = spot_df.loc[spot_entry_idx, 'volume']
    
    print(f"Avg Volume: {avg_volume:,.0f}")
    print(f"Volume at Entry: {entry_volume:,.0f}")
    print()
    
    # 7. Show minute-by-minute after entry
    print("⏱️  MINUTE-BY-MINUTE POST-ENTRY (First 30 mins)...")
    print("-" * 80)
    print(f"{'Time':<20} {'Premium':<12} {'Change %':<12} {'Volume':<12}")
    print("-" * 80)
    
    for idx, row in remaining_df.head(30).iterrows():
        change_pct = ((row['close'] - entry_candle['close']) / entry_candle['close']) * 100
        color = "🟢" if change_pct >= 0 else "🔴"
        print(f"{str(row['timestamp'])[11:19]:<20} ₹{row['close']:<10.2f} {color} {change_pct:>+8.2f}%  {row['volume']:>10,.0f}")
    
    print()
    
    await conn.close()
    
    print("=" * 80)
    print("✅ Analysis Complete!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(analyze_hindzinc_trade())
