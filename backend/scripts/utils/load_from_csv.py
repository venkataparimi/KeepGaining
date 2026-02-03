"""
Load CSV files into database using raw SQL
Avoids all SQLAlchemy async issues
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import sqlite3
from loguru import logger

DATA_DIR = Path("data_downloads")
DB_PATH = "keepgaining.db"


def load_csv_to_db(csv_file: Path, conn):
    """Load one CSV file using raw SQL"""
    logger.info(f"Loading {csv_file.name}...")
    
    df = pd.read_csv(csv_file)
    
    # Convert timestamp to string for SQLite
    df['timestamp'] = pd.to_datetime(df['timestamp']).astype(str)
    
    # Insert using raw SQL
    count = 0
    cursor = conn.cursor()
    
    for _, row in df.iterrows():
        try:
            cursor.execute("""
                INSERT INTO candle_data (
                    symbol, timeframe, timestamp,
                    open, high, low, close, volume,
                    sma_20, sma_50, ema_9, ema_21, vwma_20
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row['symbol'],
                row['timeframe'],
                row['timestamp'],
                row['open'],
                row['high'],
                row['low'],
                row['close'],
                row['volume'],
                row.get('sma_20'),
                row.get('sma_50'),
                row.get('ema_9'),
                row.get('ema_21'),
                row.get('vwma_20'),
            ))
            count += 1
            
            if count % 5000 == 0:
                conn.commit()
                logger.info(f"  Committed {count} candles...")
                
        except Exception as e:
            if "UNIQUE constraint" not in str(e):
                logger.error(f"Error inserting row: {e}")
    
    conn.commit()
    logger.success(f"✓ Loaded {count} candles from {csv_file.name}")
    return count


def main():
    """Load all CSV files"""
    if not DATA_DIR.exists():
        logger.error(f"Directory {DATA_DIR} not found!")
        return
    
    # Connect to SQLite
    conn = sqlite3.connect(DB_PATH)
    
    csv_files = list(DATA_DIR.glob("*.csv"))
    logger.info(f"Found {len(csv_files)} CSV files")
    
    total = 0
    success = 0
    
    for csv_file in csv_files:
        try:
            count = load_csv_to_db(csv_file, conn)
            total += count
            success += 1
        except Exception as e:
            logger.error(f"Error loading {csv_file.name}: {e}")
    
    conn.close()
    
    logger.success(f"\n✓ Loaded {success}/{len(csv_files)} files")
    logger.success(f"✓ Total: {total:,} candles in database")


if __name__ == "__main__":
    main()
