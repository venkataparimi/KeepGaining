"""
Optimized parallel data download for 227 F&O symbols
Uses concurrent downloads to reduce time from 23 hours to ~2-3 hours
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
from typing import List
import time

# Import complete F&O symbols list
from fno_symbols import MAJOR_INDICES, SECTOR_INDICES, FNO_STOCKS, ALL_SYMBOLS

# Configuration
MAX_CONCURRENT_DOWNLOADS = 10  # Download 10 symbols in parallel
DAYS_BACK = 180  # 6 months
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # seconds

class ParallelDownloader:
    """Optimized parallel downloader for market data"""
    
    def __init__(self, broker: FyersBroker, indicator_service: IndicatorComputationService):
        self.broker = broker
        self.indicator_service = indicator_service
        self.success_count = 0
        self.fail_count = 0
        self.total_candles = 0
        
    async def download_symbol(self, symbol: str, semaphore: asyncio.Semaphore) -> dict:
        """Download data for a single symbol with retry logic"""
        async with semaphore:
            for attempt in range(RETRY_ATTEMPTS):
                try:
                    logger.info(f"[{symbol}] Starting download (Attempt {attempt + 1}/{RETRY_ATTEMPTS})")
                    
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=DAYS_BACK)
                    
                    # Fetch historical data
                    df = await self.broker.get_historical_data(
                        symbol=symbol,
                        resolution="1",
                        start_date=start_date,
                        end_date=end_date
                    )
                    
                    if df.empty:
                        logger.warning(f"[{symbol}] No data received")
                        if attempt < RETRY_ATTEMPTS - 1:
                            await asyncio.sleep(RETRY_DELAY)
                            continue
                        return {"symbol": symbol, "status": "failed", "candles": 0, "error": "No data"}
                    
                    # Store with indicators
                    count = await self.indicator_service.store_candles_with_indicators(
                        symbol=symbol,
                        timeframe="1m",
                        df=df
                    )
                    
                    logger.success(f"[{symbol}] ✓ Stored {count:,} candles")
                    self.success_count += 1
                    self.total_candles += count
                    
                    return {"symbol": symbol, "status": "success", "candles": count}
                    
                except Exception as e:
                    logger.error(f"[{symbol}] Error: {e}")
                    if attempt < RETRY_ATTEMPTS - 1:
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        self.fail_count += 1
                        return {"symbol": symbol, "status": "failed", "candles": 0, "error": str(e)}
    
    async def download_batch(self, symbols: List[str]) -> List[dict]:
        """Download multiple symbols in parallel"""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        tasks = [self.download_symbol(symbol, semaphore) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results


async def main():
    """Main optimized download function"""
    start_time = time.time()
    
    logger.info("=" * 80)
    logger.info("OPTIMIZED PARALLEL DATA DOWNLOAD")
    logger.info("=" * 80)
    logger.info(f"Total symbols: {len(ALL_SYMBOLS)}")
    logger.info(f"Concurrent downloads: {MAX_CONCURRENT_DOWNLOADS}")
    logger.info(f"Period: {DAYS_BACK} days (6 months)")
    logger.info("=" * 80)
    
    # Initialize broker
    logger.info("Initializing Fyers broker...")
    broker = FyersBroker()
    
    # Initialize database
    db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        indicator_service = IndicatorComputationService(session)
        downloader = ParallelDownloader(broker, indicator_service)
        
        # Download in batches for better progress tracking
        batch_size = 50
        total_batches = (len(ALL_SYMBOLS) + batch_size - 1) // batch_size
        
        for batch_num in range(total_batches):
            batch_start = batch_num * batch_size
            batch_end = min(batch_start + batch_size, len(ALL_SYMBOLS))
            batch_symbols = ALL_SYMBOLS[batch_start:batch_end]
            
            logger.info(f"\n{'='*80}")
            logger.info(f"BATCH {batch_num + 1}/{total_batches}: Processing {len(batch_symbols)} symbols")
            logger.info(f"{'='*80}")
            
            batch_start_time = time.time()
            results = await downloader.download_batch(batch_symbols)
            batch_duration = time.time() - batch_start_time
            
            # Log batch summary
            batch_success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
            logger.info(f"Batch {batch_num + 1} complete: {batch_success}/{len(batch_symbols)} successful in {batch_duration:.1f}s")
    
    # Final summary
    duration = time.time() - start_time
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    
    logger.info("\n" + "=" * 80)
    logger.success("DOWNLOAD COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"Total symbols processed: {len(ALL_SYMBOLS)}")
    logger.info(f"Successful: {downloader.success_count}")
    logger.info(f"Failed: {downloader.fail_count}")
    logger.info(f"Total candles stored: {downloader.total_candles:,}")
    logger.info(f"Total time: {hours}h {minutes}m")
    logger.info(f"Average time per symbol: {duration/len(ALL_SYMBOLS):.1f}s")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
