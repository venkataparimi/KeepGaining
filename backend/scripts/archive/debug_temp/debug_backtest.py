"""
Debug: Check why no trades found
"""
import asyncio
import asyncpg
from datetime import datetime, timedelta

async def debug():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Check NIFTY equity data
    print("1. Checking NIFTY equity data...")
    nifty_inst = await conn.fetchrow("""
        SELECT instrument_id, trading_symbol FROM instrument_master
        WHERE trading_symbol = 'NIFTY' AND instrument_type = 'EQUITY'
    """)
    
    if nifty_inst:
        print(f"   ✅ Found: {nifty_inst['trading_symbol']}")
        
        # Check candles
        candles = await conn.fetchval("""
            SELECT COUNT(*) FROM candle_data
            WHERE instrument_id = $1
            AND DATE(timestamp) = '2025-12-01'
        """, nifty_inst['instrument_id'])
        print(f"   Candles on Dec 1: {candles}")
    else:
        print("   ❌ NIFTY equity not found")
    
    # Check NIFTY options
    print("\n2. Checking NIFTY options...")
    options = await conn.fetch("""
        SELECT trading_symbol FROM instrument_master
        WHERE underlying = 'NIFTY'
        AND instrument_type IN ('CE', 'PE')
        LIMIT 5
    """)
    
    if options:
        print(f"   ✅ Found {len(options)} options (showing 5):")
        for opt in options:
            print(f"      {opt['trading_symbol']}")
    else:
        print("   ❌ No NIFTY options found")
    
    # Check option candles
    print("\n3. Checking option candle data...")
    option_candles = await conn.fetchval("""
        SELECT COUNT(*) FROM candle_data cd
        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
        WHERE im.underlying = 'NIFTY'
        AND im.instrument_type IN ('CE', 'PE')
        AND DATE(cd.timestamp) = '2025-12-01'
    """)
    print(f"   Option candles on Dec 1: {option_candles:,}")
    
    # Check what underlyings have both equity and option data
    print("\n4. Checking which symbols have complete data...")
    complete = await conn.fetch("""
        SELECT DISTINCT im.underlying, COUNT(*) as opt_count
        FROM instrument_master im
        JOIN candle_data cd ON im.instrument_id = cd.instrument_id
        WHERE im.instrument_type IN ('CE', 'PE')
        AND DATE(cd.timestamp) = '2025-12-01'
        GROUP BY im.underlying
        ORDER BY opt_count DESC
        LIMIT 10
    """)
    
    print("   Symbols with option data on Dec 1:")
    for row in complete:
        print(f"      {row['underlying']:15} - {row['opt_count']:,} candles")
    
    await conn.close()

asyncio.run(debug())
