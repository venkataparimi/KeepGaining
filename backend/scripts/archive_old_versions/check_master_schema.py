"""Check schema of master tables."""
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    
    print("=== Sample FUTURES trading symbols ===")
    rows = await conn.fetch("""
        SELECT trading_symbol FROM instrument_master 
        WHERE instrument_type = 'FUTURES'
        LIMIT 20
    """)
    for r in rows:
        print(f"  {r['trading_symbol']}")
    
    await conn.close()

asyncio.run(main())
