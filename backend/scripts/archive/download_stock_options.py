"""Download comprehensive stock options - 20 strikes each side"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime, timedelta
import pandas as pd
from app.brokers.fyers import FyersBroker
from loguru import logger

# Top 10 F&O stocks - will get live prices
STOCKS = [
    {"symbol": "NSE:SBIN-EQ", "name": "SBIN", "interval": 5},
    {"symbol": "NSE:RELIANCE-EQ", "name": "RELIANCE", "interval": 10},
    {"symbol": "NSE:ICICIBANK-EQ", "name": "ICICIBANK", "interval": 10},
    {"symbol": "NSE:ITC-EQ", "name": "ITC", "interval": 5},
    {"symbol": "NSE:HDFCBANK-EQ", "name": "HDFCBANK", "interval": 10},
    {"symbol": "NSE:INFY-EQ", "name": "INFY", "interval": 10},
    {"symbol": "NSE:TCS-EQ", "name": "TCS", "interval": 50},
    {"symbol": "NSE:BHARTIARTL-EQ", "name": "BHARTIARTL", "interval": 10},
    {"symbol": "NSE:KOTAKBANK-EQ", "name": "KOTAKBANK", "interval": 25},
    {"symbol": "NSE:LT-EQ", "name": "LT", "interval": 25},
]

async def get_live_price(broker, symbol, stock_name):
    """Get current price from CSV data"""
    try:
        # Read from downloaded CSV
        csv_file = f"data_downloads/{symbol.replace(':', '_')}.csv"
        df = pd.read_csv(csv_file)
        if not df.empty:
            price = df['close'].iloc[-1]
            logger.info(f"  Got price from CSV: ₹{price:,.2f}")
            return price
    except Exception as e:
        # Fallback prices (approximate as of Nov 25, 2025)
        fallback = {
            'SBIN': 780, 'RELIANCE': 1280, 'ICICIBANK': 1280,
            'ITC': 475, 'HDFCBANK': 1750, 'INFY': 1850,
            'TCS': 4100, 'BHARTIARTL': 1650, 'KOTAKBANK': 1750, 'LT': 3600
        }
        if stock_name in fallback:
            logger.info(f"  Using fallback price: ₹{fallback[stock_name]:,.2f}")
            return fallback[stock_name]
    return None

async def main():
    OUTPUT_DIR = Path("options_data")
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    broker = FyersBroker()
    expiry = "25NOV"
    
    logger.info("="*80)
    logger.info("DOWNLOADING STOCK OPTIONS - 20 STRIKES EACH SIDE")
    logger.info("="*80)
    
    for stock in STOCKS:
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing {stock['name']}")
        logger.info(f"{'='*80}")
        
        # Get live price
        spot = await get_live_price(broker, stock['symbol'], stock['name'])
        
        if not spot:
            logger.warning(f"  Skipping {stock['name']} - no price data")
            continue
        
        logger.info(f"  Spot Price: ₹{spot:,.2f}")
        
        # Calculate ATM
        atm = round(spot / stock['interval']) * stock['interval']
        logger.info(f"  ATM Strike: {atm}")
        
        all_data = []
        success_count = 0
        
        # 20 strikes on each side: -20 to +20
        for i in range(-20, 21):
            strike = atm + (i * stock['interval'])
            
            for opt_type in ['CE', 'PE']:
                symbol = f"NSE:{stock['name']}{expiry}{int(strike)}{opt_type}"
                
                try:
                    df = await broker.get_historical_data(
                        symbol=symbol,
                        resolution="1",
                        start_date=datetime.now() - timedelta(days=7),
                        end_date=datetime.now()
                    )
                    
                    if not df.empty:
                        df['symbol'] = symbol
                        df['strike'] = strike
                        df['option_type'] = opt_type
                        df['underlying'] = stock['name']
                        df['expiry'] = expiry
                        df['atm_distance'] = i
                        all_data.append(df)
                        success_count += 1
                        
                        if success_count % 10 == 0:
                            logger.info(f"  Progress: {success_count} options downloaded...")
                    
                    await asyncio.sleep(0.15)  # Rate limiting
                    
                except Exception as e:
                    # Silently skip errors to avoid spam
                    pass
        
        if all_data:
            combined = pd.concat(all_data, ignore_index=True)
            filename = OUTPUT_DIR / f"{stock['name']}_{expiry}.csv"
            combined.to_csv(filename, index=False)
            logger.success(f"\n✓ {stock['name']}: {len(combined):,} candles from {len(all_data)} options")
        else:
            logger.warning(f"\n✗ {stock['name']}: No data downloaded")
    
    logger.info("\n" + "="*80)
    logger.success("STOCK OPTIONS DOWNLOAD COMPLETE!")
    logger.info(f"Data saved to: {OUTPUT_DIR}/")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
