"""
Daily Indicator Refresh Script.
Updates indicators for instruments that have new candle data since last refresh.
Designed to run after market hours (post 4 PM IST).
"""
import asyncio
import asyncpg
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from datetime import datetime, timedelta
from io import BytesIO
import logging
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


# Import indicator functions from compute_indicators_final
from compute_indicators_final import (
    compute_sma, compute_ema, compute_vwap, compute_vwma,
    compute_rsi, compute_macd, compute_stochastic, compute_cci,
    compute_williams_r, compute_atr, compute_bollinger_bands,
    compute_adx, compute_supertrend, compute_obv,
    arr_to_csv_strings, arr_to_csv_int_strings
)


async def get_instruments_needing_refresh(conn) -> list:
    """Find instruments where candle_data is newer than indicator_data."""
    return await conn.fetch('''
        WITH latest_candles AS (
            SELECT instrument_id, MAX(timestamp) as latest_candle
            FROM candle_data
            WHERE timeframe = '1m'
            GROUP BY instrument_id
        ),
        latest_indicators AS (
            SELECT instrument_id, MAX(timestamp) as latest_indicator
            FROM indicator_data
            WHERE timeframe = '1m'
            GROUP BY instrument_id
        )
        SELECT c.instrument_id, c.latest_candle, i.latest_indicator,
               m.trading_symbol
        FROM latest_candles c
        JOIN instrument_master m ON c.instrument_id = m.instrument_id
        LEFT JOIN latest_indicators i ON c.instrument_id = i.instrument_id
        WHERE i.latest_indicator IS NULL 
           OR c.latest_candle > i.latest_indicator
        ORDER BY c.latest_candle DESC
    ''')


