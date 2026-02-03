"""
Compute technical indicators - FINAL OPTIMIZED VERSION.
Uses vectorized numpy operations with sliding_window_view for maximum speed.
Uses text-based COPY for fastest possible inserts.
"""
import asyncio
import asyncpg
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from datetime import datetime
from typing import Optional
from io import BytesIO
import logging
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


# ============================================================================
# ARRAY CONVERSION HELPERS (for fast CSV building)
# ============================================================================

def arr_to_csv_strings(arr: np.ndarray, start_idx: int) -> list:
    """Convert numpy array slice to list of CSV strings (\\N for NaN)."""
    sliced = arr[start_idx:]
    # Use numpy vectorized operations
    nan_mask = np.isnan(sliced)
    # Convert all to string array
    str_arr = sliced.astype(str)
    # Replace 'nan' with \N
    str_arr[nan_mask] = '\\N'
    return str_arr.tolist()

def arr_to_csv_int_strings(arr: np.ndarray, start_idx: int) -> list:
    """Convert numpy array slice to list of int CSV strings (\\N for NaN)."""
    sliced = arr[start_idx:]
    nan_mask = np.isnan(sliced)
    # Convert valid values to int first, then to string
    int_arr = np.where(nan_mask, 0, sliced).astype(np.int64).astype(str)
    int_arr = np.where(nan_mask, '\\N', int_arr)
    return int_arr.tolist()

def arr_to_list(arr: np.ndarray, start_idx: int) -> list:
    """Convert numpy array slice to list with NaN -> None conversion."""
    sliced = arr[start_idx:]
    # Create mask for NaN values
    nan_mask = np.isnan(sliced)
    # Convert to Python floats
    result = sliced.tolist()
    # Replace NaN with None
    for i in np.where(nan_mask)[0]:
        result[i] = None
    return result

def arr_to_int_list(arr: np.ndarray, start_idx: int) -> list:
    """Convert numpy array slice to list of ints with NaN -> None conversion."""
    sliced = arr[start_idx:]
    nan_mask = np.isnan(sliced)
    # Convert to int where not NaN
    result = []
    for i, val in enumerate(sliced):
        if nan_mask[i]:
            result.append(None)
        else:
            result.append(int(val))
    return result


# ============================================================================
# OPTIMIZED INDICATOR FUNCTIONS
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
    tr[1:] = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1])
    ])
    if n >= period:
        result[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result


def compute_vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, timestamps) -> np.ndarray:
    """VWAP that resets at the start of each trading day - vectorized."""
    n = len(close)
    result = np.full(n, np.nan)
    typical_price = (high + low + close) / 3
    
    # Get dates - extract just date part
    if hasattr(timestamps[0], 'date'):
        dates = np.array([ts.date() for ts in timestamps])
    else:
        dates = np.array([np.datetime64(ts, 'D') for ts in timestamps])
    
    # Find day boundaries (where date changes)
    day_starts = np.where(np.concatenate([[True], dates[1:] != dates[:-1]]))[0]
    
    # Process each day
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


def compute_rolling_max_min(data: np.ndarray, period: int) -> tuple:
    n = len(data)
    roll_max = np.full(n, np.nan)
    roll_min = np.full(n, np.nan)
    if n >= period:
        windows = sliding_window_view(data, period)
        roll_max[period-1:] = np.max(windows, axis=1)
        roll_min[period-1:] = np.min(windows, axis=1)
    return roll_max, roll_min


def compute_stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                       k_period: int = 14, d_period: int = 3) -> tuple:
    n = len(close)
    stoch_k = np.full(n, np.nan)
    if n >= k_period:
        high_max, _ = compute_rolling_max_min(high, k_period)
        _, low_min = compute_rolling_max_min(low, k_period)
        denom = high_max - low_min
        with np.errstate(divide='ignore', invalid='ignore'):
            stoch_k = np.where(denom != 0, 100 * (close - low_min) / denom, np.nan)
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
        high_max, _ = compute_rolling_max_min(high, period)
        _, low_min = compute_rolling_max_min(low, period)
        denom = high_max - low_min
        with np.errstate(divide='ignore', invalid='ignore'):
            williams_r = np.where(denom != 0, -100 * (high_max - close) / denom, np.nan)
    return williams_r


def compute_supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                       period: int = 10, multiplier: float = 3.0) -> tuple:
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


