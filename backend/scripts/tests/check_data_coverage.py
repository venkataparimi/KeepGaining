"""Check data coverage for all F&O stocks"""
import sqlite3
import pandas as pd

DB_PATH = "keepgaining.db"

conn = sqlite3.connect(DB_PATH)

# Get last date for each symbol
query = """
    SELECT 
        symbol,
        MIN(timestamp) as first_date,
        MAX(timestamp) as last_date,
        COUNT(*) as candle_count
    FROM candle_data
    GROUP BY symbol
    ORDER BY last_date DESC, symbol
"""

df = pd.read_sql_query(query, conn)
conn.close()

print("="*80)
print("DATA COVERAGE CHECK")
print("="*80)

# Convert to datetime
df['first_date'] = pd.to_datetime(df['first_date'])
df['last_date'] = pd.to_datetime(df['last_date'])

# Check which stocks have data till Nov 25 end
nov_25_end = pd.to_datetime('2025-11-25 23:59:59')
today = pd.to_datetime('2025-11-26')

print(f"\nTotal stocks: {len(df)}")
print(f"\nLast date distribution:")

# Group by last date
last_dates = df['last_date'].dt.date.value_counts().sort_index(ascending=False)
for date, count in last_dates.head(10).items():
    print(f"  {date}: {count} stocks")

# Stocks missing Nov 25 data
missing_nov25 = df[df['last_date'] < nov_25_end]
if len(missing_nov25) > 0:
    print(f"\n⚠️  Stocks missing Nov 25 data: {len(missing_nov25)}")
    print("\nTop 20 stocks with oldest data:")
    print(missing_nov25[['symbol', 'last_date', 'candle_count']].head(20).to_string(index=False))
else:
    print(f"\n✓ All stocks have data through Nov 25!")

# Show sample of latest stocks
print(f"\n✓ Stocks with latest data:")
print(df[['symbol', 'last_date', 'candle_count']].head(10).to_string(index=False))

print("\n" + "="*80)