async def refresh_indicators_for_instrument(conn, instrument_id: str, timeframe: str = '1m') -> int:
    """Refresh indicators for a single instrument - only compute for new data."""
    from datetime import datetime as dt
    t_start = dt.now()
    
    # Get the latest indicator timestamp for this instrument
    last_indicator = await conn.fetchval('''
        SELECT MAX(timestamp) FROM indicator_data 
        WHERE instrument_id = $1 AND timeframe = $2
    ''', instrument_id, timeframe)
    
    # We need 200 candles of history to compute indicators properly
    # So fetch from (last_indicator - 200 candles) to ensure continuity
    if last_indicator:
        # Fetch enough history + new data
        rows = await conn.fetch('''
            SELECT timestamp, open, high, low, close, volume
            FROM candle_data 
            WHERE instrument_id = $1 AND timeframe = $2
            ORDER BY timestamp
        ''', instrument_id, timeframe)
    else:
        # No existing indicators - compute all
        rows = await conn.fetch('''
            SELECT timestamp, open, high, low, close, volume
            FROM candle_data 
            WHERE instrument_id = $1 AND timeframe = $2
            ORDER BY timestamp
        ''', instrument_id, timeframe)
    
    t_fetch = dt.now()
    
    n = len(rows)
    if n < 200:
        return 0
    
    timestamps = [r['timestamp'] for r in rows]
    high = np.array([float(r['high']) for r in rows])
    low = np.array([float(r['low']) for r in rows])
    close = np.array([float(r['close']) for r in rows])
    volume = np.array([float(r['volume']) for r in rows])
    
    t_convert = dt.now()
    
    # Compute all indicators
    sma_9 = compute_sma(close, 9)
    sma_20 = compute_sma(close, 20)
    sma_50 = compute_sma(close, 50)
    sma_200 = compute_sma(close, 200)
    ema_9 = compute_ema(close, 9)
    ema_21 = compute_ema(close, 21)
    ema_50 = compute_ema(close, 50)
    ema_200 = compute_ema(close, 200)
    vwap = compute_vwap(high, low, close, volume, timestamps)
    vwma_20 = compute_vwma(close, volume, 20)
    vwma_22 = compute_vwma(close, volume, 22)
    vwma_31 = compute_vwma(close, volume, 31)
    rsi_14 = compute_rsi(close, 14)
    macd, macd_signal, macd_histogram = compute_macd(close, 12, 26, 9)
    stoch_k, stoch_d = compute_stochastic(high, low, close, 14, 3)
    cci = compute_cci(high, low, close, 20)
    williams_r = compute_williams_r(high, low, close, 14)
    atr_14 = compute_atr(high, low, close, 14)
    bb_upper, bb_middle, bb_lower = compute_bollinger_bands(close, 20, 2)
    adx, plus_di, minus_di = compute_adx(high, low, close, 14)
    supertrend, supertrend_dir = compute_supertrend(high, low, close, 10, 3)
    obv = compute_obv(close, volume)
    volume_sma_20 = compute_sma(volume, 20)
    volume_ratio = volume / np.where(volume_sma_20 > 0, volume_sma_20, 1)
    
    # Pivot points (using previous day's values)
    range_hl = high - low
    pivot = (high + low + close) / 3
    pivot_r1 = 2 * pivot - low
    pivot_r2 = pivot + range_hl
    pivot_r3 = high + 2 * (pivot - low)
    pivot_s1 = 2 * pivot - high
    pivot_s2 = pivot - range_hl
    pivot_s3 = low - 2 * (high - pivot)
    cam_r4 = close + range_hl * 1.1 / 2
    cam_r3 = close + range_hl * 1.1 / 4
    cam_r2 = close + range_hl * 1.1 / 6
    cam_r1 = close + range_hl * 1.1 / 12
    cam_s1 = close - range_hl * 1.1 / 12
    cam_s2 = close - range_hl * 1.1 / 6
    cam_s3 = close - range_hl * 1.1 / 4
    cam_s4 = close - range_hl * 1.1 / 2
    cpr_bc = (high + low) / 2
    cpr_tc = 2 * pivot - cpr_bc
    cpr_width = np.abs(cpr_tc - cpr_bc) / pivot * 100
    fib_r1 = pivot + 0.382 * range_hl
    fib_r2 = pivot + 0.618 * range_hl
    fib_r3 = pivot + range_hl
    fib_s1 = pivot - 0.382 * range_hl
    fib_s2 = pivot - 0.618 * range_hl
    fib_s3 = pivot - range_hl
    
    t_calc = dt.now()
    
    # Determine start index - only export NEW data
    if last_indicator:
        # Find index of first timestamp after last_indicator
        start_idx = None
        for i, ts in enumerate(timestamps):
            if ts > last_indicator:
                start_idx = max(199, i)  # Need at least 199 for valid indicators
                break
        if start_idx is None:
            return 0  # No new data
    else:
        start_idx = 199
    
    n_records = n - start_idx
    if n_records <= 0:
        return 0
    
    inst_id_str = str(instrument_id)
    
    # Build CSV for new records only
    ts_strs = [str(ts) for ts in timestamps[start_idx:]]
    sma_9_s = arr_to_csv_strings(sma_9, start_idx)
    sma_20_s = arr_to_csv_strings(sma_20, start_idx)
    sma_50_s = arr_to_csv_strings(sma_50, start_idx)
    sma_200_s = arr_to_csv_strings(sma_200, start_idx)
    ema_9_s = arr_to_csv_strings(ema_9, start_idx)
    ema_21_s = arr_to_csv_strings(ema_21, start_idx)
    ema_50_s = arr_to_csv_strings(ema_50, start_idx)
    ema_200_s = arr_to_csv_strings(ema_200, start_idx)
    vwap_s = arr_to_csv_strings(vwap, start_idx)
    vwma_20_s = arr_to_csv_strings(vwma_20, start_idx)
    vwma_22_s = arr_to_csv_strings(vwma_22, start_idx)
    vwma_31_s = arr_to_csv_strings(vwma_31, start_idx)
    rsi_14_s = arr_to_csv_strings(rsi_14, start_idx)
    macd_s = arr_to_csv_strings(macd, start_idx)
    macd_signal_s = arr_to_csv_strings(macd_signal, start_idx)
    macd_histogram_s = arr_to_csv_strings(macd_histogram, start_idx)
    stoch_k_s = arr_to_csv_strings(stoch_k, start_idx)
    stoch_d_s = arr_to_csv_strings(stoch_d, start_idx)
    cci_s = arr_to_csv_strings(cci, start_idx)
    williams_r_s = arr_to_csv_strings(williams_r, start_idx)
    atr_14_s = arr_to_csv_strings(atr_14, start_idx)
    bb_upper_s = arr_to_csv_strings(bb_upper, start_idx)
    bb_middle_s = arr_to_csv_strings(bb_middle, start_idx)
    bb_lower_s = arr_to_csv_strings(bb_lower, start_idx)
    adx_s = arr_to_csv_strings(adx, start_idx)
    plus_di_s = arr_to_csv_strings(plus_di, start_idx)
    minus_di_s = arr_to_csv_strings(minus_di, start_idx)
    supertrend_s = arr_to_csv_strings(supertrend, start_idx)
    supertrend_dir_s = [str(int(x)) for x in supertrend_dir[start_idx:]]
    pivot_s = arr_to_csv_strings(pivot, start_idx)
    pivot_r1_s = arr_to_csv_strings(pivot_r1, start_idx)
    pivot_r2_s = arr_to_csv_strings(pivot_r2, start_idx)
    pivot_r3_s = arr_to_csv_strings(pivot_r3, start_idx)
    pivot_s1_s = arr_to_csv_strings(pivot_s1, start_idx)
    pivot_s2_s = arr_to_csv_strings(pivot_s2, start_idx)
    pivot_s3_s = arr_to_csv_strings(pivot_s3, start_idx)
    cam_r4_s = arr_to_csv_strings(cam_r4, start_idx)
    cam_r3_s = arr_to_csv_strings(cam_r3, start_idx)
    cam_r2_s = arr_to_csv_strings(cam_r2, start_idx)
    cam_r1_s = arr_to_csv_strings(cam_r1, start_idx)
    cam_s1_s = arr_to_csv_strings(cam_s1, start_idx)
    cam_s2_s = arr_to_csv_strings(cam_s2, start_idx)
    cam_s3_s = arr_to_csv_strings(cam_s3, start_idx)
    cam_s4_s = arr_to_csv_strings(cam_s4, start_idx)
    obv_s = [str(x) for x in obv[start_idx:]]
    volume_sma_20_s = arr_to_csv_int_strings(volume_sma_20, start_idx)
    volume_ratio_s = arr_to_csv_strings(volume_ratio, start_idx)
    high_s = [str(x) for x in high[start_idx:]]
    low_s = [str(x) for x in low[start_idx:]]
    close_s = [str(x) for x in close[start_idx:]]
    cpr_tc_s = arr_to_csv_strings(cpr_tc, start_idx)
    cpr_bc_s = arr_to_csv_strings(cpr_bc, start_idx)
    cpr_width_s = arr_to_csv_strings(cpr_width, start_idx)
    fib_r1_s = arr_to_csv_strings(fib_r1, start_idx)
    fib_r2_s = arr_to_csv_strings(fib_r2, start_idx)
    fib_r3_s = arr_to_csv_strings(fib_r3, start_idx)
    fib_s1_s = arr_to_csv_strings(fib_s1, start_idx)
    fib_s2_s = arr_to_csv_strings(fib_s2, start_idx)
    fib_s3_s = arr_to_csv_strings(fib_s3, start_idx)
    
    # Build CSV
    csv_data = '\n'.join(
        '\t'.join(row) for row in zip(
            [inst_id_str] * n_records, [timeframe] * n_records, ts_strs,
            sma_9_s, sma_20_s, sma_50_s, sma_200_s,
            ema_9_s, ema_21_s, ema_50_s, ema_200_s,
            vwap_s, vwma_20_s, vwma_22_s, vwma_31_s,
            rsi_14_s,
            macd_s, macd_signal_s, macd_histogram_s,
            stoch_k_s, stoch_d_s, cci_s, williams_r_s,
            atr_14_s,
            bb_upper_s, bb_middle_s, bb_lower_s,
            adx_s, plus_di_s, minus_di_s,
            supertrend_s, supertrend_dir_s,
            pivot_s, pivot_r1_s, pivot_r2_s, pivot_r3_s,
            pivot_s1_s, pivot_s2_s, pivot_s3_s,
            cam_r4_s, cam_r3_s, cam_r2_s, cam_r1_s,
            cam_s1_s, cam_s2_s, cam_s3_s, cam_s4_s,
            obv_s, volume_sma_20_s, volume_ratio_s,
            high_s, low_s, close_s,
            cpr_tc_s, pivot_s, cpr_bc_s, cpr_width_s,
            fib_r1_s, fib_r2_s, fib_r3_s,
            fib_s1_s, fib_s2_s, fib_s3_s,
        )
    )
    
    t_prep = dt.now()
    
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
    
    # Insert new records (no delete needed - these are new timestamps)
    await conn.copy_to_table(
        'indicator_data',
        source=BytesIO(csv_data.encode('utf-8')),
        columns=columns,
        format='text'
    )
    
    t_insert = dt.now()
    
    logger.info(f'  Refreshed {n_records} records (fetch={((t_fetch - t_start).total_seconds()):.1f}s, calc={((t_calc - t_convert).total_seconds()):.1f}s, prep={((t_prep - t_calc).total_seconds()):.1f}s, insert={((t_insert - t_prep).total_seconds()):.1f}s)')
    
    return n_records


