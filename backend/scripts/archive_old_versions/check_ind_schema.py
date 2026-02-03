import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    cols = await conn.fetch('''
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'indicator_data'
        ORDER BY ordinal_position
    ''')
    print("indicator_data columns:")
    for c in cols:
        print(f"  {c['column_name']:20} {c['data_type']}")
    await conn.close()

asyncio.run(main())
