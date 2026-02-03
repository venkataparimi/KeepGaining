"""
Check database schema
"""
import sqlite3

DB_PATH = "keepgaining.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check if table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='candle_data'")
result = cursor.fetchone()

if result:
    print("Table 'candle_data' exists")
    
    # Get column info
    cursor.execute("PRAGMA table_info(candle_data)")
    columns = cursor.fetchall()
    
    print(f"\nTable has {len(columns)} columns:")
    for col in columns[:20]:  # Show first 20
        print(f"  {col[1]} ({col[2]}){' NOT NULL' if col[3] else ''}{' PK' if col[5] else ''}")
    
    if len(columns) > 20:
        print(f"  ... and {len(columns) - 20} more columns")
else:
    print("Table 'candle_data' does NOT exist!")
    print("\nAvailable tables:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    for row in cursor.fetchall():
        print(f"  - {row[0]}")

conn.close()
