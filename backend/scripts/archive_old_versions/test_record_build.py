"""
Test faster record building approaches.
"""
import numpy as np
from datetime import datetime
import asyncio
import asyncpg

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


def safe_float(v):
    if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
        return None
    return float(v)


async def test_record_building():
    conn = await asyncpg.connect(DB_URL)
    
    inst = await conn.fetchrow('''
        SELECT instrument_id FROM candle_data_summary
        ORDER BY candle_count DESC LIMIT 1
    ''')
    
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data WHERE instrument_id = $1 AND timeframe = '1m'
        ORDER BY timestamp
    ''', inst['instrument_id'])
    
    n = len(rows)
    print(f"Records: {n}")
    
    timestamps = [r['timestamp'] for r in rows]
    close = np.array([float(r['close']) for r in rows])
    high = np.array([float(r['high']) for r in rows])
    low = np.array([float(r['low']) for r in rows])
    
    # Compute a few indicators
    sma_9 = np.full(n, np.nan)
    cumsum = np.cumsum(np.insert(close, 0, 0))
    sma_9[8:] = (cumsum[9:] - cumsum[:-9]) / 9
    
    sma_20 = np.full(n, np.nan)
    sma_20[19:] = (cumsum[20:] - cumsum[:-20]) / 20
    
    pivot = (high + low + close) / 3
    
    instrument_id = inst['instrument_id']
    timeframe = '1m'
    start_idx = 199
    n_records = n - start_idx
    
    print(f"Building {n_records} records with 10 columns\n")
    
    # Approach 1: Current approach with zip and safe_float
    print("Approach 1: zip + safe_float per element")
    t1 = datetime.now()
    records1 = [
        (instrument_id, timeframe, ts,
         safe_float(v0), safe_float(v1), safe_float(v2), safe_float(v3), safe_float(v4))
        for ts, v0, v1, v2, v3, v4
        in zip(
            timestamps[start_idx:],
            sma_9[start_idx:], sma_20[start_idx:],
            pivot[start_idx:], high[start_idx:], low[start_idx:]
        )
    ]
    t2 = datetime.now()
    print(f"  Time: {(t2-t1).total_seconds():.2f}s")
    
    # Approach 2: Pre-convert to Python objects using numpy operations
    print("\nApproach 2: Pre-convert arrays to object arrays")
    t1 = datetime.now()
    
    def to_py_array(arr):
        """Convert numpy array to python list with None for NaN."""
        result = np.empty(len(arr), dtype=object)
        mask = np.isnan(arr)
        result[~mask] = arr[~mask].astype(float)
        result[mask] = None
        return result.tolist()
    
    sma_9_py = to_py_array(sma_9[start_idx:])
    sma_20_py = to_py_array(sma_20[start_idx:])
    pivot_py = to_py_array(pivot[start_idx:])
    high_py = high[start_idx:].tolist()
    low_py = low[start_idx:].tolist()
    ts_py = timestamps[start_idx:]
    
    records2 = [
        (instrument_id, timeframe, ts_py[i],
         sma_9_py[i], sma_20_py[i], pivot_py[i], high_py[i], low_py[i])
        for i in range(n_records)
    ]
    t2 = datetime.now()
    print(f"  Time: {(t2-t1).total_seconds():.2f}s")
    
    # Approach 3: Use numpy structured array directly
    print("\nApproach 3: np.column_stack + zip")
    t1 = datetime.now()
    
    # Replace NaN with special marker that we'll convert
    def clean_array(arr):
        return np.where(np.isnan(arr), -1e99, arr)[start_idx:]
    
    arrays = [
        clean_array(sma_9), clean_array(sma_20),
        clean_array(pivot), high[start_idx:], low[start_idx:]
    ]
    
    def to_val(v):
        return None if v == -1e99 else float(v)
    
    records3 = [
        (instrument_id, timeframe, ts,
         to_val(v0), to_val(v1), to_val(v2), float(v3), float(v4))
        for ts, v0, v1, v2, v3, v4
        in zip(
            timestamps[start_idx:],
            *arrays
        )
    ]
    t2 = datetime.now()
    print(f"  Time: {(t2-t1).total_seconds():.2f}s")
    
    # Approach 4: Direct index access
    print("\nApproach 4: Direct indexed loop")
    t1 = datetime.now()
    records4 = []
    for i in range(start_idx, n):
        records4.append((
            instrument_id, timeframe, timestamps[i],
            None if np.isnan(sma_9[i]) else float(sma_9[i]),
            None if np.isnan(sma_20[i]) else float(sma_20[i]),
            None if np.isnan(pivot[i]) else float(pivot[i]),
            float(high[i]), float(low[i])
        ))
    t2 = datetime.now()
    print(f"  Time: {(t2-t1).total_seconds():.2f}s")
    
    # Approach 5: Pre-convert all to lists with None
    print("\nApproach 5: Pre-convert to lists, then zip")
    t1 = datetime.now()
    
    def arr_to_list(arr, start):
        """Fast conversion with None for NaN."""
        sliced = arr[start:]
        # Use np.where to create masked array
        mask = np.isnan(sliced)
        result = sliced.astype(object)
        result[mask] = None
        return result.tolist()
    
    sma9_list = arr_to_list(sma_9, start_idx)
    sma20_list = arr_to_list(sma_20, start_idx)
    pivot_list = arr_to_list(pivot, start_idx)
    high_list = high[start_idx:].tolist()
    low_list = low[start_idx:].tolist()
    ts_list = timestamps[start_idx:]
    
    records5 = list(zip(
        [instrument_id] * n_records,
        [timeframe] * n_records,
        ts_list,
        sma9_list, sma20_list, pivot_list, high_list, low_list
    ))
    t2 = datetime.now()
    print(f"  Time: {(t2-t1).total_seconds():.2f}s")
    
    await conn.close()

asyncio.run(test_record_building())
