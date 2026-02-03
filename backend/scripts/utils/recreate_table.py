"""
Recreate candle_data table with proper AUTOINCREMENT
"""
import sqlite3

DB_PATH = "keepgaining.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Drop existing table
print("Dropping existing candle_data table...")
cursor.execute("DROP TABLE IF EXISTS candle_data")

# Create new table with AUTOINCREMENT
print("Creating new candle_data table with AUTOINCREMENT...")
cursor.execute("""
CREATE TABLE candle_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp DATETIME NOT NULL,
    open FLOAT NOT NULL,
    high FLOAT NOT NULL,
    low FLOAT NOT NULL,
    close FLOAT NOT NULL,
    volume BIGINT NOT NULL,
    sma_9 FLOAT,
    sma_20 FLOAT,
    sma_50 FLOAT,
    sma_200 FLOAT,
    ema_9 FLOAT,
    ema_21 FLOAT,
    ema_50 FLOAT,
    ema_200 FLOAT,
    rsi_14 FLOAT,
    rsi_9 FLOAT,
    macd FLOAT,
    macd_signal FLOAT,
    macd_histogram FLOAT,
    stoch_k FLOAT,
    stoch_d FLOAT,
    bb_upper FLOAT,
    bb_middle FLOAT,
    bb_lower FLOAT,
    atr_14 FLOAT,
    supertrend FLOAT,
    supertrend_direction INTEGER,
    adx FLOAT,
    pivot_point FLOAT,
    pivot_r1 FLOAT,
    pivot_r2 FLOAT,
    pivot_r3 FLOAT,
    pivot_s1 FLOAT,
    pivot_s2 FLOAT,
    pivot_s3 FLOAT,
    fib_pivot FLOAT,
    fib_r1 FLOAT,
    fib_r2 FLOAT,
    fib_r3 FLOAT,
    fib_s1 FLOAT,
    fib_s2 FLOAT,
    fib_s3 FLOAT,
    cam_r4 FLOAT,
    cam_r3 FLOAT,
    cam_r2 FLOAT,
    cam_r1 FLOAT,
    cam_s1 FLOAT,
    cam_s2 FLOAT,
    cam_s3 FLOAT,
    cam_s4 FLOAT,
    vwap FLOAT,
    vwma_20 FLOAT,
    vwma_22 FLOAT,
    vwma_31 FLOAT,
    vwma_50 FLOAT,
    obv BIGINT,
    UNIQUE(symbol, timeframe, timestamp)
)
""")

# Create index for faster queries
print("Creating indexes...")
cursor.execute("CREATE INDEX idx_symbol_timeframe ON candle_data(symbol, timeframe)")
cursor.execute("CREATE INDEX idx_timestamp ON candle_data(timestamp)")

conn.commit()
conn.close()

print("\n✓ Table recreated successfully with AUTOINCREMENT!")
print("✓ Indexes created")
print("\nYou can now run the load script again.")
