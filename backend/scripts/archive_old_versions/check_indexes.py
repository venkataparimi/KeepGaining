import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    
    # Check indexes
    r = await conn.fetch("""
        SELECT indexname, indexdef 
        FROM pg_indexes 
        WHERE tablename='indicator_data'
    """)
    print("Indexes on indicator_data:")
    for i in r:
        print(f"  {i['indexname']}")
        print(f"    {i['indexdef'][:100]}")
    
    # Check constraints
    r = await conn.fetch("""
        SELECT conname, contype 
        FROM pg_constraint 
        WHERE conrelid = 'indicator_data'::regclass
    """)
    print("\nConstraints:")
    for c in r:
        print(f"  {c['conname']} ({c['contype']})")
    
    # Check if it's a hypertable
    r = await conn.fetch("""
        SELECT * FROM timescaledb_information.hypertables
        WHERE hypertable_name = 'indicator_data'
    """)
    print(f"\nTimescaleDB hypertable: {len(r) > 0}")
    if r:
        print(f"  Chunks: check with timescaledb_information.chunks")
    
    await conn.close()

asyncio.run(main())
