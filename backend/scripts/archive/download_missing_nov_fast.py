"""
Download Missing Nov Options - FAST VERSION
Only tries stocks that are known to have options contracts
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime, timedelta
import pandas as pd
from app.brokers.fyers import FyersBroker
from loguru import logger

# Comprehensive list of stocks likely to have options
# Based on NSE F&O stocks with high liquidity
STOCKS_WITH_OPTIONS = [
    # Nifty 50 stocks
    'SBIN', 'RELIANCE', 'ICICIBANK', 'ITC', 'HDFCBANK', 'INFY', 'TCS',
    'BHARTIARTL', 'KOTAKBANK', 'LT', 'AXISBANK', 'WIPRO', 'TATAMOTORS',
    'TATASTEEL', 'MARUTI', 'TITAN', 'ADANIENT', 'HINDALCO', 'COALINDIA',
    'VEDL', 'SAIL', 'ULTRACEMCO', 'BAJFINANCE', 'BAJAJFINSV', 'ASIANPAINT',
    'HCLTECH', 'TECHM', 'SUNPHARMA', 'DRREDDY', 'CIPLA', 'DIVISLAB',
    'M&M', 'EICHERMOT', 'HEROMOTOCO', 'POWERGRID', 'NTPC', 'ONGC',
    'BPCL', 'IOC', 'GAIL', 'INDUSINDBK', 'BANDHANBNK',
    
    # Other liquid F&O stocks
    'GODREJCP', 'GODREJPROP', 'GRASIM', 'HAL', 'INDIANB', 'INDUSTOWER',
    'LTIM', 'LUPIN', 'MANAPPURAM', 'MANKIND', 'MARICO', 'MAXHEALTH',
    'MAZDOCK', 'MCX', 'MFSL', 'MOTHERSON', 'MPHASIS', 'MUTHOOTFIN',
    'FORTIS', 'GLENMARK', 'GMRAIRPORT', 'LTF', 'CYIENT', 'DELHIVERY',
    'DMART', 'CAMS', 'CDSL', 'CGPOWER', 'ANGELONE', 'APLAPOLLO',
    
    # Bank stocks
    'FEDERALBNK', 'IDFCFIRSTB', 'PNB', 'CANBK', 'BANKBARODA',
    
    # Auto stocks
    'ASHOKLEY', 'TVSMOTOR', 'ESCORTS', 'APOLLOTYRE', 'BALKRISIND',
    
    # IT stocks
    'PERSISTENT', 'COFORGE', 'MPHASIS',
    
    # Pharma stocks
    'BIOCON', 'TORNTPHARM', 'ALKEM', 'LAURUSLABS',
    
    # Realty stocks
    'DLF', 'OBEROIRLTY', 'PHOENIXLTD',
    
    # Others
    'JINDALSTEL', 'JSWSTEEL', 'HINDZINC', 'NATIONALUM', 'VEDL',
    'TATACOMM', 'TATACONSUM', 'TATAPOWER', 'VOLTAS', 'HAVELLS',
    'PIIND', 'SIEMENS', 'ABB', 'BOSCHLTD', 'CUMMINSIND',
    'ADANIPORTS', 'ADANIPOWER', 'ADANIGREEN', 'ADANIENSOL',
    'AMBUJACEM', 'ACC', 'SHREECEM', 'RAMCOCEM', 'JKCEMENT', 'STARCEMENT',
    'BERGEPAINT', 'PIDILITIND', 'ASTRAL',
    'BRITANNIA', 'NESTLEIND', 'DABUR', 'MARICO', 'COLPAL',
    'ZEEL', 'PVR', 'SUNTV',
    'RECLTD', 'PFC', 'LICHSGFIN', 'CHOLAFIN', 'MUTHOOTFIN',
    'PAGEIND', 'NAUKRI', 'ZOMATO', 'PAYTM',
    'IRCTC', 'CONCOR', 'IRFC',
    'ABCAPITAL', 'ABFRL', 'AUROPHARMA', 'BALKRISIND', 'BEL',
    'CHAMBLFERT', 'COROMANDEL', 'CROMPTON', 'DEEPAKNTR',
    'DIXON', 'EXIDEIND', 'GUJGASLTD', 'ICICIGI', 'ICICIPRULI',
    'IDEA', 'IGL', 'INDHOTEL', 'JUBLFOOD', 'KALYANKJIL',
    'LICI', 'LODHA', 'MRF', 'NAVINFLUOR', 'OFSS',
    'PETRONET', 'POLYCAB', 'RAIN', 'SBICARD', 'SBILIFE',
    'SRF', 'TRENT', 'TORNTPOWER', 'UPL', 'ZYDUSLIFE'
]

INTERVALS = {
    5: ['SBIN', 'ITC', 'TATAMOTORS', 'SAIL', 'VEDL', 'HINDALCO', 'COALINDIA'],
    10: ['RELIANCE', 'HDFCBANK', 'ICICIBANK', 'INFY', 'BHARTIARTL', 'WIPRO', 'AXISBANK'],
    25: ['KOTAKBANK', 'LT', 'MARUTI', 'TITAN', 'ADANIENT'],
    50: ['TCS', 'ULTRACEMCO'],
    100: ['MRF'],
}

def get_interval(stock_name):
    for interval, stocks in INTERVALS.items():
        if stock_name in stocks:
            return interval
    return 10

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

async def download_stock_options(broker, stock_name, interval, expiry="25NOV"):
    try:
        csv_file = f"data_downloads/NSE_{stock_name}_EQ.csv"
        df = pd.read_csv(csv_file)
        spot = df['close'].iloc[-1]
    except:
        return None, 0
    
    atm = round(spot / interval) * interval
    all_data = []
    strikes = []
    
    for i in range(-20, 21):
        strike = atm + (i * interval)
        for opt_type in ['CE', 'PE']:
            symbol = f"NSE:{stock_name}{expiry}{int(strike)}{opt_type}"
            strikes.append((symbol, strike, opt_type))
    
    # Download in batches
    batch_size = 10
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
    
    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        return combined, len(all_data)
    
    return None, 0

async def main():
    OUTPUT_DIR = Path("options_data")
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    broker = FyersBroker()
    expiry = "25NOV"
    
    # Get missing stocks
    existing = set([f.stem.replace('_25NOV', '') for f in OUTPUT_DIR.glob("*_25NOV.csv")])
    
    missing_stocks = []
    for stock in STOCKS_WITH_OPTIONS:
        csv_file = Path(f"data_downloads/NSE_{stock}_EQ.csv")
        if csv_file.exists() and stock not in existing:
            missing_stocks.append({
                'name': stock,
                'interval': get_interval(stock)
            })
    
    logger.info("="*80)
    logger.info(f"DOWNLOADING MISSING NOV OPTIONS (FAST)")
    logger.info(f"Missing: {len(missing_stocks)} stocks")
    logger.info("="*80)
    
    if len(missing_stocks) == 0:
        logger.success("\n✓ All stocks downloaded!")
        return
    
    successful = 0
    for idx, stock in enumerate(missing_stocks, 1):
        logger.info(f"\n[{idx}/{len(missing_stocks)}] {stock['name']}")
        
        result = await download_stock_options(broker, stock['name'], stock['interval'], expiry)
        
        if result[0] is not None:
            combined, option_count = result
            filename = OUTPUT_DIR / f"{stock['name']}_25NOV.csv"
            combined.to_csv(filename, index=False)
            logger.success(f"  ✓ {len(combined):,} candles from {option_count} options")
            successful += 1
        else:
            logger.warning(f"  ✗ No data")
    
    logger.info("\n" + "="*80)
    logger.success(f"Downloaded: {successful}/{len(missing_stocks)} stocks")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
