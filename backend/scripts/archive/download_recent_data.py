"""
Download Recent Stock and Options Data from Fyers

This script downloads:
1. Stock candle data (1-minute) for the past N days
2. Options data for the same period (for stocks with F&O)

The data is saved to:
- Stock data: data/ folder as CSV files
- Options data: data/ folder as <TICKER>_options.csv files
- Also loads into the database (candle_data table)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime, timedelta
import pandas as pd
import sqlite3
from app.brokers.fyers import FyersBroker
from loguru import logger
import requests

# Configuration
DAYS_BACK = 7  # Download last 7 days
DB_PATH = "keepgaining.db"
DATA_DIR = Path(__file__).parents[1] / "data"
SYMBOL_MASTER_URL = "https://public.fyers.in/sym_details/NSE_FO.csv"

# Major F&O stocks to download
FNO_STOCKS = [
    "NSE:SBIN-EQ", "NSE:RELIANCE-EQ", "NSE:TCS-EQ", "NSE:INFY-EQ", "NSE:HDFCBANK-EQ",
    "NSE:ICICIBANK-EQ", "NSE:KOTAKBANK-EQ", "NSE:AXISBANK-EQ", "NSE:BHARTIARTL-EQ",
    "NSE:ITC-EQ", "NSE:HINDUNILVR-EQ", "NSE:LT-EQ", "NSE:ASIANPAINT-EQ", "NSE:MARUTI-EQ",
    "NSE:TITAN-EQ", "NSE:SUNPHARMA-EQ", "NSE:WIPRO-EQ", "NSE:ULTRACEMCO-EQ", "NSE:NESTLEIND-EQ",
    "NSE:BAJFINANCE-EQ", "NSE:BAJAJFINSV-EQ", "NSE:HCLTECH-EQ", "NSE:POWERGRID-EQ",
    "NSE:NTPC-EQ", "NSE:ONGC-EQ", "NSE:TATAMOTORS-EQ", "NSE:TATASTEEL-EQ", "NSE:INDUSINDBK-EQ",
    "NSE:ADANIPORTS-EQ", "NSE:JSWSTEEL-EQ", "NSE:HEROMOTOCO-EQ", "NSE:BRITANNIA-EQ",
    "NSE:CIPLA-EQ", "NSE:DRREDDY-EQ", "NSE:EICHERMOT-EQ", "NSE:GRASIM-EQ", "NSE:HINDALCO-EQ",
    "NSE:TECHM-EQ", "NSE:COALINDIA-EQ", "NSE:BPCL-EQ", "NSE:IOC-EQ", "NSE:DIVISLAB-EQ",
    "NSE:TATACONSUM-EQ", "NSE:APOLLOHOSP-EQ", "NSE:BAJAJ-AUTO-EQ", "NSE:SHREECEM-EQ",
    "NSE:UPL-EQ", "NSE:VEDL-EQ", "NSE:ADANIENT-EQ", "NSE:ATGL-EQ", "NSE:DELHIVERY-EQ",
    "NSE:FEDERALBNK-EQ", "NSE:ABCAPITAL-EQ"
]

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators needed for Volume Rocket strategy"""
    df = df.copy()
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    sma20 = df['close'].rolling(window=20).mean()
    std20 = df['close'].rolling(window=20).std()
    df['bb_upper'] = sma20 + 2 * std20
    df['bb_lower'] = sma20 - 2 * std20
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    df['vol_ma'] = df['volume'].rolling(window=20).mean()
    return df

async def download_stock_data(broker: FyersBroker, symbol: str, start_date: datetime, end_date: datetime):
    """Download stock candle data"""
    try:
        df = await broker.get_historical_data(
            symbol=symbol,
            resolution="1",
            start_date=start_date,
            end_date=end_date
        )
        if not df.empty:
            df = calculate_indicators(df)
            df['symbol'] = symbol
            df['timeframe'] = '1m'
            return df
    except Exception as e:
        logger.error(f"Error downloading {symbol}: {e}")
    return None

