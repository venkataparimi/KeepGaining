import asyncio
import asyncpg

async def check_schema():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'indicator_data'")
    cols = sorted([r['column_name'] for r in rows])
    print(f"Columns in indicator_data ({len(cols)}):")
    print(cols)
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_schema())
