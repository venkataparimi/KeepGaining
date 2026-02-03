#!/usr/bin/env python3
"""
Comprehensive Data Backfill Script for KeepGaining

This script:
1. Downloads missing data for current F&O expiries
2. Refreshes equity data to the latest date
3. Backfills historical F&O data (14 months)
4. Computes technical indicators for all new data

Usage:
    python backfill_all_data.py --mode <mode> [options]

Modes:
    analyze     - Only analyze and show what needs to be downloaded
    current     - Download current expiry F&O data
    equity      - Refresh equity data
    historical  - Backfill historical F&O data
    indicators  - Compute indicators for new data
    all         - Run all steps (current -> equity -> historical -> indicators)
"""

import asyncio
import asyncpg
import aiohttp
import argparse
import json
import os
import sys
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import time
import logging
import gzip
import io

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('backfill.log')
    ]
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'
UPSTOX_TOKEN_FILE = os.path.join(BACKEND_DIR, 'data', 'upstox_token.json')
UPSTOX_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"

# Rate limiting settings
RATE_LIMIT_CALLS = 15  # calls per second (conservative, Upstox limit is 30)
RATE_LIMIT_WINDOW = 1.0  # seconds
BATCH_SIZE = 50  # instruments per batch
CONCURRENCY = 5  # Number of concurrent downloads (reduced from 10)

# Cache for instrument keys
_instrument_key_cache: Dict[str, str] = {}


@dataclass
class BackfillStats:
    """Track backfill statistics."""
    total_instruments: int = 0
    downloaded: int = 0
    failed: int = 0
    skipped: int = 0
    not_found: int = 0  # Instruments not found in Upstox cache
    candles_added: int = 0
    rate_limited: int = 0  # Track rate limit hits
    start_time: datetime = None
    
    def __post_init__(self):
        self.start_time = datetime.now()
    
    def elapsed(self) -> str:
        elapsed = datetime.now() - self.start_time
        return str(elapsed).split('.')[0]
    
    def rate(self) -> float:
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed > 0:
            return self.downloaded / elapsed
        return 0


