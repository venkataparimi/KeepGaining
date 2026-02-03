"""
Universal Options Data Downloader
- Uses Fyers NSE_FO symbol master to get all available options
- Downloads current and future expiries automatically
- No hardcoded expiry dates
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

async def download_single_option(broker, symbol):
    """Download data for a single option contract"""
    try:
        df = await broker.get_historical_data(
            symbol=symbol,
            resolution="1",
            start_date=datetime.now() - timedelta(days=60),
            end_date=datetime.now()
        )
        if not df.empty:
            return df
    except:
        pass
    return None

async def download_stock_options(broker, stock_name, options_df, expiry_label):
    """Download all options for a specific stock and expiry"""
    stock_options = options_df[options_df[13] == stock_name]
    
    if stock_options.empty:
        return None, 0
    
    logger.info(f"  {expiry_label}: {len(stock_options)} contracts")
    
    all_data = []
    batch_size = 10
    
    for i in range(0, len(stock_options), batch_size):
        batch = stock_options.iloc[i:i+batch_size]
        tasks = [download_single_option(broker, row[9]) for _, row in batch.iterrows()]
        results = await asyncio.gather(*tasks)
        
        for j, df in enumerate(results):
            if df is not None:
                row = batch.iloc[j]
                df['symbol'] = row[9]
                df['strike'] = row[15]
                df['option_type'] = row[16]
                df['underlying'] = stock_name
                df['expiry'] = expiry_label
                all_data.append(df)
    
    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        return combined, len(all_data)
    
    return None, 0

async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    logger.info("="*80)
    logger.info("UNIVERSAL OPTIONS DATA DOWNLOADER")
    logger.info("="*80)
    
    # Download symbol master
    logger.info("\nDownloading Fyers NSE_FO symbol master...")
    response = requests.get(SYMBOL_MASTER_URL)
    master_file = Path("fyers_nse_fo_master.csv")
    master_file.write_text(response.text)
    
    # Parse CSV
    df = pd.read_csv(master_file, header=None)
    
    # Filter for options only (has strike price)
    options_df = df[df[15].notna()]  # Column 15 is strike price
    
    logger.info(f"Found {len(options_df)} option contracts")
    
    # Get unique expiries
    expiry_symbols = options_df[9].unique()
    expiries = set()
    for sym in expiry_symbols:
        # Extract expiry from symbol like NSE:SBIN25NOV780CE
        parts = sym.split(':')[1] if ':' in sym else sym
        # Find the expiry pattern (e.g., 25NOV, 25DEC)
        import re
        match = re.search(r'(\d{2}[A-Z]{3})', parts)
        if match:
            expiries.add(match.group(1))
    
    expiries = sorted(list(expiries))
    logger.info(f"Available expiries: {', '.join(expiries)}")
    
    # Get unique stocks
    stocks = options_df[13].unique()
    logger.info(f"Stocks with options: {len(stocks)}\n")
    
    broker = FyersBroker()
    
    # Download for each stock and expiry
    total_candles = 0
    successful_stocks = 0
    
    for idx, stock in enumerate(sorted(stocks), 1):
        logger.info(f"[{idx}/{len(stocks)}] {stock}")
        
        stock_data_all_expiries = []
        
        # Download all expiries for this stock
        for expiry in expiries:
            # Filter options for this stock and expiry
            expiry_options = options_df[
                (options_df[13] == stock) & 
                (options_df[9].str.contains(expiry, na=False))
            ]
            
            if len(expiry_options) == 0:
                continue
            
            result, option_count = await download_stock_options(broker, stock, expiry_options, expiry)
            
            if result is not None:
                stock_data_all_expiries.append(result)
        
        # Save combined data for all expiries
        if stock_data_all_expiries:
            combined = pd.concat(stock_data_all_expiries, ignore_index=True)
            
            # Check for existing expiry-specific files and merge
            existing_files = list(OUTPUT_DIR.glob(f"{stock}_*.csv"))
            for old_file in existing_files:
                if old_file.name != f"{stock}_options.csv":  # Don't merge with self
                    try:
                        old_data = pd.read_csv(old_file)
                        logger.info(f"  Merging {old_file.name} ({len(old_data):,} rows)")
                        combined = pd.concat([combined, old_data], ignore_index=True)
                        # Remove duplicates based on symbol and timestamp
                        combined = combined.drop_duplicates(subset=['symbol', 'timestamp'], keep='last')
                    except Exception as e:
                        logger.warning(f"  Could not merge {old_file.name}: {e}")
            
            filename = OUTPUT_DIR / f"{stock}_options.csv"
            combined.to_csv(filename, index=False)
            logger.success(f"  ✓ {len(combined):,} candles saved")
            
            # Archive old files (rename with .old extension)
            for old_file in existing_files:
                if old_file.name != f"{stock}_options.csv":
                    try:
                        old_file.rename(old_file.with_suffix('.csv.old'))
                        logger.info(f"  Archived {old_file.name}")
                    except:
                        pass
            
            total_candles += len(combined)
            successful_stocks += 1
        else:
            logger.warning(f"  ✗ No data")
    
    logger.info("\n" + "="*80)
    logger.success("DOWNLOAD COMPLETE!")
    logger.success(f"Stocks: {successful_stocks}/{len(stocks)}")
    logger.success(f"Total candles: {total_candles:,}")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
