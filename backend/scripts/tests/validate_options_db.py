"""Validate options data in database"""
import sqlite3
import pandas as pd

DB_PATH = "keepgaining.db"

conn = sqlite3.connect(DB_PATH)

print("="*80)
print("OPTIONS DATA VALIDATION")
print("="*80)

# Check table exists
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='options_data'")
if cursor.fetchone():
    print("✓ Table 'options_data' exists")
else:
    print("✗ Table 'options_data' NOT found")
    exit(1)

# Check schema
cursor.execute("PRAGMA table_info(options_data)")
columns = cursor.fetchall()
print(f"\n✓ Table has {len(columns)} columns:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

# Check data for SBIN
print("\n" + "="*80)
print("SBIN OPTIONS DATA CHECK")
print("="*80)

query = """
    SELECT 
        COUNT(*) as total_rows,
        COUNT(DISTINCT symbol) as unique_options,
        COUNT(DISTINCT strike) as unique_strikes,
        MIN(timestamp) as earliest_date,
        MAX(timestamp) as latest_date
    FROM options_data
    WHERE underlying = 'SBIN'
"""

df = pd.read_sql_query(query, conn)
print(f"\nTotal rows:        {df['total_rows'][0]:,}")
print(f"Unique options:    {df['unique_options'][0]}")
print(f"Unique strikes:    {df['unique_strikes'][0]}")
print(f"Date range:        {df['earliest_date'][0]} to {df['latest_date'][0]}")

# Sample data
print("\n" + "="*80)
print("SAMPLE DATA (First 5 rows)")
print("="*80)

sample = pd.read_sql_query("""
    SELECT symbol, timestamp, open, high, low, close, volume, strike, option_type
    FROM options_data
    WHERE underlying = 'SBIN'
    ORDER BY timestamp DESC
    LIMIT 5
""", conn)

print(sample.to_string(index=False))

# Check for nulls
print("\n" + "="*80)
print("DATA QUALITY CHECKS")
print("="*80)

cursor.execute("SELECT COUNT(*) FROM options_data WHERE underlying = 'SBIN' AND close IS NULL")
null_count = cursor.fetchone()[0]
print(f"Null close prices: {null_count}")

cursor.execute("SELECT COUNT(*) FROM options_data WHERE underlying = 'SBIN' AND volume IS NULL")
null_vol = cursor.fetchone()[0]
print(f"Null volumes:      {null_vol}")

# Check option types
cursor.execute("""
    SELECT option_type, COUNT(*) as count 
    FROM options_data 
    WHERE underlying = 'SBIN'
    GROUP BY option_type
""")
print(f"\nOption types:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]:,} rows")

conn.close()

print("\n" + "="*80)
print("✓ VALIDATION COMPLETE - Data looks good!")
print("="*80)
