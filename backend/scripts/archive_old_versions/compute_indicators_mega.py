"""
MEGA-BATCH Indicator Computation - Process 1000+ instruments at once.
The bottleneck in previous approaches was per-instrument fetch/insert.
This approach:
1. Fetches candle data for many instruments in ONE query
2. Processes all in Python (fast computation)
3. Bulk inserts ALL results at once

Target: Complete 54K instruments in <30 minutes
"""
import asyncio
import asyncpg
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from datetime import datetime
from io import BytesIO
import logging
import argparse
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


# ============================================================================
# INDICATOR FUNCTIONS (copied from compute_indicators_final.py)
# ============================================================================

def compute_sma(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(data), np.nan)
    if len(data) >= period:
        cumsum = np.cumsum(np.insert(data, 0, 0))
        result[period-1:] = (cumsum[period:] - cumsum[:-period]) / period
    return result


def compute_ema(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(data), np.nan)
    if len(data) < period:
        return result
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


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    result = np.full(n, np.nan)
    if n < 2:
        return result
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    tr[1:] = np.maximum.reduce([high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])])
    if n >= period:
        result[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result


def compute_vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, timestamps) -> np.ndarray:
    n = len(close)
    result = np.full(n, np.nan)
    typical_price = (high + low + close) / 3
    dates = np.array([ts.date() if hasattr(ts, 'date') else np.datetime64(ts, 'D') for ts in timestamps])
    day_starts = np.where(np.concatenate([[True], dates[1:] != dates[:-1]]))[0]
    for i, start in enumerate(day_starts):
        end = day_starts[i + 1] if i + 1 < len(day_starts) else n
        day_tp = typical_price[start:end]
        day_vol = volume[start:end]
        cumulative_tpv = np.cumsum(day_tp * day_vol)
        cumulative_vol = np.cumsum(day_vol)
        with np.errstate(divide='ignore', invalid='ignore'):
            result[start:end] = np.where(cumulative_vol > 0, cumulative_tpv / cumulative_vol, np.nan)
    return result


def compute_vwma(close: np.ndarray, volume: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    result = np.full(n, np.nan)
    if n < period:
        return result
    close_windows = sliding_window_view(close, period)
    vol_windows = sliding_window_view(volume, period)
    vol_sums = vol_windows.sum(axis=1)
    with np.errstate(divide='ignore', invalid='ignore'):
        weighted_sums = (close_windows * vol_windows).sum(axis=1)
        result[period-1:] = np.where(vol_sums > 0, weighted_sums / vol_sums, np.nan)
    return result


def compute_bollinger(close: np.ndarray, period: int = 20, num_std: float = 2) -> tuple:
    n = len(close)
    sma = compute_sma(close, period)
    std = np.full(n, np.nan)
    if n >= period:
        windows = sliding_window_view(close, period)
        std[period-1:] = np.std(windows, axis=1, ddof=0)
    return sma + (std * num_std), sma, sma - (std * num_std)


def compute_stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray, k_period: int = 14, d_period: int = 3) -> tuple:
    n = len(close)
    stoch_k = np.full(n, np.nan)
    if n >= k_period:
        windows_high = sliding_window_view(high, k_period)
        windows_low = sliding_window_view(low, k_period)
        high_max = np.max(windows_high, axis=1)
        low_min = np.min(windows_low, axis=1)
        denom = high_max - low_min
        with np.errstate(divide='ignore', invalid='ignore'):
            stoch_k[k_period-1:] = np.where(denom != 0, 100 * (close[k_period-1:] - low_min) / denom, np.nan)
    return stoch_k, compute_sma(stoch_k, d_period)


