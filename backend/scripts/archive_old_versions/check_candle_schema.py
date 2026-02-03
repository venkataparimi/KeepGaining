#!/usr/bin/env python3
"""Check candle_data table schema and constraints."""
import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    
    # Check candle_data columns
    rows = await conn.fetch("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'candle_data'
        ORDER BY ordinal_position
    """)
    print("=== CANDLE_DATA COLUMNS ===")
    for r in rows:
        print(f"  {r['column_name']}: {r['data_type']} (nullable: {r['is_nullable']})")
    
    # Check constraints
    rows = await conn.fetch("""
        SELECT con.conname, pg_get_constraintdef(con.oid)
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'candle_data'
    """)
    print("\n=== CANDLE_DATA CONSTRAINTS ===")
    for r in rows:
        print(f"  {r['conname']}: {r['pg_get_constraintdef']}")
    
    # Check indexes
    rows = await conn.fetch("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'candle_data'
    """)
    print("\n=== CANDLE_DATA INDEXES ===")
    for r in rows:
        print(f"  {r['indexname']}: {r['indexdef']}")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(check())
