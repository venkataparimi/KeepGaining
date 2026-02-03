"""
Profile indicator computation step by step.
"""
import asyncio
import asyncpg
import numpy as np
from datetime import datetime

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


def compute_sma(data, period):
    result = np.full(len(data), np.nan)
    if len(data) >= period:
        cumsum = np.cumsum(np.insert(data, 0, 0))
        result[period-1:] = (cumsum[period:] - cumsum[:-period]) / period
    return result


def compute_ema(data, period):
    result = np.full(len(data), np.nan)
    if len(data) >= period:
        multiplier = 2 / (period + 1)
        result[period - 1] = np.mean(data[:period])
        for i in range(period, len(data)):
            result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


async def profile():
    conn = await asyncpg.connect(DB_URL)
    
    # Get largest instrument
    inst = await conn.fetchrow('''
        SELECT instrument_id, candle_count FROM candle_data_summary
        ORDER BY candle_count DESC LIMIT 1
    ''')
    instrument_id = inst['instrument_id']
    n_candles = inst['candle_count']
    print(f"Profiling with {n_candles} candles")
    
    # 1. Fetch
    t1 = datetime.now()
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data WHERE instrument_id = $1 AND timeframe = '1m'
        ORDER BY timestamp
    ''', instrument_id)
    t2 = datetime.now()
    print(f"1. Fetch: {(t2-t1).total_seconds():.2f}s")
    
    # 2. Convert to numpy
    t1 = datetime.now()
    timestamps = [r['timestamp'] for r in rows]
    high = np.array([float(r['high']) for r in rows])
    low = np.array([float(r['low']) for r in rows])
    close = np.array([float(r['close']) for r in rows])
    volume = np.array([float(r['volume']) for r in rows])
    t2 = datetime.now()
    print(f"2. Convert to numpy: {(t2-t1).total_seconds():.2f}s")
    
    # 3. Compute SMAs
    t1 = datetime.now()
    sma_9 = compute_sma(close, 9)
    sma_20 = compute_sma(close, 20)
    sma_50 = compute_sma(close, 50)
    sma_200 = compute_sma(close, 200)
    t2 = datetime.now()
    print(f"3. Compute SMAs: {(t2-t1).total_seconds():.2f}s")
    
    # 4. Compute EMAs
    t1 = datetime.now()
    ema_9 = compute_ema(close, 9)
    ema_21 = compute_ema(close, 21)
    ema_50 = compute_ema(close, 50)
    ema_200 = compute_ema(close, 200)
    t2 = datetime.now()
    print(f"4. Compute EMAs: {(t2-t1).total_seconds():.2f}s")
    
    # 5. Build records - just 10000 to test
    def safe_float(v):
        if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
            return None
        return float(v)
    
    t1 = datetime.now()
    start_idx = 199
    # Build 10k records
    records = []
    for i in range(start_idx, min(start_idx + 10000, len(timestamps))):
        records.append((
            instrument_id, '1m', timestamps[i],
            safe_float(sma_9[i]), safe_float(sma_20[i]), safe_float(sma_50[i]), safe_float(sma_200[i]),
            safe_float(ema_9[i]), safe_float(ema_21[i]), safe_float(ema_50[i]), safe_float(ema_200[i]),
        ))
    t2 = datetime.now()
    print(f"5. Build 10k records (10 cols): {(t2-t1).total_seconds():.2f}s")
    
    # 6. Build all records with simpler approach - direct indexing without safe_float
    t1 = datetime.now()
    records2 = []
    for i in range(start_idx, start_idx + 10000):
        records2.append((
            instrument_id, '1m', timestamps[i],
            None if np.isnan(sma_9[i]) else float(sma_9[i]),
            None if np.isnan(sma_20[i]) else float(sma_20[i]),
            None if np.isnan(sma_50[i]) else float(sma_50[i]),
            None if np.isnan(sma_200[i]) else float(sma_200[i]),
            None if np.isnan(ema_9[i]) else float(ema_9[i]),
            None if np.isnan(ema_21[i]) else float(ema_21[i]),
            None if np.isnan(ema_50[i]) else float(ema_50[i]),
            None if np.isnan(ema_200[i]) else float(ema_200[i]),
        ))
    t2 = datetime.now()
    print(f"6. Build 10k records (inline isnan): {(t2-t1).total_seconds():.2f}s")
    
    # 7. Using numpy where to handle NaN then tolist
    t1 = datetime.now()
    # Replace NaN with a marker that we'll convert to None
    sma_9_clean = np.where(np.isnan(sma_9), -1e99, sma_9)[start_idx:start_idx+10000]
    sma_20_clean = np.where(np.isnan(sma_20), -1e99, sma_20)[start_idx:start_idx+10000]
    t2 = datetime.now()
    print(f"7. Numpy where for NaN replacement (2 cols, 10k): {(t2-t1).total_seconds():.4f}s")
    
    # 8. Test insert of small batch
    columns = ['instrument_id', 'timeframe', 'timestamp',
               'sma_9', 'sma_20', 'sma_50', 'sma_200',
               'ema_9', 'ema_21', 'ema_50', 'ema_200']
    
    await conn.execute('DELETE FROM indicator_data WHERE instrument_id = $1', instrument_id)
    
    t1 = datetime.now()
    await conn.copy_records_to_table('indicator_data', records=records[:1000], columns=columns)
    t2 = datetime.now()
    print(f"8. Insert 1k records (10 cols): {(t2-t1).total_seconds():.2f}s")
    
    await conn.execute('DELETE FROM indicator_data WHERE instrument_id = $1', instrument_id)
    
    t1 = datetime.now()
    await conn.copy_records_to_table('indicator_data', records=records, columns=columns)
    t2 = datetime.now()
    print(f"9. Insert 10k records (10 cols): {(t2-t1).total_seconds():.2f}s")
    
    await conn.close()

asyncio.run(profile())
