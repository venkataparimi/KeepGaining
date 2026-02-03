"""
Compute technical indicators for candle data.
Matches the actual indicator_data table schema with individual columns.

Indicators computed:
- SMA (9, 20, 50, 200)
- EMA (9, 21, 50, 200)
- RSI (14)
- MACD (12, 26, 9)
- Bollinger Bands (20, 2)
- ATR (14)
- VWAP
- SuperTrend (10, 3)
- ADX with +DI/-DI
- Stochastic (14, 3)
- CCI (20)
- Williams %R (14)
- OBV
- Volume SMA
- Pivot Points:
  * Classic/Standard (P, R1, R2, R3, S1, S2, S3)
  * Fibonacci (R1, R2, R3, S1, S2, S3 based on 38.2%, 61.8%, 100% levels)
  * Camarilla (R1-R4, S1-S4)
- CPR (Central Pivot Range): TC, Pivot, BC, Width%
- PDH/PDL/PDC (Previous Day High/Low/Close)
"""
import asyncio
import asyncpg
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

# Batch size for inserts
BATCH_SIZE = 5000


def safe_float(val) -> Optional[float]:
    """Convert to float, return None if NaN."""
    if val is None or np.isnan(val):
        return None
    return float(val)


def safe_int(val) -> Optional[int]:
    """Convert to int, return None if NaN."""
    if val is None or np.isnan(val):
        return None
    return int(val)


def compute_sma(data: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average using cumsum for efficiency."""
    result = np.full(len(data), np.nan)
    if len(data) >= period:
        cumsum = np.cumsum(np.insert(data, 0, 0))
        result[period-1:] = (cumsum[period:] - cumsum[:-period]) / period
    return result


def compute_ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    result = np.full(len(data), np.nan)
    if len(data) >= period:
        multiplier = 2 / (period + 1)
        result[period - 1] = np.mean(data[:period])
        for i in range(period, len(data)):
            result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index."""
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
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))
    
    for i in range(period + 1, len(close)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        
        if avg_loss == 0:
            result[i] = 100
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))
    
    return result


