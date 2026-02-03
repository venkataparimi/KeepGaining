"""Profile indicator computation to find bottlenecks."""
import asyncio
import asyncpg
import numpy as np
from datetime import datetime

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def test_speed():
    conn = await asyncpg.connect(DB_URL)
    
    inst = await conn.fetchrow('''
        SELECT s.instrument_id, s.candle_count, m.trading_symbol
        FROM candle_data_summary s
        JOIN instrument_master m ON s.instrument_id = m.instrument_id
        WHERE s.candle_count >= 200 AND m.instrument_type = 'EQUITY'
        ORDER BY s.candle_count 
        LIMIT 1
    ''')
    
    symbol = inst['trading_symbol']
    count = inst['candle_count']
    print(f'Testing with {symbol} ({count:,} candles)')
    
    # Time fetch
    t1 = datetime.now()
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data
        WHERE instrument_id = $1 AND timeframe = '1m'
        ORDER BY timestamp
    ''', inst['instrument_id'])
    t2 = datetime.now()
    print(f'1. DB Fetch: {(t2-t1).total_seconds():.2f}s for {len(rows):,} rows')
    
    # Time conversion
    t1 = datetime.now()
    timestamps = [r['timestamp'] for r in rows]
    close = np.array([float(r['close']) for r in rows])
    high = np.array([float(r['high']) for r in rows])
    low = np.array([float(r['low']) for r in rows])
    volume = np.array([float(r['volume']) for r in rows])
    t2 = datetime.now()
    print(f'2. Numpy Convert: {(t2-t1).total_seconds():.2f}s')
    
    # Time SMA calc
    t1 = datetime.now()
    for period in [9, 20, 50, 200]:
        result = np.full(len(close), np.nan)
        cumsum = np.cumsum(np.insert(close, 0, 0))
        result[period-1:] = (cumsum[period:] - cumsum[:-period]) / period
    t2 = datetime.now()
    print(f'3. SMA calcs: {(t2-t1).total_seconds():.4f}s')
    
    # Time record tuple creation
    t1 = datetime.now()
    records = []
    for i in range(199, len(timestamps)):
        records.append((
            inst['instrument_id'], '1m', timestamps[i],
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            int(1), float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            int(1000), int(1000), float(1.0),
            float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]), float(close[i]), float(close[i]),
            float(close[i]), float(close[i]),
        ))
    t2 = datetime.now()
    print(f'4. Tuple creation ({len(records):,} records): {(t2-t1).total_seconds():.2f}s')
    
    # Time delete
    t1 = datetime.now()
    await conn.execute('''
        DELETE FROM indicator_data 
        WHERE instrument_id = $1 AND timeframe = $2
    ''', inst['instrument_id'], '1m')
    t2 = datetime.now()
    print(f'5. Delete existing: {(t2-t1).total_seconds():.2f}s')
    
    # Time insert (batch of 5000)
    t1 = datetime.now()
    insert_sql = '''
        INSERT INTO indicator_data (
            instrument_id, timeframe, timestamp,
            sma_9, sma_20, sma_50, sma_200,
            ema_9, ema_21, ema_50, ema_200,
            vwap, vwma_20, vwma_22, vwma_31,
            rsi_14, macd, macd_signal, macd_histogram,
            stoch_k, stoch_d, cci, williams_r,
            atr_14, bb_upper, bb_middle, bb_lower,
            adx, plus_di, minus_di, supertrend, supertrend_direction,
            pivot_point, pivot_r1, pivot_r2, pivot_r3,
            pivot_s1, pivot_s2, pivot_s3,
            cam_r4, cam_r3, cam_r2, cam_r1,
            cam_s1, cam_s2, cam_s3, cam_s4,
            obv, volume_sma_20, volume_ratio,
            pdh, pdl, pdc,
            cpr_tc, cpr_pivot, cpr_bc, cpr_width,
            fib_r1, fib_r2, fib_r3, fib_s1, fib_s2, fib_s3
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
            $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28,
            $29, $30, $31, $32, $33, $34, $35, $36, $37, $38, $39, $40, $41,
            $42, $43, $44, $45, $46, $47, $48, $49, $50, $51, $52, $53, $54,
            $55, $56, $57, $58, $59, $60, $61, $62, $63
        )
    '''
    batch = records[:5000]
    await conn.executemany(insert_sql, batch)
    t2 = datetime.now()
    print(f'6. Insert 5000 rows: {(t2-t1).total_seconds():.2f}s')
    
    # Insert rest
    t1 = datetime.now()
    for i in range(5000, len(records), 5000):
        batch = records[i:i + 5000]
        await conn.executemany(insert_sql, batch)
    t2 = datetime.now()
    remaining = len(records) - 5000
    print(f'7. Insert remaining {remaining:,}: {(t2-t1).total_seconds():.2f}s')
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(test_speed())
