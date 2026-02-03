"""
Load ALL Options Data into Database
Loads all downloaded options CSV files into the options_data table
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from loguru import logger

DB_PATH = "keepgaining.db"
OPTIONS_DIR = Path("options_data")

def create_options_table():
    """Create options_data table if it doesn't exist"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS options_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            oi INTEGER,
            underlying TEXT NOT NULL,
            strike REAL NOT NULL,
            option_type TEXT NOT NULL,
            expiry TEXT NOT NULL,
            UNIQUE(symbol, timestamp)
        )
    """)
    
    # Create indexes for faster queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_options_symbol ON options_data(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_options_underlying ON options_data(underlying)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_options_timestamp ON options_data(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_options_expiry ON options_data(expiry)")
    
    conn.commit()
    conn.close()
    logger.success("Options table created/verified with indexes")

def load_stock_options(csv_file):
    """Load options data for a single stock"""
    stock_name = csv_file.stem.replace('_25NOV', '')
    
    try:
        # Read CSV
        df = pd.read_csv(csv_file)
        
        # Prepare data
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Select columns
        columns = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 
                   'volume', 'oi', 'underlying', 'strike', 'option_type', 'expiry']
        available_cols = [col for col in columns if col in df.columns]
        
        insert_data = df[available_cols].values.tolist()
        
        # Insert into database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        placeholders = ','.join(['?' for _ in available_cols])
        insert_query = f"""
            INSERT OR REPLACE INTO options_data 
            ({','.join(available_cols)}) 
            VALUES ({placeholders})
        """
        
        cursor.executemany(insert_query, insert_data)
        conn.commit()
        
        # Get stats
        unique_options = df['symbol'].nunique()
        
        conn.close()
        
        logger.success(f"✓ {stock_name:15} | {unique_options:3} options | {len(insert_data):8,} candles")
        return len(insert_data), unique_options
        
    except Exception as e:
        logger.error(f"✗ {stock_name:15} | Error: {e}")
        return 0, 0

def main():
    logger.info("="*80)
    logger.info("LOADING ALL OPTIONS DATA INTO DATABASE")
    logger.info("="*80)
    
    # Create table
    create_options_table()
    
    # Get all CSV files
    csv_files = sorted(OPTIONS_DIR.glob("*_25NOV.csv"))
    
    if not csv_files:
        logger.error("No options CSV files found!")
        return
    
    logger.info(f"\nFound {len(csv_files)} stock option files\n")
    
    total_candles = 0
    total_options = 0
    successful = 0
    
    for idx, csv_file in enumerate(csv_files, 1):
        logger.info(f"[{idx}/{len(csv_files)}] ", end="")
        candles, options = load_stock_options(csv_file)
        
        if candles > 0:
            total_candles += candles
            total_options += options
            successful += 1
    
    # Final verification
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM options_data")
    db_total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT underlying) FROM options_data")
    db_stocks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT symbol) FROM options_data")
    db_options = cursor.fetchone()[0]
    
    conn.close()
    
    logger.info("\n" + "="*80)
    logger.info("SUMMARY")
    logger.info("="*80)
    logger.success(f"Loaded:           {successful}/{len(csv_files)} stocks")
    logger.success(f"Total candles:    {total_candles:,}")
    logger.success(f"Total options:    {total_options:,}")
    logger.info("\n" + "="*80)
    logger.info("DATABASE VERIFICATION")
    logger.info("="*80)
    logger.success(f"DB total rows:    {db_total:,}")
    logger.success(f"DB stocks:        {db_stocks}")
    logger.success(f"DB unique opts:   {db_options:,}")
    logger.info("="*80)
    
    if db_total == total_candles:
        logger.success("\n✓ ALL DATA LOADED SUCCESSFULLY!")
    else:
        logger.warning(f"\n⚠ Mismatch: Loaded {total_candles:,} but DB has {db_total:,}")

if __name__ == "__main__":
    main()
