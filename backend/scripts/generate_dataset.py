"""
Generate Strategy Dataset (Parquet/CSV)
Computes comprehensive technical indicators and saves them to efficient files for backtesting.
Default output: backend/data/strategy_dataset/
"""

import asyncio
import asyncpg
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from datetime import datetime
import time
from io import BytesIO
import logging
import argparse
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('DatasetGen')

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'
OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'strategy_dataset'

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# INDICATOR FUNCTIONS (Optimized Vectorized)
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
    n = len(close)
    result = np.full(n, np.nan)
    typical_price = (high + low + close) / 3
    
    # Use pandas for easier day grouping if possible, but keeping numpy for speed
    # Convert timestamps to dates efficiently
    # Assuming timestamps satisfy np.datetime64 compatible
    if len(timestamps) > 0:
        if isinstance(timestamps[0], datetime):
            dates = np.array([t.date() for t in timestamps])
        else:
             # Fallback
            dates = np.zeros(n) 
            
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

def compute_bollinger(close: np.ndarray, period: int = 20, num_std: float = 2) -> tuple:
    n = len(close)
    sma = compute_sma(close, period)
    std = np.full(n, np.nan)
    if n >= period:
        windows = sliding_window_view(close, period)
        std[period-1:] = np.std(windows, axis=1, ddof=0)
    return sma + (std * num_std), sma, sma - (std * num_std)

def compute_supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 10, multiplier: float = 3.0) -> tuple:
    atr = compute_atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    n = len(close)
    supertrend = np.full(n, np.nan)
    direction = np.zeros(n, dtype=np.int16) # 1=UP, -1=DOWN
    if n >= period:
        supertrend[period - 1] = upper_band[period - 1]
        direction[period - 1] = -1
        for i in range(period, n):
            if close[i - 1] > supertrend[i - 1]:
                # Trend was UP
                supertrend[i] = max(lower_band[i], supertrend[i - 1] if direction[i - 1] == 1 else lower_band[i])
                direction[i] = 1
            else:
                # Trend was DOWN
                supertrend[i] = min(upper_band[i], supertrend[i - 1] if direction[i - 1] == -1 else upper_band[i])
                direction[i] = -1
    return supertrend, direction

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
        # Match lengths
        signal_line[start_idx:start_idx + len(signal_calc)] = signal_calc
    return macd_line, signal_line, macd_line - signal_line

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
        sum_di = plus_di + minus_di
        dx[sum_di > 0] = 100 * np.abs(plus_di[sum_di > 0] - minus_di[sum_di > 0]) / sum_di[sum_di > 0]
        
    adx = compute_ema(dx, period)
    return adx, plus_di, minus_di

# ============================================================================
# DATAFRAME BUILDER
# ============================================================================

