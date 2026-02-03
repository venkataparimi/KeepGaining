"""
REALITY CHECK: Backtest Strategy on OPTIONS Data
Signal: Stock (BB Trend)
Execution: Options (CE/PE)
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

def backtest_options_reality(stock, strike_ce, strike_pe, start_date="2025-11-01", end_date="2025-11-25"):
    logger.info("="*100)
    logger.info(f"REALITY CHECK: {stock} Options Backtest (Nov 2025)")
    logger.info("="*100)
    
    # 1. Load Stock Data (for Signals)
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
        
    if not options_file.exists():
        logger.error(f"❌ No options data for {stock}")
        return

    options_df = pd.read_csv(options_file)
    options_df['timestamp'] = pd.to_datetime(options_df['timestamp'])
    
    # Filter for CE and PE
    ce_symbol = f"NSE:{stock}25NOV{strike_ce}CE"
    pe_symbol = f"NSE:{stock}25NOV{strike_pe}PE"
    
    ce_data = options_df[options_df['symbol'] == ce_symbol].set_index('timestamp').sort_index()
    pe_data = options_df[options_df['symbol'] == pe_symbol].set_index('timestamp').sort_index()
    
    trades = []
    active_trade = None
    
    # Iterate Stock Candles (Signals)
    for i in range(len(stock_df) - 10):
        row = stock_df.iloc[i]
        ts = row['timestamp']
        
        # Check Entry
        if active_trade is None:
            # LONG Signal -> Buy CE
            if (row['close'] > row['ema_200']) and (row['close'] < row['bb_lower']):
                if ts in ce_data.index:
                    opt_price = ce_data.loc[ts]['close']
                    active_trade = {
                        'type': 'CE',
                        'entry_time': ts,
                        'entry_price': opt_price,
                        'entry_idx': i
                    }
            
            # SHORT Signal -> Buy PE
            elif (row['close'] < row['ema_200']) and (row['close'] > row['bb_upper']):
                if ts in pe_data.index:
                    opt_price = pe_data.loc[ts]['close']
                    active_trade = {
                        'type': 'PE',
                        'entry_time': ts,
                        'entry_price': opt_price,
                        'entry_idx': i
                    }
        
        # Manage Active Trade
        else:
            # Exit after 10 mins or End of Day
            duration = i - active_trade['entry_idx']
            
            # Force exit at 15:20
            is_eod = ts.hour == 15 and ts.minute >= 20
            
            if duration >= 10 or is_eod:
                exit_price = 0
                if active_trade['type'] == 'CE':
                    if ts in ce_data.index:
                        exit_price = ce_data.loc[ts]['close']
                    else:
                        continue # Data missing, wait
                else:
                    if ts in pe_data.index:
                        exit_price = pe_data.loc[ts]['close']
                    else:
                        continue
                
                pnl = ((exit_price - active_trade['entry_price']) / active_trade['entry_price']) * 100
                
                trades.append({
                    'Time': active_trade['entry_time'],
                    'Type': active_trade['type'],
                    'Entry': active_trade['entry_price'],
                    'Exit': exit_price,
                    'P&L': pnl
                })
                active_trade = None

    # Results
    if trades:
        df_trades = pd.DataFrame(trades)
        
        total = len(df_trades)
        wins = len(df_trades[df_trades['P&L'] > 0])
        win_rate = (wins / total) * 100
        avg_pnl = df_trades['P&L'].mean()
        total_pnl = df_trades['P&L'].sum()
        
        logger.info(f"\n{'='*80}")
        logger.info("OPTIONS TRADING RESULTS (Real P&L)")
        logger.info(f"{'='*80}")
        logger.info(f"Total Trades: {total}")
        logger.info(f"Win Rate:     {win_rate:.2f}%")
        logger.info(f"Avg P&L:      {avg_pnl:.2f}%")
        logger.info(f"Total P&L:    {total_pnl:.2f}%")
        
        # Best Trades
        best = df_trades.sort_values('P&L', ascending=False).head(5)
        logger.info(f"\n{'='*80}")
        logger.info("TOP 5 WINNERS")
        logger.info(f"{'='*80}")
        print(best.to_string(index=False))
        
        # Worst Trades
        worst = df_trades.sort_values('P&L', ascending=True).head(5)
        logger.info(f"\n{'='*80}")
        logger.info("TOP 5 LOSERS")
        logger.info(f"{'='*80}")
        print(worst.to_string(index=False))

# Run with Hero Motors 5600CE / 5600PE (ATM/OTM mix)
backtest_options_reality("HEROMOTOCO", 5600, 5600)
