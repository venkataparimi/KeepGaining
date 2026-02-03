"""Check fetch times for large instruments."""
import asyncio
import asyncpg
from datetime import datetime

async def check():
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    
    # Get top 5 by candle count
    insts = await conn.fetch('''
        SELECT s.instrument_id, s.candle_count, m.trading_symbol
        FROM candle_data_summary s
        JOIN instrument_master m ON s.instrument_id = m.instrument_id
        WHERE m.instrument_type = 'EQUITY'
        ORDER BY s.candle_count DESC
        LIMIT 5
    ''')
    
    for inst in insts:
        symbol = inst['trading_symbol']
        count = inst['candle_count']
        
        t1 = datetime.now()
        rows = await conn.fetch('''
            SELECT timestamp, open, high, low, close, volume
            FROM candle_data
            WHERE instrument_id = $1 AND timeframe = '1m'
            ORDER BY timestamp
        ''', inst['instrument_id'])
        t2 = datetime.now()
        
        print(f'{symbol}: {count:,} candles, fetch: {(t2-t1).total_seconds():.1f}s')
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(check())
