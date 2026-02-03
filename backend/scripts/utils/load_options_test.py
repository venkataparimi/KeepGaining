"""
Load Options Data into Database - Single Stock Test
Tests loading SBIN options data with all fields
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
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_options_symbol 
        ON options_data(symbol)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_options_underlying 
        ON options_data(underlying)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_options_timestamp 
        ON options_data(timestamp)
    """)
    
    conn.commit()
    conn.close()
    logger.success("Options table created/verified")

def load_single_stock(stock_name):
    """Load options data for a single stock"""
    csv_file = OPTIONS_DIR / f"{stock_name}_25NOV.csv"
    
    if not csv_file.exists():
        logger.error(f"File not found: {csv_file}")
        return False
    
    logger.info(f"Loading {stock_name} options data...")
    
    # Read CSV
    df = pd.read_csv(csv_file)
    logger.info(f"  Read {len(df):,} rows from CSV")
    
    # Prepare data for insertion
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Select only the columns we need
    columns = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 
               'volume', 'oi', 'underlying', 'strike', 'option_type', 'expiry']
    
    # Check which columns exist
    available_cols = [col for col in columns if col in df.columns]
    logger.info(f"  Available columns: {available_cols}")
    
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
    
    try:
        cursor.executemany(insert_query, insert_data)
        conn.commit()
        logger.success(f"✓ Inserted {len(insert_data):,} rows for {stock_name}")
        
        # Verify insertion
        cursor.execute("""
            SELECT COUNT(*), COUNT(DISTINCT symbol) 
            FROM options_data 
            WHERE underlying = ?
        """, (stock_name,))
        
        total_rows, unique_options = cursor.fetchone()
        logger.success(f"✓ Verified: {total_rows:,} rows, {unique_options} unique options")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Error inserting data: {e}")
        conn.close()
        return False

def main():
    logger.info("="*80)
    logger.info("LOADING OPTIONS DATA - SINGLE STOCK TEST (SBIN)")
    logger.info("="*80)
    
    # Create table
    create_options_table()
    
    # Load SBIN data
    success = load_single_stock("SBIN")
    
    if success:
        logger.info("\n" + "="*80)
        logger.success("TEST SUCCESSFUL! Ready to load all stocks.")
        logger.info("="*80)
    else:
        logger.error("\n" + "="*80)
        logger.error("TEST FAILED! Check errors above.")
        logger.info("="*80)

if __name__ == "__main__":
    main()
