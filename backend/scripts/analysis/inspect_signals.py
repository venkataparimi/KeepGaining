"""
Inspect Signal Quality
Check indicators for specific 'bad' trades to identify why logic is loose.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from loguru import logger

DB_PATH = "keepgaining.db"

def calculate_indicators(df):
    df = df.copy()
    # EMA 200
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # BB (20, 2)
    sma_20 = df['close'].rolling(window=20).mean()
    std_20 = df['close'].rolling(window=20).std()
    df['bb_upper'] = sma_20 + (std_20 * 2)
    df['bb_lower'] = sma_20 - (std_20 * 2)
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    return df

def inspect_signals(stock, timestamps):
    logger.info(f"INSPECTING SIGNALS: {stock}")
    
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT timestamp, open, high, low, close 
        FROM candle_data 
        WHERE symbol = ? 
        AND timestamp BETWEEN '2025-11-18 12:00:00' AND '2025-11-18 16:00:00'
        ORDER BY timestamp
    """
    df = pd.read_sql_query(query, conn, params=(f"NSE:{stock}-EQ",))
    conn.close()
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = calculate_indicators(df)
    
    print(f"{'Time':<16} {'Close':<8} {'EMA200':<8} {'BB_Up':<8} {'RSI':<6} {'Trend?':<10} {'Overbought?'}")
    print("-" * 80)
    
    for ts_str in timestamps:
        ts = pd.to_datetime(ts_str)
        # Get the row for this timestamp (Entry Candle)
        row = df[df['timestamp'] == ts].iloc[0]
        # Get previous row (Setup Candle)
        prev_idx = df[df['timestamp'] == ts].index[0] - 1
        prev_row = df.iloc[prev_idx]
        
        trend = "DOWN" if row['close'] < row['ema_200'] else "UP"
        dist_ema = ((row['close'] - row['ema_200']) / row['ema_200']) * 100
        
        setup = "YES" if prev_row['high'] > prev_row['bb_upper'] else "NO"
        
        print(f"{ts.strftime('%H:%M'):<16} {row['close']:<8.2f} {row['ema_200']:<8.2f} {row['bb_upper']:<8.2f} {row['rsi_14']:<6.1f} {trend} ({dist_ema:.2f}%)  {setup}")

timestamps = [
    "2025-11-18 12:42:00",
    "2025-11-18 14:07:00",
    "2025-11-18 15:04:00",
    "2025-11-18 15:21:00"
]

inspect_signals("HEROMOTOCO", timestamps)
