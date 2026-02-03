#!/usr/bin/env python3
import asyncio
import asyncpg

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def check_schema():
    conn = await asyncpg.connect(DB_URL)
    
    print("=== CANDLE_DATA SCHEMA ===")
    rows = await conn.fetch("""
        SELECT column_name, data_type, character_maximum_length
        FROM information_schema.columns 
        WHERE table_name = 'candle_data' 
        ORDER BY ordinal_position
    """)
    for r in rows:
        max_len = r['character_maximum_length']
        print(f"  {r['column_name']}: {r['data_type']}" + (f" ({max_len})" if max_len else ""))
    
    print("\n=== SAMPLE CANDLE DATA ===")
    rows = await conn.fetch("""
        SELECT * FROM candle_data LIMIT 3
    """)
    for r in rows:
        print(dict(r))
    
    await conn.close()

asyncio.run(check_schema())
