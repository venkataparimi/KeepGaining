"""
Volume Rocket Scanner
Runs the 'Volume Rocket' momentum strategy on ALL stocks with options data.
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
OPTIONS_DIR = Path("options_data")

def get_available_stocks():
    """Get list of stocks that have options data"""
    stocks = []
    # Check new format folder
    if (OPTIONS_DIR / "25NOV").exists():
        for f in (OPTIONS_DIR / "25NOV").glob("*.csv"):
            stocks.append(f.stem)
            
    # Check old format files
    for f in OPTIONS_DIR.glob("*_25NOV.csv"):
        stock_name = f.stem.replace("_25NOV", "")
        if stock_name not in stocks:
            stocks.append(stock_name)
            
    return sorted(stocks)

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
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Volume MA
    df['vol_ma'] = df['volume'].rolling(window=20).mean()
    
    return df.dropna()

def scan_stocks():
    stocks = get_available_stocks()
    logger.info(f"Scanning {len(stocks)} stocks for 'Volume Rocket' signals...")
    
    all_trades = []
    
    conn = sqlite3.connect(DB_PATH)
    
    for i, stock in enumerate(stocks, 1):
        try:
            # Load Data
            query = """
                SELECT timestamp, open, high, low, close, volume 
                FROM candle_data 
                WHERE symbol = ? 
                AND timestamp BETWEEN '2025-11-01' AND '2025-11-25'
                ORDER BY timestamp
            """
            df = pd.read_sql_query(query, conn, params=(f"NSE:{stock}-EQ",))
            
            if len(df) < 200:
                continue
                
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = calculate_indicators(df)
            
            active_trade = None
            
            for j in range(len(df)):
                row = df.iloc[j]
                
                if active_trade is None:
                    # ENTRY CONDITIONS
                    # 1. Volume > 3x Avg
                    # 2. Price > Upper BB
                    # 3. RSI > 70
                    # 4. Trend > EMA 200
                    if (row['volume'] > row['vol_ma'] * 3) and \
                       (row['close'] > row['bb_upper']) and \
                       (row['rsi'] > 70) and \
                       (row['close'] > row['ema_200']):
                           
                        active_trade = {
                            'Stock': stock,
                            'Entry Time': row['timestamp'],
                            'Entry Price': row['close'],
                            'Entry Idx': j
                        }
                else:
                    # EXIT CONDITIONS
                    # 1. Trailing Stop: Close < EMA 9
                    # 2. End of Day
                    
                    is_eod = (row['timestamp'].hour == 15 and row['timestamp'].minute >= 25)
                    
                    if (row['close'] < row['ema_9']) or is_eod:
                        exit_price = row['close']
                        pnl = ((exit_price - active_trade['Entry Price']) / active_trade['Entry Price']) * 100
                        
                        all_trades.append({
                            'Stock': active_trade['Stock'],
                            'Entry Time': active_trade['Entry Time'],
                            'Exit Time': row['timestamp'],
                            'Entry Price': active_trade['Entry Price'],
                            'Exit Price': exit_price,
                            'Gain %': pnl
                        })
                        active_trade = None
                        
        except Exception as e:
            logger.error(f"Error processing {stock}: {e}")
            
        if i % 10 == 0:
            print(f"Processed {i}/{len(stocks)} stocks...", end='\r')
            
    conn.close()
    
    # Summary
    if all_trades:
        df_res = pd.DataFrame(all_trades)
        
        # Filter for significant gains to reduce noise in output
        df_res = df_res.sort_values('Gain %', ascending=False)
        
        logger.info(f"\n{'='*100}")
        logger.info(f"VOLUME ROCKET STRATEGY RESULTS (Top 20 Trades)")
        logger.info(f"{'='*100}")
        
        # Format for display
        df_display = df_res.head(20).copy()
        df_display['Entry Time'] = df_display['Entry Time'].dt.strftime('%Y-%m-%d %H:%M')
        df_display['Exit Time'] = df_display['Exit Time'].dt.strftime('%H:%M')
        df_display['Entry Price'] = df_display['Entry Price'].apply(lambda x: f"{x:.2f}")
        df_display['Exit Price'] = df_display['Exit Price'].apply(lambda x: f"{x:.2f}")
        df_display['Gain %'] = df_display['Gain %'].apply(lambda x: f"{x:.2f}%")
        
        print(df_display.to_string(index=False))
        
        # Stats
        total = len(df_res)
        wins = len(df_res[df_res['Gain %'] > 0])
        win_rate = (wins / total) * 100
        avg_gain = df_res['Gain %'].mean()
        
        logger.info(f"\n{'='*100}")
        logger.info(f"Total Trades: {total}")
        logger.info(f"Win Rate:     {win_rate:.2f}%")
        logger.info(f"Avg Gain:     {avg_gain:.2f}%")
        logger.info(f"{'='*100}")
        
        # Save to CSV
        df_res.to_csv("volume_rocket_results.csv", index=False)
        logger.success("Full results saved to 'volume_rocket_results.csv'")

if __name__ == "__main__":
    scan_stocks()
