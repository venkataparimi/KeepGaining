"""Check actual column names for tables where indexes were skipped."""
import asyncio
import asyncpg

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def check_columns():
    conn = await asyncpg.connect(DB_URL)
    
    tables_to_check = [
        'option_master', 'future_master', 'indicator_data', 
        'trades', 'signal_log', 'option_chain_snapshot', 'option_greeks'
    ]
    
    for table in tables_to_check:
        cols = await conn.fetch('''
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = $1
            ORDER BY ordinal_position
        ''', table)
        
        print(f"\n=== {table} ===")
        for c in cols:
            print(f"  {c['column_name']}: {c['data_type']}")
    
    await conn.close()

asyncio.run(check_columns())
