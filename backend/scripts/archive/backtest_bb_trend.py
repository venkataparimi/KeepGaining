"""
Detailed Backtest: BB Reversion (Trend) Strategy
Target: HEROMOTOCO
Timeframe: 1 Minute
Period: Sept - Nov 2025
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
    # EMA 200 for Trend
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # Bollinger Bands (20, 2)
    sma_20 = df['close'].rolling(window=20).mean()
    std_20 = df['close'].rolling(window=20).std()
    df['bb_upper'] = sma_20 + (std_20 * 2)
    df['bb_lower'] = sma_20 - (std_20 * 2)
    
    return df.dropna()

def backtest_bb_trend(stock, start_date, end_date):
    logger.info("="*100)
    logger.info(f"DETAILED BACKTEST: {stock} (BB Reversion + Trend)")
    logger.info(f"Period: {start_date} to {end_date}")
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
    df = calculate_indicators(df)
    
    trades = []
    active_trade = None
    
    # Iterate candles
    for i in range(len(df) - 10):
        row = df.iloc[i]
        
        # Check for Entry
        if active_trade is None:
            # LONG Condition: Uptrend + Oversold
            if (row['close'] > row['ema_200']) and (row['close'] < row['bb_lower']):
                active_trade = {
                    'type': 'LONG',
                    'entry_time': row['timestamp'],
                    'entry_price': row['close'],
                    'target': row['close'] * 1.003,
                    'stop': row['close'] * 0.9985,
                    'entry_idx': i
                }
            
            # SHORT Condition: Downtrend + Overbought
            elif (row['close'] < row['ema_200']) and (row['close'] > row['bb_upper']):
                active_trade = {
                    'type': 'SHORT',
                    'entry_time': row['timestamp'],
                    'entry_price': row['close'],
                    'target': row['close'] * 0.997,
                    'stop': row['close'] * 1.0015,
                    'entry_idx': i
                }
        
        # Manage Active Trade
        else:
            # Check exit conditions against High/Low of current candle (simulating intra-candle price action)
            # Note: In real-time we enter at close of previous, so we check current candle for exit
            
            # Skip the entry candle for exit check (assuming entry at close)
            if i == active_trade['entry_idx']:
                continue
                
            exit_price = None
            exit_reason = None
            
            if active_trade['type'] == 'LONG':
                if row['high'] >= active_trade['target']:
                    exit_price = active_trade['target']
                    exit_reason = 'Target'
                elif row['low'] <= active_trade['stop']:
                    exit_price = active_trade['stop']
                    exit_reason = 'Stop'
                elif (i - active_trade['entry_idx']) >= 10: # Time exit
                    exit_price = row['close']
                    exit_reason = 'Time'
            
            elif active_trade['type'] == 'SHORT':
                if row['low'] <= active_trade['target']:
                    exit_price = active_trade['target']
                    exit_reason = 'Target'
                elif row['high'] >= active_trade['stop']:
                    exit_price = active_trade['stop']
                    exit_reason = 'Stop'
                elif (i - active_trade['entry_idx']) >= 10:
                    exit_price = row['close']
                    exit_reason = 'Time'
            
            if exit_price:
                pnl = 0
                if active_trade['type'] == 'LONG':
                    pnl = ((exit_price - active_trade['entry_price']) / active_trade['entry_price']) * 100
                else:
                    pnl = ((active_trade['entry_price'] - exit_price) / active_trade['entry_price']) * 100
                
                trades.append({
                    'Entry Time': active_trade['entry_time'],
                    'Type': active_trade['type'],
                    'Entry': active_trade['entry_price'],
                    'Exit': exit_price,
                    'Reason': exit_reason,
                    'P&L': pnl
                })
                active_trade = None
    
    # Analysis
    if trades:
        df_trades = pd.DataFrame(trades)
        
        total_trades = len(df_trades)
        wins = len(df_trades[df_trades['P&L'] > 0])
        win_rate = (wins / total_trades) * 100
        avg_pnl = df_trades['P&L'].mean()
        total_pnl = df_trades['P&L'].sum()
        
        logger.info(f"\n{'='*80}")
        logger.info("PERFORMANCE SUMMARY")
        logger.info(f"{'='*80}")
        logger.info(f"Total Trades: {total_trades}")
        logger.info(f"Win Rate:     {win_rate:.2f}%")
        logger.info(f"Avg P&L:      {avg_pnl:.3f}%")
        logger.info(f"Total P&L:    {total_pnl:.2f}%")
        
        # Recent Trades
        logger.info(f"\n{'='*80}")
        logger.info("RECENT TRADES (Last 10)")
        logger.info(f"{'='*80}")
        
        recent = df_trades.tail(10).copy()
        recent['Entry Time'] = recent['Entry Time'].dt.strftime('%Y-%m-%d %H:%M')
        recent['Entry'] = recent['Entry'].apply(lambda x: f"{x:.2f}")
        recent['Exit'] = recent['Exit'].apply(lambda x: f"{x:.2f}")
        recent['P&L'] = recent['P&L'].apply(lambda x: f"{x:.2f}%")
        
        print(recent.to_string(index=False))
        
        # Equity Curve Check
        df_trades['Cumulative P&L'] = df_trades['P&L'].cumsum()
        final_equity = df_trades['Cumulative P&L'].iloc[-1]
        logger.success(f"\n💰 Final Cumulative Return: {final_equity:.2f}%")

# Run
backtest_bb_trend("HEROMOTOCO", "2025-09-01", "2025-11-25")
