"""
Compute technical indicators for all candle data.
Stores results in indicator_data table.

Indicators computed:
- SMA (20, 50, 200)
- EMA (9, 21, 50)
- RSI (14)
- MACD (12, 26, 9)
- Bollinger Bands (20, 2)
- ATR (14)
- VWAP
- SuperTrend
"""
import asyncio
import asyncpg
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from typing import List, Dict, Any
import uuid
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

# Indicator parameters
SMA_PERIODS = [20, 50, 200]
EMA_PERIODS = [9, 21, 50]
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
ATR_PERIOD = 14
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3.0


def compute_sma(close: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average."""
    result = np.full(len(close), np.nan)
    if len(close) >= period:
        for i in range(period - 1, len(close)):
            result[i] = np.mean(close[i - period + 1:i + 1])
    return result


def compute_ema(close: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    result = np.full(len(close), np.nan)
    if len(close) >= period:
        multiplier = 2 / (period + 1)
        result[period - 1] = np.mean(close[:period])
        for i in range(period, len(close)):
            result[i] = (close[i] - result[i - 1]) * multiplier + result[i - 1]
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
    signal_line = compute_ema(macd_line[~np.isnan(macd_line)], signal)
    
    # Align signal line
    signal_result = np.full(len(close), np.nan)
    valid_start = np.where(~np.isnan(macd_line))[0]
    if len(valid_start) > 0:
        start_idx = valid_start[0]
        signal_result[start_idx:start_idx + len(signal_line)] = signal_line
    
    histogram = macd_line - signal_result
    
    return macd_line, signal_result, histogram


def compute_bollinger_bands(close: np.ndarray, period: int = 20, num_std: float = 2) -> tuple:
    """Bollinger Bands."""
    sma = compute_sma(close, period)
    std = np.full(len(close), np.nan)
    
    for i in range(period - 1, len(close)):
        std[i] = np.std(close[i - period + 1:i + 1])
    
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
    
    # First ATR is simple average
    if len(tr) >= period:
        result[period - 1] = np.mean(tr[:period])
        
        # Subsequent ATRs use smoothing
        for i in range(period, len(close)):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    
    return result


def compute_vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """Volume Weighted Average Price (cumulative for the day)."""
    typical_price = (high + low + close) / 3
    cumulative_tpv = np.cumsum(typical_price * volume)
    cumulative_vol = np.cumsum(volume)
    
    with np.errstate(divide='ignore', invalid='ignore'):
        vwap = np.where(cumulative_vol > 0, cumulative_tpv / cumulative_vol, np.nan)
    
    return vwap


def compute_supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray, 
                       period: int = 10, multiplier: float = 3.0) -> tuple:
    """SuperTrend indicator."""
    atr = compute_atr(high, low, close, period)
    
    hl2 = (high + low) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    
    supertrend = np.full(len(close), np.nan)
    direction = np.zeros(len(close))  # 1 = bullish, -1 = bearish
    
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


async def compute_indicators_for_instrument(
    conn,
    instrument_id: str,
    timeframe: str = '1m'
) -> int:
    """Compute all indicators for a single instrument."""
    
    # Fetch candle data
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data
        WHERE instrument_id = $1 AND timeframe = $2
        ORDER BY timestamp
    ''', instrument_id, timeframe)
    
    if len(rows) < 200:  # Need enough data for longest indicator
        return 0
    
    # Convert to numpy arrays
    timestamps = [r['timestamp'] for r in rows]
    open_prices = np.array([float(r['open']) for r in rows])
    high_prices = np.array([float(r['high']) for r in rows])
    low_prices = np.array([float(r['low']) for r in rows])
    close_prices = np.array([float(r['close']) for r in rows])
    volumes = np.array([float(r['volume']) for r in rows])
    
    # Compute indicators
    indicators = {}
    
    # SMA
    for period in SMA_PERIODS:
        indicators[f'sma_{period}'] = compute_sma(close_prices, period)
    
    # EMA
    for period in EMA_PERIODS:
        indicators[f'ema_{period}'] = compute_ema(close_prices, period)
    
    # RSI
    indicators['rsi_14'] = compute_rsi(close_prices, RSI_PERIOD)
    
    # MACD
    macd_line, signal_line, histogram = compute_macd(close_prices, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    indicators['macd'] = macd_line
    indicators['macd_signal'] = signal_line
    indicators['macd_histogram'] = histogram
    
    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = compute_bollinger_bands(close_prices, BB_PERIOD, BB_STD)
    indicators['bb_upper'] = bb_upper
    indicators['bb_middle'] = bb_middle
    indicators['bb_lower'] = bb_lower
    
    # ATR
    indicators['atr_14'] = compute_atr(high_prices, low_prices, close_prices, ATR_PERIOD)
    
    # VWAP
    indicators['vwap'] = compute_vwap(high_prices, low_prices, close_prices, volumes)
    
    # SuperTrend
    supertrend, direction = compute_supertrend(high_prices, low_prices, close_prices, 
                                                SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER)
    indicators['supertrend'] = supertrend
    indicators['supertrend_direction'] = direction
    
    # Prepare records for insertion
    records = []
    for i, ts in enumerate(timestamps):
        # Only store if we have valid indicator values
        if not np.isnan(indicators['rsi_14'][i]):
            indicator_values = {
                'sma_20': float(indicators['sma_20'][i]) if not np.isnan(indicators['sma_20'][i]) else None,
                'sma_50': float(indicators['sma_50'][i]) if not np.isnan(indicators['sma_50'][i]) else None,
                'sma_200': float(indicators['sma_200'][i]) if not np.isnan(indicators['sma_200'][i]) else None,
                'ema_9': float(indicators['ema_9'][i]) if not np.isnan(indicators['ema_9'][i]) else None,
                'ema_21': float(indicators['ema_21'][i]) if not np.isnan(indicators['ema_21'][i]) else None,
                'ema_50': float(indicators['ema_50'][i]) if not np.isnan(indicators['ema_50'][i]) else None,
                'rsi_14': float(indicators['rsi_14'][i]) if not np.isnan(indicators['rsi_14'][i]) else None,
                'macd': float(indicators['macd'][i]) if not np.isnan(indicators['macd'][i]) else None,
                'macd_signal': float(indicators['macd_signal'][i]) if not np.isnan(indicators['macd_signal'][i]) else None,
                'macd_histogram': float(indicators['macd_histogram'][i]) if not np.isnan(indicators['macd_histogram'][i]) else None,
                'bb_upper': float(indicators['bb_upper'][i]) if not np.isnan(indicators['bb_upper'][i]) else None,
                'bb_middle': float(indicators['bb_middle'][i]) if not np.isnan(indicators['bb_middle'][i]) else None,
                'bb_lower': float(indicators['bb_lower'][i]) if not np.isnan(indicators['bb_lower'][i]) else None,
                'atr_14': float(indicators['atr_14'][i]) if not np.isnan(indicators['atr_14'][i]) else None,
                'vwap': float(indicators['vwap'][i]) if not np.isnan(indicators['vwap'][i]) else None,
                'supertrend': float(indicators['supertrend'][i]) if not np.isnan(indicators['supertrend'][i]) else None,
                'supertrend_direction': int(indicators['supertrend_direction'][i]),
            }
            
            records.append((
                uuid.uuid4(),
                instrument_id,
                timeframe,
                ts,
                indicator_values
            ))
    
    # Insert in batches
    if records:
        # Delete existing indicators for this instrument
        await conn.execute('''
            DELETE FROM indicator_data 
            WHERE instrument_id = $1 AND timeframe = $2
        ''', instrument_id, timeframe)
        
        # Insert new indicators
        await conn.executemany('''
            INSERT INTO indicator_data 
            (id, instrument_id, timeframe, timestamp, indicators)
            VALUES ($1, $2, $3, $4, $5)
        ''', records)
    
    return len(records)


async def check_indicator_schema(conn):
    """Check if indicator_data table has expected schema."""
    cols = await conn.fetch('''
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'indicator_data'
        ORDER BY ordinal_position
    ''')
    
    logger.info("indicator_data schema:")
    for c in cols:
        logger.info(f"  {c['column_name']}: {c['data_type']}")
    
    return cols


async def main():
    """Main entry point."""
    conn = await asyncpg.connect(DB_URL)
    
    print("=" * 60)
    print("INDICATOR COMPUTATION")
    print("=" * 60)
    
    # Check schema first
    schema = await check_indicator_schema(conn)
    
    # Get instruments with sufficient data
    instruments = await conn.fetch('''
        SELECT instrument_id, candle_count
        FROM candle_data_summary
        WHERE candle_count >= 200
        ORDER BY candle_count DESC
        LIMIT 100
    ''')
    
    print(f"\nFound {len(instruments)} instruments with >= 200 candles")
    print("Processing top 100 instruments...")
    
    total_records = 0
    for i, inst in enumerate(instruments):
        try:
            count = await compute_indicators_for_instrument(
                conn, 
                inst['instrument_id'],
                '1m'
            )
            total_records += count
            
            if (i + 1) % 10 == 0:
                print(f"Processed {i + 1}/{len(instruments)} instruments, {total_records:,} total records")
                
        except Exception as e:
            logger.error(f"Error processing {inst['instrument_id']}: {e}")
    
    print(f"\nTotal indicator records created: {total_records:,}")
    
    await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
