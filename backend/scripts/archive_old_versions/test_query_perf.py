"""Test query performance on candle_data table."""
import asyncio
import asyncpg
import time

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def test_queries():
    conn = await asyncpg.connect(DB_URL)
    
    print('=== QUERY PERFORMANCE TESTS ===')
    
    # Get a sample instrument_id
    sample = await conn.fetchrow('SELECT instrument_id FROM candle_data LIMIT 1')
    inst_id = sample['instrument_id']
    print(f'Testing with instrument_id: {inst_id}')
    print()
    
    # Test 1: Count for single instrument
    start = time.time()
    r = await conn.fetchrow('SELECT count(*) FROM candle_data WHERE instrument_id = $1', inst_id)
    t1 = time.time() - start
    print(f'1. Count for single instrument: {r["count"]:,} rows in {t1:.3f}s')
    
    # Test 2: Distinct instruments with data
    start = time.time()
    r = await conn.fetchrow('SELECT count(DISTINCT instrument_id) FROM candle_data')
    t2 = time.time() - start
    print(f'2. Count distinct instruments: {r["count"]:,} in {t2:.3f}s')
    
    # Test 3: Date range query
    start = time.time()
    r = await conn.fetchrow('''
        SELECT count(*) FROM candle_data 
        WHERE instrument_id = $1 
        AND timestamp >= NOW() - INTERVAL '30 days'
    ''', inst_id)
    t3 = time.time() - start
    print(f'3. Count last 30 days for instrument: {r["count"]:,} in {t3:.3f}s')
    
    # Test 4: Min/Max timestamp per instrument
    start = time.time()
    r = await conn.fetchrow('''
        SELECT MIN(timestamp), MAX(timestamp) FROM candle_data WHERE instrument_id = $1
    ''', inst_id)
    t4 = time.time() - start
    print(f'4. Min/Max timestamp for instrument: {t4:.3f}s')
    print(f'   Range: {r["min"]} to {r["max"]}')
    
    # Test 5: EXPLAIN ANALYZE on typical gap-check query
    print()
    print('=== EXPLAIN ANALYZE: Gap Check Query ===')
    explain = await conn.fetch('''
        EXPLAIN ANALYZE 
        SELECT instrument_id, MIN(timestamp) as first_candle, MAX(timestamp) as last_candle, COUNT(*) as candle_count
        FROM candle_data
        WHERE instrument_id = $1
        GROUP BY instrument_id
    ''', inst_id)
    for row in explain:
        print(row[0])
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(test_queries())
