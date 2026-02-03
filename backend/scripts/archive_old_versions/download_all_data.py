#!/usr/bin/env python3
"""
Download historical data for all F&O stocks.

This script downloads 1-minute candle data from Upstox V3 API for all F&O stocks
and stores it in PostgreSQL.

Usage:
    python scripts/download_all_data.py [--from-date 2022-01-01] [--to-date 2025-11-28]
"""
import asyncio
import argparse
import logging
from datetime import date, timedelta
from typing import List, Dict, Any

import sys
sys.path.insert(0, ".")

from app.services.data_download_service import DataDownloadService
from app.services.data_providers.upstox import UpstoxDataProvider
from app.services.data_providers.base import DataProviderConfig, Interval

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Reduce noise from other loggers
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)


async def download_all(
    from_date: date,
    to_date: date,
    symbols: List[str] = None,
    batch_size: int = 10
):
    """Download historical data for all F&O stocks."""
    
    # Initialize provider
    config = DataProviderConfig(
        provider_name='upstox',
        token_file='data/upstox_token.json'
    )
    provider = UpstoxDataProvider(config)
    
    # Initialize service
    service = DataDownloadService(data_provider=provider)
    await service.initialize()
    
    logger.info("="*60)
    logger.info("HISTORICAL DATA DOWNLOAD")
    logger.info("="*60)
    logger.info(f"Date Range: {from_date} to {to_date}")
    
    # Get symbols list
    if symbols is None:
        symbols = service._get_all_fo_stocks_from_mappings()
    
    logger.info(f"Symbols: {len(symbols)} F&O stocks")
    logger.info("="*60)
    
    # Download data
    results = await service.download_historical_data(
        symbols=symbols,
        from_date=from_date,
        to_date=to_date,
        interval=Interval.MINUTE_1
    )
    
    # Print summary
    logger.info("")
    logger.info("="*60)
    logger.info("DOWNLOAD COMPLETE")
    logger.info("="*60)
    logger.info(f"Successful: {results['successful']} / {results['total_symbols']}")
    logger.info(f"Failed: {results['failed']}")
    logger.info(f"Total Candles: {results['total_candles']:,}")
    
    if results['errors']:
        logger.info("")
        logger.info(f"Errors ({len(results['errors'])}):")
        for err in results['errors'][:20]:
            logger.info(f"  {err['symbol']}: {err['error'][:80]}")
    
    # Get final status
    status = await service.get_download_status()
    logger.info("")
    logger.info("Database Status:")
    logger.info(f"  F&O Instruments: {status['total_fo_instruments']}")
    logger.info(f"  With Data: {status['instruments_with_data']}")
    logger.info(f"  Total Candles: {status['total_candles']:,}")
    if status['date_range']['min']:
        logger.info(f"  Date Range: {status['date_range']['min']} to {status['date_range']['max']}")
    
    await service.close()
    return results


def parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format."""
    return date.fromisoformat(date_str)


def main():
    parser = argparse.ArgumentParser(description='Download historical data')
    parser.add_argument('--from-date', type=parse_date, default=date(2022, 1, 1),
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to-date', type=parse_date, default=date.today(),
                        help='End date (YYYY-MM-DD)')
    parser.add_argument('--symbols', type=str, nargs='+',
                        help='Specific symbols to download (default: all F&O)')
    
    args = parser.parse_args()
    
    asyncio.run(download_all(
        from_date=args.from_date,
        to_date=args.to_date,
        symbols=args.symbols
    ))


if __name__ == "__main__":
    main()