class RateLimiter:
    """Rate limiter for API calls with exponential backoff."""
    
    def __init__(self, calls_per_second: float = RATE_LIMIT_CALLS):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0
        self.lock = asyncio.Lock()
        self.backoff_until = 0  # Timestamp until which we should back off
    
    async def wait(self):
        """Wait if needed to stay within rate limits."""
        async with self.lock:
            now = time.time()
            
            # Check if we're in backoff period
            if now < self.backoff_until:
                wait_time = self.backoff_until - now
                logger.warning(f"Rate limit backoff: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                now = time.time()
            
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self.last_call = time.time()
    
    def trigger_backoff(self, duration: float = 5.0):
        """Trigger a backoff period after hitting rate limit."""
        self.backoff_until = time.time() + duration


def parse_expiry_from_symbol(trading_symbol: str) -> Optional[date]:
    """Extract expiry date from trading symbol."""
    months = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }
    pattern = r'(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})$'
    match = re.search(pattern, trading_symbol.upper())
    if match:
        day = int(match.group(1))
        month = months[match.group(2)]
        year = 2000 + int(match.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def get_upstox_token() -> Optional[str]:
    """Load Upstox access token from file."""
    if os.path.exists(UPSTOX_TOKEN_FILE):
        with open(UPSTOX_TOKEN_FILE, 'r') as f:
            data = json.load(f)
            return data.get('access_token')
    return None


async def build_instrument_key_cache() -> Dict[str, str]:
    """
    Build trading_symbol to instrument_key mapping from Upstox instrument master.
    """
    global _instrument_key_cache
    
    if _instrument_key_cache:
        return _instrument_key_cache
    
    logger.info("Building instrument key cache from Upstox...")
    
    cache = {}
    
    # Index name mapping for slight naming differences
    index_mapping = {
        'NIFTY 50': 'NSE_INDEX|Nifty 50',
        'NIFTY BANK': 'NSE_INDEX|Nifty Bank',
        'NIFTY FIN SERVICE': 'NSE_INDEX|Nifty Fin Service',
    }
    cache.update(index_mapping)
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
        # Download NSE instruments - this includes EQ, INDEX, and FO
        nse_url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        try:
            logger.info(f"Downloading instruments from {nse_url}...")
            async with session.get(nse_url) as response:
                if response.status == 200:
                    content = await response.read()
                    with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                        data = json.loads(f.read().decode('utf-8'))
                    
                    for item in data:
                        trading_symbol = item.get('trading_symbol', '')
                        instrument_key = item.get('instrument_key', '')
                        
                        if trading_symbol and instrument_key:
                            cache[trading_symbol] = instrument_key
                            # Also store uppercase version for safety
                            cache[trading_symbol.upper()] = instrument_key
                    
                    logger.info(f"Built cache with {len(cache)} entries from {len(data)} instruments")
        except Exception as e:
            logger.error(f"Failed to download NSE instruments: {e}")
            raise
    
    _instrument_key_cache = cache
    return cache


async def get_instrument_key(trading_symbol: str, exchange: str = 'NSE') -> Optional[str]:
    """Get Upstox instrument key for a trading symbol."""
    cache = await build_instrument_key_cache()
    
    if trading_symbol in cache:
        return cache[trading_symbol]
    
    if trading_symbol.upper() in cache:
        return cache[trading_symbol.upper()]
    
    return None


async def get_db_pool():
    """Get database connection pool."""
    return await asyncpg.create_pool(DB_URL)


async def get_instruments_to_backfill(pool, mode: str) -> List[Dict[str, Any]]:
    """Get list of instruments that need backfill based on mode."""
    async with pool.acquire() as conn:
        today = date.today()
        
        if mode == 'current':
            # Get instruments for current expiries (next 60 days)
            future_cutoff = today + timedelta(days=60)
            
            query = '''
                SELECT 
                    im.instrument_id,
                    im.trading_symbol,
                    im.exchange,
                    im.instrument_type,
                    im.underlying,
                    s.last_date as last_data_date
                FROM instrument_master im
                LEFT JOIN candle_data_summary s ON im.instrument_id = s.instrument_id
                WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
                AND im.is_active = true
                ORDER BY im.underlying, im.instrument_type, im.trading_symbol
            '''
            rows = await conn.fetch(query)
            
            # Filter to current expiries
            instruments = []
            for r in rows:
                expiry = parse_expiry_from_symbol(r['trading_symbol'])
                if expiry and today <= expiry <= future_cutoff:
                    if r['last_data_date'] is None or r['last_data_date'] < today - timedelta(days=1):
                        instruments.append({
                            'instrument_id': r['instrument_id'],
                            'trading_symbol': r['trading_symbol'],
                            'exchange': r['exchange'],
                            'instrument_type': r['instrument_type'],
                            'underlying': r['underlying'],
                            'last_data_date': r['last_data_date'],
                            'expiry': expiry
                        })
            
            return instruments
        
        elif mode == 'equity':
            query = '''
                SELECT 
                    im.instrument_id,
                    im.trading_symbol,
                    im.exchange,
                    im.instrument_type,
                    im.underlying,
                    s.last_date as last_data_date
                FROM instrument_master im
                LEFT JOIN candle_data_summary s ON im.instrument_id = s.instrument_id
                WHERE im.instrument_type = 'EQUITY'
                AND im.is_active = true
                AND (s.last_date < $1 OR s.last_date IS NULL)
            '''
            rows = await conn.fetch(query, today - timedelta(days=1))
            return [dict(r) for r in rows]
        
        elif mode == 'index':
            query = '''
                SELECT 
                    im.instrument_id,
                    im.trading_symbol,
                    im.exchange,
                    im.instrument_type,
                    im.underlying,
                    s.last_date as last_data_date
                FROM instrument_master im
                LEFT JOIN candle_data_summary s ON im.instrument_id = s.instrument_id
                WHERE im.instrument_type = 'INDEX'
                AND im.is_active = true
                AND (s.last_date < $1 OR s.last_date IS NULL)
            '''
            rows = await conn.fetch(query, today - timedelta(days=1))
            return [dict(r) for r in rows]
        
        elif mode == 'historical':
            target_start = today - timedelta(days=14 * 30)
            
            query = '''
                SELECT 
                    im.instrument_id,
                    im.trading_symbol,
                    im.exchange,
                    im.instrument_type,
                    im.underlying,
                    s.first_date as first_data_date,
                    s.last_date as last_data_date
                FROM instrument_master im
                LEFT JOIN candle_data_summary s ON im.instrument_id = s.instrument_id
                WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
                AND im.is_active = true
            '''
            rows = await conn.fetch(query)
            
            instruments = []
            for r in rows:
                expiry = parse_expiry_from_symbol(r['trading_symbol'])
                if expiry and expiry >= target_start:
                    if r['first_data_date'] is None or r['first_data_date'] > target_start + timedelta(days=30):
                        instruments.append({
                            'instrument_id': r['instrument_id'],
                            'trading_symbol': r['trading_symbol'],
                            'exchange': r['exchange'],
                            'instrument_type': r['instrument_type'],
                            'underlying': r['underlying'],
                            'first_data_date': r['first_data_date'],
                            'last_data_date': r['last_data_date'],
                            'expiry': expiry
                        })
            
            return instruments
        
        elif mode == 'stale':
            query = '''
                SELECT 
                    im.instrument_id,
                    im.trading_symbol,
                    im.exchange,
                    im.instrument_type,
                    im.underlying,
                    s.last_date as last_data_date
                FROM instrument_master im
                JOIN candle_data_summary s ON im.instrument_id = s.instrument_id
                WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
                AND im.is_active = true
                AND s.last_date < $1
                ORDER BY im.trading_symbol
            '''
            rows = await conn.fetch(query, today - timedelta(days=1))
            
            instruments = []
            for r in rows:
                expiry = parse_expiry_from_symbol(r['trading_symbol'])
                if expiry and expiry >= today:
                    instruments.append({
                        'instrument_id': r['instrument_id'],
                        'trading_symbol': r['trading_symbol'],
                        'exchange': r['exchange'],
                        'instrument_type': r['instrument_type'],
                        'underlying': r['underlying'],
                        'last_data_date': r['last_data_date'],
                        'expiry': expiry
                    })
            
            return instruments
        
        elif mode == 'all_fo':
            # Get ALL F&O instruments (including expired) with no data or incomplete data
            # This will attempt to download historical data for expired contracts too
            query = '''
                SELECT 
                    im.instrument_id,
                    im.trading_symbol,
                    im.exchange,
                    im.instrument_type,
                    im.underlying,
                    s.first_date,
                    s.last_date
                FROM instrument_master im
                LEFT JOIN candle_data_summary s ON im.instrument_id = s.instrument_id
                WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
                ORDER BY im.trading_symbol
            '''
            rows = await conn.fetch(query)
            
            instruments = []
            target_start = today - timedelta(days=14 * 30)  # 14 months back
            
            for r in rows:
                expiry = parse_expiry_from_symbol(r['trading_symbol'])
                # Include if:
                # 1. Has no data at all, OR
                # 2. Expiry is within our lookback period and data is incomplete
                if expiry and expiry >= target_start:
                    if r['first_date'] is None or r['last_date'] is None:
                        # No data or incomplete
                        instruments.append({
                            'instrument_id': r['instrument_id'],
                            'trading_symbol': r['trading_symbol'],
                            'exchange': r['exchange'],
                            'instrument_type': r['instrument_type'],
                            'underlying': r['underlying'],
                            'first_data_date': r['first_date'],
                            'last_data_date': r['last_date'],
                            'expiry': expiry
                        })
            
            return instruments
        
        elif mode == 'missing':
            query = '''
                SELECT 
                    im.instrument_id,
                    im.trading_symbol,
                    im.exchange,
                    im.instrument_type,
                    im.underlying
                FROM instrument_master im
                LEFT JOIN candle_data_summary s ON im.instrument_id = s.instrument_id
                WHERE s.instrument_id IS NULL
                AND im.is_active = true
                ORDER BY im.trading_symbol
            '''
            rows = await conn.fetch(query)
            
            instruments = []
            for r in rows:
                expiry = parse_expiry_from_symbol(r['trading_symbol']) if r['instrument_type'] in ('CE', 'PE', 'FUTURES') else None
                instruments.append({
                    'instrument_id': r['instrument_id'],
                    'trading_symbol': r['trading_symbol'],
                    'exchange': r['exchange'],
                    'instrument_type': r['instrument_type'],
                    'underlying': r['underlying'],
                    'last_data_date': None,
                    'expiry': expiry
                })
            
            return instruments
        
        return []


async def download_candles_for_instrument(
    session: aiohttp.ClientSession,
    token: str,
    instrument: Dict[str, Any],
    from_date: date,
    to_date: date,
    rate_limiter: RateLimiter
) -> Optional[List[Dict[str, Any]]]:
    """Download candle data for an instrument from Upstox."""
    
    instrument_key = await get_instrument_key(
        instrument['trading_symbol'],
        instrument['exchange']
    )
    
    if not instrument_key:
        return None
    
    from_str = from_date.strftime('%Y-%m-%d')
    to_str = to_date.strftime('%Y-%m-%d')
    
    url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/1minute/{to_str}/{from_str}"
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    await rate_limiter.wait()
    
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                candles = data.get('data', {}).get('candles', [])
                
                result = []
                for candle in candles:
                    result.append({
                        'timestamp': datetime.fromisoformat(candle[0].replace('Z', '+00:00')),
                        'open': float(candle[1]),
                        'high': float(candle[2]),
                        'low': float(candle[3]),
                        'close': float(candle[4]),
                        'volume': int(candle[5]),
                        'oi': int(candle[6]) if len(candle) > 6 else 0
                    })
                return result
            
            elif response.status == 429:
                # Trigger backoff in rate limiter
                rate_limiter.trigger_backoff(10.0)  # 10 second backoff
                logger.warning(f"Rate limited (429) on {instrument['trading_symbol']}, backing off 10s...")
                await asyncio.sleep(10)
                # Don't retry immediately, let the caller handle it
                return []
            
            else:
                logger.error(f"API {response.status} for {instrument['trading_symbol']}")
                return []
    
    except Exception as e:
        logger.error(f"Network error {instrument['trading_symbol']}: {e}")
        return []


async def save_candles_to_db(conn, instrument_id, candles: List[Dict[str, Any]], timeframe: str = '1m') -> int:
    """Save candles to database using batch insert."""
    if not candles:
        return 0
    
    records = [
        (
            instrument_id,
            timeframe,
            candle['timestamp'],
            candle['open'],
            candle['high'],
            candle['low'],
            candle['close'],
            candle['volume'],
            candle.get('oi', 0)
        )
        for candle in candles
    ]
    
    try:
        await conn.execute(f"CREATE TEMP TABLE IF NOT EXISTS temp_candles_{instrument_id.hex} (LIKE candle_data INCLUDING DEFAULTS)")
        await conn.execute(f"TRUNCATE temp_candles_{instrument_id.hex}")
        
        await conn.copy_records_to_table(
            f'temp_candles_{instrument_id.hex}',
            records=records,
            columns=['instrument_id', 'timeframe', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi']
        )
        
        result = await conn.execute(f'''
            INSERT INTO candle_data (instrument_id, timeframe, timestamp, open, high, low, close, volume, oi)
            SELECT instrument_id, timeframe, timestamp, open, high, low, close, volume, oi
            FROM temp_candles_{instrument_id.hex}
            ON CONFLICT (instrument_id, timeframe, timestamp) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                oi = EXCLUDED.oi
        ''')
        
        await conn.execute(f"DROP TABLE temp_candles_{instrument_id.hex}")
        
        count = int(result.split()[-1]) if result else len(records)
        return count
        
    except Exception as e:
        logger.error(f"Batch insert failed: {e}")
        return 0


async def process_one_instrument(
    instrument: Dict[str, Any],
    from_date: date,
    to_date: date,
    token: str,
    rate_limiter: RateLimiter,
    session: aiohttp.ClientSession,
    pool: asyncpg.Pool,
    stats: BackfillStats,
    progress: str
):
    """Process a single instrument."""
    try:
        start_date = from_date
        if instrument.get('last_data_date'):
            start_date = max(from_date, instrument['last_data_date'] + timedelta(days=1))
        
        if start_date >= to_date:
            stats.skipped += 1
            print(f"{progress} {instrument['trading_symbol']:<15} | Skipped (Up to date)")
            return

        # F&O Expiry Check
        if instrument.get('expiry') and instrument['instrument_type'] in ('CE', 'PE'):
            earliest = instrument['expiry'] - timedelta(days=60)
            start_date = max(start_date, earliest)

        current_start = start_date
        total_candles = 0
        found_data = False
        
        # Download loop (chunks of 1 yr)
        while current_start < to_date:
            chunk_end = min(current_start + timedelta(days=365), to_date)
            
            candles = await download_candles_for_instrument(
                session, token, instrument, current_start, chunk_end, rate_limiter
            )
            
            if candles is None:
                stats.not_found += 1
                print(f"{progress} {instrument['trading_symbol']:<15} | Not Found in Upstox")
                return
            
            if candles:
                found_data = True
                async with pool.acquire() as conn:
                    saved = await save_candles_to_db(conn, instrument['instrument_id'], candles)
                    total_candles += saved
            
            current_start = chunk_end + timedelta(days=1)
        
        stats.downloaded += 1
        stats.candles_added += total_candles
        
        status = "Updated" if found_data else "No Data"
        print(f"{progress} {instrument['trading_symbol']:<15} | {status:<8} | +{total_candles} candles")
        
    except Exception as e:
        stats.failed += 1
        logger.error(f"Error processing {instrument['trading_symbol']}: {e}")
        print(f"{progress} {instrument['trading_symbol']:<15} | Failed")


async def backfill_instruments(
    instruments: List[Dict[str, Any]],
    from_date: date,
    to_date: date,
    token: str,
    stats: BackfillStats
) -> None:
    """Backfill data for a list of instruments with concurrency."""
    
    pool = await get_db_pool()
    rate_limiter = RateLimiter()
    sem = asyncio.Semaphore(CONCURRENCY)
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i, inst in enumerate(instruments):
            progress_str = f"[{i+1}/{len(instruments)}]"
            
            async def worker(inner_inst, inner_prog):
                async with sem:
                    await process_one_instrument(
                        inner_inst, from_date, to_date, token, rate_limiter, session, pool, stats, inner_prog
                    )

            tasks.append(worker(inst, progress_str))
        
        await asyncio.gather(*tasks)
    
    await pool.close()


async def compute_indicators_for_new_data(pool, since_date: date = None) -> Dict[str, int]:
    # Placeholder for indicator computation logic
    async with pool.acquire() as conn:
        if since_date is None:
            since_date = date.today() - timedelta(days=7)
        
        query = '''
            SELECT COUNT(DISTINCT cd.instrument_id)
            FROM candle_data cd
            WHERE cd.timestamp::date >= $1
        '''
        count = await conn.fetchval(query, since_date)
        return {'instruments_with_new_data': count}


async def run_backfill(mode: str, dry_run: bool = False, limit: int = 0) -> Dict[str, Any]:
    """Run the backfill process."""
    
    token = get_upstox_token()
    if not token and not dry_run:
        logger.error("No Upstox token found. Please authenticate first.")
        return {'error': 'No token'}
    
    pool = await get_db_pool()
    today = date.today()
    
    result = {
        'mode': mode,
        'started': datetime.now().isoformat(),
        'stats': {}
    }
    
    try:
        # Helper to run specific modes
        async def run_phase(name, get_func_mode, days_lookback=30):
            logger.info("=" * 60)
            logger.info(f"PHASE: {name}")
            logger.info("=" * 60)
            instruments = await get_instruments_to_backfill(pool, get_func_mode)
            if limit > 0:
                instruments = instruments[:limit]
            
            result['stats'][get_func_mode] = {'instruments_found': len(instruments)}
            logger.info(f"Found {len(instruments)} instruments")
            
            if not dry_run and instruments:
                stats = BackfillStats(total_instruments=len(instruments))
                await backfill_instruments(
                    instruments, today - timedelta(days=days_lookback), today, token, stats
                )
                result['stats'][get_func_mode].update({
                    'downloaded': stats.downloaded,
                    'failed': stats.failed,
                    'candles': stats.candles_added
                })

        # Logic for 'all' or specific modes
        if mode in ('current', 'all'):
            await run_phase("Current Expiry F&O", 'current', 30)
        
        if mode in ('equity', 'all'):
            # Logic tailored for equity (lookback 7 days usually enough if running daily)
            # If missing, it goes back 7 days only?
            # The original script had logic for 'missing' mode separately.
            await run_phase("Equity Data Refresh", 'equity', 7)
            
        if mode in ('index', 'all'):
            await run_phase("Index Data Refresh", 'index', 7)
            
        if mode in ('historical', 'all'):
            await run_phase("Historical F&O Backfill", 'historical', 420) # 14 months

        if mode == 'missing':
             await run_phase("All Missing Data", 'missing', 60)
             
        if mode == 'stale':
             await run_phase("Stale Data Refresh", 'stale', 7)
        
        if mode == 'all_fo':
             await run_phase("ALL F&O (Including Expired)", 'all_fo', 420)  # 14 months

    finally:
        await pool.close()
    
    result['completed'] = datetime.now().isoformat()
    return result


async def analyze_only():
    pool = await get_db_pool()
    print("\nBACKFILL ANALYSIS")
    print("=" * 60)
    
    modes = ['current', 'equity', 'index', 'historical']
    total_inst = 0
    for m in modes:
        insts = await get_instruments_to_backfill(pool, m)
        print(f"{m.upper()}: {len(insts)} instruments")
        total_inst += len(insts)
    
    print(f"\nTotal Estimate: {total_inst} instruments")
    await pool.close()


def main():
    parser = argparse.ArgumentParser(description='Backfill historical data')
    parser.add_argument('--mode', choices=['analyze', 'current', 'equity', 'index', 'historical', 'missing', 'stale', 'all_fo', 'all'], default='analyze')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    if args.mode == 'analyze':
        asyncio.run(analyze_only())
    else:
        asyncio.run(run_backfill(args.mode, args.dry_run, args.limit))

if __name__ == "__main__":
    main()
