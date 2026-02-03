"""
Optimized indicator functions using vectorized rolling operations.
"""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def compute_sma(data: np.ndarray, period: int) -> np.ndarray:
    """SMA using cumsum (fast)."""
    result = np.full(len(data), np.nan)
    if len(data) >= period:
        cumsum = np.cumsum(np.insert(data, 0, 0))
        result[period-1:] = (cumsum[period:] - cumsum[:-period]) / period
    return result


def compute_ema(data: np.ndarray, period: int) -> np.ndarray:
    """EMA - optimized with numba if available, else loop."""
    result = np.full(len(data), np.nan)
    if len(data) < period:
        return result
    
    multiplier = 2 / (period + 1)
    result[period - 1] = np.mean(data[:period])
    
    # Loop is actually efficient for EMA due to data dependency
    for i in range(period, len(data)):
        result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI - loop needed due to Wilder smoothing."""
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
    """ATR - vectorized TR, loop for smoothing."""
    n = len(close)
    result = np.full(n, np.nan)
    if n < 2:
        return result
    
    # Vectorized True Range
    tr = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1])
    ])
    tr = np.insert(tr, 0, high[0] - low[0])
    
    if n >= period:
        result[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result


def compute_vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """VWAP - fully vectorized."""
    typical_price = (high + low + close) / 3
    cumulative_tpv = np.cumsum(typical_price * volume)
    cumulative_vol = np.cumsum(volume)
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(cumulative_vol > 0, cumulative_tpv / cumulative_vol, np.nan)


def compute_vwma(close: np.ndarray, volume: np.ndarray, period: int) -> np.ndarray:
    """VWMA - vectorized using sliding_window_view."""
    n = len(close)
    result = np.full(n, np.nan)
    if n < period:
        return result
    
    # Create sliding windows
    close_windows = sliding_window_view(close, period)
    vol_windows = sliding_window_view(volume, period)
    
    # Sum along window axis
    vol_sums = vol_windows.sum(axis=1)
    with np.errstate(divide='ignore', invalid='ignore'):
        weighted_sums = (close_windows * vol_windows).sum(axis=1)
        result[period-1:] = np.where(vol_sums > 0, weighted_sums / vol_sums, np.nan)
    
    return result


def compute_bollinger(close: np.ndarray, period: int = 20, num_std: float = 2) -> tuple:
    """Bollinger Bands - vectorized std."""
    n = len(close)
    sma = compute_sma(close, period)
    
    std = np.full(n, np.nan)
    if n >= period:
        windows = sliding_window_view(close, period)
        std[period-1:] = np.std(windows, axis=1, ddof=0)
    
    return sma + (std * num_std), sma, sma - (std * num_std)


def compute_rolling_max_min(data: np.ndarray, period: int) -> tuple:
    """Rolling max and min - vectorized."""
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
    """Stochastic - vectorized."""
    n = len(close)
    stoch_k = np.full(n, np.nan)
    
    if n >= k_period:
        high_max, _ = compute_rolling_max_min(high, k_period)
        _, low_min = compute_rolling_max_min(low, k_period)
        
        denom = high_max - low_min
        with np.errstate(divide='ignore', invalid='ignore'):
            stoch_k = np.where(denom != 0, 100 * (close - low_min) / denom, np.nan)
    
    stoch_d = compute_sma(stoch_k, d_period)
    return stoch_k, stoch_d


def compute_cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 20) -> np.ndarray:
    """CCI - vectorized."""
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
    """Williams %R - vectorized."""
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
    """SuperTrend - ATR vectorized, trend loop needed."""
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
    """ADX - vectorized DM, EMA smoothing."""
    n = len(close)
    
    # Vectorized DM calculation
    up_move = np.diff(high, prepend=high[0])
    down_move = np.diff(-low, prepend=-low[0])
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    # Vectorized TR
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    tr[1:] = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1])
    ])
    
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
    
    adx = compute_ema(dx, period)
    return adx, plus_di, minus_di


def compute_macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """MACD."""
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
    """OBV - vectorized."""
    signs = np.sign(np.diff(close, prepend=close[0]))
    signs[0] = 1
    return np.cumsum(signs * volume).astype(np.int64)


# Test
if __name__ == '__main__':
    import asyncio
    import asyncpg
    from datetime import datetime
    
    DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'
    
    async def test():
        conn = await asyncpg.connect(DB_URL)
        
        inst = await conn.fetchrow('''
            SELECT instrument_id, candle_count FROM candle_data_summary
            ORDER BY candle_count DESC LIMIT 1
        ''')
        
        rows = await conn.fetch('''
            SELECT timestamp, open, high, low, close, volume
            FROM candle_data WHERE instrument_id = $1 AND timeframe = '1m'
            ORDER BY timestamp
        ''', inst['instrument_id'])
        
        high = np.array([float(r['high']) for r in rows])
        low = np.array([float(r['low']) for r in rows])
        close = np.array([float(r['close']) for r in rows])
        volume = np.array([float(r['volume']) for r in rows])
        
        print(f"Testing with {len(rows)} candles\n")
        
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
            ("Williams %R", lambda: compute_williams_r(high, low, close, 14)),
            ("SuperTrend", lambda: compute_supertrend(high, low, close, 10, 3)),
            ("MACD", lambda: compute_macd(close, 12, 26, 9)),
            ("OBV", lambda: compute_obv(close, volume)),
        ]
        
        total = 0
        for name, func in indicators:
            t1 = datetime.now()
            func()
            t2 = datetime.now()
            elapsed = (t2-t1).total_seconds()
            total += elapsed
            print(f"{name:20s}: {elapsed:.2f}s")
        
        print(f"\nTotal: {total:.2f}s")
        
        await conn.close()
    
    asyncio.run(test())
