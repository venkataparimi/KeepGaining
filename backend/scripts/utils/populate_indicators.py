"""
Populate historical candle data with pre-computed indicators
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.services.indicator_computation import IndicatorComputationService
from app.brokers.fyers import FyersBroker
from loguru import logger

# Import complete F&O symbols list
from fno_symbols import MAJOR_INDICES, SECTOR_INDICES, FNO_STOCKS, ALL_SYMBOLS

# Use all symbols (227 total: 2 major indices + 12 sector indices + 213 F&O stocks)
SYMBOLS = ALL_SYMBOLS

logger.info(f"Total symbols to download: {len(SYMBOLS)}")
logger.info(f"  - Major Indices: {len(MAJOR_INDICES)}")
logger.info(f"  - Sector Indices: {len(SECTOR_INDICES)}")
logger.info(f"  - F&O Stocks: {len(FNO_STOCKS)}")

# Download only 1-minute data (we'll resample to other timeframes)
TIMEFRAMES = {
    "1": "1m",   # 1 minute only
}

async def populate_symbol_data(
    broker: FyersBroker,
    indicator_service: IndicatorComputationService,
    symbol: str,
    timeframe_key: str,
    timeframe_label: str,
    days_back: int = 365
):
    """Populate data for a single symbol and timeframe"""
    try:
        logger.info(f"Fetching {symbol} {timeframe_label} data...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Fetch historical data from broker
        df = await broker.get_historical_data(
            symbol=symbol,
            resolution=timeframe_key,
            start_date=start_date,
            end_date=end_date
        )
        
        if df.empty:
            logger.warning(f"No data received for {symbol} {timeframe_label}")
            return 0
        
        logger.info(f"Received {len(df)} candles for {symbol} {timeframe_label}")
        
        # Store with indicators
        count = await indicator_service.store_candles_with_indicators(
            symbol=symbol,
            timeframe=timeframe_label,
            df=df
        )
        
        logger.success(f"✓ Stored {count} candles for {symbol} {timeframe_label}")
        return count
        
    except Exception as e:
        logger.error(f"Failed to populate {symbol} {timeframe_label}: {e}")
        return 0


async def main():
    """Main population script"""
    logger.info("=" * 60)
    logger.info("Starting Historical Data Population with Indicators")
    logger.info("=" * 60)
    
    # Initialize broker
    logger.info("Initializing Fyers broker...")
    broker = FyersBroker()
    
    # Initialize database
    db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    total_candles = 0
    
    async with async_session() as session:
        indicator_service = IndicatorComputationService(session)
        
        # Populate each symbol and timeframe
        for symbol in SYMBOLS:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing: {symbol}")
            logger.info(f"{'='*60}")
            
            for tf_key, tf_label in TIMEFRAMES.items():
                # Download 6 months of 1-minute data for all symbols
                days_back = 180  # 6 months
                
                count = await populate_symbol_data(
                    broker=broker,
                    indicator_service=indicator_service,
                    symbol=symbol,
                    timeframe_key=tf_key,
                    timeframe_label=tf_label,
                    days_back=days_back
                )
                
                total_candles += count
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(1)
    
    logger.info("\n" + "=" * 60)
    logger.success(f"✓ Population Complete!")
    logger.info(f"Total candles stored: {total_candles:,}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
