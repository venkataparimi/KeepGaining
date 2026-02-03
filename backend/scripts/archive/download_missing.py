"""
Download missing symbols only
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger
from app.brokers.fyers import FyersBroker
from app.services.indicator_computation import IndicatorComputationService

# Missing symbols
MISSING_SYMBOLS = [
    "NSE:DALMIABHART-EQ",
    "NSE:GMRINFRA-EQ",
    "NSE:M&M-EQ",
    "NSE:NIFTYFIN-INDEX",
    "NSE:NIFTYOILGAS-INDEX",
    "NSE:PEL-EQ",
    "NSE:TATAMOTORS-EQ",
    "NSE:ZOMATO-EQ",
]

DATA_DIR = Path("data_downloads")
DATA_DIR.mkdir(exist_ok=True)


async def download_symbol(broker: FyersBroker, symbol: str, from_date: datetime, to_date: datetime):
    """Download data for one symbol"""
    try:
        logger.info(f"Downloading {symbol}...")
        
        # Fetch data
        df = await broker.get_historical_data(
            symbol=symbol,
            resolution="1",
            start_date=from_date,
            end_date=to_date
        )
        
        if df.empty:
            logger.warning(f"No data for {symbol}")
            return
        
        # Add symbol and timeframe columns
        df['symbol'] = symbol
        df['timeframe'] = '1m'
        
        # Rename columns to match our schema
        df = df.rename(columns={'datetime': 'timestamp'})
        
        # Compute basic indicators
        indicator_service = IndicatorComputationService()
        df['sma_20'] = indicator_service._compute_sma(df['close'], 20)
        df['sma_50'] = indicator_service._compute_sma(df['close'], 50)
        df['ema_9'] = indicator_service._compute_ema(df['close'], 9)
        df['ema_21'] = indicator_service._compute_ema(df['close'], 21)
        df['vwma_20'] = indicator_service._compute_vwma(df['close'], df['volume'], 20)
        
        # Save to CSV
        filename = symbol.replace(":", "_").replace("-", "_").replace("&", "")
        csv_path = DATA_DIR / f"{filename}.csv"
        df.to_csv(csv_path, index=False)
        
        logger.success(f"Saved {len(df)} candles to {csv_path.name}")
        
    except Exception as e:
        logger.error(f"Error downloading {symbol}: {e}")


async def main():
    """Download all missing symbols"""
    logger.info(f"Downloading {len(MISSING_SYMBOLS)} missing symbols...")
    
    # Initialize broker
    broker = FyersBroker()
    
    # Date range: 6 months
    to_date = datetime.now()
    from_date = to_date - timedelta(days=180)
    
    logger.info(f"Date range: {from_date.date()} to {to_date.date()}")
    
    # Download sequentially to avoid rate limits
    for symbol in MISSING_SYMBOLS:
        await download_symbol(broker, symbol, from_date, to_date)
        await asyncio.sleep(1)  # Rate limit
    
    logger.success(f"\nCompleted! Downloaded {len(MISSING_SYMBOLS)} symbols")


if __name__ == "__main__":
    asyncio.run(main())