def compute_cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 20) -> np.ndarray:
    n = len(close)
    typical_price = (high + low + close) / 3
    sma = compute_sma(typical_price, period)
    mean_dev = np.full(n, np.nan)
    if n >= period:
        windows = sliding_window_view(typical_price, period)
        sma_expanded = sma[period-1:].reshape(-1, 1)
        mean_dev[period-1:] = np.mean(np.abs(windows - sma_expanded), axis=1)
    cci = np.full(n, np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        valid = mean_dev > 0
        cci[valid] = (typical_price[valid] - sma[valid]) / (0.015 * mean_dev[valid])
    return cci


def compute_williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    williams_r = np.full(n, np.nan)
    if n >= period:
        windows_high = sliding_window_view(high, period)
        windows_low = sliding_window_view(low, period)
        high_max = np.max(windows_high, axis=1)
        low_min = np.min(windows_low, axis=1)
        denom = high_max - low_min
        with np.errstate(divide='ignore', invalid='ignore'):
            williams_r[period-1:] = np.where(denom != 0, -100 * (high_max - close[period-1:]) / denom, np.nan)
    return williams_r


def compute_supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 10, multiplier: float = 3.0) -> tuple:
    atr = compute_atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    n = len(close)
    supertrend = np.full(n, np.nan)
    direction = np.zeros(n, dtype=np.int16)
    if n >= period:
        supertrend[period - 1] = upper_band[period - 1]
        direction[period - 1] = -1
        for i in range(period, n):
            if close[i - 1] > supertrend[i - 1]:
                supertrend[i] = max(lower_band[i], supertrend[i - 1] if direction[i - 1] == 1 else lower_band[i])
                direction[i] = 1
            else:
                supertrend[i] = min(upper_band[i], supertrend[i - 1] if direction[i - 1] == -1 else upper_band[i])
                direction[i] = -1
    return supertrend, direction


def compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> tuple:
    n = len(close)
    up_move = np.diff(high, prepend=high[0])
    down_move = np.diff(-low, prepend=-low[0])
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    tr[1:] = np.maximum.reduce([high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])])
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


def compute_obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    signs = np.sign(np.diff(close, prepend=close[0]))
    signs[0] = 1
    return np.cumsum(signs * volume).astype(np.int64)


def arr_to_csv(arr: np.ndarray, start_idx: int) -> list:
    sliced = arr[start_idx:]
    nan_mask = np.isnan(sliced)
    str_arr = sliced.astype(str)
    str_arr[nan_mask] = '\\N'
    return str_arr.tolist()


def arr_to_csv_int(arr: np.ndarray, start_idx: int) -> list:
    sliced = arr[start_idx:]
    if np.issubdtype(sliced.dtype, np.floating):
        nan_mask = np.isnan(sliced)
        int_arr = np.where(nan_mask, 0, sliced).astype(np.int64).astype(str)
        int_arr = np.where(nan_mask, '\\N', int_arr)
        return int_arr.tolist()
    return sliced.astype(str).tolist()


