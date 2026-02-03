"""
Backfill historical F&O (Options and Futures) data from January 2023
Uses month-based chunking to avoid date boundary issues
"""
import asyncio
import asyncpg
import aiohttp
import json
from datetime import datetime, timedelta
from calendar import monthrange
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from backfill_all_data import get_instrument_key, build_instrument_key_cache

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'
TOKEN_FILE = Path(__file__).parent.parent / 'data' / 'upstox_token.json'

async def get_token():
    with open(TOKEN_FILE) as f:
        return json.load(f)['access_token']

async def download_historical_candle(session, instrument_key, from_date, to_date, token):
    """Download candles for a date range"""
    url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/1minute/{to_date}/{from_date}"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('data', {}).get('candles', [])
            else:
                return []
    except Exception as e:
        return []

async def backfill_fo_historical(
    underlying: str = None,
    instrument_type: str = None,
    start_year: int = 2023,
    start_month: int = 1,
    limit: int = 0
):
    """
    Backfill historical F&O data
    
    Args:
        underlying: Filter by underlying (e.g., 'NIFTY', 'BANKNIFTY', 'RELIANCE')
        instrument_type: Filter by type ('FUTURES', 'CE', 'PE', or None for all)
        start_year: Year to start from (default: 2023)
        start_month: Month to start from (default: 1)
        limit: Limit number of instruments (0 = all)
    """
    print(f"=== Backfilling F&O from {start_year}-{start_month:02d} ===")
    if underlying:
        print(f"Underlying: {underlying}")
    if instrument_type:
        print(f"Type: {instrument_type}")
    
    pool = await asyncpg.create_pool(DB_URL)
    token = await get_token()
    
    await build_instrument_key_cache()
    
    async with pool.acquire() as conn:
        # Build query to get F&O instruments
        query = """
            SELECT 
                im.instrument_id,
                im.trading_symbol,
                im.exchange,
                im.instrument_type,
                im.underlying
            FROM instrument_master im
            WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
        """
        
        params = []
        if underlying:
            query += " AND im.underlying = $1"
            params.append(underlying)
        
        if instrument_type:
            if params:
                query += f" AND im.instrument_type = ${len(params) + 1}"
            else:
                query += " AND im.instrument_type = $1"
            params.append(instrument_type)
        
        query += " ORDER BY im.underlying, im.instrument_type, im.trading_symbol"
        
        if limit > 0:
            query += f" LIMIT {limit}"
        
        instruments = await conn.fetch(query, *params) if params else await conn.fetch(query)
        
        print(f"Found {len(instruments)} F&O instruments to backfill")
        
        today = datetime.now().date()
        start_date = datetime(start_year, start_month, 1).date()
        
        total_instruments = len(instruments)
        processed = 0
        total_candles = 0
        
        async with aiohttp.ClientSession() as session:
            for idx, inst in enumerate(instruments, 1):
                inst_id = inst['instrument_id']
                symbol = inst['trading_symbol']
                
                # Get instrument key
                inst_key = await get_instrument_key(symbol, inst['exchange'])
                
                if not inst_key:
                    print(f"[{idx}/{total_instruments}] {symbol:40} | ❌ No key")
                    continue
                
                # Check existing data
                existing = await conn.fetchrow("""
                    SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest, COUNT(*) as cnt
                    FROM candle_data WHERE instrument_id = $1
                """, inst_id)
                
                # Determine download range
                # Download up to today (we can't determine expiry without the column)
                end_date = today
                
                # Skip if already have data covering the period
                if existing['cnt'] > 0 and existing['earliest'].date() <= start_date:
                    print(f"[{idx}/{total_instruments}] {symbol:40} | ✅ Already has data from {existing['earliest'].date()}")
                    continue
                
                instrument_candles = 0
                current_date = start_date
                
                while current_date < end_date:
                    # Get month end
                    last_day = monthrange(current_date.year, current_date.month)[1]
                    month_end = current_date.replace(day=last_day)
                    
                    if month_end > end_date:
                        month_end = end_date
                    
                    candles = await download_historical_candle(
                        session, inst_key,
                        current_date.strftime('%Y-%m-%d'),
                        month_end.strftime('%Y-%m-%d'),
                        token
                    )
                    
                    if candles:
                        for c in candles:
                            ts = datetime.fromisoformat(c[0].replace('Z', '+00:00'))
                            try:
                                await conn.execute("""
                                    INSERT INTO candle_data (instrument_id, timestamp, timeframe, open, high, low, close, volume, oi)
                                    VALUES ($1, $2, '1m', $3, $4, $5, $6, $7, $8)
                                    ON CONFLICT (instrument_id, timestamp, timeframe) DO NOTHING
                                """, inst_id, ts, c[1], c[2], c[3], c[4], c[5], c[6] if len(c) > 6 else 0)
                                instrument_candles += 1
                            except:
                                pass
                    
                    current_date = month_end + timedelta(days=1)
                    await asyncio.sleep(0.3)  # Rate limiting
                
                if instrument_candles > 0:
                    print(f"[{idx}/{total_instruments}] {symbol:40} | ✅ {instrument_candles:,} candles")
                    total_candles += instrument_candles
                    processed += 1
                else:
                    print(f"[{idx}/{total_instruments}] {symbol:40} | ⏭️  No new data")
        
        print(f"\n✅ Processed {processed}/{total_instruments} instruments")
        print(f"✅ Total candles added: {total_candles:,}")
    
    await pool.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Backfill historical F&O data')
    parser.add_argument('--underlying', help='Filter by underlying (e.g., NIFTY, BANKNIFTY)')
    parser.add_argument('--type', choices=['FUTURES', 'CE', 'PE'], help='Filter by instrument type')
    parser.add_argument('--year', type=int, default=2023, help='Start year (default: 2023)')
    parser.add_argument('--month', type=int, default=1, help='Start month (default: 1)')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of instruments (0 = all)')
    
    args = parser.parse_args()
    
    asyncio.run(backfill_fo_historical(
        underlying=args.underlying,
        instrument_type=args.type,
        start_year=args.year,
        start_month=args.month,
        limit=args.limit
    ))
