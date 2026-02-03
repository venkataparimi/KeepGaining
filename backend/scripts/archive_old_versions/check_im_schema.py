"""Check instrument_master schema."""
import asyncio
import asyncpg

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def main():
    conn = await asyncpg.connect(DB_URL)
    cols = await conn.fetch('''
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'instrument_master'
    ''')
    print('instrument_master columns:')
    for c in cols:
        print(f"  {c['column_name']}")
    await conn.close()

asyncio.run(main())
