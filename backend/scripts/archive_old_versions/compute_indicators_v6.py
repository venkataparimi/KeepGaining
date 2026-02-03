"""
Compute technical indicators for candle data - OPTIMIZED VERSION.
Uses asyncpg copy_records_to_table with pre-computed arrays.
"""
import asyncio
import asyncpg
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import logging
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


def compute_sma(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(data), np.nan)
    if len(data) >= period:
        cumsum = np.cumsum(np.insert(data, 0, 0))
        result[period-1:] = (cumsum[period:] - cumsum[:-period]) / period
    return result


def compute_ema(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(data), np.nan)
    if len(data) >= period:
        multiplier = 2 / (period + 1)
        result[period - 1] = np.mean(data[:period])
        for i in range(period, len(data)):
            result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    result = np.full(len(close), np.nan)
    if len(close) < period + 1:
        return result
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        result[period] = 100
    else:
        result[period] = 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, len(close)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            result[i] = 100
        else:
            result[i] = 100 - (100 / (1 + avg_gain / avg_loss))
    return result


def compute_macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    ema_fast = compute_ema(close, fast)
    ema_slow = compute_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = np.full(len(close), np.nan)
    valid_macd = ~np.isnan(macd_line)
    if np.sum(valid_macd) >= signal:
        macd_valid = macd_line[valid_macd]
        signal_calc = compute_ema(macd_valid, signal)
        start_idx = np.where(valid_macd)[0][0]
        signal_line[start_idx:start_idx + len(signal_calc)] = signal_calc
    return macd_line, signal_line, macd_line - signal_line


def compute_bollinger_bands(close: np.ndarray, period: int = 20, num_std: float = 2) -> tuple:
    sma = compute_sma(close, period)
    std = np.full(len(close), np.nan)
    for i in range(period - 1, len(close)):
        std[i] = np.std(close[i - period + 1:i + 1], ddof=0)
    return sma + (std * num_std), sma, sma - (std * num_std)


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    result = np.full(len(close), np.nan)
    if len(close) < 2:
        return result
    tr = np.zeros(len(close))
    tr[0] = high[0] - low[0]
    for i in range(1, len(close)):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    if len(tr) >= period:
        result[period - 1] = np.mean(tr[:period])
        for i in range(period, len(close)):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result


def compute_vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    typical_price = (high + low + close) / 3
    cumulative_tpv = np.cumsum(typical_price * volume)
    cumulative_vol = np.cumsum(volume)
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(cumulative_vol > 0, cumulative_tpv / cumulative_vol, np.nan)


def compute_vwma(close: np.ndarray, volume: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(close), np.nan)
    if len(close) >= period:
        for i in range(period - 1, len(close)):
            vol_sum = np.sum(volume[i - period + 1:i + 1])
            if vol_sum > 0:
                result[i] = np.sum(close[i - period + 1:i + 1] * volume[i - period + 1:i + 1]) / vol_sum
    return result


def compute_supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                       period: int = 10, multiplier: float = 3.0) -> tuple:
    atr = compute_atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    supertrend = np.full(len(close), np.nan)
    direction = np.zeros(len(close), dtype=np.int16)
    if len(close) >= period:
        supertrend[period - 1] = upper_band[period - 1]
        direction[period - 1] = -1
        for i in range(period, len(close)):
            if close[i - 1] > supertrend[i - 1]:
                supertrend[i] = max(lower_band[i], supertrend[i - 1] if direction[i - 1] == 1 else lower_band[i])
                direction[i] = 1
            else:
                supertrend[i] = min(upper_band[i], supertrend[i - 1] if direction[i - 1] == -1 else upper_band[i])
                direction[i] = -1
    return supertrend, direction


def compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> tuple:
    n = len(close)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    tr = np.zeros(n)
    for i in range(1, n):
        up_move = high[i] - high[i-1]
        down_move = low[i-1] - low[i]
        plus_dm[i] = up_move if up_move > down_move and up_move > 0 else 0
        minus_dm[i] = down_move if down_move > up_move and down_move > 0 else 0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    atr = compute_ema(tr, period)
    smooth_plus_dm = compute_ema(plus_dm, period)
    smooth_minus_dm = compute_ema(minus_dm, period)
    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)
    dx = np.full(n, np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        valid = atr > 0
        plus_di[valid] = 100 * smooth_plus_dm[valid] / atr[valid]
        minus_di[valid] = 100 * smooth_minus_dm[valid] / atr[valid]
        di_sum = plus_di + minus_di
        valid_sum = di_sum > 0
        dx[valid_sum] = 100 * np.abs(plus_di[valid_sum] - minus_di[valid_sum]) / di_sum[valid_sum]
    return compute_ema(dx, period), plus_di, minus_di


def compute_stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                       k_period: int = 14, d_period: int = 3) -> tuple:
    n = len(close)
    stoch_k = np.full(n, np.nan)
    for i in range(k_period - 1, n):
        highest = np.max(high[i - k_period + 1:i + 1])
        lowest = np.min(low[i - k_period + 1:i + 1])
        if highest != lowest:
            stoch_k[i] = 100 * (close[i] - lowest) / (highest - lowest)
    return stoch_k, compute_sma(stoch_k, d_period)


