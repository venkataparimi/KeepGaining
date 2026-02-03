"""Test insert speed for indicator_data table."""
import asyncio
import asyncpg
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO
import time

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


async def test_copy_records():
    """Test copy_records_to_table speed."""
    conn = await asyncpg.connect(DB_URL)
    
    # Get a sample instrument
    inst = await conn.fetchrow('''
        SELECT instrument_id FROM instrument_master 
        WHERE instrument_type = 'EQUITY' LIMIT 1
    ''')
    inst_id = inst['instrument_id']
    
    # Generate 100k test records
    n = 100000
    base_time = datetime(2020, 1, 1)
    
    print("Generating records...")
    t1 = time.time()
    
    records = []
    for i in range(n):
        records.append((
            inst_id, '1m', base_time + timedelta(minutes=i),
            100.0, 100.0, 100.0, 100.0,  # sma
            100.0, 100.0, 100.0, 100.0,  # ema
            100.0, 100.0, 100.0, 100.0,  # vwap, vwma
            50.0,  # rsi
            0.5, 0.4, 0.1,  # macd
            50.0, 50.0, 0.0, -50.0,  # stoch, cci, williams
            2.0,  # atr
            105.0, 100.0, 95.0,  # bb
            25.0, 25.0, 25.0, 100.0, 1,  # adx, supertrend
            100.0, 101.0, 102.0, 103.0,  # pivot
            99.0, 98.0, 97.0,  # pivot support
            104.0, 103.0, 102.0, 101.0,  # cam r
            99.0, 98.0, 97.0, 96.0,  # cam s
            1000000, 500000, 2.0,  # obv, vol
            101.0, 99.0, 100.0,  # pdh, pdl, pdc
            100.5, 100.0, 99.5, 1.0,  # cpr
            100.5, 101.0, 101.5,  # fib r
            99.5, 99.0, 98.5,  # fib s
        ))
    
    t2 = time.time()
    print(f"Record generation: {t2-t1:.2f}s")
    
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
    
    # Clean up first
    await conn.execute('DELETE FROM indicator_data WHERE instrument_id = $1', inst_id)
    
    # Test copy_records_to_table
    print(f"\nTesting copy_records_to_table with {n:,} records...")
    t1 = time.time()
    await conn.copy_records_to_table('indicator_data', records=records, columns=columns)
    t2 = time.time()
    print(f"copy_records_to_table: {t2-t1:.2f}s ({n/(t2-t1):.0f} records/s)")
    
    await conn.execute('DELETE FROM indicator_data WHERE instrument_id = $1', inst_id)
    await conn.close()


async def test_copy_text():
    """Test copy_to_table with text format."""
    conn = await asyncpg.connect(DB_URL)
    
    # Get a sample instrument
    inst = await conn.fetchrow('''
        SELECT instrument_id FROM instrument_master 
        WHERE instrument_type = 'EQUITY' LIMIT 1
    ''')
    inst_id = str(inst['instrument_id'])
    
    n = 100000
    base_time = datetime(2020, 1, 1)
    
    print(f"\nGenerating {n:,} lines of CSV...")
    t1 = time.time()
    
    lines = []
    for i in range(n):
        ts = (base_time + timedelta(minutes=i)).isoformat()
        line = '\t'.join([
            inst_id, '1m', ts,
            '100.0', '100.0', '100.0', '100.0',  # sma
            '100.0', '100.0', '100.0', '100.0',  # ema
            '100.0', '100.0', '100.0', '100.0',  # vwap, vwma
            '50.0',  # rsi
            '0.5', '0.4', '0.1',  # macd
            '50.0', '50.0', '0.0', '-50.0',  # stoch, cci, williams
            '2.0',  # atr
            '105.0', '100.0', '95.0',  # bb
            '25.0', '25.0', '25.0', '100.0', '1',  # adx, supertrend
            '100.0', '101.0', '102.0', '103.0',  # pivot
            '99.0', '98.0', '97.0',  # pivot support
            '104.0', '103.0', '102.0', '101.0',  # cam r
            '99.0', '98.0', '97.0', '96.0',  # cam s
            '1000000', '500000', '2.0',  # obv, vol
            '101.0', '99.0', '100.0',  # pdh, pdl, pdc
            '100.5', '100.0', '99.5', '1.0',  # cpr
            '100.5', '101.0', '101.5',  # fib r
            '99.5', '99.0', '98.5',  # fib s
        ])
        lines.append(line)
    
    csv_data = '\n'.join(lines)
    
    t2 = time.time()
    print(f"CSV generation: {t2-t1:.2f}s")
    
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
    
    # Test copy_to_table
    print(f"\nTesting copy_to_table with text format...")
    t1 = time.time()
    await conn.copy_to_table(
        'indicator_data',
        source=BytesIO(csv_data.encode('utf-8')),
        columns=columns,
        format='text'
    )
    t2 = time.time()
    print(f"copy_to_table (text): {t2-t1:.2f}s ({n/(t2-t1):.0f} records/s)")
    
    await conn.execute('DELETE FROM indicator_data WHERE instrument_id = $1::uuid', inst_id)
    await conn.close()


if __name__ == '__main__':
    asyncio.run(test_copy_records())
    asyncio.run(test_copy_text())
