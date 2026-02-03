"""
Stage 3: Optimized Parallel Load of Parquet Files to Database
Uses connection pool + parallel workers + COPY protocol for max throughput.
"""
import asyncio
import asyncpg
import pandas as pd
from pathlib import Path
from datetime import datetime
import logging
import argparse
import json
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'
PARQUET_DIR = Path(__file__).parent.parent / 'data' / 'indicators'
LOADED_DIR = Path(__file__).parent.parent / 'data' / 'loaded'
PROGRESS_FILE = Path(__file__).parent.parent / 'data' / 'db_load_progress.json'

# Number of parallel workers
NUM_WORKERS = 16

# Columns to load into database
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
    """Load set of already loaded file stems."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return set(json.load(f).get('loaded', []))
    return set()


def save_progress(loaded: set):
    """Save progress."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({'loaded': list(loaded), 'updated_at': datetime.now().isoformat()}, f)


def read_parquet_file(parquet_file: Path):
    """Read parquet file in thread pool (I/O bound)."""
    try:
        df = pd.read_parquet(parquet_file)
        return parquet_file, df
    except Exception as e:
        logger.error(f"Error reading {parquet_file.name}: {e}")
        return parquet_file, None


async def load_df_to_db(pool: asyncpg.Pool, parquet_file: Path, df: pd.DataFrame) -> int:
    """Load a DataFrame into the database using COPY protocol."""
    if df is None or len(df) == 0:
        return 0
    
    instrument_id = df['instrument_id'].iloc[0]
    
    # Prepare columns
    available_cols = [c for c in DB_COLUMNS if c in df.columns]
    df_insert = df[available_cols].copy()
    
    # Handle NaN -> None
    df_insert = df_insert.replace({np.nan: None})
    
    # Convert supertrend_direction to int
    if 'supertrend_direction' in df_insert.columns:
        df_insert['supertrend_direction'] = df_insert['supertrend_direction'].apply(
            lambda x: int(x) if x is not None else None
        )
    
    if len(df_insert) == 0:
        return 0
    
    # Convert to records
    records = [tuple(r) for r in df_insert.to_records(index=False)]
    
    async with pool.acquire() as conn:
        try:
            # Use COPY for bulk insert (much faster than executemany)
            # First create temp table - handle both UUID and string instrument_id
            inst_id_str = str(instrument_id).replace('-', '')[:8]
            temp_table = f"temp_ind_{inst_id_str}"
            
            await conn.execute(f"""
                CREATE TEMP TABLE IF NOT EXISTS {temp_table} (
                    instrument_id UUID,
                    timeframe VARCHAR(10),
                    timestamp TIMESTAMPTZ,
                    sma_9 DOUBLE PRECISION, sma_20 DOUBLE PRECISION, sma_50 DOUBLE PRECISION, sma_200 DOUBLE PRECISION,
                    ema_9 DOUBLE PRECISION, ema_21 DOUBLE PRECISION, ema_50 DOUBLE PRECISION, ema_200 DOUBLE PRECISION,
                    vwap DOUBLE PRECISION, rsi_14 DOUBLE PRECISION,
                    macd DOUBLE PRECISION, macd_signal DOUBLE PRECISION, macd_histogram DOUBLE PRECISION,
                    atr_14 DOUBLE PRECISION, bb_upper DOUBLE PRECISION, bb_middle DOUBLE PRECISION, bb_lower DOUBLE PRECISION,
                    adx DOUBLE PRECISION, plus_di DOUBLE PRECISION, minus_di DOUBLE PRECISION,
                    supertrend DOUBLE PRECISION, supertrend_direction INTEGER,
                    obv DOUBLE PRECISION, volume_sma_20 DOUBLE PRECISION,
                    pivot_point DOUBLE PRECISION, pivot_r1 DOUBLE PRECISION, pivot_r2 DOUBLE PRECISION, 
                    pivot_s1 DOUBLE PRECISION, pivot_s2 DOUBLE PRECISION,
                    fib_r1 DOUBLE PRECISION, fib_r2 DOUBLE PRECISION, fib_s1 DOUBLE PRECISION, fib_s2 DOUBLE PRECISION
                )
            """)
            
            await conn.execute(f"TRUNCATE {temp_table}")
            
            # COPY records to temp table
            await conn.copy_records_to_table(
                temp_table,
                records=records,
                columns=available_cols
            )
            
            # Insert from temp table with ON CONFLICT
            result = await conn.execute(f"""
                INSERT INTO indicator_data ({', '.join(available_cols)})
                SELECT {', '.join(available_cols)} FROM {temp_table}
                ON CONFLICT (instrument_id, timeframe, timestamp) DO NOTHING
            """)
            
            await conn.execute(f"DROP TABLE {temp_table}")
            
            count = int(result.split()[-1]) if result else len(records)
            return count
            
        except Exception as e:
            logger.error(f"Error inserting {parquet_file.stem}: {e}")
            return 0


