import asyncio
import asyncpg
import sys

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

async def main():
    print(f"Connecting to {DB_URL}...")
    try:
        conn = await asyncpg.connect(DB_URL)
        print("Connected.")
        
        # Check for locks/active queries
        print("Checking for active queries...")
        rows = await conn.fetch("""
            SELECT pid, state, query_start, query 
            FROM pg_stat_activity 
            WHERE state != 'idle' AND pid != pg_backend_pid()
        """)
        
        for r in rows:
            print(f"[{r['pid']}] {r['state']} since {r['query_start']}: {r['query'][:100]}...")
            # Kill fetching query if stuck
            if "FROM candle_data" in r['query'] and r['state'] == 'active':
                print(f"Terminating stuck query {r['pid']}...")
                await conn.execute(f"SELECT pg_terminate_backend({r['pid']})")
        
        if not rows:
            print("No other active sessions found.")

        # VACUUM
        print("Running VACUUM ANALYZE (this may take time)...")
        # VACUUM cannot run inside a transaction block, asyncpg connection autocommit is fine usually?
        # asyncpg executes in transaction by default? No.
        # But for VACUUM we need to be careful.
        # If this fails, we catch it.
        try:
             await conn.execute("VACUUM ANALYZE candle_data")
             print("VACUUM ANALYZE complete.")
        except Exception as e:
             print(f"VACUUM failed (might imply heavy load or lock): {e}")

        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
