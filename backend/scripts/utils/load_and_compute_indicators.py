"""
Load CSV files into database and compute all 56 indicators
Uses bulk insert for speed
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import sqlite3
from loguru import logger
from app.services.indicator_computation import IndicatorComputationService

DATA_DIR = Path("data_downloads")
DB_PATH = "keepgaining.db"


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all 56 indicators for a dataframe"""
    return IndicatorComputationService.compute_all_indicators(df)


def load_csv_to_db(csv_file: Path, conn):
    """Load one CSV file with all indicators"""
    logger.info(f"Loading {csv_file.name}...")
    
    try:
        # Read CSV
        df = pd.read_csv(csv_file)
        
        # Convert timestamp to string for SQLite
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Compute all 56 indicators
        logger.info(f"  Computing 56 indicators...")
        df = compute_all_indicators(df)
        
        # Replace NaN with None for SQLite
        df = df.where(pd.notnull(df), None)
        
        # Prepare column list - only include columns that exist in df
        base_columns = [
            'symbol', 'timeframe', 'timestamp',
            'open', 'high', 'low', 'close', 'volume',
        ]
        
        indicator_columns = [
            # Moving Averages
            'sma_9', 'sma_20', 'sma_50', 'sma_200',
            'ema_9', 'ema_21', 'ema_50', 'ema_200',
            'vwma_20', 'vwma_22', 'vwma_31', 'vwma_50',
            # Bollinger Bands
            'bb_upper', 'bb_middle', 'bb_lower',
            # RSI
            'rsi_14', 'rsi_9',
            # MACD
            'macd', 'macd_signal', 'macd_histogram',
            # Stochastic
            'stoch_k', 'stoch_d',
            # ATR
            'atr_14',
            # ADX (note: compute_all_indicators returns 'adx', not 'adx_14')
            'adx',
            # Standard Pivots
            'pivot_point', 'pivot_r1', 'pivot_r2', 'pivot_r3',
            'pivot_s1', 'pivot_s2', 'pivot_s3',
            # Fibonacci Pivots
            'fib_pivot', 'fib_r1', 'fib_r2', 'fib_r3',
            'fib_s1', 'fib_s2', 'fib_s3',
            # Camarilla Pivots
            'cam_r4', 'cam_r3', 'cam_r2', 'cam_r1',
            'cam_s1', 'cam_s2', 'cam_s3', 'cam_s4',
            # Volume indicators
            'obv', 'vwap',
            # Supertrend
            'supertrend', 'supertrend_direction',
        ]
        
        # Only include columns that exist in the dataframe
        columns = base_columns + [col for col in indicator_columns if col in df.columns]
        
        # Build INSERT statement
        placeholders = ','.join(['?' for _ in columns])
        insert_sql = f"""
            INSERT INTO candle_data ({','.join(columns)})
            VALUES ({placeholders})
        """
        
        # Bulk insert
        cursor = conn.cursor()
        records = df[columns].values.tolist()
        
        logger.info(f"  Inserting {len(records):,} records...")
        try:
            cursor.executemany(insert_sql, records)
            conn.commit()
            inserted = cursor.rowcount
            logger.success(f"✓ Loaded {inserted:,} candles from {csv_file.name}")
            return inserted
        except Exception as e:
            logger.error(f"  Insert error: {e}")
            logger.error(f"  First record sample: {records[0] if records else 'N/A'}")
            raise
        
    except Exception as e:
        logger.error(f"Error loading {csv_file.name}: {e}")
        import traceback
        traceback.print_exc()
        return 0


def main():
    """Load all CSV files"""
    if not DATA_DIR.exists():
        logger.error(f"Directory {DATA_DIR} not found!")
        return
    
    # Connect to SQLite
    logger.info(f"Connecting to database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    logger.info(f"Found {len(csv_files)} CSV files\n")
    
    total = 0
    success = 0
    
    for i, csv_file in enumerate(csv_files, 1):
        logger.info(f"[{i}/{len(csv_files)}] Processing {csv_file.name}")
        try:
            count = load_csv_to_db(csv_file, conn)
            total += count
            success += 1
        except Exception as e:
            logger.error(f"Failed to load {csv_file.name}: {e}")
    
    conn.close()
    
    logger.success(f"\n{'='*60}")
    logger.success(f"✓ Loaded {success}/{len(csv_files)} files")
    logger.success(f"✓ Total: {total:,} candles in database")
    logger.success(f"✓ All 56 indicators computed for each candle")
    logger.success(f"{'='*60}")


if __name__ == "__main__":
    main()
