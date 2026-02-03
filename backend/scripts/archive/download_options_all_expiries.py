"""
Options Data Downloader - All Expiries
Downloads options for all available expiries, saves each expiry separately
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

async def download_single_option_range(broker, symbol, start_date):
    """Download option data from specific start date"""
    try:
        df = await broker.get_historical_data(
            symbol=symbol,
            resolution="1",
            start_date=start_date,
            end_date=datetime.now()
        )
        if not df.empty:
            return df
    except:
        pass
    return None

async def download_expiry_options(broker, stock_name, options_df, expiry_label):
    """Download all options for a specific stock and expiry"""
    all_data = []
    batch_size = 10
    
    for i in range(0, len(options_df), batch_size):
        batch = options_df.iloc[i:i+batch_size]
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
    logger.info("OPTIONS DATA DOWNLOADER - ALL EXPIRIES")
    logger.info("="*80)
    
    # Download symbol master
    logger.info("\nDownloading Fyers NSE_FO symbol master...")
    response = requests.get(SYMBOL_MASTER_URL)
    df = pd.read_csv(pd.io.common.StringIO(response.text), header=None)
    
    # Filter for options
    options_df = df[df[15].notna()]
    logger.info(f"Found {len(options_df)} option contracts")
    
    # Extract unique expiries
    import re
    expiries = set()
    for sym in options_df[9].unique():
        match = re.search(r'(\d{2}[A-Z]{3})', sym)
        if match:
            expiries.add(match.group(1))
    
    expiries = sorted(list(expiries))
    logger.info(f"Available expiries: {', '.join(expiries)}")
    
    # Get unique stocks
    stocks = sorted(options_df[13].unique())
    logger.info(f"Stocks with options: {len(stocks)}\n")
    
    broker = FyersBroker()
    total_files = 0
    total_candles = 0
    
    for idx, stock in enumerate(stocks, 1):
        logger.info(f"[{idx}/{len(stocks)}] {stock}")
        
        for expiry in expiries:
            # Create expiry folder
            expiry_dir = OUTPUT_DIR / expiry
            expiry_dir.mkdir(exist_ok=True)
            
            filename = expiry_dir / f"{stock}.csv"
            
            # Check if file exists and needs backfill
            start_date = datetime.now() - timedelta(days=60)
            backfill_mode = False
            
            if filename.exists():
                try:
                    existing_df = pd.read_csv(filename)
                    if len(existing_df) > 0:
                        last_timestamp = pd.to_datetime(existing_df['timestamp'].max())
                        days_missing = (datetime.now() - last_timestamp).days
                        
                        if days_missing <= 1:
                            logger.info(f"  {expiry}: ✓ Up to date")
                            continue
                        else:
                            logger.info(f"  {expiry}: Backfill {days_missing} days")
                            start_date = last_timestamp + timedelta(days=1)
                            backfill_mode = True
                except Exception as e:
                    logger.warning(f"  {expiry}: Error reading file, re-downloading")
            
            # Filter options for this stock and expiry
            expiry_options = options_df[
                (options_df[13] == stock) & 
                (options_df[9].str.contains(expiry, na=False))
            ]
            
            if len(expiry_options) == 0:
                continue
            
            if not backfill_mode:
                logger.info(f"  {expiry}: {len(expiry_options)} contracts (new)")
            
            # Download with custom date range
            all_data = []
            batch_size = 10
            
            for i in range(0, len(expiry_options), batch_size):
                batch = expiry_options.iloc[i:i+batch_size]
                tasks = []
                for _, row in batch.iterrows():
                    tasks.append(download_single_option_range(broker, row[9], start_date))
                results = await asyncio.gather(*tasks)
                
                for j, df in enumerate(results):
                    if df is not None:
                        row = batch.iloc[j]
                        df['symbol'] = row[9]
                        df['strike'] = row[15]
                        df['option_type'] = row[16]
                        df['underlying'] = stock
                        df['expiry'] = expiry
                        all_data.append(df)
            
            if all_data:
                new_data = pd.concat(all_data, ignore_index=True)
                
                if backfill_mode:
                    # Merge with existing data
                    combined = pd.concat([existing_df, new_data], ignore_index=True)
                    combined = combined.drop_duplicates(subset=['symbol', 'timestamp'], keep='last')
                    combined = combined.sort_values('timestamp')
                    combined.to_csv(filename, index=False)
                    logger.success(f"  {expiry}: ✓ Added {len(new_data):,} candles (total: {len(combined):,})")
                else:
                    new_data.to_csv(filename, index=False)
                    logger.success(f"  {expiry}: ✓ {len(new_data):,} candles")
                
                total_files += 1
                total_candles += len(new_data)
            else:
                logger.warning(f"  {expiry}: ✗ No data")
    
    logger.info("\n" + "="*80)
    logger.success("DOWNLOAD COMPLETE!")
    logger.success(f"Files created: {total_files}")
    logger.success(f"Total candles: {total_candles:,}")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
