"""
Incremental Dataset Generator
Only processes NEW candles since last run, significantly faster for daily updates.

Usage:
    python generate_dataset_incremental.py              # Update all instruments
    python generate_dataset_incremental.py --symbol RELIANCE  # Update specific symbol
    python generate_dataset_incremental.py --full       # Force full regeneration
"""

import asyncio
import asyncpg
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import time
from pathlib import Path
import sys
import argparse

sys.path.append(str(Path(__file__).parent))

# Import indicator functions from the original script
from generate_dataset import (
    compute_sma, compute_ema, compute_rsi, compute_macd, 
    compute_bollinger, compute_supertrend, compute_adx,
    compute_atr, compute_vwap
)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'
OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'strategy_dataset'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def get_last_timestamp_from_parquet(filepath: Path) -> datetime:
    """Get the last timestamp from existing Parquet file."""
    try:
        if filepath.exists():
            df = pd.read_parquet(filepath)
            if not df.empty and 'timestamp' in df.columns:
                return pd.to_datetime(df['timestamp']).max()
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}")
    return None


async def fetch_new_candles(conn, instrument_id, last_timestamp):
    """Fetch only candles newer than last_timestamp."""
    if last_timestamp:
        query = '''
            SELECT timestamp, open, high, low, close, volume, oi
            FROM candle_data 
            WHERE instrument_id = $1 AND timeframe = '1m'
            AND timestamp > $2
            ORDER BY timestamp ASC
        '''
        rows = await conn.fetch(query, instrument_id, last_timestamp)
    else:
        # No existing data, fetch all
        query = '''
            SELECT timestamp, open, high, low, close, volume, oi
            FROM candle_data 
            WHERE instrument_id = $1 AND timeframe = '1m'
            ORDER BY timestamp ASC
        '''
        rows = await conn.fetch(query, instrument_id)
    
    return rows


async def process_instrument_incremental(conn, instrument_id, symbol, force_full=False):
    """
    Process instrument incrementally:
    1. Load existing Parquet file
    2. Fetch only new candles
    3. Compute indicators for new data
    4. Append and save
    """
    filename = f"{symbol.replace(' ', '_')}_EQUITY.parquet"
    filepath = OUTPUT_DIR / filename
    
    # Check if we have existing data
    last_timestamp = None if force_full else await get_last_timestamp_from_parquet(filepath)
    
    if last_timestamp:
        print(f"  Last data: {last_timestamp}, fetching new candles...")
    
    # Fetch new candles
    new_rows = await fetch_new_candles(conn, instrument_id, last_timestamp)
    
    if not new_rows:
        return None, "No new data"
    
    # Convert to DataFrame
    new_df = pd.DataFrame([dict(r) for r in new_rows])
    
    # Convert Decimal types to float (database returns Decimal for numeric columns)
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'oi']
    for col in numeric_cols:
        if col in new_df.columns:
            new_df[col] = pd.to_numeric(new_df[col], errors='coerce')
    
    # If we have existing data, we need to load it and combine
    # BUT we need enough historical context to compute indicators correctly
    if last_timestamp and filepath.exists():
        # Load existing data
        existing_df = pd.read_parquet(filepath)
        
        # Get last 200 rows for indicator context (for SMA_200)
        # Only select the RAW candle columns to avoid type mismatches
        context_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi']
        context_df = existing_df[context_cols].tail(200).copy()
        
        # Ensure new_df has the same columns
        new_df = new_df[context_cols].copy()
        
        # Combine context + new data for indicator computation
        combined_df = pd.concat([context_df, new_df], ignore_index=True)
        
        # Compute indicators on combined data
        df_with_indicators = compute_all_indicators(combined_df, symbol, instrument_id)
        
        if df_with_indicators is None:
            return None, "Insufficient data for indicators"
        
        # Only keep the NEW rows (skip the context rows)
        new_rows_with_indicators = df_with_indicators.tail(len(new_df))
        
        # Append to existing (keep all columns from existing)
        final_df = pd.concat([existing_df, new_rows_with_indicators], ignore_index=True)
        
        # Remove duplicates (in case of overlap)
        final_df = final_df.drop_duplicates(subset=['timestamp'], keep='last')
        final_df = final_df.sort_values('timestamp').reset_index(drop=True)
        
        return final_df, f"Added {len(new_df)} new rows"
    
    else:
        # No existing data, compute from scratch
        df_with_indicators = compute_all_indicators(new_df, symbol, instrument_id)
        return df_with_indicators, f"Created with {len(new_df)} rows"


