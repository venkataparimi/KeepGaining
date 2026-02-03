import asyncio
import asyncpg

async def check_indexes():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    print("Checking indexes on indicator_data...")
    rows = await conn.fetch("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'indicator_data'")
    for r in rows:
        print(f"{r['indexname']}: {r['indexdef']}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_indexes())
