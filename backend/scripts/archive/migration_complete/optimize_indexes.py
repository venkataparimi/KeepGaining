"""
Add optimized indexes for candle_data table.

The main issue is that counting distinct instruments requires scanning all 363M rows.
Solutions:
1. Create a materialized view or summary table for instrument coverage
2. Add a covering index if needed

For TimescaleDB conversion:
- Would require re-creating the table as a hypertable
- Significant downtime for 363M rows
- Consider for future but not now
"""
import asyncio
import asyncpg
import time

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def add_indexes():
    conn = await asyncpg.connect(DB_URL)
    
    print('=== OPTIMIZING candle_data TABLE ===')
    print()
    
    # Check if summary table exists
    exists = await conn.fetchval('''
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'candle_data_summary'
        )
    ''')
    
    if not exists:
        print('Creating candle_data_summary materialized view...')
        start = time.time()
        
        # Create a summary table with pre-aggregated stats per instrument
        await conn.execute('''
            CREATE MATERIALIZED VIEW IF NOT EXISTS candle_data_summary AS
            SELECT 
                instrument_id,
                timeframe,
                MIN(timestamp) as first_candle,
                MAX(timestamp) as last_candle,
                COUNT(*) as candle_count,
                MIN(timestamp::date) as first_date,
                MAX(timestamp::date) as last_date
            FROM candle_data
            GROUP BY instrument_id, timeframe
        ''')
        
        elapsed = time.time() - start
        print(f'  Created in {elapsed:.1f}s')
        
        # Add indexes on the summary table
        print('Adding indexes on summary table...')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_summary_instrument ON candle_data_summary (instrument_id)
        ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_summary_last_date ON candle_data_summary (last_date)
        ''')
        print('  Done')
    else:
        print('candle_data_summary already exists')
        print('Refreshing materialized view...')
        start = time.time()
        await conn.execute('REFRESH MATERIALIZED VIEW candle_data_summary')
        elapsed = time.time() - start
        print(f'  Refreshed in {elapsed:.1f}s')
    
    # Check the summary table
    print()
    print('=== SUMMARY TABLE STATS ===')
    count = await conn.fetchval('SELECT count(*) FROM candle_data_summary')
    print(f'Instruments with data: {count:,}')
    
    # Test query on summary table
    print()
    print('=== QUERY PERFORMANCE ON SUMMARY ===')
    start = time.time()
    r = await conn.fetchval('SELECT count(DISTINCT instrument_id) FROM candle_data_summary')
    t = time.time() - start
    print(f'Count distinct instruments: {r:,} in {t:.3f}s')
    
    # Get sample stats
    sample = await conn.fetch('''
        SELECT * FROM candle_data_summary 
        ORDER BY candle_count DESC 
        LIMIT 5
    ''')
    print()
    print('Top 5 instruments by candle count:')
    for row in sample:
        print(f'  {row["instrument_id"]}: {row["candle_count"]:,} candles ({row["first_date"]} to {row["last_date"]})')
    
    await conn.close()
    print()
    print('Done!')

if __name__ == '__main__':
    asyncio.run(add_indexes())