async def main(parallel: int = 4):
    """Main refresh function."""
    print("=" * 60)
    print("DAILY INDICATOR REFRESH")
    print("=" * 60)
    
    pool = await asyncpg.create_pool(DB_URL, min_size=parallel, max_size=parallel + 2)
    
    async with pool.acquire() as conn:
        instruments = await get_instruments_needing_refresh(conn)
    
    print(f"\nFound {len(instruments)} instruments needing refresh")
    
    if not instruments:
        print("All indicators are up to date!")
        await pool.close()
        return
    
    total_records = 0
    processed = 0
    errors = 0
    start_time = datetime.now()
    
    # Process in parallel batches
    inst_list = list(instruments)
    
    for batch_start in range(0, len(inst_list), parallel):
        batch = inst_list[batch_start:batch_start + parallel]
        
        async def process_one(inst):
            async with pool.acquire() as conn:
                return await refresh_indicators_for_instrument(conn, inst['instrument_id'], '1m')
        
        tasks = [process_one(inst) for inst in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                errors += 1
                logger.error(f"Error refreshing {batch[i]['trading_symbol']}: {r}")
            else:
                total_records += r
                processed += 1
        
        # Progress
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"Progress: {processed}/{len(instruments)} | Records: {total_records:,} | Errors: {errors}")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'=' * 60}")
    print(f"REFRESH COMPLETE")
    print(f"{'=' * 60}")
    print(f"Instruments refreshed: {processed}")
    print(f"New indicator records: {total_records:,}")
    print(f"Errors: {errors}")
    print(f"Time elapsed: {elapsed:.1f}s")
    
    await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Refresh indicators for new candle data')
    parser.add_argument('--parallel', type=int, default=4, help='Number of parallel workers (default: 4)')
    args = parser.parse_args()
    
    asyncio.run(main(args.parallel))
