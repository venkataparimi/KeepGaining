"""
Bulk Indicator Computation for TimescaleDB.
Computes all technical indicators for all instruments with candle data.
Optimized for large datasets (351M+ candles) with parallel processing.
"""
import asyncio
import asyncpg
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from datetime import datetime
from io import BytesIO
import logging
import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('indicator_computation.log')
    ]
)
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


# ============================================================================
# ARRAY CONVERSION HELPERS (for fast CSV building)
# ============================================================================

def arr_to_csv_strings(arr: np.ndarray, start_idx: int) -> list:
    """Convert numpy array slice to list of CSV strings (\\N for NaN)."""
    sliced = arr[start_idx:]
    nan_mask = np.isnan(sliced)
    str_arr = sliced.astype(str)
    str_arr[nan_mask] = '\\N'
    return str_arr.tolist()


def arr_to_csv_int_strings(arr: np.ndarray, start_idx: int) -> list:
    """Convert numpy array slice to list of int CSV strings (\\N for NaN)."""
    sliced = arr[start_idx:]
    nan_mask = np.isnan(sliced)
    int_arr = np.where(nan_mask, 0, sliced).astype(np.int64).astype(str)
    int_arr = np.where(nan_mask, '\\N', int_arr)
    return int_arr.tolist()


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
    """VWAP that resets at the start of each trading day."""
    n = len(close)
    result = np.full(n, np.nan)
    typical_price = (high + low + close) / 3
    
    # Get dates
    if hasattr(timestamps[0], 'date'):
        dates = np.array([ts.date() for ts in timestamps])
    else:
        dates = np.array([np.datetime64(ts, 'D') for ts in timestamps])
    
    # Find day boundaries
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


# ============================================================================
# MAIN COMPUTATION
# ============================================================================