def arr_to_list(arr: np.ndarray, start: int) -> list:
    """Fast conversion of numpy array to list with None for NaN values."""
    sliced = arr[start:]
    mask = np.isnan(sliced)
    result = sliced.astype(object)
    result[mask] = None
    return result.tolist()


def arr_to_int_list(arr: np.ndarray, start: int) -> list:
    """Fast conversion of numpy array to int list with None for NaN values."""
    sliced = arr[start:]
    if np.issubdtype(sliced.dtype, np.floating):
        mask = np.isnan(sliced)
        result = np.empty(len(sliced), dtype=object)
        result[~mask] = sliced[~mask].astype(np.int64)
        result[mask] = None
        return result.tolist()
    else:
        return sliced.astype(np.int64).tolist()


# ============================================================================
# MAIN COMPUTATION
# ============================================================================

async def compute_indicators_for_instrument(conn, instrument_id: str, timeframe: str = '1m', skip_delete: bool = False) -> int:
    """Compute all indicators for a single instrument."""
    from datetime import datetime as dt
    t_start = dt.now()
    
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data WHERE instrument_id = $1 AND timeframe = $2
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
    
    # Compute all indicators (optimized)
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
    
    # Pivots (vectorized)
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
    
    # Build CSV text directly (much faster than copy_records_to_table)
    start_idx = 199
    n_records = n - start_idx
    inst_id_str = str(instrument_id)
    
    # Pre-convert arrays to CSV strings
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
    
    # Build CSV lines using zip (faster than indexing)
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
    
    if n_records == 0:
        return 0
    
    # Delete existing (skip in batch mode where table is truncated)
    if not skip_delete:
        await conn.execute('DELETE FROM indicator_data WHERE instrument_id = $1 AND timeframe = $2',
                          instrument_id, timeframe)
    
    # Bulk insert using text COPY (2.6x faster than copy_records_to_table)
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
    
    t_insert = dt.now()
    
    logger.info(f'  Timing: fetch={((t_fetch - t_start).total_seconds()):.1f}s, calc={((t_calc - t_convert).total_seconds()):.1f}s, prep={((t_prep - t_calc).total_seconds()):.1f}s, insert={((t_insert - t_prep).total_seconds()):.1f}s')
    
    return n_records