def compute_cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 20) -> np.ndarray:
    typical_price = (high + low + close) / 3
    sma = compute_sma(typical_price, period)
    mean_dev = np.full(len(close), np.nan)
    for i in range(period - 1, len(close)):
        mean_dev[i] = np.mean(np.abs(typical_price[i - period + 1:i + 1] - sma[i]))
    cci = np.full(len(close), np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        valid = mean_dev > 0
        cci[valid] = (typical_price[valid] - sma[valid]) / (0.015 * mean_dev[valid])
    return cci


def compute_williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    williams_r = np.full(n, np.nan)
    for i in range(period - 1, n):
        highest = np.max(high[i - period + 1:i + 1])
        lowest = np.min(low[i - period + 1:i + 1])
        if highest != lowest:
            williams_r[i] = -100 * (highest - close[i]) / (highest - lowest)
    return williams_r


def compute_obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    signs = np.sign(np.diff(close, prepend=close[0]))
    signs[0] = 1
    return np.cumsum(signs * volume).astype(np.int64)


def safe_float(v) -> Optional[float]:
    """Convert to float or None if NaN."""
    if v is None:
        return None
    if isinstance(v, (float, np.floating)) and np.isnan(v):
        return None
    return float(v)


def safe_int(v) -> Optional[int]:
    """Convert to int or None if NaN."""
    if v is None:
        return None
    if isinstance(v, (float, np.floating)) and np.isnan(v):
        return None
    return int(v)


async def compute_indicators_for_instrument(conn, instrument_id: str, timeframe: str = '1m') -> int:
    """Compute all indicators - optimized with sliced arrays."""
    from datetime import datetime as dt
    t_start = dt.now()
    
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data WHERE instrument_id = $1 AND timeframe = $2
        ORDER BY timestamp
    ''', instrument_id, timeframe)
    
    t_fetch = dt.now()
    if len(rows) < 200:
        return 0
    
    n = len(rows)
    timestamps = [r['timestamp'] for r in rows]
    high = np.array([float(r['high']) for r in rows])
    low = np.array([float(r['low']) for r in rows])
    close = np.array([float(r['close']) for r in rows])
    volume = np.array([float(r['volume']) for r in rows])
    
    t_convert = dt.now()
    
    # Compute all indicators (vectorized where possible)
    sma_9 = compute_sma(close, 9)
    sma_20 = compute_sma(close, 20)
    sma_50 = compute_sma(close, 50)
    sma_200 = compute_sma(close, 200)
    ema_9 = compute_ema(close, 9)
    ema_21 = compute_ema(close, 21)
    ema_50 = compute_ema(close, 50)
    ema_200 = compute_ema(close, 200)
    vwap = compute_vwap(high, low, close, volume)
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
    volume_ratio = np.where(volume_sma_20 > 0, volume / volume_sma_20, np.nan)
    
    # Pivots (all vectorized)
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
    
    # Slice from index 199 onwards (pre-slice all arrays)
    start_idx = 199
    n_records = n - start_idx
    
    # Pre-slice all arrays for faster record building
    ts_slice = timestamps[start_idx:]
    
    # Build records using zip over sliced arrays (more efficient than indexing in loop)
    inst_id = instrument_id  # Avoid repeated UUID conversion
    
    # Create iterator tuples for each column
    records = [
        (inst_id, timeframe, ts,
         safe_float(v0), safe_float(v1), safe_float(v2), safe_float(v3),
         safe_float(v4), safe_float(v5), safe_float(v6), safe_float(v7),
         safe_float(v8), safe_float(v9), safe_float(v10), safe_float(v11),
         safe_float(v12),
         safe_float(v13), safe_float(v14), safe_float(v15),
         safe_float(v16), safe_float(v17), safe_float(v18), safe_float(v19),
         safe_float(v20),
         safe_float(v21), safe_float(v22), safe_float(v23),
         safe_float(v24), safe_float(v25), safe_float(v26),
         safe_float(v27), safe_int(v28),
         safe_float(v29), safe_float(v30), safe_float(v31), safe_float(v32),
         safe_float(v33), safe_float(v34), safe_float(v35),
         safe_float(v36), safe_float(v37), safe_float(v38), safe_float(v39),
         safe_float(v40), safe_float(v41), safe_float(v42), safe_float(v43),
         safe_int(v44), safe_int(v45), safe_float(v46),
         safe_float(v47), safe_float(v48), safe_float(v49),
         safe_float(v50), safe_float(v51), safe_float(v52), safe_float(v53),
         safe_float(v54), safe_float(v55), safe_float(v56),
         safe_float(v57), safe_float(v58), safe_float(v59))
        for ts, v0, v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, v11, v12, v13, v14, v15, v16, v17, v18, v19, v20, v21, v22, v23, v24, v25, v26, v27, v28, v29, v30, v31, v32, v33, v34, v35, v36, v37, v38, v39, v40, v41, v42, v43, v44, v45, v46, v47, v48, v49, v50, v51, v52, v53, v54, v55, v56, v57, v58, v59
        in zip(
            ts_slice,
            sma_9[start_idx:], sma_20[start_idx:], sma_50[start_idx:], sma_200[start_idx:],
            ema_9[start_idx:], ema_21[start_idx:], ema_50[start_idx:], ema_200[start_idx:],
            vwap[start_idx:], vwma_20[start_idx:], vwma_22[start_idx:], vwma_31[start_idx:],
            rsi_14[start_idx:],
            macd[start_idx:], macd_signal[start_idx:], macd_histogram[start_idx:],
            stoch_k[start_idx:], stoch_d[start_idx:], cci[start_idx:], williams_r[start_idx:],
            atr_14[start_idx:],
            bb_upper[start_idx:], bb_middle[start_idx:], bb_lower[start_idx:],
            adx[start_idx:], plus_di[start_idx:], minus_di[start_idx:],
            supertrend[start_idx:], supertrend_dir[start_idx:],
            pivot[start_idx:], pivot_r1[start_idx:], pivot_r2[start_idx:], pivot_r3[start_idx:],
            pivot_s1[start_idx:], pivot_s2[start_idx:], pivot_s3[start_idx:],
            cam_r4[start_idx:], cam_r3[start_idx:], cam_r2[start_idx:], cam_r1[start_idx:],
            cam_s1[start_idx:], cam_s2[start_idx:], cam_s3[start_idx:], cam_s4[start_idx:],
            obv[start_idx:], volume_sma_20[start_idx:], volume_ratio[start_idx:],
            high[start_idx:], low[start_idx:], close[start_idx:],
            cpr_tc[start_idx:], pivot[start_idx:], cpr_bc[start_idx:], cpr_width[start_idx:],
            fib_r1[start_idx:], fib_r2[start_idx:], fib_r3[start_idx:],
            fib_s1[start_idx:], fib_s2[start_idx:], fib_s3[start_idx:],
        )
    ]
    
    t_prep = dt.now()
    
    if not records:
        return 0
    
    # Delete existing
    await conn.execute('''
        DELETE FROM indicator_data 
        WHERE instrument_id = $1 AND timeframe = $2
    ''', instrument_id, timeframe)
    
    # Bulk insert using copy_records_to_table
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
    
    await conn.copy_records_to_table('indicator_data', records=records, columns=columns)
    
    t_insert = dt.now()
    
    fetch_s = (t_fetch - t_start).total_seconds()
    convert_s = (t_convert - t_fetch).total_seconds()
    calc_s = (t_calc - t_convert).total_seconds()
    prep_s = (t_prep - t_calc).total_seconds()
    insert_s = (t_insert - t_prep).total_seconds()
    logger.info(f'  Timing: fetch={fetch_s:.1f}s, convert={convert_s:.1f}s, calc={calc_s:.1f}s, prep={prep_s:.1f}s, insert={insert_s:.1f}s')
    
    return n_records


async def main(instrument_type: str = None, limit: int = 100):
    conn = await asyncpg.connect(DB_URL)
    
    print("=" * 60)
    print("INDICATOR COMPUTATION (OPTIMIZED ZIP)")
    print("=" * 60)
    
    if instrument_type:
        instruments = await conn.fetch('''
            SELECT s.instrument_id, s.candle_count, m.instrument_type, m.trading_symbol
            FROM candle_data_summary s
            JOIN instrument_master m ON s.instrument_id = m.instrument_id
            WHERE s.candle_count >= 200 AND m.instrument_type = $1
            ORDER BY s.candle_count DESC
            LIMIT $2
        ''', instrument_type, limit)
    else:
        instruments = await conn.fetch('''
            SELECT s.instrument_id, s.candle_count, m.instrument_type, m.trading_symbol
            FROM candle_data_summary s
            JOIN instrument_master m ON s.instrument_id = m.instrument_id
            WHERE s.candle_count >= 200
            ORDER BY s.candle_count DESC
            LIMIT $1
        ''', limit)
    
    print(f"\nFound {len(instruments)} instruments with >= 200 candles")
    
    total_records = 0
    start_time = datetime.now()
    
    for i, inst in enumerate(instruments):
        try:
            count = await compute_indicators_for_instrument(conn, inst['instrument_id'], '1m')
            total_records += count
            
            if (i + 1) % 10 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"Progress: {i + 1}/{len(instruments)} | Records: {total_records:,} | Rate: {rate:.2f}/s")
                
        except Exception as e:
            logger.error(f"Error processing {inst['trading_symbol']}: {e}")
            import traceback
            traceback.print_exc()
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'=' * 60}")
    print(f"COMPLETE")
    print(f"{'=' * 60}")
    print(f"Instruments processed: {len(instruments)}")
    print(f"Total indicator records: {total_records:,}")
    print(f"Time elapsed: {elapsed:.1f}s")
    
    await conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute technical indicators')
    parser.add_argument('--type', choices=['EQUITY', 'INDEX', 'FUTURES', 'CE', 'PE'], help='Instrument type')
    parser.add_argument('--limit', type=int, default=100, help='Max instruments (default: 100)')
    args = parser.parse_args()
    asyncio.run(main(args.type, args.limit))
