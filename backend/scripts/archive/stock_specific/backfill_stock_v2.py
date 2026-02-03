"""
Backfill historical data for a specific stock (e.g., IEX)
Downloads historical data back to January 2022 using month-based chunking
to avoid Feb-Mar overlap issues
"""
import asyncio
import asyncpg
import aiohttp
import json
from datetime import datetime, timedelta
from calendar import monthrange
from pathlib import Path
import sys

# Add parent path to import from backfill_all_data
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
                print(f"API {resp.status}")
                return []
    except Exception as e:
        print(f"Error: {e}")
        return []

async def backfill_stock(symbol: str, start_year: int = 2022, start_month: int = 1):
    """
    Backfill historical data for a specific stock
    
    Args:
        symbol: Stock symbol (e.g., 'IEX', 'RELIANCE')
        start_year: Year to start from (default: 2022)
        start_month: Month to start from (default: 1 for January)
    """
    print(f"=== Backfilling {symbol} from {start_year}-{start_month:02d} ===")
    
    pool = await asyncpg.create_pool(DB_URL)
    token = await get_token()
    
    # Build the instrument key cache first
    await build_instrument_key_cache()
    
    async with pool.acquire() as conn:
        # Get instrument info from database
        inst = await conn.fetchrow("""
            SELECT instrument_id, trading_symbol, exchange
            FROM instrument_master
            WHERE trading_symbol = $1 AND instrument_type = 'EQUITY'
        """, symbol)
        
        if not inst:
            print(f"❌ {symbol} not found in instrument_master")
            await pool.close()
            return
        
        inst_id = inst['instrument_id']
        
        # Get Upstox instrument key using the cache
        inst_key = await get_instrument_key(inst['trading_symbol'], inst['exchange'])
        
        if not inst_key:
            print(f"❌ Could not find Upstox instrument key for {symbol}")
            await pool.close()
            return
        
        print(f"Found: {inst['trading_symbol']} | Key: {inst_key}")
        
        # Check existing data
        existing = await conn.fetchrow("""
            SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest, COUNT(*) as cnt
            FROM candle_data WHERE instrument_id = $1
        """, inst_id)
        
        if existing['cnt'] > 0:
            print(f"Existing data: {existing['earliest']} to {existing['latest']} ({existing['cnt']:,} candles)")
        
        # Download in chunks using calendar months to avoid boundary issues
        today = datetime.now().date()
        start_date = datetime(start_year, start_month, 1).date()
        
        print(f"Downloading from {start_date} to {today}")
        
        total_candles = 0
        months_processed = 0
        
        async with aiohttp.ClientSession() as session:
            current_date = start_date
            
            while current_date < today:
                # Get the last day of current month
                last_day = monthrange(current_date.year, current_date.month)[1]
                month_end = current_date.replace(day=last_day)
                
                # Don't go beyond today
                if month_end > today:
                    month_end = today
                
                month_name = current_date.strftime('%b %Y')
                print(f"  {month_name:12} ({current_date} to {month_end})...", end=" ")
                
                candles = await download_historical_candle(
                    session, inst_key, 
                    current_date.strftime('%Y-%m-%d'),
                    month_end.strftime('%Y-%m-%d'),
                    token
                )
                
                if candles:
                    # Insert candles
                    inserted = 0
                    for c in candles:
                        ts = datetime.fromisoformat(c[0].replace('Z', '+00:00'))
                        try:
                            await conn.execute("""
                                INSERT INTO candle_data (instrument_id, timestamp, timeframe, open, high, low, close, volume, oi)
                                VALUES ($1, $2, '1m', $3, $4, $5, $6, $7, $8)
                                ON CONFLICT (instrument_id, timestamp, timeframe) DO NOTHING
                            """, inst_id, ts, c[1], c[2], c[3], c[4], c[5], c[6] if len(c) > 6 else 0)
                            inserted += 1
                        except Exception as e:
                            pass
                    
                    print(f"{inserted:,} candles")
                    total_candles += inserted
                else:
                    print("No data")
                
                # Move to next month
                months_processed += 1
                current_date = (month_end + timedelta(days=1))
                
                await asyncio.sleep(0.5)  # Rate limiting
        
        print(f"\n✅ Total: {total_candles:,} candles across {months_processed} months")
        
        # Refresh summary (skip CONCURRENTLY if it fails)
        try:
            await conn.execute("REFRESH MATERIALIZED VIEW candle_data_summary")
            print("✅ Refreshed candle_data_summary")
        except Exception as e:
            print(f"⚠️  Could not refresh materialized view: {e}")
    
    await pool.close()

if __name__ == "__main__":
    import sys
    
    symbol = sys.argv[1] if len(sys.argv) > 1 else "IEX"
    start_year = int(sys.argv[2]) if len(sys.argv) > 2 else 2022
    start_month = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    asyncio.run(backfill_stock(symbol, start_year, start_month))
