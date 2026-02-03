"""
Download Missing Nov Options - Using Dec Symbol Master
Downloads Fyers Dec symbol master and replaces 25DEC with 25NOV
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

async def main():
    OUTPUT_DIR = Path("options_data")
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    logger.info("="*80)
    logger.info("DOWNLOADING MISSING NOV OPTIONS")
    logger.info("="*80)
    
    # Download Dec symbol master
    logger.info("\nDownloading Dec symbol master...")
    response = requests.get(SYMBOL_MASTER_URL)
    master_file = Path("fyers_symbol_master_dec.csv")
    master_file.write_text(response.text)
    
    # Parse and convert Dec to Nov
    df = pd.read_csv(master_file, header=None)
    
    # Filter for Dec options
    dec_options = df[df[9].str.contains('25DEC', na=False)]
    logger.info(f"Found {len(dec_options)} Dec option contracts")
    
    # Convert to Nov symbols
    nov_symbols = []
    for _, row in dec_options.iterrows():
        dec_symbol = row[9]  # e.g., NSE:SBIN25DEC780CE
        nov_symbol = dec_symbol.replace('25DEC', '25NOV')
        underlying = row[13]
        strike = row[15]
        opt_type = row[16]
        
        nov_symbols.append({
            'symbol': nov_symbol,
            'underlying': underlying,
            'strike': strike,
            'option_type': opt_type
        })
    
    logger.info(f"Converted to {len(nov_symbols)} Nov symbols")
    
    # Get already downloaded stocks
    existing = set([f.stem.replace('_25NOV', '') for f in OUTPUT_DIR.glob("*_25NOV.csv")])
    logger.info(f"Already downloaded: {len(existing)} stocks")
    
    # Group by underlying
    nov_df = pd.DataFrame(nov_symbols)
    grouped = nov_df.groupby('underlying')
    
    missing_stocks = [stock for stock in grouped.groups.keys() if stock not in existing]
    logger.info(f"Missing: {len(missing_stocks)} stocks\n")
    
    if len(missing_stocks) == 0:
        logger.success("✓ All stocks already downloaded!")
        return
    
    broker = FyersBroker()
    successful = 0
    
    for idx, stock in enumerate(missing_stocks, 1):
        logger.info(f"[{idx}/{len(missing_stocks)}] {stock}")
        
        stock_options = nov_df[nov_df['underlying'] == stock]
        all_data = []
        
        # Download in batches
        batch_size = 10
        symbols_list = stock_options['symbol'].tolist()
        
        for i in range(0, len(symbols_list), batch_size):
            batch = symbols_list[i:i+batch_size]
            tasks = [download_single_option(broker, sym) for sym in batch]
            results = await asyncio.gather(*tasks)
            
            for j, df in enumerate(results):
                if df is not None:
                    row = stock_options.iloc[i+j]
                    df['symbol'] = row['symbol']
                    df['strike'] = row['strike']
                    df['option_type'] = row['option_type']
                    df['underlying'] = stock
                    df['expiry'] = '25NOV'
                    all_data.append(df)
        
        if all_data:
            combined = pd.concat(all_data, ignore_index=True)
            filename = OUTPUT_DIR / f"{stock}_25NOV.csv"
            combined.to_csv(filename, index=False)
            logger.success(f"  ✓ {len(combined):,} candles from {len(all_data)} options")
            successful += 1
        else:
            logger.warning(f"  ✗ No data")
    
    logger.info("\n" + "="*80)
    logger.success(f"Downloaded: {successful}/{len(missing_stocks)} stocks")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