def compute_all_indicators(df, symbol, instrument_id):
    """Compute all technical indicators on a DataFrame."""
    if df.empty or len(df) < 200:
        return None
    
    # Extract arrays
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    volume = df['volume'].values
    timestamps = df['timestamp'].values
    
    # Compute indicators
    df['sma_5'] = compute_sma(close, 5)
    df['sma_10'] = compute_sma(close, 10)
    df['sma_20'] = compute_sma(close, 20)
    df['sma_50'] = compute_sma(close, 50)
    df['sma_200'] = compute_sma(close, 200)
    
    df['ema_9'] = compute_ema(close, 9)
    df['ema_21'] = compute_ema(close, 21)
    df['ema_50'] = compute_ema(close, 50)
    df['ema_200'] = compute_ema(close, 200)
    
    df['rsi_14'] = compute_rsi(close, 14)
    
    macd, signal, hist = compute_macd(close)
    df['macd'] = macd
    df['macd_signal'] = signal
    df['macd_hist'] = hist
    
    bb_upper, bb_middle, bb_lower = compute_bollinger(close, 20, 2)
    df['bb_upper'] = bb_upper
    df['bb_middle'] = bb_middle
    df['bb_lower'] = bb_lower
    
    df['vwap'] = compute_vwap(high, low, close, volume, timestamps)
    
    st, st_dir = compute_supertrend(high, low, close)
    df['supertrend'] = st
    df['supertrend_dir'] = st_dir
    
    adx, plus_di, minus_di = compute_adx(high, low, close)
    df['adx'] = adx
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    
    df['atr_14'] = compute_atr(high, low, close, 14)
    
    # Add metadata
    df['symbol'] = symbol
    df['instrument_id'] = str(instrument_id)
    
    # Clean up NaN rows
    df_clean = df.dropna(subset=['sma_200']).copy()
    return df_clean


async def main():
    parser = argparse.ArgumentParser(description='Incremental Dataset Generator')
    parser.add_argument('--symbol', help='Process specific symbol only')
    parser.add_argument('--full', action='store_true', help='Force full regeneration (ignore existing data)')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of instruments to process')
    args = parser.parse_args()
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    print(f"Connecting to {DB_URL}...")
    pool = await asyncpg.create_pool(DB_URL)
    print("Connected successfully.")
    
    # Get instruments to process
    async with pool.acquire() as conn:
        if args.symbol:
            instruments = await conn.fetch('''
                SELECT instrument_id, trading_symbol, instrument_type
                FROM instrument_master
                WHERE trading_symbol = $1 AND instrument_type IN ('EQUITY', 'INDEX')
            ''', args.symbol)
        else:
            instruments = await conn.fetch('''
                SELECT instrument_id, trading_symbol, instrument_type
                FROM instrument_master
                WHERE instrument_type IN ('EQUITY', 'INDEX')
                ORDER BY trading_symbol
            ''')
    
    if args.limit > 0:
        instruments = instruments[:args.limit]
    
    print(f"Processing {len(instruments)} instruments...")
    if args.full:
        print("⚠️  FULL REGENERATION MODE - Ignoring existing data")
    else:
        print("📈 INCREMENTAL MODE - Only processing new candles")
    
    updated = 0
    skipped = 0
    errors = 0
    
    for idx, inst in enumerate(instruments):
        symbol = inst['trading_symbol']
        inst_id = inst['instrument_id']
        
        try:
            async with pool.acquire() as conn:
                t0 = time.time()
                df, status = await process_instrument_incremental(conn, inst_id, symbol, args.full)
                dt = time.time() - t0
                
                if df is not None and not df.empty:
                    # Save to Parquet
                    filename = f"{symbol.replace(' ', '_')}_{inst['instrument_type']}.parquet"
                    filepath = OUTPUT_DIR / filename
                    df.to_parquet(filepath, index=False, engine='pyarrow', compression='snappy')
                    
                    updated += 1
                    print(f"[{idx+1}/{len(instruments)}] {symbol:<15} | {status:<25} | {dt:>5.1f}s | ✅")
                else:
                    skipped += 1
                    print(f"[{idx+1}/{len(instruments)}] {symbol:<15} | {status:<25} | {dt:>5.1f}s | ⏭️")
        
        except Exception as e:
            errors += 1
            import traceback
            print(f"[{idx+1}/{len(instruments)}] {symbol:<15} | ❌ ERROR")
            print(f"  {traceback.format_exc()}")
    
    print("\n" + "="*70)
    print("INCREMENTAL UPDATE COMPLETE")
    print("="*70)
    print(f"Updated: {updated}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")
    print(f"Output: {OUTPUT_DIR}")
    
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