def compute_all_indicators_for_instrument(instrument_id: str, data: list, timeframe: str = '1m') -> str:
    """Compute all indicators for one instrument and return CSV data."""
    n = len(data)
    if n < 200:
        return ''
    
    timestamps = [r['timestamp'] for r in data]
    high = np.array([float(r['high']) for r in data])
    low = np.array([float(r['low']) for r in data])
    close = np.array([float(r['close']) for r in data])
    volume = np.array([float(r['volume']) for r in data])
    
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
    bb_upper, bb_middle, bb_lower = compute_bollinger(close, 20, 2)
    adx, plus_di, minus_di = compute_adx(high, low, close, 14)
    supertrend, supertrend_dir = compute_supertrend(high, low, close, 10, 3)
    obv = compute_obv(close, volume)
    volume_sma_20 = compute_sma(volume, 20)
    volume_ratio = np.where(volume_sma_20 > 0, volume / volume_sma_20, np.nan)
    
    # Pivots
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
    
    # Build CSV rows starting from index 199
    start_idx = 199
    n_records = n - start_idx
    inst_id_str = str(instrument_id)
    
    ts_strs = [str(ts) for ts in timestamps[start_idx:]]
    
    # Build CSV lines
    lines = []
    for i in range(n_records):
        idx = start_idx + i
        line = '\t'.join([
            inst_id_str, timeframe, ts_strs[i],
            f'{sma_9[idx]:.4f}' if not np.isnan(sma_9[idx]) else '\\N',
            f'{sma_20[idx]:.4f}' if not np.isnan(sma_20[idx]) else '\\N',
            f'{sma_50[idx]:.4f}' if not np.isnan(sma_50[idx]) else '\\N',
            f'{sma_200[idx]:.4f}' if not np.isnan(sma_200[idx]) else '\\N',
            f'{ema_9[idx]:.4f}' if not np.isnan(ema_9[idx]) else '\\N',
            f'{ema_21[idx]:.4f}' if not np.isnan(ema_21[idx]) else '\\N',
            f'{ema_50[idx]:.4f}' if not np.isnan(ema_50[idx]) else '\\N',
            f'{ema_200[idx]:.4f}' if not np.isnan(ema_200[idx]) else '\\N',
            f'{vwap[idx]:.4f}' if not np.isnan(vwap[idx]) else '\\N',
            f'{vwma_20[idx]:.4f}' if not np.isnan(vwma_20[idx]) else '\\N',
            f'{vwma_22[idx]:.4f}' if not np.isnan(vwma_22[idx]) else '\\N',
            f'{vwma_31[idx]:.4f}' if not np.isnan(vwma_31[idx]) else '\\N',
            f'{rsi_14[idx]:.4f}' if not np.isnan(rsi_14[idx]) else '\\N',
            f'{macd[idx]:.4f}' if not np.isnan(macd[idx]) else '\\N',
            f'{macd_signal[idx]:.4f}' if not np.isnan(macd_signal[idx]) else '\\N',
            f'{macd_histogram[idx]:.4f}' if not np.isnan(macd_histogram[idx]) else '\\N',
            f'{stoch_k[idx]:.4f}' if not np.isnan(stoch_k[idx]) else '\\N',
            f'{stoch_d[idx]:.4f}' if not np.isnan(stoch_d[idx]) else '\\N',
            f'{cci[idx]:.4f}' if not np.isnan(cci[idx]) else '\\N',
            f'{williams_r[idx]:.4f}' if not np.isnan(williams_r[idx]) else '\\N',
            f'{atr_14[idx]:.4f}' if not np.isnan(atr_14[idx]) else '\\N',
            f'{bb_upper[idx]:.4f}' if not np.isnan(bb_upper[idx]) else '\\N',
            f'{bb_middle[idx]:.4f}' if not np.isnan(bb_middle[idx]) else '\\N',
            f'{bb_lower[idx]:.4f}' if not np.isnan(bb_lower[idx]) else '\\N',
            f'{adx[idx]:.4f}' if not np.isnan(adx[idx]) else '\\N',
            f'{plus_di[idx]:.4f}' if not np.isnan(plus_di[idx]) else '\\N',
            f'{minus_di[idx]:.4f}' if not np.isnan(minus_di[idx]) else '\\N',
            f'{supertrend[idx]:.4f}' if not np.isnan(supertrend[idx]) else '\\N',
            str(int(supertrend_dir[idx])),
            f'{pivot[idx]:.4f}', f'{pivot_r1[idx]:.4f}', f'{pivot_r2[idx]:.4f}', f'{pivot_r3[idx]:.4f}',
            f'{pivot_s1[idx]:.4f}', f'{pivot_s2[idx]:.4f}', f'{pivot_s3[idx]:.4f}',
            f'{cam_r4[idx]:.4f}', f'{cam_r3[idx]:.4f}', f'{cam_r2[idx]:.4f}', f'{cam_r1[idx]:.4f}',
            f'{cam_s1[idx]:.4f}', f'{cam_s2[idx]:.4f}', f'{cam_s3[idx]:.4f}', f'{cam_s4[idx]:.4f}',
            str(obv[idx]),
            str(int(volume_sma_20[idx])) if not np.isnan(volume_sma_20[idx]) else '\\N',
            f'{volume_ratio[idx]:.4f}' if not np.isnan(volume_ratio[idx]) else '\\N',
            f'{high[idx-1]:.4f}', f'{low[idx-1]:.4f}', f'{close[idx-1]:.4f}',
            f'{cpr_tc[idx]:.4f}', f'{pivot[idx]:.4f}', f'{cpr_bc[idx]:.4f}', f'{cpr_width[idx]:.4f}',
            f'{fib_r1[idx]:.4f}', f'{fib_r2[idx]:.4f}', f'{fib_r3[idx]:.4f}',
            f'{fib_s1[idx]:.4f}', f'{fib_s2[idx]:.4f}', f'{fib_s3[idx]:.4f}',
        ])
        lines.append(line)
    
    return '\n'.join(lines), n_records


