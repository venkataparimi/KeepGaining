"""
Volume Rocket Option Trade Generator
Calculates exact option premiums for Volume Rocket signals.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from loguru import logger
import warnings
warnings.filterwarnings('ignore')

OPTIONS_DIR = Path("options_data")

def find_closest_strike(stock, price, option_type='CE'):
    """Find closest strike price available in options data"""
    # Load options file to get available strikes
    options_file = OPTIONS_DIR / "25NOV" / f"{stock}.csv"
    if not options_file.exists():
        options_file = OPTIONS_DIR / f"{stock}_25NOV.csv"
        
    if not options_file.exists():
        return None
        
    # Read unique symbols to find strikes
    # Format: NSE:STOCK25NOV{STRIKE}{TYPE}
    df = pd.read_csv(options_file, usecols=['symbol'])
    symbols = df['symbol'].unique()
    
    strikes = []
    for s in symbols:
        if option_type in s:
            try:
                # Extract strike: NSE:HEROMOTOCO25NOV5600CE -> 5600
                part = s.split('25NOV')[1]
                strike = int(part.replace(option_type, ''))
                strikes.append(strike)
            except:
                continue
                
    if not strikes:
        return None
        
    strikes.sort()
    
    # Find closest OTM/ATM strike
    # For CE: Closest strike >= Price (or slightly below if ATM)
    # Simple logic: Absolute closest
    closest_strike = min(strikes, key=lambda x: abs(x - price))
    return closest_strike

def get_option_price(stock, strike, option_type, timestamp):
    """Get option price at specific timestamp"""
    options_file = OPTIONS_DIR / "25NOV" / f"{stock}.csv"
    if not options_file.exists():
        options_file = OPTIONS_DIR / f"{stock}_25NOV.csv"
        
    df = pd.read_csv(options_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    symbol = f"NSE:{stock}25NOV{strike}{option_type}"
    row = df[(df['symbol'] == symbol) & (df['timestamp'] == timestamp)]
    
    if not row.empty:
        return row.iloc[0]['close']
    return None

def generate_option_table():
    logger.info("Generating Option Trade Table for Volume Rocket Signals...")
    
    # Load signals
    try:
        signals = pd.read_csv("volume_rocket_results.csv")
    except:
        logger.error("Please run scan_volume_rocket.py first!")
        return

    # Filter for top 50 signals to save time
    signals = signals.head(50)
    
    option_trades = []
    
    for i, row in signals.iterrows():
        stock = row['Stock']
        entry_time = pd.to_datetime(row['Entry Time'])
        exit_time = pd.to_datetime(row['Exit Time'])
        stock_entry = row['Entry Price']
        
        # 1. Select Strike (CE since it's a Long strategy)
        strike = find_closest_strike(stock, stock_entry, 'CE')
        if not strike:
            continue
            
        # 2. Get Premiums
        entry_premium = get_option_price(stock, strike, 'CE', entry_time)
        exit_premium = get_option_price(stock, strike, 'CE', exit_time)
        
        if entry_premium and exit_premium:
            pnl = ((exit_premium - entry_premium) / entry_premium) * 100
            
            option_trades.append({
                'Stock': stock,
                'Date': entry_time.strftime('%Y-%m-%d'),
                'Entry Time': entry_time.strftime('%H:%M'),
                'Exit Time': exit_time.strftime('%H:%M'),
                'Strike': strike,
                'Type': 'CE',
                'Entry Premium': entry_premium,
                'Exit Premium': exit_premium,
                'P&L %': pnl
            })
            
        print(f"Processed {i+1}/{len(signals)}...", end='\r')

    # Display Table
    if option_trades:
        df_opt = pd.DataFrame(option_trades)
        df_opt = df_opt.sort_values('P&L %', ascending=False)
        
        logger.info(f"\n{'='*120}")
        logger.info(f"VOLUME ROCKET - OPTION TRADE RESULTS")
        logger.info(f"{'='*120}")
        
        # Format
        df_display = df_opt.copy()
        df_display['Entry Premium'] = df_display['Entry Premium'].apply(lambda x: f"{x:.2f}")
        df_display['Exit Premium'] = df_display['Exit Premium'].apply(lambda x: f"{x:.2f}")
        df_display['P&L %'] = df_display['P&L %'].apply(lambda x: f"{x:.2f}%")
        
        print(df_display.to_string(index=False))
        
        # Save
        df_opt.to_csv("volume_rocket_options.csv", index=False)
        logger.success("Saved to 'volume_rocket_options.csv'")

if __name__ == "__main__":
    generate_option_table()
