"""
Advanced Backtester - Multi-Timeframe & Confluence Analysis
Resamples data and tests combined strategies with volume filtering
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from loguru import logger

DB_PATH = "keepgaining.db"

def resample_data(df, timeframe):
    """Resample 1-min data to higher timeframes"""
    # Ensure timestamp is index
    df = df.set_index('timestamp')
    
    # Resample logic
    ohlc_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    
    df_resampled = df.resample(timeframe).agg(ohlc_dict).dropna()
    
    # Recalculate indicators manually
    
    # 1. VWAP
    # VWAP = Cumulative(Price * Volume) / Cumulative(Volume)
    # For intraday, we usually reset daily, but for this backtest we'll use a rolling window or simple calculation
    # Since we resampled, we can approximate VWAP using typical price
    typical_price = (df_resampled['high'] + df_resampled['low'] + df_resampled['close']) / 3
    df_resampled['vwap'] = (typical_price * df_resampled['volume']).cumsum() / df_resampled['volume'].cumsum()
    
    # 2. RSI
    delta = df_resampled['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df_resampled['rsi_14'] = 100 - (100 / (1 + rs))
    
    # 3. Volume MA
    df_resampled['vol_ma_20'] = df_resampled['volume'].rolling(window=20).mean()
    
    return df_resampled.reset_index()

def run_backtest(stock, start_date, end_date):
    logger.info("="*100)
    logger.info(f"ADVANCED BACKTEST: {stock} | {start_date} to {end_date}")
    logger.info("="*100)
    
    # Load 1-min data
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT timestamp, open, high, low, close, volume 
        FROM candle_data 
        WHERE symbol = ? 
        AND timestamp BETWEEN ? AND ?
        ORDER BY timestamp
    """
    stock_symbol = f"NSE:{stock}-EQ"
    df_1min = pd.read_sql_query(query, conn, params=(stock_symbol, start_date, end_date))
    conn.close()
    
    if len(df_1min) == 0:
        logger.error("No data found")
        return
        
    df_1min['timestamp'] = pd.to_datetime(df_1min['timestamp'])
    
    # Test Timeframes
    timeframes = ['1min', '3min', '5min', '15min']
    
    results = []
    
    for tf in timeframes:
        logger.info(f"\nProcessing {tf} timeframe...")
        
        if tf == '1min':
            # Calculate indicators for 1min
            df_tf = df_1min.copy()
            df_tf.set_index('timestamp', inplace=True)
            
            # VWAP
            typical_price = (df_tf['high'] + df_tf['low'] + df_tf['close']) / 3
            df_tf['vwap'] = (typical_price * df_tf['volume']).cumsum() / df_tf['volume'].cumsum()
            
            # RSI
            delta = df_tf['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df_tf['rsi_14'] = 100 - (100 / (1 + rs))
            
            # Volume MA
            df_tf['vol_ma_20'] = df_tf['volume'].rolling(window=20).mean()
            
            df_tf.reset_index(inplace=True)
        else:
            # Resample
            df_tf = resample_data(df_1min.copy(), tf.replace('min', 'T'))
        
        # Drop NaN (warmup period for indicators)
        df_tf.dropna(inplace=True)
        
        # Define Strategies
        strategies = {
            'VWAP Only': lambda row: row['close'] < row['vwap'] * 0.997,
            'RSI Only': lambda row: row['rsi_14'] < 30,
            'VWAP + Volume': lambda row: (row['close'] < row['vwap'] * 0.997) and (row['volume'] > row['vol_ma_20'] * 1.5),
            'VWAP + RSI': lambda row: (row['close'] < row['vwap'] * 0.997) and (row['rsi_14'] < 40),
            'ALL (VWAP+RSI+Vol)': lambda row: (row['close'] < row['vwap'] * 0.997) and (row['rsi_14'] < 40) and (row['volume'] > row['vol_ma_20'] * 1.5)
        }
        
        for name, condition in strategies.items():
            trades = 0
            wins = 0
            total_pnl = 0
            
            # Simple vector backtest loop
            for i in range(len(df_tf) - 5): # Stop before end
                row = df_tf.iloc[i]
                
                if condition(row):
                    trades += 1
                    entry_price = row['close']
                    
                    # Exit after 5 candles or end of day
                    exit_idx = min(i + 5, len(df_tf) - 1)
                    exit_price = df_tf.iloc[exit_idx]['close']
                    
                    pnl = ((exit_price - entry_price) / entry_price) * 100
                    total_pnl += pnl
                    
                    if pnl > 0.2: # 0.2% target (scalping)
                        wins += 1
            
            if trades > 0:
                win_rate = (wins / trades) * 100
                avg_pnl = total_pnl / trades
                
                results.append({
                    'Timeframe': tf,
                    'Strategy': name,
                    'Trades': trades,
                    'Win Rate': win_rate,
                    'Avg P&L': avg_pnl
                })
    
    # Display Results
    if results:
        df_res = pd.DataFrame(results)
        df_res = df_res.sort_values(by=['Win Rate', 'Avg P&L'], ascending=False)
        
        logger.info(f"\n{'='*100}")
        logger.info("MULTI-TIMEFRAME & CONFLUENCE RESULTS")
        logger.info(f"{'='*100}\n")
        
        # Format for display
        df_display = df_res.copy()
        df_display['Win Rate'] = df_display['Win Rate'].apply(lambda x: f"{x:.1f}%")
        df_display['Avg P&L'] = df_display['Avg P&L'].apply(lambda x: f"{x:.2f}%")
        
        print(df_display.to_string(index=False))
        
        best = df_res.iloc[0]
        logger.success(f"\n🏆 BEST COMBO: {best['Timeframe']} - {best['Strategy']} (Win Rate: {best['Win Rate']:.1f}%)")

# Run
run_backtest("HEROMOTOCO", "2025-11-01", "2025-11-25")
