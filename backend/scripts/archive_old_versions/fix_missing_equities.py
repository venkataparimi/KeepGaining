"""
Fix missing equities and backfill current F&O data.
"""
import asyncio
import asyncpg
import aiohttp
import json
import gzip
import io
from datetime import date, timedelta
import os

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
TOKEN_FILE = os.path.join(BACKEND_DIR, 'data', 'upstox_token.json')

# Known symbol mappings for NSE stocks that may have different names in Upstox
SYMBOL_MAPPINGS = {
    'GMRINFRA': ['GMRINFRA', 'GMR-INFRA', 'GMRP&UI'],  # GMR merged
    'LARSENTOUB': ['LT', 'L&T', 'LARSEN'],  # Larsen & Toubro
    'NATCOPHARMA': ['NATCOPHARM', 'NATCOPHARMA'],
    'PEL': ['PEL', 'PIRAMAL', 'PIRAMALENT'],  # Piramal
    'PVR': ['PVRINOX', 'PVR', 'PVRINOX'],  # PVR merged with INOX
    'TATAMOTORS': ['TATAMOTORS', 'TATAMTR', 'TATAMOTOR'],
    'ZOMATO': ['ZOMATO', 'ZOMATO LTD'],
}

async def get_upstox_instruments():
    """Download and parse Upstox instruments."""
    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                compressed = await resp.read()
                decompressed = gzip.decompress(compressed)
                return json.loads(decompressed)
    return []

async def find_equity_instrument_keys():
    """Find the correct Upstox instrument keys for missing equities."""
    print("=" * 60)
    print("FINDING MISSING EQUITY INSTRUMENT KEYS")
    print("=" * 60)
    
    instruments = await get_upstox_instruments()
    print(f"Loaded {len(instruments)} instruments from Upstox")
    
    # Filter to equities only
    equities = [i for i in instruments if i.get('instrument_type') == 'EQUITY']
    print(f"Found {len(equities)} equities")
    
    missing_stocks = ['GMRINFRA', 'LARSENTOUB', 'NATCOPHARMA', 'PEL', 'PVR', 'TATAMOTORS', 'ZOMATO']
    
    found_mappings = {}
    
    for stock in missing_stocks:
        print(f"\nSearching for {stock}...")
        
        # Try exact match first
        for eq in equities:
            symbol = eq.get('trading_symbol', '')
            name = eq.get('name', '').upper()
            
            if stock.upper() in symbol.upper() or stock.upper() in name:
                print(f"  Found: {eq.get('trading_symbol')} - {eq.get('name')} -> {eq.get('instrument_key')}")
                found_mappings[stock] = eq
                break
        
        # Try alternative names
        if stock not in found_mappings and stock in SYMBOL_MAPPINGS:
            for alt_name in SYMBOL_MAPPINGS[stock]:
                for eq in equities:
                    if eq.get('trading_symbol', '').upper() == alt_name.upper():
                        print(f"  Found via mapping: {eq.get('trading_symbol')} - {eq.get('name')} -> {eq.get('instrument_key')}")
                        found_mappings[stock] = eq
                        break
                if stock in found_mappings:
                    break
        
        if stock not in found_mappings:
            print(f"  NOT FOUND in Upstox")
    
    return found_mappings

async def backfill_equity(instrument_key: str, token: str, from_date: date, to_date: date):
    """Fetch candle data for an equity."""
    from_str = from_date.strftime('%Y-%m-%d')
    to_str = to_date.strftime('%Y-%m-%d')
    
    url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/1minute/{to_str}/{from_str}"
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get('status') == 'success':
                    return data.get('data', {}).get('candles', [])
            else:
                text = await resp.text()
                print(f"Error {resp.status}: {text[:200]}")
    return []

async def main():
    # Load token
    with open(TOKEN_FILE) as f:
        token_data = json.load(f)
        token = token_data.get('access_token')
    
    if not token:
        print("No token found!")
        return
    
    # Find instrument keys
    found = await find_equity_instrument_keys()
    
    print("\n" + "=" * 60)
    print("BACKFILLING FOUND EQUITIES")
    print("=" * 60)
    
    conn = await asyncpg.connect(DB_URL)
    today = date.today()
    from_date = today - timedelta(days=365 * 3)  # 3 years back
    
    for stock, upstox_data in found.items():
        instrument_key = upstox_data.get('instrument_key')
        trading_symbol = upstox_data.get('trading_symbol')
        
        print(f"\nFetching {trading_symbol} ({instrument_key})...")
        
        candles = await backfill_equity(instrument_key, token, from_date, today)
        print(f"  Got {len(candles)} candles")
        
        if candles:
            # Check if we have this instrument in our DB
            db_instrument = await conn.fetchrow('''
                SELECT instrument_id FROM instrument_master
                WHERE trading_symbol = $1 AND instrument_type = 'EQUITY'
            ''', stock)  # Use original symbol
            
            if not db_instrument:
                # Try the Upstox symbol
                db_instrument = await conn.fetchrow('''
                    SELECT instrument_id FROM instrument_master
                    WHERE trading_symbol = $1 AND instrument_type = 'EQUITY'
                ''', trading_symbol)
            
            if db_instrument:
                instrument_id = db_instrument['instrument_id']
                print(f"  Found in DB: {instrument_id}")
                
                # Insert candles
                inserted = 0
                for candle in candles:
                    try:
                        # Candle format: [timestamp, open, high, low, close, volume, oi]
                        ts = candle[0]
                        await conn.execute('''
                            INSERT INTO candle_data (instrument_id, timeframe, timestamp, open, high, low, close, volume)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (instrument_id, timeframe, timestamp) DO NOTHING
                        ''', instrument_id, '1m', ts, candle[1], candle[2], candle[3], candle[4], candle[5])
                        inserted += 1
                    except Exception as e:
                        pass
                
                print(f"  Inserted {inserted} candles")
            else:
                print(f"  NOT in our DB - need to add to instrument_master")
    
    await conn.close()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Found {len(found)}/{len(['GMRINFRA', 'LARSENTOUB', 'NATCOPHARMA', 'PEL', 'PVR', 'TATAMOTORS', 'ZOMATO'])} missing equities")
    print("\nStocks that could not be found may be:")
    print("  - Delisted")
    print("  - Merged with another company")
    print("  - Renamed (need manual mapping)")

if __name__ == '__main__':
    asyncio.run(main())
