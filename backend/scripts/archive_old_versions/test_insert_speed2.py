"""
Test batch insert speed with a smaller instrument.
"""
import asyncio
import asyncpg
import numpy as np
from datetime import datetime

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def test_batch_insert():
    conn = await asyncpg.connect(DB_URL)
    
    # Get a smaller instrument (~50k records)
    inst = await conn.fetchrow('''
        SELECT s.instrument_id, s.candle_count
        FROM candle_data_summary s
        WHERE s.candle_count BETWEEN 50000 AND 60000
        ORDER BY s.candle_count DESC
        LIMIT 1
    ''')
    
    instrument_id = inst['instrument_id']
    timeframe = '1m'
    
    # Fetch data
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data WHERE instrument_id = $1 AND timeframe = $2
        ORDER BY timestamp
    ''', instrument_id, timeframe)
    
    n = len(rows)
    print(f"Records to insert: {n - 199}")
    
    # Generate dummy records
    timestamps = [r['timestamp'] for r in rows]
    records = [
        (instrument_id, timeframe, timestamps[i],
         100.0, 100.0, 100.0, 100.0,
         100.0, 100.0, 100.0, 100.0,
         100.0, 100.0, 100.0, 100.0,
         50.0,
         1.0, 1.0, 1.0,
         50.0, 50.0, 100.0, -50.0,
         10.0,
         110.0, 100.0, 90.0,
         25.0, 25.0, 25.0,
         100.0, 1,
         100.0, 105.0, 110.0, 115.0,
         95.0, 90.0, 85.0,
         120.0, 115.0, 110.0, 105.0,
         95.0, 90.0, 85.0, 80.0,
         1000000, 50000, 1.5,
         100.0, 100.0, 100.0,
         100.0, 100.0, 100.0, 0.5,
         102.0, 104.0, 106.0,
         98.0, 96.0, 94.0)
        for i in range(199, n)
    ]
    
    columns = [
        'instrument_id', 'timeframe', 'timestamp',
        'sma_9', 'sma_20', 'sma_50', 'sma_200',
        'ema_9', 'ema_21', 'ema_50', 'ema_200',
        'vwap', 'vwma_20', 'vwma_22', 'vwma_31',
        'rsi_14', 'macd', 'macd_signal', 'macd_histogram',
        'stoch_k', 'stoch_d', 'cci', 'williams_r',
        'atr_14', 'bb_upper', 'bb_middle', 'bb_lower',
        'adx', 'plus_di', 'minus_di', 'supertrend', 'supertrend_direction',
        'pivot_point', 'pivot_r1', 'pivot_r2', 'pivot_r3',
        'pivot_s1', 'pivot_s2', 'pivot_s3',
        'cam_r4', 'cam_r3', 'cam_r2', 'cam_r1',
        'cam_s1', 'cam_s2', 'cam_s3', 'cam_s4',
        'obv', 'volume_sma_20', 'volume_ratio',
        'pdh', 'pdl', 'pdc',
        'cpr_tc', 'cpr_pivot', 'cpr_bc', 'cpr_width',
        'fib_r1', 'fib_r2', 'fib_r3', 'fib_s1', 'fib_s2', 'fib_s3'
    ]
    
    # Test 1: Normal insert (with FK and indexes)
    print("\n=== Test 1: Normal insert (with FK + indexes) ===")
    await conn.execute('DELETE FROM indicator_data WHERE instrument_id = $1 AND timeframe = $2', instrument_id, timeframe)
    t1 = datetime.now()
    await conn.copy_records_to_table('indicator_data', records=records, columns=columns)
    t2 = datetime.now()
    print(f"Time: {(t2-t1).total_seconds():.1f}s")
    
    # Test 2: With replication mode (disables FK triggers)
    print("\n=== Test 2: With session_replication_role = replica ===")
    await conn.execute('DELETE FROM indicator_data WHERE instrument_id = $1 AND timeframe = $2', instrument_id, timeframe)
    await conn.execute("SET session_replication_role = 'replica'")
    t1 = datetime.now()
    await conn.copy_records_to_table('indicator_data', records=records, columns=columns)
    t2 = datetime.now()
    await conn.execute("SET session_replication_role = 'origin'")
    print(f"Time: {(t2-t1).total_seconds():.1f}s")
    
    await conn.close()

asyncio.run(test_batch_insert())
