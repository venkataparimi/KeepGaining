"""
Incremental Parquet Updater
Efficiently appends new data to existing strategy datasets (Parquet files).
Designed for daily use after market hours.
"""

import asyncio
import asyncpg
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from pathlib import Path
from io import BytesIO
import pyarrow.parquet as pq
import pyarrow as pa
import sys

# Import indicator functions (reuse existing optimized ones)
sys.path.append(str(Path(__file__).parent))
from generate_dataset import (
    compute_sma, compute_ema, compute_rsi, compute_atr, 
    compute_vwap, compute_bollinger, compute_supertrend, 
    compute_macd, compute_adx, DB_URL, OUTPUT_DIR
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ParquetUpdater')

async def update_instrument_parquet(conn, instrument_id: str, symbol: str, instrument_type: str):
    """
    Updates the parquet file for a single instrument by fetching only new data
    plus enough history to recompute indicators correctly.
    """
    file_path = OUTPUT_DIR / f"{symbol.replace(' ', '_')}_{instrument_type}.parquet"
    
    # 1. Determine last timestamp in existing file
    last_timestamp = None
    if file_path.exists():
        try:
            #Read metadata only to get last timestamp (fast)
            meta = pq.read_metadata(file_path)
            # This requires reading the last row, which is still reasonably fast
            # Faster method: read only 'timestamp' column, take last
            df_existing_tail = pd.read_parquet(file_path, columns=['timestamp']).iloc[-1]
            last_timestamp = df_existing_tail['timestamp']
            
            # Ensure it's a datetime object
            if isinstance(last_timestamp, np.datetime64):
                last_timestamp = pd.to_datetime(last_timestamp).to_pydatetime()
                
            logger.info(f"  {symbol}: Existing data up to {last_timestamp}")
        except Exception as e:
            logger.warning(f"  {symbol}: Error reading existing file ({e}). Recreating full.")
            last_timestamp = None
    
    # 2. Fetch New Data + Buffer
    # We need ~200 candles BEFORE the last_timestamp to correctly compute 
    # rolling indicators (EMA, SMA200) for the NEW rows.
    
    if last_timestamp:
        # Fetch data starting 5 days before last_timestamp to ensure sufficient lookback buffer
        # (Assuming mostly 1m data, 5 days is safely > 200 candles)
        fetch_start = last_timestamp - timedelta(days=5)
        
        rows = await conn.fetch('''
            SELECT timestamp, open, high, low, close, volume, oi
            FROM candle_data 
            WHERE instrument_id = $1 AND timeframe = '1m' AND timestamp >= $2
            ORDER BY timestamp ASC
        ''', instrument_id, fetch_start)
    else:
        # Fetch all
        rows = await conn.fetch('''
            SELECT timestamp, open, high, low, close, volume, oi
            FROM candle_data 
            WHERE instrument_id = $1 AND timeframe = '1m'
            ORDER BY timestamp ASC
        ''', instrument_id)
        
    if not rows:
        return # No data
        
    # Convert to DataFrame
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
    
    # Check if we actually have NEW data
    if last_timestamp:
        # Filter strictly greater than last_known
        # Note: We fetched overlapping data for computation, but we only want to APPEND new rows
        new_rows_mask = df['timestamp'] > last_timestamp
        if not new_rows_mask.any():
            logger.info(f"  {symbol}: No new data found.")
            return

    # 3. Compute Indicators on the Buffer + New Data Chunk
    # (We recompute on the buffer to ensure the first 'new' point has correct history)
    
    # Ensure float types
    for col in ['open', 'high', 'low', 'close', 'volume', 'oi']:
        df[col] = df[col].astype(float)
        
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    volume = df['volume'].values
    timestamps = df['timestamp'].tolist()
    
    # --- Indicator Computation (Same as generation script) ---
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
    st, st_dir = compute_supertrend(high, low, close)
    df['supertrend'] = st
    df['supertrend_dir'] = st_dir
    adx, plus_di, minus_di = compute_adx(high, low, close)
    df['adx'] = adx
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    df['atr_14'] = compute_atr(high, low, close, 14)
    
    df['symbol'] = symbol
    df['instrument_id'] = str(instrument_id)
    # -----------------------------------------------------

    # 4. Slice ONLY the new rows for appending
    if last_timestamp:
        df_new = df[df['timestamp'] > last_timestamp].copy()
    else:
        df_new = df.dropna(subset=['sma_200']).copy() # Initial load clean

    if df_new.empty:
        return

    # 5. Efficient Append
    table = pa.Table.from_pandas(df_new)
    
    if file_path.exists() and last_timestamp:
        # Append to existing Parquet file
        # Note: Parquet files are immutable, 'appending' usually necessitates rewriting 
        # OR writing to a partitioned dataset. 
        # For single files, we read the old, concat, and write.
        # Ideally, we should use a partitioned dataset structure (by year/month) for true scalability.
        # But for simplicity and speed now (file size < 1GB), reading/writing is okay.
        
        # HOWEVER, fastparquet/pyarrow allows writing multiple 'row groups'.
        # But standard readers often expect a single schema.
        
        # Strategy: Read Full -> Concat -> Write Full
        # This is safe and ensures data integrity.
        # For massive scale, we'd switch to partitioned folders (symbol/year=2024/month=12/part.parquet)
        
        df_old = pd.read_parquet(file_path)
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        # Drop duplicates just in case
        df_combined = df_combined.drop_duplicates(subset=['timestamp'], keep='last')
        
        df_combined.to_parquet(file_path, index=False, engine='pyarrow', compression='snappy')
        logger.info(f"  {symbol}: Appended {len(df_new)} rows. Total: {len(df_combined)}")
    else:
        # Create new
        df_new.to_parquet(file_path, index=False, engine='pyarrow', compression='snappy')
        logger.info(f"  {symbol}: Created new file with {len(df_new)} rows.")

    # 6. Save new rows to DB
    await save_to_db(conn, df_new)

async def save_to_db(conn, df: pd.DataFrame, table_name='indicator_data'):
    """Performs bulk upsert of indicators to database."""
    if df.empty: return
    
    col_map = {
        'instrument_id': 'instrument_id', 'timestamp': 'timestamp',
        'sma_20': 'sma_20', 'sma_50': 'sma_50', 'sma_200': 'sma_200',
        'ema_9': 'ema_9', 'ema_21': 'ema_21', 'rsi_14': 'rsi_14',
        'macd': 'macd', 'macd_signal': 'macd_signal', 'macd_hist': 'macd_histogram',
        'bb_upper': 'bb_upper', 'bb_lower': 'bb_lower',
        'supertrend': 'supertrend', 'supertrend_dir': 'supertrend_direction',
        'adx': 'adx', 'atr_14': 'atr_14', 'vwap': 'vwap'
    }
    
    db_df = df[list(col_map.keys())].rename(columns=col_map)
    db_df['timeframe'] = '1m'
    cols = list(db_df.columns)
    
    temp_table = f"temp_ind_upd_{int(datetime.now().timestamp())}_{df.iloc[0]['instrument_id']}"
    
    try:
        await conn.execute(f"CREATE TEMP TABLE {temp_table} (LIKE {table_name} INCLUDING DEFAULTS)")
        output = BytesIO()
        db_df.to_csv(output, sep='\t', header=False, index=False, na_rep='\\N')
        output.seek(0)
        
        await conn.copy_to_table(temp_table, source=output, columns=cols, format='text', delimiter='\t', null='\\N')
        
        update_cols = [c for c in cols if c not in ('instrument_id', 'timeframe', 'timestamp')]
        update_stmt = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])
        
        await conn.execute(f"""
            INSERT INTO {table_name} ({", ".join(cols)})
            SELECT {", ".join(cols)} FROM {temp_table}
            ON CONFLICT (instrument_id, timeframe, timestamp)
            DO UPDATE SET {update_stmt}
        """)
        await conn.execute(f"DROP TABLE {temp_table}")
        
    except Exception as e:
        logger.error(f"  {df.iloc[0]['symbol']}: DB Save Failed: {e}")

async def main():
    pool = await asyncpg.create_pool(DB_URL)
    from io import BytesIO
    
    # Identify instruments that have new data
    # (In a production system, we'd query the 'last_updated' timestamp from a tracking table)
    # For now, we iterate active equities.
    
    async with pool.acquire() as conn:
        instruments = await conn.fetch('''
            SELECT instrument_id, trading_symbol, instrument_type
            FROM instrument_master 
            WHERE instrument_type IN ('EQUITY', 'INDEX')
            ORDER BY trading_symbol
        ''')
        
    logger.info(f"Checking updates for {len(instruments)} instruments...")
    
    for inst in instruments:
        symbol = inst['trading_symbol']
        await process_instrument_update(pool, inst['instrument_id'], symbol, inst['instrument_type'])
        
    await pool.close()

async def process_instrument_update(pool, inst_id, symbol, inst_type):
    async with pool.acquire() as conn:
        await update_instrument_parquet(conn, inst_id, symbol, inst_type)

if __name__ == "__main__":
    asyncio.run(main())
