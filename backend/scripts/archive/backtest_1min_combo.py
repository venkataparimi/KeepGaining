"""
1-Minute Strategy Optimizer
Tests advanced indicator combinations to filter noise on 1-min timeframe
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from loguru import logger

DB_PATH = "keepgaining.db"

def calculate_indicators(df):
    """Calculate technical indicators manually for 1-min data"""
    df = df.copy()
    
    # 1. EMAs
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # 2. RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    # 3. MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # 4. Bollinger Bands (20, 2)
    sma_20 = df['close'].rolling(window=20).mean()
    std_20 = df['close'].rolling(window=20).std()
    df['bb_upper'] = sma_20 + (std_20 * 2)
    df['bb_lower'] = sma_20 - (std_20 * 2)
    
    # 5. VWAP (Rolling 1-day approx or simple cumulative)
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    
    # 6. Volume MA
    df['vol_ma_20'] = df['volume'].rolling(window=20).mean()
    
    return df.dropna()

def run_optimization(stock, start_date, end_date):
    logger.info("="*100)
    logger.info(f"1-MINUTE STRATEGY OPTIMIZER: {stock}")
    logger.info("="*100)
    
    # Load Data
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT timestamp, open, high, low, close, volume 
        FROM candle_data 
        WHERE symbol = ? 
        AND timestamp BETWEEN ? AND ?
        ORDER BY timestamp
    """
    df = pd.read_sql_query(query, conn, params=(f"NSE:{stock}-EQ", start_date, end_date))
    conn.close()
    
    if len(df) == 0:
        logger.error("No data found")
        return

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Calculate Indicators
    df = calculate_indicators(df)
    logger.info(f"Analyzed {len(df)} 1-min candles")
    
    # Define Strategies
    strategies = {
        '1. Trend Following': lambda row: (row['close'] > row['ema_200']) and (row['ema_9'] > row['ema_21']),
        
        '2. BB Reversion (Trend)': lambda row: (row['close'] > row['ema_200']) and (row['close'] < row['bb_lower']),
        
        '3. RSI + Trend': lambda row: (row['close'] > row['ema_200']) and (row['rsi_14'] < 30),
        
        '4. MACD + Volume': lambda row: (row['macd'] > row['macd_signal']) and (row['macd_hist'] > 0) and (row['volume'] > row['vol_ma_20'] * 1.5),
        
        '5. VWAP + RSI + Trend': lambda row: (row['close'] > row['ema_200']) and (row['close'] < row['vwap']) and (row['rsi_14'] < 40),
        
        '6. SUPER COMBO': lambda row: (row['close'] > row['ema_200']) and (row['close'] < row['bb_lower']) and (row['rsi_14'] < 30) and (row['volume'] > row['vol_ma_20'] * 1.2)
    }
    
    results = []
    
    for name, condition in strategies.items():
        trades = 0
        wins = 0
        total_pnl = 0
        
        # Backtest Loop
        # We need to be careful not to look ahead. 
        # We iterate and check condition on current candle, then check result in future.
        
        i = 0
        while i < len(df) - 10:
            row = df.iloc[i]
            
            if condition(row):
                trades += 1
                entry_price = row['close']
                
                # Exit Logic: 
                # Target: 0.3% | Stop: 0.15% | Max Time: 10 mins
                exit_price = entry_price
                
                for j in range(1, 11): # Look ahead 10 candles
                    future_row = df.iloc[i + j]
                    
                    # Check Take Profit
                    if future_row['high'] >= entry_price * 1.003:
                        exit_price = entry_price * 1.003
                        break
                    
                    # Check Stop Loss
                    if future_row['low'] <= entry_price * 0.9985:
                        exit_price = entry_price * 0.9985
                        break
                    
                    # Time exit
                    if j == 10:
                        exit_price = future_row['close']
                
                pnl = ((exit_price - entry_price) / entry_price) * 100
                total_pnl += pnl
                
                if pnl > 0:
                    wins += 1
                
                # Skip ahead to avoid overlapping trades
                i += 5 
            else:
                i += 1
        
        if trades > 0:
            win_rate = (wins / trades) * 100
            avg_pnl = total_pnl / trades
            results.append({
                'Strategy': name,
                'Trades': trades,
                'Win Rate': win_rate,
                'Avg P&L': avg_pnl
            })

    # Display Results
    if results:
        df_res = pd.DataFrame(results)
        df_res = df_res.sort_values(by='Win Rate', ascending=False)
        
        logger.info(f"\n{'='*100}")
        logger.info("1-MINUTE STRATEGY RESULTS (Sorted by Win Rate)")
        logger.info(f"{'='*100}\n")
        
        # Format
        df_display = df_res.copy()
        df_display['Win Rate'] = df_display['Win Rate'].apply(lambda x: f"{x:.1f}%")
        df_display['Avg P&L'] = df_display['Avg P&L'].apply(lambda x: f"{x:.3f}%")
        
        print(df_display.to_string(index=False))
        
        best = df_res.iloc[0]
        logger.success(f"\n🏆 BEST 1-MIN STRATEGY: {best['Strategy']} (Win Rate: {best['Win Rate']:.1f}%)")

# Run
run_optimization("HEROMOTOCO", "2025-11-01", "2025-11-25")
