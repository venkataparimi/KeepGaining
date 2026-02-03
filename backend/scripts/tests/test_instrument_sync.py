"""
Test Instrument Sync Service

Downloads instruments from Upstox and Fyers and displays statistics.
Can optionally sync to database.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import date
from loguru import logger

from app.services.instrument_sync import (
    InstrumentSyncService,
    UPSTOX_INSTRUMENT_URLS,
    FYERS_SYMBOL_URLS,
)


async def test_upstox_download():
    """Test Upstox instrument download."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING UPSTOX INSTRUMENT DOWNLOAD")
    logger.info("=" * 80)
    
    service = InstrumentSyncService()
    
    try:
        # Download NSE instruments
        instruments = await service.download_upstox_instruments("NSE")
        
        if not instruments:
            logger.error("No instruments downloaded!")
            return
        
        # Categorize
        equities = [i for i in instruments if i.is_equity]
        indices = [i for i in instruments if i.is_index]
        futures = [i for i in instruments if i.is_future]
        options = [i for i in instruments if i.is_option]
        
        logger.info(f"\n📊 Upstox NSE Instruments Summary:")
        logger.info(f"   Total: {len(instruments)}")
        logger.info(f"   Equities: {len(equities)}")
        logger.info(f"   Indices: {len(indices)}")
        logger.info(f"   Futures: {len(futures)}")
        logger.info(f"   Options: {len(options)}")
        
        # Sample equities
        logger.info(f"\n📈 Sample Equities (first 10):")
        for inst in equities[:10]:
            logger.info(f"   {inst.trading_symbol}: {inst.name} (Lot: {inst.lot_size}, ISIN: {inst.isin})")
        
        # Sample indices
        logger.info(f"\n📊 Sample Indices (first 10):")
        for inst in indices[:10]:
            logger.info(f"   {inst.trading_symbol}: {inst.name}")
        
        # Sample futures
        if futures:
            logger.info(f"\n📅 Sample Futures (first 10):")
            for inst in futures[:10]:
                logger.info(f"   {inst.trading_symbol}: Expiry={inst.expiry}, Lot={inst.lot_size}")
        
        # Sample options
        if options:
            logger.info(f"\n🎯 Sample Options (first 10):")
            for inst in options[:10]:
                logger.info(
                    f"   {inst.trading_symbol}: Strike={inst.strike_price}, "
                    f"Type={inst.option_type}, Expiry={inst.expiry}"
                )
        
        # F&O stocks
        fno_stocks = [i for i in equities if i.is_fno]
        logger.info(f"\n💹 F&O Eligible Equities: {len(fno_stocks)}")
        
    finally:
        await service.close()