async def main(instrument_type: str = None, limit: int = 100):
    conn = await asyncpg.connect(DB_URL)
    
    print("=" * 60)
    print("INDICATOR COMPUTATION (FINAL OPTIMIZED)")
    print("=" * 60)
    
    if instrument_type:
        instruments = await conn.fetch('''
            SELECT s.instrument_id, s.candle_count, m.trading_symbol
            FROM candle_data_summary s
            JOIN instrument_master m ON s.instrument_id = m.instrument_id
            WHERE s.candle_count >= 200 AND m.instrument_type = $1
            ORDER BY s.candle_count DESC
            LIMIT $2
        ''', instrument_type, limit)
    else:
        instruments = await conn.fetch('''
            SELECT s.instrument_id, s.candle_count, m.trading_symbol
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
            
            if (i + 1) % 5 == 0:
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
    print(f"Average per instrument: {elapsed/len(instruments):.1f}s")
    
    await conn.close()


async def main_batch(instrument_type: str = None, limit: int = 100):
    """Batch mode with dropped indexes and disabled FK checks for maximum speed."""
    conn = await asyncpg.connect(DB_URL)
    
    print("=" * 60)
    print("INDICATOR COMPUTATION (BATCH MODE - FAST)")
    print("=" * 60)
    
    # Step 1: Drop all indexes including PK, and disable FK checks
    print("\nDropping all indexes for maximum speed...")
    await conn.execute('DROP INDEX IF EXISTS idx_indicator_time')
    await conn.execute('DROP INDEX IF EXISTS idx_ind_instrument_time')
    await conn.execute('ALTER TABLE indicator_data DROP CONSTRAINT IF EXISTS pk_indicator_data')
    await conn.execute("SET session_replication_role = 'replica'")  # Skip FK triggers
    
    if instrument_type:
        instruments = await conn.fetch('''
            SELECT s.instrument_id, s.candle_count, m.trading_symbol
            FROM candle_data_summary s
            JOIN instrument_master m ON s.instrument_id = m.instrument_id
            WHERE s.candle_count >= 200 AND m.instrument_type = $1
            ORDER BY s.candle_count DESC
            LIMIT $2
        ''', instrument_type, limit)
    else:
        instruments = await conn.fetch('''
            SELECT s.instrument_id, s.candle_count, m.trading_symbol
            FROM candle_data_summary s
            JOIN instrument_master m ON s.instrument_id = m.instrument_id
            WHERE s.candle_count >= 200
            ORDER BY s.candle_count DESC
            LIMIT $1
        ''', limit)
    
    print(f"\nFound {len(instruments)} instruments with >= 200 candles")
    
    # TRUNCATE all existing indicator data for the type we're processing
    # This is faster than per-instrument DELETE
    if instrument_type:
        inst_ids = [inst['instrument_id'] for inst in instruments]
        await conn.execute('DELETE FROM indicator_data WHERE instrument_id = ANY($1::uuid[])', inst_ids)
        print(f"Cleared existing indicator data for {len(inst_ids)} instruments")
    else:
        await conn.execute('TRUNCATE indicator_data')
        print("Truncated indicator_data table")
    
    total_records = 0
    start_time = datetime.now()
    
    for i, inst in enumerate(instruments):
        try:
            count = await compute_indicators_for_instrument(conn, inst['instrument_id'], '1m', skip_delete=True)
            total_records += count
            
            if (i + 1) % 10 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                est_remain = (len(instruments) - i - 1) / rate if rate > 0 else 0
                print(f"Progress: {i + 1}/{len(instruments)} | Records: {total_records:,} | Rate: {rate:.2f}/s | ETA: {est_remain/60:.1f}m")
                
        except Exception as e:
            logger.error(f"Error processing {inst['trading_symbol']}: {e}")
            import traceback
            traceback.print_exc()
    
    # Step 2: Reset session and rebuild indexes
    await conn.execute("SET session_replication_role = 'origin'")
    
    print("\nRebuilding indexes (this may take a while for large datasets)...")
    t1 = datetime.now()
    
    # Try to add PK - may fail if duplicates exist in source data
    try:
        await conn.execute('ALTER TABLE indicator_data ADD CONSTRAINT pk_indicator_data PRIMARY KEY (instrument_id, timeframe, timestamp)')
        t2 = datetime.now()
        print(f"Primary key rebuild: {(t2-t1).total_seconds():.1f}s")
    except Exception as e:
        print(f"Warning: Could not create PK (likely duplicate timestamps in source): {e}")
        t2 = datetime.now()
    
    await conn.execute('CREATE INDEX IF NOT EXISTS idx_indicator_time ON indicator_data (timestamp)')
    await conn.execute('CREATE INDEX IF NOT EXISTS idx_ind_instrument_time ON indicator_data (instrument_id, timestamp)')
    t3 = datetime.now()
    print(f"Secondary indexes rebuild: {(t3-t2).total_seconds():.1f}s")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'=' * 60}")
    print(f"COMPLETE (BATCH MODE)")
    print(f"{'=' * 60}")
    print(f"Instruments processed: {len(instruments)}")
    print(f"Total indicator records: {total_records:,}")
    print(f"Time elapsed: {elapsed:.1f}s")
    print(f"Average per instrument: {elapsed/len(instruments) if instruments else 0:.1f}s")
    
    await conn.close()


async def process_instrument_worker(pool, instrument_id: str, worker_id: int) -> int:
    """Worker to process a single instrument using connection from pool."""
    async with pool.acquire() as conn:
        return await compute_indicators_for_instrument(conn, instrument_id, '1m', skip_delete=True)


async def main_parallel(instrument_type: str = None, limit: int = 100, workers: int = 8):
    """Parallel batch mode - process multiple instruments concurrently."""
    import asyncpg
    
    # Create connection pool
    pool = await asyncpg.create_pool(DB_URL, min_size=workers, max_size=workers + 2)
    
    print("=" * 60)
    print(f"INDICATOR COMPUTATION (PARALLEL - {workers} workers)")
    print("=" * 60)
    
    async with pool.acquire() as conn:
        # Step 1: Drop all indexes including PK, and disable FK checks
        print("\nDropping all indexes for maximum speed...")
        await conn.execute('DROP INDEX IF EXISTS idx_indicator_time')
        await conn.execute('DROP INDEX IF EXISTS idx_ind_instrument_time')
        await conn.execute('ALTER TABLE indicator_data DROP CONSTRAINT IF EXISTS pk_indicator_data')
        
        if instrument_type:
            instruments = await conn.fetch('''
                SELECT s.instrument_id, s.candle_count, m.trading_symbol
                FROM candle_data_summary s
                JOIN instrument_master m ON s.instrument_id = m.instrument_id
                WHERE s.candle_count >= 200 AND m.instrument_type = $1
                ORDER BY s.candle_count DESC
                LIMIT $2
            ''', instrument_type, limit)
        else:
            instruments = await conn.fetch('''
                SELECT s.instrument_id, s.candle_count, m.trading_symbol
                FROM candle_data_summary s
                JOIN instrument_master m ON s.instrument_id = m.instrument_id
                WHERE s.candle_count >= 200
                ORDER BY s.candle_count DESC
                LIMIT $1
            ''', limit)
        
        print(f"\nFound {len(instruments)} instruments with >= 200 candles")
        
        # TRUNCATE all existing indicator data
        if instrument_type:
            inst_ids = [inst['instrument_id'] for inst in instruments]
            await conn.execute('DELETE FROM indicator_data WHERE instrument_id = ANY($1::uuid[])', inst_ids)
            print(f"Cleared existing indicator data for {len(inst_ids)} instruments")
        else:
            await conn.execute('TRUNCATE indicator_data')
            print("Truncated indicator_data table")
    
    # Set replication role on all connections
    async with pool.acquire() as conn:
        await conn.execute("SET session_replication_role = 'replica'")
    
    total_records = 0
    start_time = datetime.now()
    processed = 0
    errors = 0
    
    # Process in batches of workers
    inst_list = list(instruments)
    
    for batch_start in range(0, len(inst_list), workers):
        batch = inst_list[batch_start:batch_start + workers]
        
        # Create tasks for this batch
        tasks = []
        for i, inst in enumerate(batch):
            tasks.append(process_instrument_worker(pool, inst['instrument_id'], i))
        
        # Run batch concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for r in results:
            if isinstance(r, Exception):
                errors += 1
                logger.error(f"Worker error: {r}")
            else:
                total_records += r
                processed += 1
        
        # Progress update
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = processed / elapsed if elapsed > 0 else 0
        est_remain = (len(inst_list) - processed) / rate if rate > 0 else 0
        print(f"Progress: {processed}/{len(inst_list)} | Records: {total_records:,} | Rate: {rate:.1f}/s | ETA: {est_remain/60:.1f}m | Errors: {errors}")
    
    # Step 2: Reset and rebuild indexes
    async with pool.acquire() as conn:
        await conn.execute("SET session_replication_role = 'origin'")
        
        print("\nRebuilding indexes (this may take a while for large datasets)...")
        t1 = datetime.now()
        
        try:
            await conn.execute('ALTER TABLE indicator_data ADD CONSTRAINT pk_indicator_data PRIMARY KEY (instrument_id, timeframe, timestamp)')
            t2 = datetime.now()
            print(f"Primary key rebuild: {(t2-t1).total_seconds():.1f}s")
        except Exception as e:
            print(f"Warning: Could not create PK: {e}")
            t2 = datetime.now()
        
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_indicator_time ON indicator_data (timestamp)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_ind_instrument_time ON indicator_data (instrument_id, timestamp)')
        t3 = datetime.now()
        print(f"Secondary indexes rebuild: {(t3-t2).total_seconds():.1f}s")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'=' * 60}")
    print(f"COMPLETE (PARALLEL)")
    print(f"{'=' * 60}")
    print(f"Instruments processed: {processed}")
    print(f"Errors: {errors}")
    print(f"Total indicator records: {total_records:,}")
    print(f"Time elapsed: {elapsed:.1f}s")
    print(f"Average per instrument: {elapsed/processed if processed else 0:.1f}s")
    print(f"Effective rate: {processed/elapsed*60:.1f} instruments/min")
    
    await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute technical indicators')
    parser.add_argument('--type', choices=['EQUITY', 'INDEX', 'FUTURES', 'CE', 'PE'], help='Instrument type')
    parser.add_argument('--limit', type=int, default=100, help='Max instruments (default: 100)')
    parser.add_argument('--batch', action='store_true', help='Batch mode: drop indexes and skip FK checks')
    parser.add_argument('--parallel', type=int, metavar='N', help='Parallel mode with N workers')
    args = parser.parse_args()
    
    if args.parallel:
        asyncio.run(main_parallel(args.type, args.limit, args.parallel))
    elif args.batch:
        asyncio.run(main_batch(args.type, args.limit))
    else:
        asyncio.run(main(args.type, args.limit))
