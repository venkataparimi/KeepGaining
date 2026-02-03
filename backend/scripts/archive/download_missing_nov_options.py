"""
Download Missing Nov Options - For stocks that weren't downloaded yet
Uses direct symbol construction instead of symbol master
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime, timedelta
import pandas as pd
from app.brokers.fyers import FyersBroker
from loguru import logger
from scripts.fno_symbols import FNO_STOCKS

# Stock intervals (strike price gaps)
INTERVALS = {
    5: ['SBIN', 'ITC', 'TATAMOTORS', 'SAIL', 'VEDL', 'HINDALCO', 'COALINDIA'],
    10: ['RELIANCE', 'HDFCBANK', 'ICICIBANK', 'INFY', 'BHARTIARTL', 'WIPRO', 'AXISBANK'],
    25: ['KOTAKBANK', 'LT', 'MARUTI', 'TITAN', 'ADANIENT'],
    50: ['TCS', 'ULTRACEMCO', 'NESTLEIND'],
    100: ['MRF'],
}

def get_interval(stock_name):
    """Get strike interval for stock"""
    for interval, stocks in INTERVALS.items():
        if stock_name in stocks:
            return interval
    return 10  # Default

async def download_single_option(broker, symbol):
    """Download data for a single option contract - no retries for speed"""
    try:
        # Direct call without retries
        df = await broker.get_historical_data(
            symbol=symbol,
            resolution="1",
            start_date=datetime.now() - timedelta(days=60),
            end_date=datetime.now()
        )
        
        if not df.empty:
            return df
    except Exception as e:
        # Silently skip - many stocks don't have options
        pass
    
    return None

async def download_stock_options(broker, stock_name, interval, expiry="25NOV"):
    """Download all options for a specific stock"""
    
    # Get spot price from equity CSV
    try:
        csv_file = f"data_downloads/NSE_{stock_name}_EQ.csv"
        df = pd.read_csv(csv_file)
        spot = df['close'].iloc[-1]
    except:
        logger.warning(f"  ✗ No price data for {stock_name}")
        return None
    
    logger.info(f"  Spot: ₹{spot:,.2f}, Interval: {interval}")
    
    atm = round(spot / interval) * interval
    all_data = []
    
    # Download in batches of 10
    batch_size = 10
    strikes = []
    
    # Generate all strikes (-20 to +20)
    for i in range(-20, 21):
        strike = atm + (i * interval)
        for opt_type in ['CE', 'PE']:
            symbol = f"NSE:{stock_name}{expiry}{int(strike)}{opt_type}"
            strikes.append((symbol, strike, opt_type))
    
    # Download in batches
    for i in range(0, len(strikes), batch_size):
        batch = strikes[i:i+batch_size]
        
        tasks = [download_single_option(broker, s[0]) for s in batch]
        results = await asyncio.gather(*tasks)
        
        for j, df in enumerate(results):
            if df is not None:
                symbol, strike, opt_type = batch[j]
                df['symbol'] = symbol
                df['strike'] = strike
                df['option_type'] = opt_type
                df['underlying'] = stock_name
                df['expiry'] = expiry
                all_data.append(df)
        
        if len(all_data) % 50 == 0 and len(all_data) > 0:
            logger.info(f"  Progress: {len(all_data)} options downloaded...")
    
    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        return combined, len(all_data)
    
    return None, 0

async def main():
    OUTPUT_DIR = Path("options_data")
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    broker = FyersBroker()
    expiry = "25NOV"
    
    # Get list of stocks that need downloading
    existing_files = set([f.stem.replace('_25NOV', '') for f in OUTPUT_DIR.glob("*_25NOV.csv")])
    
    # Extract stock names from FNO_STOCKS
    all_stocks = []
    for symbol in FNO_STOCKS:
        stock_name = symbol.replace('NSE:', '').replace('-EQ', '')
        
        # Check if we have equity data
        csv_file = Path(f"data_downloads/NSE_{stock_name}_EQ.csv")
        if csv_file.exists() and stock_name not in existing_files:
            all_stocks.append({
                'name': stock_name,
                'interval': get_interval(stock_name)
            })
    
    logger.info("="*80)
    logger.info(f"DOWNLOADING MISSING NOV OPTIONS")
    logger.info(f"Already downloaded: {len(existing_files)} stocks")
    logger.info(f"Missing: {len(all_stocks)} stocks")
    logger.info("="*80)
    
    if len(all_stocks) == 0:
        logger.success("\n✓ All stocks already downloaded!")
        return
    
    total_candles = 0
    successful = 0
    
    for idx, stock in enumerate(all_stocks, 1):
        logger.info(f"\n[{idx}/{len(all_stocks)}] {stock['name']}")
        
        result = await download_stock_options(broker, stock['name'], stock['interval'], expiry)
        
        if result[0] is not None:
            combined, option_count = result
            filename = OUTPUT_DIR / f"{stock['name']}_25NOV.csv"
            combined.to_csv(filename, index=False)
            logger.success(f"  ✓ {len(combined):,} candles from {option_count} options")
            total_candles += len(combined)
            successful += 1
        else:
            logger.warning(f"  ✗ No options data found")
    
    logger.info("\n" + "="*80)
    logger.success(f"DOWNLOAD COMPLETE!")
    logger.success(f"Downloaded: {successful}/{len(all_stocks)} stocks")
    logger.success(f"Total candles: {total_candles:,}")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