async def download_options_for_stock(broker: FyersBroker, ticker: str, start_date: datetime, end_date: datetime):
    """Download all options for a given stock ticker"""
    try:
        # Get symbol master for options
        response = requests.get(SYMBOL_MASTER_URL)
        master_df = pd.read_csv(pd.io.common.StringIO(response.text), header=None)
        
        # Filter for this stock's options (current month expiry)
        # Assuming December 2025 expiry (25DEC)
        current_expiry = "25DEC"
        stock_options = master_df[
            (master_df[13] == ticker) &  # Underlying
            (master_df[9].str.contains(current_expiry, na=False))  # Expiry
        ]
        
        if stock_options.empty:
            logger.warning(f"No options found for {ticker}")
            return None
        
        all_option_data = []
        
        # Download each option contract
        for _, row in stock_options.iterrows():
            option_symbol = row[9]  # e.g., NSE:SBIN25DEC780CE
            strike = row[15]
            opt_type = row[16]  # CE or PE
            
            try:
                df = await broker.get_historical_data(
                    symbol=option_symbol,
                    resolution="1",
                    start_date=start_date,
                    end_date=end_date
                )
                
                if not df.empty:
                    df['symbol'] = option_symbol
                    df['strike'] = strike
                    df['type'] = opt_type
                    df['underlying'] = ticker
                    # Rename 'close' to 'premium' for options
                    df['premium'] = df['close']
                    all_option_data.append(df[['timestamp', 'strike', 'type', 'premium', 'underlying']])
                    
                await asyncio.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                logger.debug(f"Could not download {option_symbol}: {e}")
                continue
        
        if all_option_data:
            combined = pd.concat(all_option_data, ignore_index=True)
            return combined
            
    except Exception as e:
        logger.error(f"Error downloading options for {ticker}: {e}")
    
    return None

def save_to_database(df: pd.DataFrame, symbol: str):
    """Save stock data to database"""
    conn = sqlite3.connect(DB_PATH)
    try:
        # Remove old data for this symbol in the date range
        min_date = df['timestamp'].min()
        max_date = df['timestamp'].max()
        
        conn.execute(
            "DELETE FROM candle_data WHERE symbol = ? AND timestamp BETWEEN ? AND ?",
            (symbol, min_date, max_date)
        )
        
        # Insert new data
        df.to_sql('candle_data', conn, if_exists='append', index=False)
        logger.success(f"  ✓ Saved {len(df)} candles to database")
    finally:
        conn.close()

async def main():
    logger.info("=" * 80)
    logger.info("DOWNLOADING RECENT STOCK AND OPTIONS DATA FROM FYERS")
    logger.info("=" * 80)
    logger.info(f"Period: Last {DAYS_BACK} days")
    logger.info(f"Stocks: {len(FNO_STOCKS)}")
    logger.info("")
    
    DATA_DIR.mkdir(exist_ok=True)
    broker = FyersBroker()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=DAYS_BACK)
    
    successful_stocks = 0
    successful_options = 0
    
    for idx, symbol in enumerate(FNO_STOCKS, 1):
        ticker = symbol.replace('NSE:', '').replace('-EQ', '')
        logger.info(f"[{idx}/{len(FNO_STOCKS)}] {ticker}")
        
        # Download stock data
        stock_df = await download_stock_data(broker, symbol, start_date, end_date)
        
        if stock_df is not None:
            # Save to CSV
            csv_path = DATA_DIR / f"{ticker}.csv"
            stock_df.to_csv(csv_path, index=False)
            logger.success(f"  ✓ Stock: {len(stock_df)} candles saved to {csv_path.name}")
            
            # Save to database
            save_to_database(stock_df, symbol)
            successful_stocks += 1
        else:
            logger.warning(f"  ✗ No stock data")
            continue
        
        # Download options data
        options_df = await download_options_for_stock(broker, ticker, start_date, end_date)
        
        if options_df is not None:
            # Save to CSV
            options_csv_path = DATA_DIR / f"{ticker}_options.csv"
            options_df.to_csv(options_csv_path, index=False)
            logger.success(f"  ✓ Options: {len(options_df)} records from {options_df['strike'].nunique()} strikes saved to {options_csv_path.name}")
            successful_options += 1
        else:
            logger.warning(f"  ✗ No options data")
        
        await asyncio.sleep(0.5)  # Rate limiting between stocks
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("DOWNLOAD COMPLETE")
    logger.info("=" * 80)
    logger.success(f"Stock data: {successful_stocks}/{len(FNO_STOCKS)} symbols")
    logger.success(f"Options data: {successful_options}/{len(FNO_STOCKS)} symbols")
    logger.info(f"Data saved to: {DATA_DIR}")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Run backfill_stock_and_options.py to analyze Volume Rocket signals")
    logger.info("2. Or run backtest_volume_rocket_fixed_entry.py for 09:16+ entry analysis")

if __name__ == "__main__":
    asyncio.run(main())