async def worker(
    worker_id: int,
    queue: asyncio.Queue,
    pool: asyncpg.Pool,
    loaded: set,
    stats: dict,
    executor: ThreadPoolExecutor
):
    """Worker that processes parquet files from queue."""
    loop = asyncio.get_event_loop()
    
    while True:
        parquet_file = await queue.get()
        if parquet_file is None:  # Poison pill
            queue.task_done()
            break
        
        try:
            # Read file in thread pool (I/O bound)
            _, df = await loop.run_in_executor(executor, read_parquet_file, parquet_file)
            
            if df is not None and len(df) > 0:
                # Load to DB
                rows = await load_df_to_db(pool, parquet_file, df)
                
                if rows > 0:
                    stats['rows'] += rows
                    stats['files'] += 1
                    loaded.add(parquet_file.stem)
                    
                    # Move file
                    try:
                        parquet_file.rename(LOADED_DIR / parquet_file.name)
                    except:
                        pass
            
            stats['processed'] += 1
            
        except Exception as e:
            logger.error(f"Worker {worker_id} error on {parquet_file.name}: {e}")
            stats['errors'] += 1
        
        queue.task_done()


async def main(num_workers: int = NUM_WORKERS):
    """Load all Parquet files to database with parallel workers."""
    
    LOADED_DIR.mkdir(parents=True, exist_ok=True)
    loaded = load_progress()
    
    logger.info("=" * 80)
    logger.info(f"STAGE 3: OPTIMIZED DATABASE LOAD ({num_workers} workers)")
    logger.info("=" * 80)
    
    # Find files to process
    parquet_files = [f for f in PARQUET_DIR.glob('*.parquet') if f.stem not in loaded]
    total_files = len(parquet_files)
    
    logger.info(f"Found {total_files} Parquet files to load (skipping {len(loaded)} already done)")
    
    if total_files == 0:
        logger.info("Nothing to load!")
        return
    
    # Create connection pool
    pool = await asyncpg.create_pool(
        DB_URL, 
        min_size=num_workers, 
        max_size=num_workers + 4,
        command_timeout=120
    )
    
    # Create queue and stats
    queue = asyncio.Queue(maxsize=num_workers * 2)
    stats = {'rows': 0, 'files': 0, 'processed': 0, 'errors': 0}
    start_time = datetime.now()
    
    # Thread pool for reading parquet files
    executor = ThreadPoolExecutor(max_workers=num_workers)
    
    # Start workers
    workers = [
        asyncio.create_task(worker(i, queue, pool, loaded, stats, executor))
        for i in range(num_workers)
    ]
    
    # Progress reporter
    async def report_progress():
        last_files = 0
        while stats['processed'] < total_files:
            await asyncio.sleep(10)
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = stats['files'] / elapsed if elapsed > 0 else 0
            remaining = total_files - stats['processed']
            eta_min = remaining / rate / 60 if rate > 0 else 0
            logger.info(
                f"Progress: {stats['processed']}/{total_files} | "
                f"Loaded: {stats['files']} | "
                f"Rows: {stats['rows']:,} | "
                f"Rate: {rate:.1f}/s | "
                f"ETA: {eta_min:.0f}min"
            )
            
            # Save progress every 30 seconds
            if stats['files'] - last_files >= 100:
                save_progress(loaded)
                last_files = stats['files']
    
    progress_task = asyncio.create_task(report_progress())
    
    # Feed files to queue
    for pf in parquet_files:
        await queue.put(pf)
    
    # Send poison pills to stop workers
    for _ in range(num_workers):
        await queue.put(None)
    
    # Wait for all workers to finish
    await asyncio.gather(*workers)
    progress_task.cancel()
    
    # Cleanup
    executor.shutdown(wait=False)
    save_progress(loaded)
    await pool.close()
    
    elapsed = (datetime.now() - start_time).total_seconds()
    final_rate = stats['files'] / elapsed if elapsed > 0 else 0
    
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 3 COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Files loaded: {stats['files']}")
    logger.info(f"Total rows: {stats['rows']:,}")
    logger.info(f"Errors: {stats['errors']}")
    logger.info(f"Time: {elapsed/60:.1f} minutes")
    logger.info(f"Average rate: {final_rate:.1f} files/s")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Stage 3: Optimized Parallel DB Load')
    parser.add_argument('--workers', type=int, default=NUM_WORKERS, help=f'Number of parallel workers (default: {NUM_WORKERS})')
    
    args = parser.parse_args()
    
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main(args.workers))
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
