#!/usr/bin/env python3
"""Check trading symbol formats in our database."""
import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    
    # Check sample F&O trading symbols
    rows = await conn.fetch("""
        SELECT trading_symbol, instrument_type, underlying 
        FROM instrument_master 
        WHERE instrument_type IN ('CE', 'PE', 'FUTURES')
        LIMIT 10
    """)
    print('Sample F&O trading symbols in DB:')
    for r in rows:
        print(f"  {r['instrument_type']}: {r['trading_symbol']} (underlying: {r['underlying']})")
    
    # Check equity
    rows = await conn.fetch("""
        SELECT trading_symbol, instrument_type
        FROM instrument_master 
        WHERE instrument_type = 'EQUITY'
        LIMIT 5
    """)
    print('\nSample EQUITY trading symbols:')
    for r in rows:
        print(f"  {r['trading_symbol']}")
    
    # Check index
    rows = await conn.fetch("""
        SELECT trading_symbol, instrument_type
        FROM instrument_master 
        WHERE instrument_type = 'INDEX'
        LIMIT 5
    """)
    print('\nSample INDEX trading symbols:')
    for r in rows:
        print(f"  {r['trading_symbol']}")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(check())
