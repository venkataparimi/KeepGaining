import asyncio
import asyncpg

async def check_tables():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Get all tables
    tables = await conn.fetch("""
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname='public' 
        ORDER BY tablename
    """)
    
    print("All tables:")
    for t in tables:
        print(f"  - {t['tablename']}")
    
    await conn.close()

asyncio.run(check_tables())
