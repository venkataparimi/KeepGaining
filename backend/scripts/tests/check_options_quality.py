"""Check quality of downloaded options data"""
import pandas as pd
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("options_data")

print("="*80)
print("OPTIONS DATA QUALITY CHECK")
print("="*80)

csv_files = list(OUTPUT_DIR.glob("*_25NOV.csv"))

if not csv_files:
    print("\nNo options data files found yet.")
else:
    print(f"\nFound {len(csv_files)} stock option files\n")
    
    total_candles = 0
    total_options = 0
    issues = []
    
    for csv_file in sorted(csv_files):
        df = pd.read_csv(csv_file)
        
        stock_name = csv_file.stem.replace('_25NOV', '')
        unique_options = df['symbol'].nunique()
        candles = len(df)
        
        total_candles += candles
        total_options += unique_options
        
        print(f"{stock_name:15} | {unique_options:3} options | {candles:8,} candles")
        
        # Check for data quality issues
        if df.isnull().any().any():
            issues.append(f"{stock_name}: Has null values")
        
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            date_range = (df['timestamp'].max() - df['timestamp'].min()).days
            if date_range < 7:
                issues.append(f"{stock_name}: Only {date_range} days of data")
        
        # Check for duplicates
        if df.duplicated(subset=['timestamp', 'symbol']).any():
            dup_count = df.duplicated(subset=['timestamp', 'symbol']).sum()
            issues.append(f"{stock_name}: {dup_count} duplicate rows")
    
    print("\n" + "="*80)
    print(f"SUMMARY")
    print("="*80)
    print(f"Total stocks:        {len(csv_files)}")
    print(f"Total options:       {total_options:,}")
    print(f"Total candles:       {total_candles:,}")
    print(f"Avg candles/option:  {total_candles//total_options if total_options > 0 else 0:,}")
    
    if issues:
        print(f"\n⚠️  DATA QUALITY ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n✓ No data quality issues found!")
    
    print("="*80)
