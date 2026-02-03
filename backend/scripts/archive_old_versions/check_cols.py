import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    
    # Check sample options from instrument_master
    print("Sample options from instrument_master:")
    rows = await conn.fetch("""
        SELECT instrument_id, trading_symbol, underlying, instrument_type
        FROM instrument_master 
        WHERE instrument_type IN ('CE', 'PE')
        LIMIT 5
    """)
    for r in rows:
        print(f"  {r['instrument_id']} | {r['trading_symbol']} | {r['underlying']} | {r['instrument_type']}")
    
    # Check expiry_calendar
    print("\nExpiry calendar (next 5):")
    rows = await conn.fetch("""
        SELECT * FROM expiry_calendar 
        WHERE expiry_date >= CURRENT_DATE
        ORDER BY expiry_date
        LIMIT 5
    """)
    for r in rows:
        print(f"  {dict(r)}")
    
    await conn.close()

asyncio.run(main())
