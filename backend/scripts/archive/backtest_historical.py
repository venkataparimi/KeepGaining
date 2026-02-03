"""
Historical Stock Backtester: Volume Rocket Strategy
Runs on 6 months of stock data to estimate performance.
Extrapolates Option Gains based on Stock Moves.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from loguru import logger
import warnings
warnings.filterwarnings('ignore')

DB_PATH = "keepgaining.db"

def calculate_indicators(df):
    df = df.copy()
    # EMA 9 (Trailing Stop)
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    # EMA 200 (Trend)
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # Bollinger Bands (20, 2)
    sma_20 = df['close'].rolling(window=20).mean()
    std_20 = df['close'].rolling(window=20).std()
    df['bb_upper'] = sma_20 + (std_20 * 2)
    df['bb_lower'] = sma_20 - (std_20 * 2)
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Volume MA
    df['vol_ma'] = df['volume'].rolling(window=20).mean()
    
    return df.dropna()

def backtest_historical():
    logger.info("Starting Historical Backtest (6 Months)...")
    
    conn = sqlite3.connect(DB_PATH)
    
    # Get all symbols
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT symbol FROM candle_data")
    symbols = [row[0] for row in cursor.fetchall()]
    
    all_trades = []
    
    # Multiplier for Option Gain Estimation (Conservative 10x)
    # 1% Stock Move -> 10% Option Move
    OPTION_MULTIPLIER = 10 
    
    for i, symbol in enumerate(symbols, 1):
        stock_name = symbol.replace('NSE:', '').replace('-EQ', '')
        
        try:
            # Load 6 months data (approx)
            query = """
                SELECT timestamp, open, high, low, close, volume 
                FROM candle_data 
                WHERE symbol = ? 
                AND timestamp >= '2025-06-01'
                ORDER BY timestamp
            """
            df = pd.read_sql_query(query, conn, params=(symbol,))
            
            if len(df) < 200:
                continue
                
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = calculate_indicators(df)
            
            active_trade = None
            
            for j in range(len(df)):
                row = df.iloc[j]
                
                if active_trade is None:
                    # LONG ENTRY
                    if (row['volume'] > row['vol_ma'] * 3) and \
                       (row['close'] > row['bb_upper']) and \
                       (row['rsi'] > 70) and \
                       (row['close'] > row['ema_200']):
                           
                        active_trade = {
                            'Stock': stock_name,
                            'Entry Time': row['timestamp'],
                            'Entry Price': row['close'],
                            'Type': 'LONG'
                        }
                        
                    # SHORT ENTRY
                    elif (row['volume'] > row['vol_ma'] * 3) and \
                         (row['close'] < row['bb_lower']) and \
                         (row['rsi'] < 30) and \
                         (row['close'] < row['ema_200']):
                             
                        active_trade = {
                            'Stock': stock_name,
                            'Entry Time': row['timestamp'],
                            'Entry Price': row['close'],
                            'Type': 'SHORT'
                        }
                else:
                    # EXIT
                    exit_signal = False
                    
                    # Trailing Stop (EMA 9)
                    if active_trade['Type'] == 'LONG':
                        if row['close'] < row['ema_9']:
                            exit_signal = True
                    else:
                        if row['close'] > row['ema_9']:
                            exit_signal = True
                            
                    # End of Day Force Exit
                    if row['timestamp'].hour == 15 and row['timestamp'].minute >= 25:
                        exit_signal = True
                        
                    if exit_signal:
                        exit_price = row['close']
                        
                        if active_trade['Type'] == 'LONG':
                            stock_pnl = ((exit_price - active_trade['Entry Price']) / active_trade['Entry Price']) * 100
                        else:
                            stock_pnl = ((active_trade['Entry Price'] - exit_price) / active_trade['Entry Price']) * 100
                        
                        est_opt_pnl = stock_pnl * OPTION_MULTIPLIER
                        
                        all_trades.append({
                            'Stock': active_trade['Stock'],
                            'Type': active_trade['Type'],
                            'Entry Time': active_trade['Entry Time'],
                            'Exit Time': row['timestamp'],
                            'Stock Gain %': stock_pnl,
                            'Est Option %': est_opt_pnl
                        })
                        active_trade = None
                        
        except Exception as e:
            pass
            
        if i % 10 == 0:
            print(f"Processed {i}/{len(symbols)} stocks...", end='\r')
            
    conn.close()
    
    # Results
    if all_trades:
        df_res = pd.DataFrame(all_trades)
        
        # Stats
        total = len(df_res)
        wins = len(df_res[df_res['Stock Gain %'] > 0])
        win_rate = (wins / total) * 100
        avg_stock_gain = df_res['Stock Gain %'].mean()
        avg_opt_gain = df_res['Est Option %'].mean()
        
        logger.info(f"\n{'='*100}")
        logger.info(f"HISTORICAL BACKTEST RESULTS (June - Nov 2025)")
        logger.info(f"{'='*100}")
        logger.info(f"Total Trades:     {total}")
        logger.info(f"Win Rate:         {win_rate:.2f}%")
        logger.info(f"Avg Stock Gain:   {avg_stock_gain:.2f}%")
        logger.info(f"Est Option Gain:  {avg_opt_gain:.2f}% (10x Multiplier)")
        logger.info(f"{'='*100}")
        
        # Top Winners
        logger.info(f"\nTOP 10 WINNERS (Stock Gain)")
        top = df_res.sort_values('Stock Gain %', ascending=False).head(10)
        
        # Format
        top_disp = top.copy()
        top_disp['Entry Time'] = top_disp['Entry Time'].dt.strftime('%Y-%m-%d %H:%M')
        top_disp['Stock Gain %'] = top_disp['Stock Gain %'].apply(lambda x: f"{x:.2f}%")
        top_disp['Est Option %'] = top_disp['Est Option %'].apply(lambda x: f"{x:.0f}%")
        
        print(top_disp.to_string(index=False))
        
        df_res.to_csv("historical_backtest_results.csv", index=False)
        logger.success("Saved to 'historical_backtest_results.csv'")

if __name__ == "__main__":
    backtest_historical()