async def process_mega_batch(batch_num: int, instrument_ids: list, conn) -> tuple:
    """Process a mega-batch of instruments."""
    t_start = datetime.now()
    
    # Fetch ALL candle data for all instruments in this batch - ONE QUERY
    rows = await conn.fetch('''
        SELECT instrument_id, timestamp, open, high, low, close, volume
        FROM candle_data 
        WHERE instrument_id = ANY($1::uuid[]) AND timeframe = '1m'
        ORDER BY instrument_id, timestamp
    ''', instrument_ids)
    
    t_fetch = datetime.now()
    
    # Group by instrument_id
    data_by_instrument = defaultdict(list)
    for row in rows:
        data_by_instrument[str(row['instrument_id'])].append(row)
    
    t_group = datetime.now()
    
    # Compute indicators for each instrument
    all_csv_parts = []
    total_records = 0
    instruments_processed = 0
    
    for inst_id in instrument_ids:
        inst_data = data_by_instrument.get(str(inst_id), [])
        if len(inst_data) >= 200:
            csv_data, n_records = compute_all_indicators_for_instrument(str(inst_id), inst_data)
            if csv_data:
                all_csv_parts.append(csv_data)
                total_records += n_records
                instruments_processed += 1
    
    t_compute = datetime.now()
    
    if not all_csv_parts:
        return 0, 0
    
    # Bulk insert ALL results
    csv_data = '\n'.join(all_csv_parts)
    
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
    
    await conn.copy_to_table(
        'indicator_data',
        source=BytesIO(csv_data.encode('utf-8')),
        columns=columns,
        format='text'
    )
    
    t_insert = datetime.now()
    
    fetch_time = (t_fetch - t_start).total_seconds()
    compute_time = (t_compute - t_group).total_seconds()
    insert_time = (t_insert - t_compute).total_seconds()
    
    logger.info(f"Batch {batch_num}: {instruments_processed} inst, {total_records:,} rec | fetch={fetch_time:.1f}s compute={compute_time:.1f}s insert={insert_time:.1f}s")
    
    return instruments_processed, total_records