async def test_fyers_download():
    """Test Fyers instrument download."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING FYERS INSTRUMENT DOWNLOAD")
    logger.info("=" * 80)
    
    service = InstrumentSyncService()
    
    try:
        # Test NSE Cash Market (JSON)
        logger.info("\n📥 Downloading NSE_CM (JSON format)...")
        cm_instruments = await service.download_fyers_instruments("NSE_CM", use_json=True)
        
        if cm_instruments:
            equities = [i for i in cm_instruments if i.is_equity]
            indices = [i for i in cm_instruments if i.is_index]
            
            logger.info(f"\n📊 Fyers NSE_CM Summary:")
            logger.info(f"   Total: {len(cm_instruments)}")
            logger.info(f"   Equities: {len(equities)}")
            logger.info(f"   Indices: {len(indices)}")
            
            # Sample equities
            logger.info(f"\n📈 Sample Equities (first 10):")
            for inst in equities[:10]:
                logger.info(f"   {inst.symbol_ticker}: {inst.symbol_details} (Lot: {inst.lot_size})")
            
            # Sample indices
            logger.info(f"\n📊 Sample Indices:")
            for inst in indices[:10]:
                logger.info(f"   {inst.symbol_ticker}: {inst.symbol_details}")
        
        # Test NSE F&O (JSON)
        logger.info("\n📥 Downloading NSE_FO (JSON format)...")
        fo_instruments = await service.download_fyers_instruments("NSE_FO", use_json=True)
        
        if fo_instruments:
            futures = [i for i in fo_instruments if i.is_future]
            options = [i for i in fo_instruments if i.is_option]
            
            logger.info(f"\n📊 Fyers NSE_FO Summary:")
            logger.info(f"   Total: {len(fo_instruments)}")
            logger.info(f"   Futures: {len(futures)}")
            logger.info(f"   Options: {len(options)}")
            
            # Sample futures
            if futures:
                logger.info(f"\n📅 Sample Futures (first 10):")
                for inst in futures[:10]:
                    logger.info(
                        f"   {inst.symbol_ticker}: Underlying={inst.underlying_symbol}, "
                        f"Expiry={inst.expiry_date}, Lot={inst.lot_size}"
                    )
            
            # Sample options
            if options:
                logger.info(f"\n🎯 Sample Options (first 10):")
                for inst in options[:10]:
                    logger.info(
                        f"   {inst.symbol_ticker}: Strike={inst.strike_price}, "
                        f"Type={inst.option_type}, Expiry={inst.expiry_date}"
                    )
            
            # NIFTY options
            nifty_options = [
                i for i in options 
                if i.underlying_symbol and "NIFTY" in i.underlying_symbol.upper()
            ]
            logger.info(f"\n🎯 NIFTY Options Count: {len(nifty_options)}")
            
            # Get unique expiries
            expiries = set()
            for inst in options:
                if inst.expiry_date:
                    expiries.add(inst.expiry_date)
            
            logger.info(f"\n📅 Unique Expiry Dates: {len(expiries)}")
            sorted_expiries = sorted(expiries)[:10]
            for exp in sorted_expiries:
                logger.info(f"   {exp}")
        
    finally:
        await service.close()


async def test_download_stats():
    """Show download statistics for all sources."""
    logger.info("\n" + "=" * 80)
    logger.info("INSTRUMENT DATA SOURCES SUMMARY")
    logger.info("=" * 80)
    
    service = InstrumentSyncService()
    
    try:
        # Upstox
        logger.info("\n📊 UPSTOX SOURCES:")
        for name, url in UPSTOX_INSTRUMENT_URLS.items():
            logger.info(f"   {name}: {url}")
        
        # Fyers
        logger.info("\n📊 FYERS SOURCES:")
        for name, url in FYERS_SYMBOL_URLS.items():
            logger.info(f"   {name}: {url}")
        
        # Quick count from NSE
        logger.info("\n📥 Quick Download Test (NSE only)...")
        
        upstox_nse = await service.download_upstox_instruments("NSE")
        fyers_cm = await service.download_fyers_instruments("NSE_CM", use_json=True)
        fyers_fo = await service.download_fyers_instruments("NSE_FO", use_json=True)
        
        logger.info(f"\n📊 TOTALS:")
        logger.info(f"   Upstox NSE: {len(upstox_nse)} instruments")
        logger.info(f"   Fyers NSE_CM: {len(fyers_cm)} instruments")
        logger.info(f"   Fyers NSE_FO: {len(fyers_fo)} instruments")
        
        # Coverage analysis
        upstox_symbols = {i.trading_symbol for i in upstox_nse if i.is_equity}
        fyers_symbols = {
            i.symbol_ticker.split(":")[-1].replace("-EQ", "") 
            for i in fyers_cm if i.is_equity
        }
        
        common = upstox_symbols & fyers_symbols
        only_upstox = upstox_symbols - fyers_symbols
        only_fyers = fyers_symbols - upstox_symbols
        
        logger.info(f"\n📊 EQUITY COVERAGE:")
        logger.info(f"   Common symbols: {len(common)}")
        logger.info(f"   Upstox only: {len(only_upstox)}")
        logger.info(f"   Fyers only: {len(only_fyers)}")
        
    finally:
        await service.close()


async def main():
    """Run all tests."""
    logger.info("=" * 80)
    logger.info("INSTRUMENT SYNC SERVICE TEST")
    logger.info("=" * 80)
    
    # Test downloads
    await test_download_stats()
    await test_upstox_download()
    await test_fyers_download()
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ ALL TESTS COMPLETED")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
