"""
Recompute VWAP for all data in database
VWAP now resets daily instead of being cumulative
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from loguru import logger
from app.services.indicator_computation import IndicatorComputationService

DB_PATH = "keepgaining.db"

def recompute_vwap():
    """Recompute VWAP for all symbols in database"""
    conn = sqlite3.connect(DB_PATH)
    
    # Get all unique symbols
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT symbol FROM candle_data ORDER BY symbol")
    symbols = [row[0] for row in cursor.fetchall()]
    
    logger.info(f"Found {len(symbols)} symbols to update")
    
    for idx, symbol in enumerate(symbols, 1):
        logger.info(f"[{idx}/{len(symbols)}] Updating {symbol}...")
        
        # Load data for this symbol
        df = pd.read_sql_query(
            "SELECT * FROM candle_data WHERE symbol = ? ORDER BY timestamp",
            conn,
            params=(symbol,)
        )
        
        if len(df) == 0:
            continue
        
        # Recompute VWAP (now with daily reset)
        df['vwap'] = IndicatorComputationService._compute_vwap(
            df['high'], df['low'], df['close'], df['volume'], df['timestamp']
        )
        
        # Update database
        for _, row in df.iterrows():
            cursor.execute(
                "UPDATE candle_data SET vwap = ? WHERE id = ?",
                (row['vwap'], row['id'])
            )
        
        conn.commit()
        logger.success(f"  ✓ Updated {len(df):,} rows")
    
    conn.close()
    logger.success(f"\n✓ VWAP recomputed for all {len(symbols)} symbols!")

if __name__ == "__main__":
    logger.info("="*80)
    logger.info("RECOMPUTING VWAP WITH DAILY RESET")
    logger.info("="*80)
    recompute_vwap()
