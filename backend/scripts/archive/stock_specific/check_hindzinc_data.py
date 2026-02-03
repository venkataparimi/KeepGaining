"""
Analyze HINDZINC 500 CE trade - check available data first
"""
import asyncio
import asyncpg

async def check_hindzinc_data():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    print("🔍 Checking available HINDZINC data...")
    print()
    
    # Check instrument master
    print("1. Checking instrument_master for HINDZINC...")
    query1 = """
        SELECT underlying, instrument_type, trading_symbol, lot_size
        FROM instrument_master
        WHERE underlying = 'HINDZINC'
        LIMIT 10
    """
    result = await conn.fetch(query1)
    if result:
        print(f"✅ Found {len(result)} HINDZINC instruments")
        for r in result[:5]:
            print(f"   {r['trading_symbol']} ({r['instrument_type']}) - Lot: {r['lot_size']}")
    else:
        print("❌ No HINDZINC instruments found")
    
    print()
    
    # Check fo_candles
    print("2. Checking fo_candles for HINDZINC options...")
    query2 = """
        SELECT COUNT(*) as count, MIN(timestamp) as min_date, MAX(timestamp) as max_date
        FROM fo_candles fc
        JOIN instrument_master im ON fc.instrument_id = im.instrument_id
        WHERE im.underlying = 'HINDZINC'
    """
    result = await conn.fetchrow(query2)
    if result and result['count'] > 0:
        print(f"✅ Found {result['count']} candles")
        print(f"   Date range: {result['min_date']} to {result['max_date']}")
    else:
        print("❌ No fo_candles data for HINDZINC")
    
    print()
    
    # Check what tables exist
    print("3. Checking available tables...")
    query3 = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        AND table_name LIKE '%candle%'
    """
    tables = await conn.fetch(query3)
    print(f"Available candle tables:")
    for t in tables:
        print(f"   - {t['table_name']}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_hindzinc_data())