async def main(limit: int = None, batch_size: int = 500):
    """Main entry point - process all instruments in mega-batches."""
    conn = await asyncpg.connect(DB_URL)
    
    print("=" * 80)
    print("MEGA-BATCH INDICATOR COMPUTATION")
    print("=" * 80)
    
    # Step 1: Prepare
    print("\n[1/5] Preparing database...")
    await conn.execute("SET session_replication_role = 'replica'")
    await conn.execute('DROP INDEX IF EXISTS idx_indicator_time')
    await conn.execute('DROP INDEX IF EXISTS idx_ind_instrument_time')
    await conn.execute('ALTER TABLE indicator_data DROP CONSTRAINT IF EXISTS pk_indicator_data')
    await conn.execute('ALTER TABLE indicator_data DROP CONSTRAINT IF EXISTS fk_indicator_data_instrument_id_instrument_master')
    await conn.execute('TRUNCATE indicator_data')
    print("   Done")
    
    # Step 2: Get instruments
    print("\n[2/5] Getting instruments...")
    if limit:
        instruments = await conn.fetch('''
            SELECT instrument_id FROM (
                SELECT instrument_id, COUNT(*) as cnt
                FROM candle_data WHERE timeframe = '1m'
                GROUP BY instrument_id HAVING COUNT(*) >= 200
                ORDER BY COUNT(*) DESC
            ) sub LIMIT $1
        ''', limit)
    else:
        instruments = await conn.fetch('''
            SELECT instrument_id, COUNT(*) as cnt
            FROM candle_data WHERE timeframe = '1m'
            GROUP BY instrument_id HAVING COUNT(*) >= 200
            ORDER BY COUNT(*) DESC
        ''')
    
    print(f"   Found {len(instruments)} instruments")
    
    # Step 3: Process in mega-batches
    print(f"\n[3/5] Processing in batches of {batch_size}...")
    
    total_instruments = 0
    total_records = 0
    start_time = datetime.now()
    
    inst_ids = [r['instrument_id'] for r in instruments]
    
    for i in range(0, len(inst_ids), batch_size):
        batch_num = i // batch_size + 1
        batch_ids = inst_ids[i:i+batch_size]
        
        n_inst, n_rec = await process_mega_batch(batch_num, batch_ids, conn)
        
        total_instruments += n_inst
        total_records += n_rec
        
        elapsed = (datetime.now() - start_time).total_seconds()
        rate_inst = total_instruments / elapsed if elapsed > 0 else 0
        rate_rec = total_records / elapsed if elapsed > 0 else 0
        eta = (len(inst_ids) - i - len(batch_ids)) / rate_inst / 60 if rate_inst > 0 else 0
        
        print(f"   Progress: {total_instruments}/{len(inst_ids)} | {total_records:,} rec | {rate_rec:,.0f}/sec | ETA: {eta:.1f}m")
    
    # Step 4: Rebuild indexes
    print("\n[4/5] Rebuilding indexes...")
    await conn.execute("SET session_replication_role = 'origin'")
    
    t1 = datetime.now()
    await conn.execute('CREATE INDEX IF NOT EXISTS idx_indicator_time ON indicator_data (timestamp)')
    await conn.execute('CREATE INDEX IF NOT EXISTS idx_ind_instrument_time ON indicator_data (instrument_id, timestamp)')
    print(f"   Indexes: {(datetime.now() - t1).total_seconds():.1f}s")
    
    try:
        await conn.execute('''
            ALTER TABLE indicator_data 
            ADD CONSTRAINT fk_indicator_data_instrument_id_instrument_master 
            FOREIGN KEY (instrument_id) REFERENCES instrument_master(instrument_id)
        ''')
        print("   FK constraint added")
    except Exception as e:
        print(f"   Warning: Could not add FK: {e}")
    
    # Step 5: Verify
    print("\n[5/5] Verification...")
    result = await conn.fetchrow('SELECT COUNT(*) as cnt, COUNT(DISTINCT instrument_id) as inst FROM indicator_data')
    
    total_time = (datetime.now() - start_time).total_seconds()
    
    print("\n" + "=" * 80)
    print("COMPLETE!")
    print("=" * 80)
    print(f"   Instruments: {result['inst']:,}")
    print(f"   Records: {result['cnt']:,}")
    print(f"   Time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
    print(f"   Rate: {result['cnt']/total_time:,.0f} records/second")
    print("=" * 80)
    
    await conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mega-batch indicator computation')
    parser.add_argument('--limit', type=int, help='Limit number of instruments')
    parser.add_argument('--batch', type=int, default=500, help='Batch size (instruments per batch)')
    args = parser.parse_args()
    
    asyncio.run(main(args.limit, args.batch))
