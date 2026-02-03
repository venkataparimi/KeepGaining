"""
Forensic Analysis of Winning Trade
Reverse-engineer the indicators at the exact entry time to find the winning pattern.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from loguru import logger

DB_PATH = "keepgaining.db"

def analyze_entry_point(stock, entry_time):
    logger.info(f"FORENSIC ANALYSIS: {stock} at {entry_time}")
    
    conn = sqlite3.connect(DB_PATH)
    # Get data around the entry time (need history for indicators)
    query = """
        SELECT timestamp, open, high, low, close, volume 
        FROM candle_data 
        WHERE symbol = ? 
        AND timestamp <= ?
        ORDER BY timestamp DESC
        LIMIT 300
    """
    df = pd.read_sql_query(query, conn, params=(f"NSE:{stock}-EQ", entry_time))
    conn.close()
    
    df = df.iloc[::-1].reset_index(drop=True) # Reverse to chronological order
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Calculate ALL Indicators Manually
    
    # 1. EMAs
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # 2. RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 3. MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # 4. Bollinger Bands
    sma_20 = df['close'].rolling(window=20).mean()
    std_20 = df['close'].rolling(window=20).std()
    df['bb_upper'] = sma_20 + (std_20 * 2)
    df['bb_lower'] = sma_20 - (std_20 * 2)
    
    # 5. VWAP (Cumulative for the loaded period)
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    
    # 6. Volume MA
    df['vol_ma'] = df['volume'].rolling(window=20).mean()
    
    # Get the specific entry row
    entry_row = df[df['timestamp'] == pd.to_datetime(entry_time)].iloc[0]
    prev_row = df[df['timestamp'] == pd.to_datetime(entry_time)].shift(1).iloc[0]
    
    # Print Report
    logger.info(f"\n{'='*60}")
    logger.info(f"INDICATOR STATE AT {entry_time}")
    logger.info(f"{'='*60}")
    
    print(f"Price:      {entry_row['close']:.2f}")
    print(f"VWAP:       {entry_row['vwap']:.2f}  (Diff: {((entry_row['close']-entry_row['vwap'])/entry_row['vwap'])*100:.2f}%)")
    print(f"EMA 200:    {entry_row['ema_200']:.2f}  (Trend: {'BULLISH' if entry_row['close'] > entry_row['ema_200'] else 'BEARISH'})")
    print(f"EMA 9/21:   {entry_row['ema_9']:.2f} / {entry_row['ema_21']:.2f} ({'CROSSOVER' if entry_row['ema_9'] > entry_row['ema_21'] else 'BEARISH'})")
    print(f"RSI:        {entry_row['rsi']:.2f}")
    print(f"MACD:       {entry_row['macd']:.2f} (Hist: {entry_row['macd_hist']:.2f})")
    print(f"Bollinger:  Upper {entry_row['bb_upper']:.2f} | Lower {entry_row['bb_lower']:.2f}")
    print(f"Volume:     {entry_row['volume']} (vs Avg: {entry_row['vol_ma']:.0f})")
    
    logger.info(f"\n{'='*60}")
    logger.info("POTENTIAL TRIGGERS IDENTIFIED")
    logger.info(f"{'='*60}")
    
    triggers = []
    
    # Check VWAP
    if entry_row['close'] < entry_row['vwap']:
        triggers.append(f"✅ VWAP Reversion: Price below VWAP (Undervalued)")
    elif entry_row['close'] > entry_row['vwap']:
        triggers.append(f"✅ VWAP Breakout: Price above VWAP")
        
    # Check RSI
    if entry_row['rsi'] < 30:
        triggers.append(f"✅ RSI Oversold (<30)")
    elif entry_row['rsi'] > 70:
        triggers.append(f"✅ RSI Overbought (>70)")
    elif entry_row['rsi'] > 50 and prev_row['rsi'] <= 50:
        triggers.append(f"✅ RSI Bullish Cross (>50)")
        
    # Check MACD
    if entry_row['macd'] > entry_row['macd_signal']:
        triggers.append(f"✅ MACD Bullish")
        if prev_row['macd'] <= prev_row['macd_signal']:
             triggers.append(f"🚀 MACD FRESH CROSSOVER")
             
    # Check BB
    if entry_row['close'] < entry_row['bb_lower']:
        triggers.append(f"✅ BB Oversold (Below Lower Band)")
    elif entry_row['close'] > entry_row['bb_upper']:
        triggers.append(f"✅ BB Breakout (Above Upper Band)")
        
    # Check Volume
    if entry_row['volume'] > entry_row['vol_ma'] * 1.5:
        triggers.append(f"✅ Volume Spike (>1.5x Avg)")
        
    for t in triggers:
        print(t)

# Run analysis
analyze_entry_point("HEROMOTOCO", "2025-11-17 09:17:00")
