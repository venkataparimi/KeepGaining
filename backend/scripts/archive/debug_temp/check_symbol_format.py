"""
Check actual trading symbol format in database
"""
import asyncio
import asyncpg

async def check_symbols():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    rows = await conn.fetch("""
        SELECT trading_symbol, instrument_type, underlying
        FROM instrument_master
        WHERE instrument_type IN ('CE', 'PE')
        LIMIT 20
    """)
    
    print("Sample option symbols:")
    print("-" * 80)
    for r in rows:
        print(f"{r['trading_symbol']:40} | {r['instrument_type']:2} | {r['underlying']}")
    
    await conn.close()

asyncio.run(check_symbols())
