"""
Check database contents
"""
import sqlite3
from pathlib import Path

DB_PATH = "keepgaining.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Total candles
cursor.execute("SELECT COUNT(*) FROM candle_data")
total = cursor.fetchone()[0]
print(f"\nTotal candles in database: {total:,}")

# Count by symbol
cursor.execute("""
    SELECT symbol, COUNT(*) as count 
    FROM candle_data 
    GROUP BY symbol 
    ORDER BY symbol
    LIMIT 10
""")

print("\nSample symbols:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]:,} candles")

# Check if indicators are populated
cursor.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(sma_20) as has_sma,
        COUNT(ema_9) as has_ema,
        COUNT(rsi_14) as has_rsi,
        COUNT(macd) as has_macd,
        COUNT(vwma_20) as has_vwma
    FROM candle_data
""")

row = cursor.fetchone()
print(f"\nIndicator coverage:")
print(f"  Total candles: {row[0]:,}")
print(f"  With SMA-20: {row[1]:,}")
print(f"  With EMA-9: {row[2]:,}")
print(f"  With RSI-14: {row[3]:,}")
print(f"  With MACD: {row[4]:,}")
print(f"  With VWMA-20: {row[5]:,}")

conn.close()
