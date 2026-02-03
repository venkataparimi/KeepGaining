import asyncio
import asyncpg

async def check_schema():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    cols = await conn.fetch("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'instrument_master' 
        ORDER BY ordinal_position
    """)
    print("instrument_master columns:")
    for r in cols:
        print(f"  {r['column_name']:30} {r['data_type']}")
    await conn.close()

asyncio.run(check_schema())
