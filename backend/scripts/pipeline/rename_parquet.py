"""
Rename Parquet files from GUID names to stock symbol names.
Also reports the timestamp range of each file.
"""
import pandas as pd
from pathlib import Path
import asyncio
import asyncpg

PARQUET_DIR = Path(__file__).parent.parent / 'data' / 'indicators'
DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


async def get_symbol_mapping():
    """Get mapping of instrument_id to trading_symbol from database."""
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch("""
        SELECT instrument_id::text, trading_symbol 
        FROM instrument_master 
        WHERE instrument_type = 'EQUITY'
    """)
    await conn.close()
    return {r['instrument_id']: r['trading_symbol'] for r in rows}


def rename_parquet_files():
    """Rename all GUID-named parquet files to use stock symbols."""
    parquet_files = list(PARQUET_DIR.glob('*.parquet'))
    
    print(f"Found {len(parquet_files)} parquet files")
    
    # Get symbol mapping
    symbol_map = asyncio.run(get_symbol_mapping())
    print(f"Loaded {len(symbol_map)} symbol mappings from database")
    
    renamed = 0
    skipped = 0
    timestamp_ranges = []
    
    for pq_file in parquet_files:
        # Check if it's a GUID name (36 chars with hyphens) or already named
        if '_indicators_' in pq_file.stem:
            print(f"  Skipping {pq_file.name} (already named)")
            skipped += 1
            continue
        
        # Try to find the instrument_id in the file
        try:
            df = pd.read_parquet(pq_file)
            
            if 'instrument_id' in df.columns:
                inst_id = df['instrument_id'].iloc[0]
                symbol = symbol_map.get(inst_id, None)
                
                if symbol:
                    # Get timestamp range
                    min_ts = df['timestamp'].min()
                    max_ts = df['timestamp'].max()
                    timestamp_ranges.append((symbol, min_ts, max_ts, len(df)))
                    
                    # Rename the file
                    timeframe = df['timeframe'].iloc[0] if 'timeframe' in df.columns else '1m'
                    safe_symbol = symbol.replace('&', '_').replace(' ', '_').replace('-', '_')
                    new_name = f"{safe_symbol}_indicators_{timeframe}.parquet"
                    new_path = PARQUET_DIR / new_name
                    
                    pq_file.rename(new_path)
                    print(f"  {pq_file.name} -> {new_name}")
                    renamed += 1
                else:
                    print(f"  {pq_file.name}: Symbol not found for {inst_id}")
            else:
                print(f"  {pq_file.name}: No instrument_id column")
                
        except Exception as e:
            print(f"  Error processing {pq_file.name}: {e}")
    
    print(f"\n{'='*60}")
    print(f"Renamed: {renamed}")
    print(f"Skipped: {skipped}")
    
    # Print timestamp range summary
    if timestamp_ranges:
        print(f"\n{'='*60}")
        print("TIMESTAMP RANGES:")
        print(f"{'='*60}")
        
        # Sort by min timestamp
        timestamp_ranges.sort(key=lambda x: x[1])
        
        # Show first and last few
        print("\nFirst 5 (oldest data):")
        for sym, min_ts, max_ts, rows in timestamp_ranges[:5]:
            print(f"  {sym}: {min_ts} to {max_ts} ({rows:,} rows)")
        
        print("\nLast 5 (newest data):")
        for sym, min_ts, max_ts, rows in timestamp_ranges[-5:]:
            print(f"  {sym}: {min_ts} to {max_ts} ({rows:,} rows)")
        
        # Overall range
        all_min = min(r[1] for r in timestamp_ranges)
        all_max = max(r[2] for r in timestamp_ranges)
        print(f"\n{'='*60}")
        print(f"OVERALL DATA RANGE:")
        print(f"  EARLIEST: {all_min}")
        print(f"  LATEST:   {all_max}")


if __name__ == '__main__':
    rename_parquet_files()