def compute_macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """MACD indicator."""
    ema_fast = compute_ema(close, fast)
    ema_slow = compute_ema(close, slow)
    macd_line = ema_fast - ema_slow
    
    # Signal line from MACD line (not from close)
    signal_line = np.full(len(close), np.nan)
    valid_macd = ~np.isnan(macd_line)
    if np.sum(valid_macd) >= signal:
        macd_valid = macd_line[valid_macd]
        signal_calc = compute_ema(macd_valid, signal)
        start_idx = np.where(valid_macd)[0][0]
        signal_line[start_idx:start_idx + len(signal_calc)] = signal_calc
    
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger_bands(close: np.ndarray, period: int = 20, num_std: float = 2) -> tuple:
    """Bollinger Bands."""
    sma = compute_sma(close, period)
    
    # Rolling std
    std = np.full(len(close), np.nan)
    for i in range(period - 1, len(close)):
        std[i] = np.std(close[i - period + 1:i + 1], ddof=0)
    
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return upper, sma, lower


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Average True Range."""
    result = np.full(len(close), np.nan)
    if len(close) < 2:
        return result
    
    tr = np.zeros(len(close))
    tr[0] = high[0] - low[0]
    
    for i in range(1, len(close)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )
    
    if len(tr) >= period:
        result[period - 1] = np.mean(tr[:period])
        for i in range(period, len(close)):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    
    return result


def compute_vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """Volume Weighted Average Price."""
    typical_price = (high + low + close) / 3
    cumulative_tpv = np.cumsum(typical_price * volume)
    cumulative_vol = np.cumsum(volume)
    
    with np.errstate(divide='ignore', invalid='ignore'):
        vwap = np.where(cumulative_vol > 0, cumulative_tpv / cumulative_vol, np.nan)
    return vwap


def compute_vwma(close: np.ndarray, volume: np.ndarray, period: int) -> np.ndarray:
    """Volume Weighted Moving Average."""
    result = np.full(len(close), np.nan)
    if len(close) >= period:
        for i in range(period - 1, len(close)):
            vol_sum = np.sum(volume[i - period + 1:i + 1])
            if vol_sum > 0:
                result[i] = np.sum(close[i - period + 1:i + 1] * volume[i - period + 1:i + 1]) / vol_sum
    return result


def compute_supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                       period: int = 10, multiplier: float = 3.0) -> tuple:
    """SuperTrend indicator."""
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
    """ADX with +DI and -DI."""
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
    
    # Smoothed values
    atr = compute_ema(tr, period)
    smooth_plus_dm = compute_ema(plus_dm, period)
    smooth_minus_dm = compute_ema(minus_dm, period)
    
    # DI values
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
    
    adx = compute_ema(dx, period)
    return adx, plus_di, minus_di


def compute_stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                       k_period: int = 14, d_period: int = 3) -> tuple:
    """Stochastic Oscillator."""
    n = len(close)
    stoch_k = np.full(n, np.nan)
    
    for i in range(k_period - 1, n):
        highest = np.max(high[i - k_period + 1:i + 1])
        lowest = np.min(low[i - k_period + 1:i + 1])
        if highest != lowest:
            stoch_k[i] = 100 * (close[i] - lowest) / (highest - lowest)
    
    stoch_d = compute_sma(stoch_k, d_period)
    return stoch_k, stoch_d


def compute_cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 20) -> np.ndarray:
    """Commodity Channel Index."""
    typical_price = (high + low + close) / 3
    sma = compute_sma(typical_price, period)
    
    # Mean deviation
    mean_dev = np.full(len(close), np.nan)
    for i in range(period - 1, len(close)):
        mean_dev[i] = np.mean(np.abs(typical_price[i - period + 1:i + 1] - sma[i]))
    
    cci = np.full(len(close), np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        valid = mean_dev > 0
        cci[valid] = (typical_price[valid] - sma[valid]) / (0.015 * mean_dev[valid])
    
    return cci


def compute_williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Williams %R."""
    n = len(close)
    williams_r = np.full(n, np.nan)
    
    for i in range(period - 1, n):
        highest = np.max(high[i - period + 1:i + 1])
        lowest = np.min(low[i - period + 1:i + 1])
        if highest != lowest:
            williams_r[i] = -100 * (highest - close[i]) / (highest - lowest)
    
    return williams_r


def compute_obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """On Balance Volume."""
    obv = np.zeros(len(close), dtype=np.int64)
    obv[0] = int(volume[0])
    
    for i in range(1, len(close)):
        if close[i] > close[i-1]:
            obv[i] = obv[i-1] + int(volume[i])
        elif close[i] < close[i-1]:
            obv[i] = obv[i-1] - int(volume[i])
        else:
            obv[i] = obv[i-1]
    
    return obv


