"""Debug script to check data coverage."""

import asyncio
import asyncpg
from datetime import date, timedelta

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def check():
    conn = await asyncpg.connect(DB_URL)
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    # Check how many instruments already have data up to yesterday
    rows = await conn.fetch('''
        SELECT 
            im.trading_symbol,
            im.instrument_type,
            MAX(cd.timestamp)::date as last_data
        FROM instrument_master im
        LEFT JOIN candle_data cd ON im.instrument_id = cd.instrument_id
        WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
        AND im.is_active = true
        GROUP BY im.instrument_id, im.trading_symbol, im.instrument_type
        HAVING MAX(cd.timestamp)::date >= $1
        LIMIT 20
    ''', yesterday)
    
    print(f"Instruments with data up to at least {yesterday}:")
    print(f"Found {len(rows)} in sample")
    for r in rows[:10]:
        print(f"  {r['trading_symbol']:50} | Last: {r['last_data']}")
    
    # Count total with recent data
    count = await conn.fetchval('''
        SELECT COUNT(*) FROM (
            SELECT im.instrument_id
            FROM instrument_master im
            LEFT JOIN candle_data cd ON im.instrument_id = cd.instrument_id
            WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
            AND im.is_active = true
            GROUP BY im.instrument_id
            HAVING MAX(cd.timestamp)::date >= $1
        ) sub
    ''', yesterday)
    
    print(f"\nTotal F&O instruments with data up to {yesterday}: {count}")
    
    # Check instruments without ANY data
    no_data = await conn.fetchval('''
        SELECT COUNT(*) FROM (
            SELECT im.instrument_id
            FROM instrument_master im
            LEFT JOIN candle_data cd ON im.instrument_id = cd.instrument_id
            WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
            AND im.is_active = true
            GROUP BY im.instrument_id
            HAVING MAX(cd.timestamp) IS NULL
        ) sub
    ''')
    
    print(f"F&O instruments with NO data: {no_data}")
    
    # Check a specific instrument that should have data
    symbol = "BANKNIFTY FUT 30 DEC 25"
    inst = await conn.fetchrow('''
        SELECT 
            im.instrument_id,
            im.trading_symbol,
            MAX(cd.timestamp) as last_data,
            COUNT(cd.timestamp) as candle_count
        FROM instrument_master im
        LEFT JOIN candle_data cd ON im.instrument_id = cd.instrument_id
        WHERE im.trading_symbol = $1
        GROUP BY im.instrument_id, im.trading_symbol
    ''', symbol)
    
    if inst:
        print(f"\nSample instrument: {symbol}")
        print(f"  Last data: {inst['last_data']}")
        print(f"  Candle count: {inst['candle_count']}")
    else:
        print(f"\nSymbol not found: {symbol}")
    
    # Check exchange vs segment
    inst2 = await conn.fetchrow('''
        SELECT exchange, segment FROM instrument_master WHERE trading_symbol = $1
    ''', symbol)
    print(f"  Exchange: {inst2['exchange']}")
    print(f"  Segment: {inst2['segment']}")
    
    await conn.close()


if __name__ == "__main__":
    asyncio.run(check())
