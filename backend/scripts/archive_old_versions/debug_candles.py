"""Debug why candles show as saved=0."""

import asyncio
import asyncpg
from datetime import date, datetime, timedelta

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def check():
    conn = await asyncpg.connect(DB_URL)
    
    # Get instrument_id for 360ONE FUT 30 DEC 25
    symbol = "360ONE FUT 30 DEC 25"
    inst = await conn.fetchrow('''
        SELECT instrument_id FROM instrument_master WHERE trading_symbol = $1
    ''', symbol)
    
    if not inst:
        print(f"Symbol not found: {symbol}")
        return
    
    inst_id = inst['instrument_id']
    print(f"Instrument ID: {inst_id}")
    
    # Check what candles exist
    count = await conn.fetchval('''
        SELECT COUNT(*) FROM candle_data WHERE instrument_id = $1
    ''', inst_id)
    print(f"Total candles: {count}")
    
    # Get latest candle
    latest = await conn.fetchrow('''
        SELECT timestamp, open, high, low, close, volume 
        FROM candle_data 
        WHERE instrument_id = $1 
        ORDER BY timestamp DESC 
        LIMIT 1
    ''', inst_id)
    print(f"Latest candle: {latest['timestamp'] if latest else 'None'}")
    
    # Check candles from Nov 29 to Dec 2
    start = datetime(2025, 11, 29, tzinfo=None)
    end = datetime(2025, 12, 2, tzinfo=None)
    
    recent_count = await conn.fetchval('''
        SELECT COUNT(*) FROM candle_data 
        WHERE instrument_id = $1 
        AND timestamp >= $2 
        AND timestamp <= $3
    ''', inst_id, start, end)
    print(f"Candles from Nov 29 to Dec 2: {recent_count}")
    
    # Get date range in DB
    date_range = await conn.fetchrow('''
        SELECT 
            MIN(timestamp) as earliest,
            MAX(timestamp) as latest
        FROM candle_data WHERE instrument_id = $1
    ''', inst_id)
    print(f"Date range in DB: {date_range['earliest']} to {date_range['latest']}")
    
    await conn.close()


if __name__ == "__main__":
    asyncio.run(check())
