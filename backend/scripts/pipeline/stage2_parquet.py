"""
Stage 2: Convert Computed Indicators to Parquet
Watches the computed/ directory for new .pkl files and converts them to Parquet.
"""
import pickle
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from datetime import datetime
import logging
import argparse
import time
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

COMPUTED_DIR = Path(__file__).parent.parent / 'data' / 'computed'
PARQUET_DIR = Path(__file__).parent.parent / 'data' / 'indicators'
PROGRESS_FILE = Path(__file__).parent.parent / 'data' / 'parquet_progress.json'


def load_progress() -> set:
    """Load set of already processed instrument IDs."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return set(json.load(f).get('processed', []))
    return set()


def save_progress(processed: set):
    """Save progress."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({'processed': list(processed), 'updated_at': datetime.now().isoformat()}, f)


def convert_to_parquet(pkl_file: Path) -> bool:
    """Convert a single .pkl file to Parquet."""
    try:
        with open(pkl_file, 'rb') as f:
            data = pickle.load(f)
        
        # Extract metadata
        instrument_id = data.pop('instrument_id')
        trading_symbol = data.pop('trading_symbol')
        timeframe = data.pop('timeframe')
        computed_at = data.pop('computed_at')
        candle_count = data.pop('candle_count')
        
        # Convert timestamps to proper datetime
        timestamps = data.pop('timestamp')
        
        # Build DataFrame
        df = pd.DataFrame({
            'timestamp': timestamps,
            'instrument_id': instrument_id,
            'timeframe': timeframe,
        })
        
        # Add all indicator columns
        for col_name, col_data in data.items():
            if isinstance(col_data, np.ndarray):
                df[col_name] = col_data
            else:
                df[col_name] = col_data
        
        # Write to Parquet with compression - use symbol name for readability
        # Clean the symbol name (remove special chars that could cause issues)
        safe_symbol = trading_symbol.replace('&', '_').replace(' ', '_').replace('-', '_')
        output_file = PARQUET_DIR / f"{safe_symbol}_indicators_{timeframe}.parquet"
        df.to_parquet(output_file, engine='pyarrow', compression='snappy', index=False)
        
        logger.info(f"  {trading_symbol}: {len(df)} rows -> {output_file.name}")
        
        # Delete the .pkl file after successful conversion
        pkl_file.unlink()
        
        return True
        
    except Exception as e:
        logger.error(f"Error converting {pkl_file.name}: {e}")
        return False


def process_batch(watch: bool = False, interval: int = 5):
    """Process all pending .pkl files."""
    
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    processed = load_progress()
    
    logger.info("=" * 80)
    logger.info("STAGE 2: PARQUET CONVERSION")
    logger.info("=" * 80)
    
    total_converted = 0
    total_failed = 0
    
    while True:
        # Find all .pkl files
        pkl_files = list(COMPUTED_DIR.glob('*.pkl'))
        
        if not pkl_files:
            if watch:
                logger.info(f"No pending files. Waiting {interval}s...")
                time.sleep(interval)
                continue
            else:
                break
        
        logger.info(f"Found {len(pkl_files)} files to convert")
        
        for pkl_file in pkl_files:
            inst_id = pkl_file.stem
            
            if inst_id in processed:
                logger.info(f"  Skipping {inst_id} (already processed)")
                pkl_file.unlink()  # Clean up duplicate
                continue
            
            if convert_to_parquet(pkl_file):
                processed.add(inst_id)
                total_converted += 1
            else:
                total_failed += 1
            
            # Save progress periodically
            if total_converted % 10 == 0:
                save_progress(processed)
        
        save_progress(processed)
        
        if not watch:
            break
    
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 2 COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Converted: {total_converted}")
    logger.info(f"Failed: {total_failed}")
    logger.info(f"Output directory: {PARQUET_DIR}")


if __name__ == '__main__':
    import numpy as np  # Import here for pickle loading
    
    parser = argparse.ArgumentParser(description='Stage 2: Convert to Parquet')
    parser.add_argument('--watch', action='store_true', help='Watch mode - continuously monitor for new files')
    parser.add_argument('--interval', type=int, default=5, help='Watch interval in seconds (default: 5)')
    
    args = parser.parse_args()
    
    try:
        process_batch(args.watch, args.interval)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
