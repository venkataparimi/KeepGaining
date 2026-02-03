"""
Inspect Data Quality
Investigate the specific 'crash' trade to identify data issues.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from loguru import logger

OPTIONS_DIR = Path("options_data")

def inspect_data(stock, strike, option_type, target_time):
    logger.info(f"INSPECTING RAW DATA: {stock} {strike}{option_type} around {target_time}")
    
    # Load Options Data
    options_file = OPTIONS_DIR / "25NOV" / f"{stock}.csv"
    if not options_file.exists():
        options_file = OPTIONS_DIR / f"{stock}_25NOV.csv"
    
    df = pd.read_csv(options_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    symbol = f"NSE:{stock}25NOV{strike}{option_type}"
    df = df[df['symbol'] == symbol]
    
    # Filter for the specific day
    target_dt = pd.to_datetime(target_time)
    day_df = df[df['timestamp'].dt.date == target_dt.date()]
    
    print(f"Searching for Close price around 10.30 in {len(day_df)} rows...")
    matches = day_df[(day_df['close'] >= 10.0) & (day_df['close'] <= 10.60)]
    if not matches.empty:
        print("Found matches:")
        print(matches.to_string(index=False))
    else:
        print("No matches found for 10.30")
        
    # Also check CE just in case
    ce_symbol = f"NSE:{stock}25NOV{strike}CE"
    ce_df = pd.read_csv(options_file)
    ce_df['timestamp'] = pd.to_datetime(ce_df['timestamp'])
    ce_df = ce_df[ce_df['symbol'] == ce_symbol]
    ce_matches = ce_df[(ce_df['close'] >= 10.0) & (ce_df['close'] <= 10.60) & (ce_df['timestamp'].dt.date == target_dt.date())]
    if not ce_matches.empty:
        print("\nFound matches in CE:")
        print(ce_matches.to_string(index=False))

# Inspect the crash trade: 18th Nov 15:21, PE 5600
inspect_data("HEROMOTOCO", 5600, "PE", "2025-11-18 15:21:00")