async def process_instrument(conn, instrument_id: str, symbol: str) -> pd.DataFrame:
    """Fetch data and compute indicators for one instrument."""
    
    # 1. Fetch raw candles (1 minute)
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume, oi
        FROM candle_data 
        WHERE instrument_id = $1 AND timeframe = '1m'
        ORDER BY timestamp ASC
    ''', instrument_id)
    
    if len(rows) < 50:
        return None
        
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
    
    # Ensure float types
    for col in ['open', 'high', 'low', 'close', 'volume', 'oi']:
        df[col] = df[col].astype(float)
        
    # Convert numpy arrays for fast calculation
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    volume = df['volume'].values
    timestamps = df['timestamp'].tolist()
    
    # 2. Compute Indicators
    df['sma_20'] = compute_sma(close, 20)
    df['sma_50'] = compute_sma(close, 50)
    df['sma_200'] = compute_sma(close, 200)
    
    df['ema_9'] = compute_ema(close, 9)
    df['ema_21'] = compute_ema(close, 21)
    
    df['rsi_14'] = compute_rsi(close, 14)
    
    df['vwap'] = compute_vwap(high, low, close, volume, timestamps)
    
    macd, signal, hist = compute_macd(close)
    df['macd'] = macd
    df['macd_signal'] = signal
    df['macd_hist'] = hist
    
    upper, mid, lower = compute_bollinger(close)
    df['bb_upper'] = upper
    df['bb_lower'] = lower
    # Mid is sma_20
    
    st, st_dir = compute_supertrend(high, low, close)
    df['supertrend'] = st
    df['supertrend_dir'] = st_dir
    
    adx, plus_di, minus_di = compute_adx(high, low, close)
    df['adx'] = adx
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    
    df['atr_14'] = compute_atr(high, low, close, 14)
    
    # 3. Add Metadata
    df['symbol'] = symbol
    df['instrument_id'] = str(instrument_id)
    
    # drop initial rows
    df_clean = df.dropna(subset=['sma_200']).copy()
    return df_clean

async def save_to_db(conn, df: pd.DataFrame, table_name='indicator_data'):
    """
    Saves the DataFrame to the database using COPY + Upsert strategy.
    Maps DataFrame columns to Database columns.
    """
    if df.empty:
        return

    # Map DF columns to DB columns
    # We only map what we have computed. 
    # Ensure these names match the DB schema exactly.
    col_map = {
        'instrument_id': 'instrument_id',
        'timestamp': 'timestamp',
        'sma_20': 'sma_20',
        'sma_50': 'sma_50',
        'sma_200': 'sma_200',
        'ema_9': 'ema_9',
        'ema_21': 'ema_21',
        'rsi_14': 'rsi_14',
        'macd': 'macd',
        'macd_signal': 'macd_signal',
        'macd_hist': 'macd_histogram',
        'bb_upper': 'bb_upper',
        'bb_lower': 'bb_lower',
        'supertrend': 'supertrend',
        'supertrend_dir': 'supertrend_direction',
        'adx': 'adx',
        'atr_14': 'atr_14',
        'vwap': 'vwap'
    }
    
    # Filter DF to valid columns and rename
    db_df = df[list(col_map.keys())].rename(columns=col_map)
    db_df['timeframe'] = '1m' # Add missing required column
    
    # Create temp table
    temp_table = f"temp_indicators_{int(datetime.now().timestamp())}"
    
    # Get columns that actually exist in the DB for this insert
    # We assume the table structure allows nulls for missing columns (e.g. Pivots)
    cols = list(db_df.columns)
    
    try:
        # Create temp table matching structure
        # We use a trick: CREATE TEMP TABLE AS SELECT ... WITH NO DATA
        await conn.execute(f"CREATE TEMP TABLE {temp_table} (LIKE {table_name} INCLUDING DEFAULTS)")
        
        # Prepare CSV data for COPY
        output = BytesIO()
        db_df.to_csv(output, sep='\t', header=False, index=False, na_rep='\\N')
        output.seek(0)
        
        # Copy to Temp
        await conn.copy_to_table(
            temp_table,
            source=output,
            columns=cols,
            format='text',
            delimiter='\t',
            null='\\N'
        )
        
        # Upsert from Temp to Main
        # Construct dynamic SET clause
        update_cols = [c for c in cols if c not in ('instrument_id', 'timeframe', 'timestamp')]
        update_stmt = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])
        
        sql = f"""
            INSERT INTO {table_name} ({", ".join(cols)})
            SELECT {", ".join(cols)} FROM {temp_table}
            ON CONFLICT (instrument_id, timeframe, timestamp)
            DO UPDATE SET {update_stmt}
        """
        
        await conn.execute(sql)
        await conn.execute(f"DROP TABLE {temp_table}")
        
    except Exception as e:
        logger.error(f"DB Save Failed: {e}")
        # Don't raise, just log, so Parquet generation continues

async def main():
    parser = argparse.ArgumentParser(description='Generate strategy dataset')
    parser.add_argument('--symbol', help='Generate for specific symbol (e.g., RELIANCE)')
    args = parser.parse_args()
    
    print(f"Connecting to {DB_URL}...")
    pool = await asyncpg.create_pool(DB_URL)
    print("Connected to DB successfully.")
    
    from io import BytesIO # Needed for save_to_db
    
    # Get all active Equity/Index instruments first (High priority for strategy)
    async with pool.acquire() as conn:
        # Optimized: Fetch all equity/index instruments without checking for candle data first.
        # The check will happen individually in process_instrument.
        if args.symbol:
            instruments = await conn.fetch('''
                SELECT instrument_id, trading_symbol, instrument_type
                FROM instrument_master
                WHERE instrument_type IN ('EQUITY', 'INDEX')
                AND trading_symbol = $1
            ''', args.symbol)
        else:
            instruments = await conn.fetch('''
                SELECT instrument_id, trading_symbol, instrument_type
                FROM instrument_master
                WHERE instrument_type IN ('EQUITY', 'INDEX')
                ORDER BY trading_symbol
            ''')
        
    print(f"Found {len(instruments)} instruments to process.")
    
    total_rows = 0
    file_count = 0
    
    for idx, inst in enumerate(instruments):
        symbol = inst['trading_symbol']
        inst_id = inst['instrument_id']
        
        async with pool.acquire() as conn:
            t0 = time.time()
            df = await process_instrument(conn, inst_id, symbol)
            dt = time.time() - t0
            
            if df is not None and not df.empty:
                # 1. Save to Parquet
                filename = f"{symbol.replace(' ', '_')}_{inst['instrument_type']}.parquet"
                filepath = OUTPUT_DIR / filename
                df.to_parquet(filepath, index=False, engine='pyarrow', compression='snappy')
                
                # 2. Save to Database (New Feature)
                await save_to_db(conn, df)
                
                total_rows += len(df)
                file_count += 1
                
                # Concise log for every instrument
                print(f"[{idx+1}/{len(instruments)}] {symbol:<15} | {len(df):>7} rows | {dt:>5.1f}s | Saved")

        if df is None or df.empty:
             print(f"[{idx+1}/{len(instruments)}] Skipped {symbol} (insufficient data)")
            
    print("\n" + "="*50)
    print("DATASET GENERATION COMPLETE")
    print("="*50)
    print(f"Files Created: {file_count}")
    print(f"Total Rows: {total_rows:,}")
    print(f"Output Directory: {OUTPUT_DIR}")
    
    await pool.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
