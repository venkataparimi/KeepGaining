import asyncio
import asyncpg
import pandas as pd
import pandas_ta as ta

async def analyze_trade():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # 1. Fetch Spot Data for LAURUSLABS on 2025-12-09
    spot_rows = await pool.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data c
        JOIN instrument_master im ON c.instrument_id = im.instrument_id
        WHERE im.trading_symbol = 'LAURUSLABS'
          AND DATE(timestamp) = '2025-12-09'
          AND timestamp::time >= '03:45:00'  -- 9:15 IST
          AND timestamp::time <= '05:30:00'  -- 11:00 IST (Analysis Window)
        ORDER BY timestamp
    ''')
    
    # 2. Fetch Option Data (PE) - We need to find which strike was traded
    # Based on previous logs, it was a PE trade. Let's find ATM PE at 9:30.
    # Spot at 9:30 (approx 04:00 UTC)
    
    if not spot_rows:
        print("No spot data found.")
        return

    df = pd.DataFrame([dict(r) for r in spot_rows])
    df['timestamp'] = pd.to_datetime(df['timestamp']) # + pd.Timedelta(hours=5, minutes=30) # Convert to IST for display
    # Keep UTC for logic, convert for display
    
    # Calculate Indicators
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
    df['ema_9'] = ta.ema(df['close'], length=9)
    df['ema_20'] = ta.ema(df['close'], length=20)
    
    print(f"\n{'='*80}")
    print(f"DEEP DIVE: LAURUSLABS (2025-12-09) - 9:15 to 11:00 AM")
    print(f"{'='*80}")
    print(f"{'Time (IST)':<12} | {'Close':<8} | {'VWAP':<8} | {'RSI':<6} | {'EMA9':<8} | {'Trend Interpretation'}")
    print("-" * 80)
    
    for i, row in df.iterrows():
        ts_ist = row['timestamp'] + pd.Timedelta(hours=5, minutes=30)
        time_str = ts_ist.strftime('%H:%M')
        
        # Simple Logic Interpretation
        vwap_signal = "ABOVE" if row['close'] > row['vwap'] else "BELOW"
        ema_signal = "BULL" if row['ema_9'] > row['ema_20'] else "BEAR"
        rsi_signal = f"{row['rsi']:.1f}"
        
        # Highlight Entry Moment (9:30)
        marker = ""
        if time_str == "09:30":
            marker = "  <-- ENTRY SIGNAL (MOMENTUM)"
        
        print(f"{time_str:<12} | {row['close']:<8.2f} | {row['vwap']:<8.2f} | {rsi_signal:<6} | {row['ema_9']:<8.2f} | {vwap_signal} VWAP, {ema_signal} EMA {marker}")

    await pool.close()

asyncio.run(analyze_trade())
