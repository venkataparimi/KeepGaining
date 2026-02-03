"""
Backfill Equity and Index data from 2022.
Downloads 1-minute historical data for 193 stocks and major indices.
Uses UUIDs from instrument_master and connects to candle_data.
"""
import asyncio
import aiohttp
import asyncpg
import logging
import sys
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

# Add backend to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.brokers.upstox_auth_automation import UpstoxAuthAutomation
from scripts.utils.instrument_loader import get_stock_keys

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

# Indices to backfill
INDEX_SYMBOLS = {
    'Nifty 50': 'NSE_INDEX|Nifty 50',
    'Nifty Bank': 'NSE_INDEX|Nifty Bank',
    'Nifty Fin Service': 'NSE_INDEX|Nifty Fin Service',
    'NIFTY MID SELECT': 'NSE_INDEX|NIFTY MID SELECT',
    'SENSEX': 'BSE_INDEX|SENSEX',
    'BANKEX': 'BSE_INDEX|BANKEX'
}

async def get_instrument_mapping():
    """Get mapping of trading_symbol to (instrument_id, exchange)"""
    conn = await asyncpg.connect(DB_URL)
    # We want either Equity or Index instruments that are active
    rows = await conn.fetch("""
        SELECT instrument_id, trading_symbol, exchange, instrument_type
        FROM instrument_master 
        WHERE (instrument_type = 'EQUITY' OR instrument_type = 'INDEX') 
    """)
    await conn.close()
    
    # Map by trading_symbol
    # Note: For indices, Upstox key is 'NSE_INDEX|Nifty 50' but trading_symbol in DB might be 'NIFTY' or 'Nifty 50'
    return {r['trading_symbol']: (r['instrument_id'], r['exchange'], r['instrument_type']) for r in rows}

async def backfill_instrument(session, token, symbol, instrument_key, db_inst_id, start_date='2022-01-01'):
    """Backfill a single instrument's historical data"""
    logger.info(f"Backfilling {symbol} ({instrument_key}) -> DB ID {db_inst_id} from {start_date}...")
    
    conn = await asyncpg.connect(DB_URL)
    
    # Check if we already have some data to avoid redundant calls
    existing_min = await conn.fetchval("SELECT MIN(timestamp) FROM candle_data WHERE instrument_id = $1", db_inst_id)
    
    end_dt = datetime.now()
    if existing_min:
        existing_min_naive = existing_min.replace(tzinfo=None)
        current_to = existing_min_naive
    else:
        current_to = end_dt
        
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    
    if current_to <= start_dt:
        logger.info(f"  Existing data for {symbol} already goes back to {current_to}. Skipping.")
        await conn.close()
        return

    # Iterate backwards in chunks
    while current_to > start_dt:
        current_from = max(start_dt, current_to - timedelta(days=7))
        
        from_str = current_from.strftime('%Y-%m-%d')
        to_str = current_to.strftime('%Y-%m-%d')
        
        logger.info(f"  Fetching {symbol}: {from_str} to {to_str}")
        
        url = f"https://api.upstox.com/v2/historical-candle/{quote(instrument_key)}/1minute/{to_str}/{from_str}"
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candles = data.get('data', {}).get('candles', [])
                    
                    if candles:
                        rows = []
                        for c in candles:
                            dt = datetime.fromisoformat(c[0])
                            # Rows: instrument_id, timeframe, timestamp, open, high, low, close, volume, oi
                            rows.append((db_inst_id, '1m', dt, float(c[1]), float(c[2]), float(c[3]), float(c[4]), int(c[5]), int(c[6])))
                        
                        await conn.executemany("""
                            INSERT INTO candle_data (instrument_id, timeframe, timestamp, open, high, low, close, volume, oi, created_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                            ON CONFLICT (instrument_id, timestamp, timeframe) DO NOTHING
                        """, rows)
                        logger.info(f"    Inserted {len(rows)} candles")
                    else:
                        logger.info("    No data found for this range")
                elif resp.status == 429:
                    logger.warning("    Rate limit hit. Waiting 5s...")
                    await asyncio.sleep(5)
                    continue
                else:
                    logger.error(f"    API Error {resp.status} for {symbol}: {await resp.text()}")
                    break
        except Exception as e:
            logger.error(f"    Exception: {e}")
            break
            
        current_to = current_from - timedelta(days=1)
        await asyncio.sleep(0.4) 
        
    await conn.close()

async def run_2022_backfill():
    logger.info("Initializing 2022 Long-term Backfill")
    
    # 1. Auth
    auth = UpstoxAuthAutomation()
    token = await auth.get_fresh_token()
    
    # 2. Get DB Instruments
    mapping = await get_instrument_mapping()
    
    # 3. Resolve Stock Keys for those in DB
    db_symbols = list(mapping.keys())
    # Separate stocks and indices
    stock_symbols = [s for s in db_symbols if mapping[s][2] == 'EQUITY']
    index_symbols = [s for s in db_symbols if mapping[s][2] == 'INDEX']
    
    logger.info(f"Found {len(stock_symbols)} stocks and {len(index_symbols)} indices in DB")
    
    stock_keys = await get_stock_keys(stock_symbols)
    logger.info(f"Resolved {len(stock_keys)} Upstox keys for stocks")
    
    targets = []
    
    # Process Indices
    # Map index trading_symbol to Upstox key
    # Most common names: 'NIFTY 50' or 'NIFM'? In INDEX_SYMBOLS I have common names.
    # I'll check if the db symbol matches any key in INDEX_SYMBOLS
    for db_sym in index_symbols:
        upstox_key = INDEX_SYMBOLS.get(db_sym)
        if not upstox_key:
            # Try fuzzy match?
            for k, v in INDEX_SYMBOLS.items():
                if k.lower() in db_sym.lower() or db_sym.lower() in k.lower():
                    upstox_key = v
                    break
        
        if upstox_key:
            targets.append((db_sym, upstox_key, mapping[db_sym][0]))
        else:
            logger.warning(f"Could not find Upstox key for index symbol: {db_sym}")
            
    # Process Stocks
    for db_sym in stock_symbols:
        if db_sym in stock_keys:
            targets.append((db_sym, stock_keys[db_sym], mapping[db_sym][0]))
        else:
            # Maybe the DB has something like 'RELIANCE-EQ'?
            pass
            
    logger.info(f"Total targets to process: {len(targets)}")
    
    # 4. Processing
    async with aiohttp.ClientSession() as session:
        for symbol, key, db_id in targets:
            try:
                await backfill_instrument(session, token, symbol, key, db_id, '2022-01-01')
            except Exception as e:
                logger.error(f"Critical error processing {symbol}: {e}")
            
            await asyncio.sleep(1) # Delay between symbols

if __name__ == "__main__":
    asyncio.run(run_2022_backfill())
