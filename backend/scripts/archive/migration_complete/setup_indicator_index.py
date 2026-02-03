import asyncio
import asyncpg

async def setup_db():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    print("Creating unique index on indicator_data...")
    try:
        await conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_indicator_unique ON indicator_data (instrument_id, timeframe, timestamp)')
        print("✅ Index created successfully.")
    except Exception as e:
        print(f"❌ Error creating index: {e}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(setup_db())
