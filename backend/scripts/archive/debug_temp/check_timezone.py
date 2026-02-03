"""
Check the actual timezone of timestamps in the database
"""
import asyncio
import asyncpg
from datetime import datetime

async def check_timezone():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Get a sample stock
    inst = await conn.fetchrow("""
        SELECT instrument_id, trading_symbol FROM instrument_master
        WHERE trading_symbol = 'RELIANCE' AND instrument_type = 'EQUITY'
    """)
    
    if not inst:
        print("RELIANCE not found")
        await conn.close()
        return
    
    print(f"Checking timestamps for: {inst['trading_symbol']}")
    print("=" * 80)
    
    # Get sample candles from a known trading day
    candles = await conn.fetch("""
        SELECT timestamp, open, high, low, close
        FROM candle_data
        WHERE instrument_id = $1
        AND DATE(timestamp) = '2025-12-02'
        AND timeframe = '1m'
        ORDER BY timestamp
        LIMIT 20
    """, inst['instrument_id'])
    
    if not candles:
        print("No candles found for Dec 2, 2025")
        await conn.close()
        return
    
    print(f"\nFound {len(candles)} candles for Dec 2, 2025")
    print("\nFirst 10 timestamps (as stored in database):")
    print("-" * 80)
    
    for i, candle in enumerate(candles[:10]):
        ts = candle['timestamp']
        print(f"{i+1:2}. {ts} | Open: ₹{candle['open']}")
    
    print("\n" + "=" * 80)
    print("ANALYSIS:")
    print("=" * 80)
    
    first_ts = candles[0]['timestamp']
    print(f"\nFirst candle timestamp: {first_ts}")
    print(f"Hour: {first_ts.hour}")
    print(f"Minute: {first_ts.minute}")
    
    if first_ts.hour == 9 and first_ts.minute == 15:
        print("\n✅ Timestamps appear to be in IST (market opens at 9:15 AM IST)")
        print("   No conversion needed!")
    elif first_ts.hour == 3 and first_ts.minute == 45:
        print("\n⚠️  Timestamps appear to be in UTC (9:15 AM IST = 3:45 AM UTC)")
        print("   Need to add +5:30 hours for IST conversion")
    else:
        print(f"\n❓ Unexpected time: {first_ts.hour}:{first_ts.minute:02d}")
        print("   Need to investigate further")
    
    # Check timezone info
    print(f"\nTimezone info: {first_ts.tzinfo}")
    
    # Get last candle to see market close
    last_candles = await conn.fetch("""
        SELECT timestamp, close
        FROM candle_data
        WHERE instrument_id = $1
        AND DATE(timestamp) = '2025-12-02'
        AND timeframe = '1m'
        ORDER BY timestamp DESC
        LIMIT 5
    """, inst['instrument_id'])
    
    print("\n" + "-" * 80)
    print("Last 5 timestamps (market close):")
    print("-" * 80)
    
    for i, candle in enumerate(last_candles):
        ts = candle['timestamp']
        print(f"{i+1}. {ts} | Close: ₹{candle['close']}")
    
    last_ts = last_candles[0]['timestamp']
    print(f"\nLast candle timestamp: {last_ts}")
    print(f"Hour: {last_ts.hour}")
    print(f"Minute: {last_ts.minute}")
    
    if last_ts.hour == 15 and last_ts.minute >= 29:
        print("\n✅ Market close appears to be around 3:30 PM IST (correct)")
    elif last_ts.hour == 9 and last_ts.minute >= 59:
        print("\n⚠️  Market close appears to be around 10:00 AM UTC (3:30 PM IST)")
    
    await conn.close()

asyncio.run(check_timezone())
