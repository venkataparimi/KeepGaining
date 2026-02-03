"""
Backtest Volume Rocket with Fixed Entry Time (09:16)
Only trades that would be entered at 09:16 are considered.
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
    # EMA 9 (trailing stop)
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    # EMA 200 (trend)
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    # Bollinger Bands (20,2)
    sma_20 = df['close'].rolling(window=20).mean()
    std_20 = df['close'].rolling(window=20).std()
    df['bb_upper'] = sma_20 + (std_20 * 2)
    df['bb_lower'] = sma_20 - (std_20 * 2)
    # RSI 14
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    # Volume MA 20
    df['vol_ma'] = df['volume'].rolling(window=20).mean()
    return df.dropna()

def backtest_fixed_entry():
    logger.info("=== BACKTEST: Volume Rocket – ENTRY ONLY AT 09:16 ===")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT symbol FROM candle_data")
    symbols = [row[0] for row in cursor.fetchall()]
    all_trades = []
    for symbol in symbols:
        stock = symbol.replace('NSE:', '').replace('-EQ', '')
        # Load data for the month of November 2025 (same period as earlier scans)
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM candle_data
            WHERE symbol = ?
            AND timestamp BETWEEN '2025-11-01' AND '2025-11-25'
            ORDER BY timestamp
        """
        df = pd.read_sql_query(query, conn, params=(symbol,))
                            'Type': 'LONG'
                        }
                    # SHORT (PE) condition
                    elif (row['volume'] > row['vol_ma'] * 3) and (row['close'] < row['bb_lower']) and (row['rsi'] < 30) and (row['close'] < row['ema_200']):
                        active_trade = {
                            'Stock': stock,
                            'Entry Time': row['timestamp'],
                            'Entry Price': row['close'],
                            'Type': 'SHORT'
                        }
            else:
                # Exit logic – trailing EMA9 or end‑of‑day (15:25)
                is_eod = (row['timestamp'].hour == 15 and row['timestamp'].minute >= 25)
                exit_signal = False
                if active_trade['Type'] == 'LONG' and row['close'] < row['ema_9']:
                    exit_signal = True
                if active_trade['Type'] == 'SHORT' and row['close'] > row['ema_9']:
                    exit_signal = True
                if is_eod:
                    exit_signal = True
                if exit_signal:
                    exit_price = row['close']
                    pnl = ((exit_price - active_trade['Entry Price']) / active_trade['Entry Price']) * 100
                    if active_trade['Type'] == 'SHORT':
                        pnl = -pnl  # reverse for short
                    all_trades.append({
                        'Stock': active_trade['Stock'],
                        'Type': active_trade['Type'],
                        'Entry Time': active_trade['Entry Time'],
                        'Exit Time': row['timestamp'],
                        'Entry Price': active_trade['Entry Price'],
                        'Exit Price': exit_price,
                        'Gain %': pnl
                    })
                    active_trade = None
        # end for rows
    conn.close()
    # Summarize
    if not all_trades:
        logger.info("No trades entered at 09:16 across the universe.")
        return
    df_res = pd.DataFrame(all_trades)
    total = len(df_res)
    wins = len(df_res[df_res['Gain %'] > 0])
    win_rate = wins / total * 100
    avg_gain = df_res['Gain %'].mean()
    logger.info(f"\n{'='*80}")
    logger.info("RESULTS – FIXED 09:16 ENTRY")
    logger.info(f"{'='*80}")
    logger.info(f"Total Trades: {total}")
    logger.info(f"Win Rate: {win_rate:.2f}%")
    logger.info(f"Avg Gain: {avg_gain:.2f}%")
    # Show top 10
    top = df_res.sort_values('Gain %', ascending=False).head(10)
    top_disp = top.copy()
    top_disp['Entry Time'] = top_disp['Entry Time'].dt.strftime('%Y-%m-%d %H:%M')
    top_disp['Exit Time'] = top_disp['Exit Time'].dt.strftime('%H:%M')
    print(top_disp.to_string(index=False))
    # Save full results
    df_res.to_csv('volume_rocket_fixed_entry.csv', index=False)
    logger.success("Full results saved to 'volume_rocket_fixed_entry.csv'")

if __name__ == "__main__":
    backtest_fixed_entry()
