"""
Complete Data Backfill Orchestrator
Backfills Stocks & Indices, Options & Futures, filling all historical gaps.
"""
import asyncio
import asyncpg
import aiohttp
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

from scripts.backfill_expired_options import (
    backfill_expired_instrument, 
    get_expired_expiries,
    get_token,
    INSTRUMENT_KEYS as INDEX_KEYS
)
from scripts.utils.instrument_loader import get_stock_keys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

# Earliest GAP start date. 
# Coverage check showed options data starts 2024-09-03.
# User wants "prior to Dec 25 gap" and potentially earlier history.
# We will target expiries > 2024-01-01 to be safe, or stick to identified needs?
# Let's target > 2024-09-01 to start filling the known gap, but user said "prior to dec 25".
# Actually, let's fetch ALL available expiries returned by API.
# The API returns a list. We can process all of them.
# Limit per symbol: 0 (all contract types).

async def get_fno_stocks():
    """Get list of F&O stocks from DB"""
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch("""
        SELECT trading_symbol FROM instrument_master 
        WHERE instrument_type = 'EQUITY' AND is_active = true
        ORDER BY trading_symbol
    """)
    await conn.close()
    return [r['trading_symbol'] for r in rows]

async def process_symbol(symbol: str, instrument_key: str, token: str, session):
    """Process a single symbol (Options & Futures)"""
    logger.info(f"Processing symbol: {symbol}")
    
    # 1. Available Expiries
    expiries = await get_expired_expiries(session, token, instrument_key)
    if not expiries:
        logger.warning(f"No expiries found for {symbol}")
        return
    
    # Sort Expiries recent to old or old to recent?
    # Old to recent ensures chronological fill.
    # Expiries come sorted? Usually recent first?
    # Let's filter for relevant range.
    # We want to fill gaps.
    # Let's fill EVERYTHING listing provided.
    
    # Filter for relevant range if needed to save time?
    # Step 313 showed expiries back to 2024-10-03.
    # We should process valid dates.
    
    valid_expiries = [e for e in expiries if e >= '2022-01-01' and e <= '2024-09-30'] 
    
    logger.info(f"Found {len(valid_expiries)} expiries for {symbol}")
    
    for expiry in valid_expiries:
        logger.info(f"--- Processing {symbol} Expiry: {expiry} ---")
        
        # 2. Backfill Options (CE & PE)
        # We pass option_type='CE' but fetch function handles specific type.
        # Wait, backfill_expired_instrument takes 'option_type'.
        # Should we run twice for CE and PE?
        # Yes.
        
        # CE
        await backfill_expired_instrument(
            symbol=symbol,
            instrument_key=instrument_key,
            expiry=expiry,
            instrument_type='OPTION',
            option_type='CE',
            limit=0
        )
        
        # PE
        await backfill_expired_instrument(
            symbol=symbol,
            instrument_key=instrument_key,
            expiry=expiry,
            instrument_type='OPTION',
            option_type='PE',
            limit=0
        )
        
        # 3. Backfill Futures
        await backfill_expired_instrument(
            symbol=symbol,
            instrument_key=instrument_key,
            expiry=expiry,
            instrument_type='FUTURE',
            limit=0
        )
        
        await asyncio.sleep(1) # Delay between expiries

async def run_complete_backfill():
    logger.info("Starting COMPLETE DATA BACKFILL")
    
    # 1. Get Token
    token = await get_token()
    
    # 2. Get Stocks & Keys
    stocks = await get_fno_stocks()
    logger.info(f"Found {len(stocks)} F&O stocks")
    
    stock_keys = await get_stock_keys(stocks)
    logger.info(f"Resolved {len(stock_keys)} keys")
    
    # 3. Targets
    targets = []
    
    # Add Indices
    for sym, key in INDEX_KEYS.items():
        targets.append((sym, key))
        
    # Add Stocks
    for sym in stocks:
        if sym in stock_keys:
            targets.append((sym, stock_keys[sym]))
        else:
            logger.warning(f"Could not resolve key for {sym}")
            
    logger.info(f"Total targets: {len(targets)}")
    
    # 4. Processing Loop
    async with aiohttp.ClientSession() as session:
        for symbol, key in targets:
            try:
                await process_symbol(symbol, key, token, session)
            except Exception as e:
                logger.error(f"Failed to process {symbol}: {e}")
                
            await asyncio.sleep(2) # Delay between symbols

if __name__ == "__main__":
    asyncio.run(run_complete_backfill())
