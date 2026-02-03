import asyncio
import asyncpg
import sys

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

async def main():
    conn = await asyncpg.connect(DB_URL)
    
    # Check active queries
    print("Active queries:")
    rows = await conn.fetch("""
        SELECT pid, state, query_start, now() - query_start as duration, left(query, 100) as query
        FROM pg_stat_activity 
        WHERE state = 'active' AND pid != pg_backend_pid()
        ORDER BY query_start
    """)
    
    for r in rows:
        print(f"[{r['pid']}] {r['duration']} - {r['query']}")
    
    if not rows:
        print("No active queries")
    
    await conn.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
