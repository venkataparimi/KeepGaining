"""
Deep Dive Backtest: Trade-by-Trade Breakdown
Shows exact correlation between Stock Signals and Option Execution
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from loguru import logger

DB_PATH = "keepgaining.db"
OPTIONS_DIR = Path("options_data")

def calculate_stock_indicators(df):
    df = df.copy()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    sma_20 = df['close'].rolling(window=20).mean()
    std_20 = df['close'].rolling(window=20).std()
    df['bb_upper'] = sma_20 + (std_20 * 2)
    df['bb_lower'] = sma_20 - (std_20 * 2)
    return df.dropna()

def deep_dive_backtest(stock, strike_ce, strike_pe, start_date="2025-11-01", end_date="2025-11-25"):
    logger.info("="*120)
    logger.info(f"DEEP DIVE BACKTEST: {stock} (Stock Signal -> Option Execution)")
    logger.info("="*120)
    
    # 1. Load Stock Data
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT timestamp, open, high, low, close 
        FROM candle_data 
        WHERE symbol = ? 
        AND timestamp BETWEEN ? AND ?
        ORDER BY timestamp
    """
    stock_df = pd.read_sql_query(query, conn, params=(f"NSE:{stock}-EQ", start_date, end_date))
    conn.close()
    
    stock_df['timestamp'] = pd.to_datetime(stock_df['timestamp'])
    stock_df = calculate_stock_indicators(stock_df)
    
    # 2. Load Options Data
    options_file = OPTIONS_DIR / "25NOV" / f"{stock}.csv"
    if not options_file.exists():
        options_file = OPTIONS_DIR / f"{stock}_25NOV.csv"
    
    options_df = pd.read_csv(options_file)
    options_df['timestamp'] = pd.to_datetime(options_df['timestamp'])
    
    ce_symbol = f"NSE:{stock}25NOV{strike_ce}CE"
    pe_symbol = f"NSE:{stock}25NOV{strike_pe}PE"
    
    ce_data = options_df[options_df['symbol'] == ce_symbol].set_index('timestamp').sort_index()
    pe_data = options_df[options_df['symbol'] == pe_symbol].set_index('timestamp').sort_index()
    
    trades = []
    active_trade = None
    
    # Iterate Stock Candles
    for i in range(len(stock_df) - 10):
        row = stock_df.iloc[i]
        ts = row['timestamp']
        
        # Check Entry
        if active_trade is None:
            # LONG Signal: Uptrend + Touch Lower BB + GREEN Candle Confirmation
            # We check if PREVIOUS candle touched BB, and CURRENT candle is GREEN
            if i > 0:
                prev_row = stock_df.iloc[i-1]
                
                # Setup: Previous candle was below/touching Lower Band
                setup_long = (prev_row['close'] < prev_row['bb_lower']) or (prev_row['low'] < prev_row['bb_lower'])
                
                # Trigger: Current candle is GREEN and closes ABOVE Previous High (Strong Reversal)
                trigger_long = (row['close'] > row['open']) and (row['close'] > prev_row['high'])
                
                # Trend: Above EMA 200
                trend_long = row['close'] > row['ema_200']
                
                if setup_long and trigger_long and trend_long:
                    if ts in ce_data.index:
                        opt_price = ce_data.loc[ts]['close']
                        active_trade = {
                            'type': 'CE',
                            'entry_time': ts,
                            'stock_entry': row['close'],
                            'opt_entry': opt_price,
                            'target': row['close'] * 1.004, # Increased target to 0.4%
                            'stop': row['low'], # Stop is low of reversal candle
                            'entry_idx': i
                        }
            
            # SHORT Signal: Downtrend + Touch Upper BB + RED Candle Confirmation
            if i > 0:
                prev_row = stock_df.iloc[i-1]
                
                setup_short = (prev_row['close'] > prev_row['bb_upper']) or (prev_row['high'] > prev_row['bb_upper'])
                trigger_short = (row['close'] < row['open']) and (row['close'] < prev_row['low'])
                trend_short = row['close'] < row['ema_200']
                
                if setup_short and trigger_short and trend_short:
                    if ts in pe_data.index:
                        opt_price = pe_data.loc[ts]['close']
                        active_trade = {
                            'type': 'PE',
                            'entry_time': ts,
                            'stock_entry': row['close'],
                            'opt_entry': opt_price,
                            'target': row['close'] * 0.996,
                            'stop': row['high'],
                            'entry_idx': i
                        }
        
        # Manage Active Trade
        else:
            # Check Stock Exit Conditions
            exit_triggered = False
            exit_reason = ""
            stock_exit_price = 0
            
            if active_trade['type'] == 'CE':
                if row['high'] >= active_trade['target']:
                    exit_triggered = True
                    exit_reason = "Target"
                    stock_exit_price = active_trade['target']
                elif row['low'] <= active_trade['stop']:
                    exit_triggered = True
                    exit_reason = "Stop"
                    stock_exit_price = active_trade['stop']
                elif (i - active_trade['entry_idx']) >= 10:
                    exit_triggered = True
                    exit_reason = "Time"
                    stock_exit_price = row['close']
            else: # PE
                if row['low'] <= active_trade['target']:
                    exit_triggered = True
                    exit_reason = "Target"
                    stock_exit_price = active_trade['target']
                elif row['high'] >= active_trade['stop']:
                    exit_triggered = True
                    exit_reason = "Stop"
                    stock_exit_price = active_trade['stop']
                elif (i - active_trade['entry_idx']) >= 10:
                    exit_triggered = True
                    exit_reason = "Time"
                    stock_exit_price = row['close']
            
            if exit_triggered:
                # Get Option Price at Exit Time
                opt_exit_price = 0
                if active_trade['type'] == 'CE':
                    if ts in ce_data.index:
                        opt_exit_price = ce_data.loc[ts]['close']
                    else:
                        # Fallback to last known price if missing
                        opt_exit_price = active_trade['opt_entry'] 
                else:
                    if ts in pe_data.index:
                        opt_exit_price = pe_data.loc[ts]['close']
                    else:
                        opt_exit_price = active_trade['opt_entry']
                
                pnl = ((opt_exit_price - active_trade['opt_entry']) / active_trade['opt_entry']) * 100
                
                trades.append({
                    'Entry Time': active_trade['entry_time'].strftime('%Y-%m-%d %H:%M'),
                    'Exit Time': ts.strftime('%H:%M'),
                    'Type': active_trade['type'],
                    'Stock Entry': f"{active_trade['stock_entry']:.2f}",
                    'Stock Exit': f"{stock_exit_price:.2f}",
                    'Opt Entry': f"{active_trade['opt_entry']:.2f}",
                    'Opt Exit': f"{opt_exit_price:.2f}",
                    'Reason': exit_reason,
                    'P&L': f"{pnl:.2f}%"
                })
                active_trade = None

    # Display Detailed Table
    if trades:
        df_trades = pd.DataFrame(trades)
        
        logger.info(f"\n{'='*120}")
        logger.info("TRADE-BY-TRADE BREAKDOWN (Last 20 Trades)")
        logger.info(f"{'='*120}")
        print(df_trades.tail(20).to_string(index=False))
        
        # Stats
        df_trades['P&L_Val'] = df_trades['P&L'].str.rstrip('%').astype(float)
        win_rate = (len(df_trades[df_trades['P&L_Val'] > 0]) / len(df_trades)) * 100
        logger.info(f"\nTotal Trades: {len(df_trades)}")
        logger.info(f"Win Rate: {win_rate:.2f}%")

# Run
deep_dive_backtest("HEROMOTOCO", 5600, 5600)