async def compute_indicators_for_instrument(conn, instrument_id: str, trading_symbol: str, timeframe: str = '1m') -> int:
    """Compute all indicators for a single instrument."""
    t_start = datetime.now()
    
    # Fetch candle data
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data 
        WHERE instrument_id = $1 AND timeframe = $2
        ORDER BY timestamp
    ''', instrument_id, timeframe)
    
    n = len(rows)
    if n < 200:
        logger.info(f"  {trading_symbol}: Skipped (only {n} candles, need >= 200)")
        return 0
    
    # Convert to numpy arrays
    timestamps = [r['timestamp'] for r in rows]
    high = np.array([float(r['high']) for r in rows])
    low = np.array([float(r['low']) for r in rows])
    close = np.array([float(r['close']) for r in rows])
    volume = np.array([float(r['volume']) for r in rows])
    
    t_convert = datetime.now()
    
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
    
    t_calc = datetime.now()
    
    # Build CSV for COPY (skip first 199 rows as they don't have all indicators)
    start_idx = 199
    n_records = n - start_idx
    inst_id_str = str(instrument_id)
    
    # Convert to CSV strings
    ts_strs = [str(ts) for ts in timestamps[start_idx:]]
    csv_data = '\n'.join(
        '\t'.join([
            inst_id_str, timeframe, ts_strs[i],
            arr_to_csv_strings(sma_9, start_idx)[i],
            arr_to_csv_strings(sma_20, start_idx)[i],
            arr_to_csv_strings(sma_50, start_idx)[i],
            arr_to_csv_strings(sma_200, start_idx)[i],
            arr_to_csv_strings(ema_9, start_idx)[i],
            arr_to_csv_strings(ema_21, start_idx)[i],
            arr_to_csv_strings(ema_50, start_idx)[i],
            arr_to_csv_strings(ema_200, start_idx)[i],
            arr_to_csv_strings(vwap, start_idx)[i],
            arr_to_csv_strings(vwma_20, start_idx)[i],
            arr_to_csv_strings(vwma_22, start_idx)[i],
            arr_to_csv_strings(vwma_31, start_idx)[i],
            arr_to_csv_strings(rsi_14, start_idx)[i],
            arr_to_csv_strings(macd, start_idx)[i],
            arr_to_csv_strings(macd_signal, start_idx)[i],
            arr_to_csv_strings(macd_histogram, start_idx)[i],
            arr_to_csv_strings(stoch_k, start_idx)[i],
            arr_to_csv_strings(stoch_d, start_idx)[i],
            arr_to_csv_strings(cci, start_idx)[i],
            arr_to_csv_strings(williams_r, start_idx)[i],
            arr_to_csv_strings(atr_14, start_idx)[i],
            arr_to_csv_strings(bb_upper, start_idx)[i],
            arr_to_csv_strings(bb_middle, start_idx)[i],
            arr_to_csv_strings(bb_lower, start_idx)[i],
            arr_to_csv_strings(adx, start_idx)[i],
            arr_to_csv_strings(plus_di, start_idx)[i],
            arr_to_csv_strings(minus_di, start_idx)[i],
            arr_to_csv_strings(supertrend, start_idx)[i],
            str(int(supertrend_dir[start_idx + i])),
            arr_to_csv_strings(pivot, start_idx)[i],
            arr_to_csv_strings(pivot_r1, start_idx)[i],
            arr_to_csv_strings(pivot_r2, start_idx)[i],
            arr_to_csv_strings(pivot_r3, start_idx)[i],
            arr_to_csv_strings(pivot_s1, start_idx)[i],
            arr_to_csv_strings(pivot_s2, start_idx)[i],
            arr_to_csv_strings(pivot_s3, start_idx)[i],
            arr_to_csv_strings(cam_r4, start_idx)[i],
            arr_to_csv_strings(cam_r3, start_idx)[i],
            arr_to_csv_strings(cam_r2, start_idx)[i],
            arr_to_csv_strings(cam_r1, start_idx)[i],
            arr_to_csv_strings(cam_s1, start_idx)[i],
            arr_to_csv_strings(cam_s2, start_idx)[i],
            arr_to_csv_strings(cam_s3, start_idx)[i],
            arr_to_csv_strings(cam_s4, start_idx)[i],
            str(obv[start_idx + i]),
            arr_to_csv_int_strings(volume_sma_20, start_idx)[i],
            arr_to_csv_strings(volume_ratio, start_idx)[i],
            str(high[start_idx + i]),
            str(low[start_idx + i]),
            str(close[start_idx + i]),
            arr_to_csv_strings(cpr_tc, start_idx)[i],
            arr_to_csv_strings(pivot, start_idx)[i],
            arr_to_csv_strings(cpr_bc, start_idx)[i],
            arr_to_csv_strings(cpr_width, start_idx)[i],
            arr_to_csv_strings(fib_r1, start_idx)[i],
            arr_to_csv_strings(fib_r2, start_idx)[i],
            arr_to_csv_strings(fib_r3, start_idx)[i],
            arr_to_csv_strings(fib_s1, start_idx)[i],
            arr_to_csv_strings(fib_s2, start_idx)[i],
            arr_to_csv_strings(fib_s3, start_idx)[i],
        ]) for i in range(n_records)
    )
    
    t_prep = datetime.now()
    
    if n_records == 0:
        return 0
    
    # Bulk insert using COPY
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
    
    elapsed = (t_insert - t_start).total_seconds()
    logger.info(f"  {trading_symbol}: {n_records:,} indicators computed in {elapsed:.1f}s")
    
    return n_records


async def process_instrument_worker(pool, inst_id: str, symbol: str) -> tuple:
    """Worker to process a single instrument using connection from pool."""
    try:
        async with pool.acquire() as conn:
            count = await compute_indicators_for_instrument(conn, inst_id, symbol, '1m')
            return (symbol, count, None)
    except Exception as e:
        logger.error(f"Error processing {symbol}: {e}")
        return (symbol, 0, str(e))


async def main(workers: int = 8, instrument_type: str = None, limit: int = None):
    """Main parallel computation with connection pooling."""
    
    # Create connection pool
    pool = await asyncpg.create_pool(DB_URL, min_size=workers, max_size=workers + 2)
    
    logger.info("=" * 80)
    logger.info(f"BULK INDICATOR COMPUTATION (Parallel - {workers} workers)")
    logger.info("=" * 80)
    
    # Get instruments to process
    async with pool.acquire() as conn:
        if instrument_type:
            if limit:
                query = '''
                    SELECT DISTINCT c.instrument_id, m.trading_symbol, COUNT(*) as candle_count
                    FROM candle_data c
                    JOIN instrument_master m ON c.instrument_id = m.instrument_id
                    WHERE c.timeframe = '1m' AND m.instrument_type = $1
                    GROUP BY c.instrument_id, m.trading_symbol
                    HAVING COUNT(*) >= 200
                    ORDER BY COUNT(*) DESC
                    LIMIT $2
                '''
                instruments = await conn.fetch(query, instrument_type, limit)
            else:
                query = '''
                    SELECT DISTINCT c.instrument_id, m.trading_symbol, COUNT(*) as candle_count
                    FROM candle_data c
                    JOIN instrument_master m ON c.instrument_id = m.instrument_id
                    WHERE c.timeframe = '1m' AND m.instrument_type = $1
                    GROUP BY c.instrument_id, m.trading_symbol
                    HAVING COUNT(*) >= 200
                    ORDER BY COUNT(*) DESC
                '''
                instruments = await conn.fetch(query, instrument_type)
        else:
            if limit:
                query = '''
                    SELECT DISTINCT c.instrument_id, m.trading_symbol, COUNT(*) as candle_count
                    FROM candle_data c
                    JOIN instrument_master m ON c.instrument_id = m.instrument_id
                    WHERE c.timeframe = '1m'
                    GROUP BY c.instrument_id, m.trading_symbol
                    HAVING COUNT(*) >= 200
                    ORDER BY COUNT(*) DESC
                    LIMIT $1
                '''
                instruments = await conn.fetch(query, limit)
            else:
                query = '''
                    SELECT DISTINCT c.instrument_id, m.trading_symbol, COUNT(*) as candle_count
                    FROM candle_data c
                    JOIN instrument_master m ON c.instrument_id = m.instrument_id
                    WHERE c.timeframe = '1m'
                    GROUP BY c.instrument_id, m.trading_symbol
                    HAVING COUNT(*) >= 200
                    ORDER BY COUNT(*) DESC
                '''
                instruments = await conn.fetch(query)
        
        logger.info(f"\nFound {len(instruments)} instruments with >= 200 candles")
        
        # Truncate existing indicator data
        logger.info("Clearing existing indicator data...")
        await conn.execute('TRUNCATE indicator_data')
    
    # Process instruments in batches
    total_records = 0
    processed = 0
    errors = 0
    start_time = datetime.now()
    
    inst_list = list(instruments)
    
    for batch_start in range(0, len(inst_list), workers):
        batch = inst_list[batch_start:batch_start + workers]
        
        # Create tasks for this batch
        tasks = [
            process_instrument_worker(pool, inst['instrument_id'], inst['trading_symbol'])
            for inst in batch
        ]
        
        # Run batch concurrently
        results = await asyncio.gather(*tasks)
        
        for symbol, count, error in results:
            if error:
                errors += 1
            else:
                total_records += count
                processed += 1
        
        # Progress update
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = processed / elapsed if elapsed > 0 else 0
        est_remain = (len(inst_list) - processed) / rate if rate > 0 else 0
        logger.info(f"\nProgress: {processed}/{len(inst_list)} ({100*processed/len(inst_list):.1f}%) | "
                   f"Records: {total_records:,} | Rate: {rate:.1f} inst/s | "
                   f"ETA: {est_remain/60:.0f}m | Errors: {errors}")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("\n" + "=" * 80)
    logger.info("COMPUTATION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Instruments processed: {processed}")
    logger.info(f"Errors: {errors}")
    logger.info(f"Total indicator records: {total_records:,}")
    logger.info(f"Time elapsed: {elapsed/60:.1f} minutes")
    logger.info(f"Average per instrument: {elapsed/processed if processed else 0:.1f}s")
    logger.info(f"Effective rate: {processed/elapsed*60:.1f} instruments/min")
    
    await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute technical indicators in bulk')
    parser.add_argument('--workers', type=int, default=8, help='Number of parallel workers (default: 8)')
    parser.add_argument('--type', choices=['EQUITY', 'INDEX', 'FUTURES', 'CE', 'PE'], 
                       help='Instrument type filter')
    parser.add_argument('--limit', type=int, help='Limit number of instruments to process')
    
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args.workers, args.type, args.limit))
    except KeyboardInterrupt:
        logger.info("\n\nInterrupted by user")
    except Exception as e:
        logger.error(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
