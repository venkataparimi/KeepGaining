"""
Profile each indicator function.
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


def compute_ema_vectorized(data, period):
    """Vectorized EMA using pandas/scipy approach."""
    result = np.full(len(data), np.nan)
    if len(data) < period:
        return result
    
    alpha = 2 / (period + 1)
    # First value is SMA of first 'period' values
    result[period - 1] = np.mean(data[:period])
    
    # Vectorized computation using scipy's lfilter
    from scipy.signal import lfilter
    # Filter coefficients
    b = [alpha]
    a = [1, -(1 - alpha)]
    
    # Apply filter starting from period-1
    filtered = lfilter(b, a, data[period-1:], zi=[result[period-1] * (1 - alpha)])
    result[period-1:] = filtered[0]
    
    return result


def compute_rsi(close, period=14):
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


def compute_atr(high, low, close, period=14):
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


def compute_vwma(close, volume, period):
    result = np.full(len(close), np.nan)
    if len(close) >= period:
        for i in range(period - 1, len(close)):
            vol_sum = np.sum(volume[i - period + 1:i + 1])
            if vol_sum > 0:
                result[i] = np.sum(close[i - period + 1:i + 1] * volume[i - period + 1:i + 1]) / vol_sum
    return result


def compute_adx(high, low, close, period=14):
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


def compute_bollinger(close, period=20, num_std=2):
    sma = compute_sma(close, period)
    std = np.full(len(close), np.nan)
    for i in range(period - 1, len(close)):
        std[i] = np.std(close[i - period + 1:i + 1], ddof=0)
    return sma + (std * num_std), sma, sma - (std * num_std)


def compute_stochastic(high, low, close, k_period=14, d_period=3):
    n = len(close)
    stoch_k = np.full(n, np.nan)
    for i in range(k_period - 1, n):
        highest = np.max(high[i - k_period + 1:i + 1])
        lowest = np.min(low[i - k_period + 1:i + 1])
        if highest != lowest:
            stoch_k[i] = 100 * (close[i] - lowest) / (highest - lowest)
    return stoch_k, compute_sma(stoch_k, d_period)


def compute_cci(high, low, close, period=20):
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


def compute_williams(high, low, close, period=14):
    n = len(close)
    williams_r = np.full(n, np.nan)
    for i in range(period - 1, n):
        highest = np.max(high[i - period + 1:i + 1])
        lowest = np.min(low[i - period + 1:i + 1])
        if highest != lowest:
            williams_r[i] = -100 * (highest - close[i]) / (highest - lowest)
    return williams_r


def compute_supertrend(high, low, close, period=10, multiplier=3.0):
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


async def profile():
    conn = await asyncpg.connect(DB_URL)
    
    inst = await conn.fetchrow('''
        SELECT instrument_id, candle_count FROM candle_data_summary
        ORDER BY candle_count DESC LIMIT 1
    ''')
    instrument_id = inst['instrument_id']
    n_candles = inst['candle_count']
    print(f"Profiling with {n_candles} candles\n")
    
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data WHERE instrument_id = $1 AND timeframe = '1m'
        ORDER BY timestamp
    ''', instrument_id)
    
    timestamps = [r['timestamp'] for r in rows]
    high = np.array([float(r['high']) for r in rows])
    low = np.array([float(r['low']) for r in rows])
    close = np.array([float(r['close']) for r in rows])
    volume = np.array([float(r['volume']) for r in rows])
    
    # Profile each indicator
    indicators = [
        ("SMA (4 periods)", lambda: [compute_sma(close, p) for p in [9, 20, 50, 200]]),
        ("EMA (4 periods)", lambda: [compute_ema(close, p) for p in [9, 21, 50, 200]]),
        ("RSI", lambda: compute_rsi(close, 14)),
        ("ATR", lambda: compute_atr(high, low, close, 14)),
        ("VWMA (3 periods)", lambda: [compute_vwma(close, volume, p) for p in [20, 22, 31]]),
        ("ADX (+DI/-DI)", lambda: compute_adx(high, low, close, 14)),
        ("Bollinger", lambda: compute_bollinger(close, 20, 2)),
        ("Stochastic", lambda: compute_stochastic(high, low, close, 14, 3)),
        ("CCI", lambda: compute_cci(high, low, close, 20)),
        ("Williams %R", lambda: compute_williams(high, low, close, 14)),
        ("SuperTrend", lambda: compute_supertrend(high, low, close, 10, 3)),
    ]
    
    total = 0
    for name, func in indicators:
        t1 = datetime.now()
        func()
        t2 = datetime.now()
        elapsed = (t2-t1).total_seconds()
        total += elapsed
        print(f"{name:20s}: {elapsed:.2f}s")
    
    print(f"\nTotal indicators: {total:.2f}s")
    
    await conn.close()

asyncio.run(profile())
