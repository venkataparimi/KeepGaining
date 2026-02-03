import pandas as pd
from pathlib import Path

files = ['SBIN_25NOV.csv', 'RELIANCE_25NOV.csv', 'ICICIBANK_25NOV.csv', 'ITC_25NOV.csv']
total = 0

for f in files:
    df = pd.read_csv(f'options_data/{f}')
    print(f'{f}: {len(df):,} candles')
    total += len(df)

print(f'\nTotal: {total:,} candles across 4 stocks')
