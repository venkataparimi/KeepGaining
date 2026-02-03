"""
Download Options Data Using Fyers Symbol Master
Automatically identifies which stocks have options by parsing the symbol master file
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime, timedelta
import pandas as pd
import requests
from app.brokers.fyers import FyersBroker
from loguru import logger

OUTPUT_DIR = Path("options_data")
SYMBOL_MASTER_URL = "https://public.fyers.in/sym_details/NSE_FO.csv"

def download_symbol_master():
    """Download and parse Fyers symbol master to find stocks with options"""
    logger.info("Downloading Fyers symbol master...")
    
    response = requests.get(SYMBOL_MASTER_URL)
    
    # Save to file
    master_file = Path("fyers_symbol_master.csv")
    master_file.write_text(response.text)
    
    # Parse CSV
    df = pd.read_csv(master_file, header=None)
    
    # Column 9 has the Fyers symbol (e.g., NSE:SBIN25NOV780CE)
    # Column 13 has the underlying name (e.g., SBIN)
    # Column 16 has option type (CE/PE)
    
    # Filter for Nov 25 expiry options only
    options_df = df[df[9].str.contains('25NOV', na=False)]
    
    # Get unique underlying stocks
    stocks_with_options = options_df[13].unique().tolist()
    
    logger.success(f"Found {len(stocks_with_options)} stocks with Nov 25 options")
    
    return stocks_with_options, options_df

async def download_single_option(broker, row, stock_name, expiry):
    """Download data for a single option contract"""
    fyers_symbol = row[9]
    strike = row[15]
    opt_type = row[16]
    
    try:
        df = await broker.get_historical_data(
            symbol=fyers_symbol,
            resolution="1",
            start_date=datetime.now() - timedelta(days=60),
            end_date=datetime.now()
        )
        
        if not df.empty:
            df['symbol'] = fyers_symbol
            df['strike'] = strike
            df['option_type'] = opt_type
            df['underlying'] = stock_name
            df['expiry'] = expiry
            return df
    except:
        pass
    
    return None

async def download_stock_options(broker, stock_name, options_df, expiry="25NOV"):
    """Download all options for a specific stock using parallel downloads"""
    stock_options = options_df[options_df[13] == stock_name]
    
    if stock_options.empty:
        return None
    
    logger.info(f"\n{'='*60}")
    logger.info(f"{stock_name}: {len(stock_options)} option contracts")
    logger.info(f"{'='*60}")
    
    # Download in batches of 5 (optimal for 10 req/sec rate limit)
    batch_size = 50
    all_data = []
    
    for i in range(0, len(stock_options), batch_size):
        batch = stock_options.iloc[i:i+batch_size]
        
        # Download batch in parallel
        tasks = [download_single_option(broker, row, stock_name, expiry) 
                 for _, row in batch.iterrows()]
        results = await asyncio.gather(*tasks)
        
        # Collect successful downloads
        for df in results:
            if df is not None:
                all_data.append(df)
        
        
        if len(all_data) % 50 == 0 and len(all_data) > 0:
            logger.info(f"  Progress: {len(all_data)} options downloaded...")
    
    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        filename = OUTPUT_DIR / f"{stock_name}_25NOV.csv"
        combined.to_csv(filename, index=False)
        logger.success(f"✓ {stock_name}: {len(combined):,} candles from {len(all_data)} options")
        return len(combined)
    
    return None

async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    logger.info("="*80)
    logger.info("DOWNLOADING OPTIONS DATA USING FYERS SYMBOL MASTER")
    logger.info("="*80)
    
    # Download and parse symbol master
    stocks_with_options, options_df = download_symbol_master()
    
    broker = FyersBroker()
    
    total_candles = 0
    successful_stocks = 0
    
    for idx, stock in enumerate(stocks_with_options, 1):
        logger.info(f"\n[{idx}/{len(stocks_with_options)}] {stock}")
        
        # Check if already downloaded
        filename = OUTPUT_DIR / f"{stock}_25NOV.csv"
        if filename.exists():
            logger.info(f"  ✓ Already downloaded, skipping...")
            continue
        
        candles = await download_stock_options(broker, stock, options_df)
        
        if candles:
            total_candles += candles
            successful_stocks += 1
    
    logger.info("\n" + "="*80)
    logger.success(f"DOWNLOAD COMPLETE!")
    logger.success(f"Stocks: {successful_stocks}/{len(stocks_with_options)}")
    logger.success(f"Total candles: {total_candles:,}")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