def compute_pivot_points(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> dict:
    """
    Compute all pivot point types:
    - Classic/Standard Pivots
    - Fibonacci Pivots
    - Camarilla Pivots
    - CPR (Central Pivot Range)
    - PDH/PDL (Previous Day High/Low)
    """
    n = len(close)
    range_hl = high - low
    
    # Classic/Standard pivots
    pivot = (high + low + close) / 3
    r1 = 2 * pivot - low
    r2 = pivot + range_hl
    r3 = high + 2 * (pivot - low)
    s1 = 2 * pivot - high
    s2 = pivot - range_hl
    s3 = low - 2 * (high - pivot)
    
    # Fibonacci pivots (based on Fibonacci retracement levels)
    fib_r1 = pivot + 0.382 * range_hl
    fib_r2 = pivot + 0.618 * range_hl
    fib_r3 = pivot + 1.000 * range_hl
    fib_s1 = pivot - 0.382 * range_hl
    fib_s2 = pivot - 0.618 * range_hl
    fib_s3 = pivot - 1.000 * range_hl
    
    # Camarilla pivots
    cam_r4 = close + range_hl * 1.1 / 2
    cam_r3 = close + range_hl * 1.1 / 4
    cam_r2 = close + range_hl * 1.1 / 6
    cam_r1 = close + range_hl * 1.1 / 12
    cam_s1 = close - range_hl * 1.1 / 12
    cam_s2 = close - range_hl * 1.1 / 6
    cam_s3 = close - range_hl * 1.1 / 4
    cam_s4 = close - range_hl * 1.1 / 2
    
    # CPR (Central Pivot Range)
    # Pivot = (H + L + C) / 3 (same as classic)
    # BC (Bottom Central) = (H + L) / 2
    # TC (Top Central) = (Pivot - BC) + Pivot = 2*Pivot - BC
    cpr_bc = (high + low) / 2
    cpr_tc = 2 * pivot - cpr_bc
    cpr_width = np.abs(cpr_tc - cpr_bc) / pivot * 100  # CPR width as %
    
    # PDH, PDL, PDC (Previous Day High/Low/Close)
    # These are just the raw values passed in (should be previous day's)
    pdh = high.copy()
    pdl = low.copy()
    pdc = close.copy()
    
    return {
        # Classic Pivots
        'pivot_point': pivot, 'pivot_r1': r1, 'pivot_r2': r2, 'pivot_r3': r3,
        'pivot_s1': s1, 'pivot_s2': s2, 'pivot_s3': s3,
        # Fibonacci Pivots
        'fib_r1': fib_r1, 'fib_r2': fib_r2, 'fib_r3': fib_r3,
        'fib_s1': fib_s1, 'fib_s2': fib_s2, 'fib_s3': fib_s3,
        # Camarilla Pivots
        'cam_r4': cam_r4, 'cam_r3': cam_r3, 'cam_r2': cam_r2, 'cam_r1': cam_r1,
        'cam_s1': cam_s1, 'cam_s2': cam_s2, 'cam_s3': cam_s3, 'cam_s4': cam_s4,
        # CPR
        'cpr_tc': cpr_tc, 'cpr_pivot': pivot, 'cpr_bc': cpr_bc, 'cpr_width': cpr_width,
        # PDH/PDL/PDC
        'pdh': pdh, 'pdl': pdl, 'pdc': pdc
    }


async def compute_indicators_for_instrument(
    conn,
    instrument_id: str,
    timeframe: str = '1m'
) -> int:
    """Compute all indicators for a single instrument."""
    from datetime import datetime as dt
    
    t_start = dt.now()
    
    # Fetch candle data
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data
        WHERE instrument_id = $1 AND timeframe = $2
        ORDER BY timestamp
    ''', instrument_id, timeframe)
    
    t_fetch = dt.now()
    
    if len(rows) < 200:
        return 0
    
    # Convert to numpy
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
    
    pivots = compute_pivot_points(high, low, close)
    
    obv = compute_obv(close, volume)
    volume_sma_20 = compute_sma(volume, 20)
    volume_ratio = np.full(len(close), np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        valid = volume_sma_20 > 0
        volume_ratio[valid] = volume[valid] / volume_sma_20[valid]
    
    t_calc = dt.now()
    
    # Prepare records (start from index 200 where all indicators are valid)
    records = []
    for i in range(199, len(timestamps)):
        records.append((
            instrument_id,
            timeframe,
            timestamps[i],
            safe_float(sma_9[i]),
            safe_float(sma_20[i]),
            safe_float(sma_50[i]),
            safe_float(sma_200[i]),
            safe_float(ema_9[i]),
            safe_float(ema_21[i]),
            safe_float(ema_50[i]),
            safe_float(ema_200[i]),
            safe_float(vwap[i]),
            safe_float(vwma_20[i]),
            safe_float(vwma_22[i]),
            safe_float(vwma_31[i]),
            safe_float(rsi_14[i]),
            safe_float(macd[i]),
            safe_float(macd_signal[i]),
            safe_float(macd_histogram[i]),
            safe_float(stoch_k[i]),
            safe_float(stoch_d[i]),
            safe_float(cci[i]),
            safe_float(williams_r[i]),
            safe_float(atr_14[i]),
            safe_float(bb_upper[i]),
            safe_float(bb_middle[i]),
            safe_float(bb_lower[i]),
            safe_float(adx[i]),
            safe_float(plus_di[i]),
            safe_float(minus_di[i]),
            safe_float(supertrend[i]),
            safe_int(supertrend_dir[i]),
            safe_float(pivots['pivot_point'][i]),
            safe_float(pivots['pivot_r1'][i]),
            safe_float(pivots['pivot_r2'][i]),
            safe_float(pivots['pivot_r3'][i]),
            safe_float(pivots['pivot_s1'][i]),
            safe_float(pivots['pivot_s2'][i]),
            safe_float(pivots['pivot_s3'][i]),
            safe_float(pivots['cam_r4'][i]),
            safe_float(pivots['cam_r3'][i]),
            safe_float(pivots['cam_r2'][i]),
            safe_float(pivots['cam_r1'][i]),
            safe_float(pivots['cam_s1'][i]),
            safe_float(pivots['cam_s2'][i]),
            safe_float(pivots['cam_s3'][i]),
            safe_float(pivots['cam_s4'][i]),
            safe_int(obv[i]),
            safe_int(volume_sma_20[i]) if not np.isnan(volume_sma_20[i]) else None,
            safe_float(volume_ratio[i]),
            # New columns: PDH, PDL, PDC, CPR, Fibonacci
            safe_float(pivots['pdh'][i]),
            safe_float(pivots['pdl'][i]),
            safe_float(pivots['pdc'][i]),
            safe_float(pivots['cpr_tc'][i]),
            safe_float(pivots['cpr_pivot'][i]),
            safe_float(pivots['cpr_bc'][i]),
            safe_float(pivots['cpr_width'][i]),
            safe_float(pivots['fib_r1'][i]),
            safe_float(pivots['fib_r2'][i]),
            safe_float(pivots['fib_r3'][i]),
            safe_float(pivots['fib_s1'][i]),
            safe_float(pivots['fib_s2'][i]),
            safe_float(pivots['fib_s3'][i]),
        ))
    
    t_prep = dt.now()
    
    if not records:
        return 0
    
    # Use temp table for fast insert, then swap
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
    
    # Create temp table (UNLOGGED for speed, no indexes/constraints)
    await conn.execute('DROP TABLE IF EXISTS temp_indicator_batch')
    await conn.execute('''
        CREATE UNLOGGED TABLE temp_indicator_batch (LIKE indicator_data INCLUDING DEFAULTS)
    ''')
    
    # COPY into temp table (very fast - no indexes/FK checks)
    await conn.copy_records_to_table(
        'temp_indicator_batch',
        records=records,
        columns=columns
    )
    
    # Delete existing from main table and insert from temp in one transaction
    await conn.execute('''
        DELETE FROM indicator_data 
        WHERE instrument_id = $1 AND timeframe = $2
    ''', instrument_id, timeframe)
    
    await conn.execute('''
        INSERT INTO indicator_data SELECT * FROM temp_indicator_batch
    ''')
    
    await conn.execute('DROP TABLE temp_indicator_batch')
    
    t_insert = dt.now()
    
    # Log timing breakdown
    fetch_s = (t_fetch - t_start).total_seconds()
    convert_s = (t_convert - t_fetch).total_seconds()
    calc_s = (t_calc - t_convert).total_seconds()
    prep_s = (t_prep - t_calc).total_seconds()
    insert_s = (t_insert - t_prep).total_seconds()
    logger.info(f'  Timing: fetch={fetch_s:.1f}s, convert={convert_s:.1f}s, calc={calc_s:.1f}s, prep={prep_s:.1f}s, insert={insert_s:.1f}s')
    
    return len(records)


async def main(instrument_type: str = None, limit: int = 100):
    """Main entry point."""
    conn = await asyncpg.connect(DB_URL)
    
    print("=" * 60)
    print("INDICATOR COMPUTATION")
    print("=" * 60)
    
    # Build query for instruments
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
                print(f"Progress: {i + 1}/{len(instruments)} | Records: {total_records:,} | Rate: {rate:.1f}/s | {inst['trading_symbol'][:20]}")
                
        except Exception as e:
            logger.error(f"Error processing {inst['trading_symbol']}: {e}")
    
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
    parser.add_argument('--type', choices=['EQUITY', 'INDEX', 'FUTURES', 'CE', 'PE'],
                        help='Instrument type to process')
    parser.add_argument('--limit', type=int, default=100,
                        help='Max instruments to process (default: 100)')
    
    args = parser.parse_args()
    asyncio.run(main(args.type, args.limit))
