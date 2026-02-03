"""
Stage 3: Load Parquet Files to Database
Reads Parquet files and bulk loads into indicator_data table.
"""
import asyncio
import asyncpg
import pandas as pd
from pathlib import Path
from datetime import datetime
from io import StringIO
import logging
import argparse
import json
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'
PARQUET_DIR = Path(__file__).parent.parent / 'data' / 'indicators'
LOADED_DIR = Path(__file__).parent.parent / 'data' / 'loaded'
PROGRESS_FILE = Path(__file__).parent.parent / 'data' / 'db_load_progress.json'

# Columns to load into database (must match indicator_data table schema)
DB_COLUMNS = [
    'instrument_id', 'timeframe', 'timestamp',
    'sma_9', 'sma_20', 'sma_50', 'sma_200',
    'ema_9', 'ema_21', 'ema_50', 'ema_200',
    'vwap', 'rsi_14',
    'macd', 'macd_signal', 'macd_histogram',
    'atr_14', 'bb_upper', 'bb_middle', 'bb_lower',
    'adx', 'plus_di', 'minus_di',
    'supertrend', 'supertrend_direction',
    'obv', 'volume_sma_20',
    'pivot_point', 'pivot_r1', 'pivot_r2', 'pivot_s1', 'pivot_s2',
    'fib_r1', 'fib_r2', 'fib_s1', 'fib_s2'
]


def load_progress() -> set:
    """Load set of already loaded instrument IDs."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return set(json.load(f).get('loaded', []))
    return set()


def save_progress(loaded: set):
    """Save progress."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({'loaded': list(loaded), 'updated_at': datetime.now().isoformat()}, f)


async def load_parquet_to_db(conn, parquet_file: Path) -> int:
    """Load a single Parquet file into the database."""
    
    df = pd.read_parquet(parquet_file)
    
    if len(df) == 0:
        return 0
    
    # Get instrument_id from first row
    instrument_id = df['instrument_id'].iloc[0]
    
    # Check if data already exists for this instrument
    existing = await conn.fetchval(
        "SELECT COUNT(*) FROM indicator_data WHERE instrument_id = $1",
        instrument_id
    )
    
    if existing > 0:
        logger.info(f"  {parquet_file.stem}: Already has {existing} rows in DB, skipping")
        return 0
    
    # Prepare data for insertion
    # Filter to only the columns we need and handle missing columns
    available_cols = [c for c in DB_COLUMNS if c in df.columns]
    df_insert = df[available_cols].copy()
    
    # Handle NaN values - convert to None for proper NULL handling
    df_insert = df_insert.replace({np.nan: None})
    
    # Convert supertrend_direction to int if present
    if 'supertrend_direction' in df_insert.columns:
        df_insert['supertrend_direction'] = df_insert['supertrend_direction'].apply(
            lambda x: int(x) if x is not None else None
        )
    
    # Load all rows - indicators that need warmup period (e.g., SMA-200) will have NULL values\n    # for the initial rows, which is expected and handled properly\n    \n    if len(df_insert) == 0:\n        return 0
    
    # Build insert values
    records = df_insert.to_records(index=False)
    
    # Use executemany with ON CONFLICT
    insert_sql = f"""
        INSERT INTO indicator_data ({', '.join(available_cols)})
        VALUES ({', '.join([f'${i+1}' for i in range(len(available_cols))])})
        ON CONFLICT (instrument_id, timeframe, timestamp) DO NOTHING
    """
    
    try:
        await conn.executemany(insert_sql, [tuple(r) for r in records])
        return len(df_insert)
    except Exception as e:
        logger.error(f"Error inserting {parquet_file.stem}: {e}")
        return 0


async def main(batch_size: int = 10, move_after_load: bool = True):
    """Load all Parquet files to database."""
    
    LOADED_DIR.mkdir(parents=True, exist_ok=True)
    loaded = load_progress()
    
    conn = await asyncpg.connect(DB_URL)
    
    logger.info("=" * 80)
    logger.info("STAGE 3: DATABASE LOAD")
    logger.info("=" * 80)
    
    # Find all Parquet files
    parquet_files = [f for f in PARQUET_DIR.glob('*.parquet') if f.stem not in loaded]
    
    logger.info(f"Found {len(parquet_files)} Parquet files to load (skipping {len(loaded)} already done)")
    
    total_rows = 0
    total_files = 0
    start_time = datetime.now()
    
    for i, pq_file in enumerate(parquet_files):
        try:
            rows = await load_parquet_to_db(conn, pq_file)
            
            if rows > 0:
                total_rows += rows
                total_files += 1
                loaded.add(pq_file.stem)
                
                # Move file to loaded directory
                if move_after_load:
                    pq_file.rename(LOADED_DIR / pq_file.name)
                
                logger.info(f"  {pq_file.stem}: Loaded {rows} rows")
            
            # Save progress periodically
            if (i + 1) % batch_size == 0:
                save_progress(loaded)
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = total_files / elapsed if elapsed > 0 else 0
                logger.info(f"Progress: {i+1}/{len(parquet_files)} | Rows: {total_rows:,} | Rate: {rate:.1f} files/s")
                
        except Exception as e:
            logger.error(f"Error processing {pq_file.name}: {e}")
    
    save_progress(loaded)
    await conn.close()
    
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 3 COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Files loaded: {total_files}")
    logger.info(f"Total rows: {total_rows:,}")
    logger.info(f"Time: {elapsed/60:.1f} minutes")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Stage 3: Load Parquet to Database')
    parser.add_argument('--batch-size', type=int, default=10, help='Progress save interval (default: 10)')
    parser.add_argument('--no-move', action='store_true', help='Keep Parquet files after loading (default: move to loaded/)')
    
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args.batch_size, not args.no_move))
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
