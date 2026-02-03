"""Debug API call for a specific instrument."""

import asyncio
import aiohttp
import json
import os
from datetime import date, timedelta
import gzip

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
TOKEN_FILE = os.path.join(BACKEND_DIR, 'data', 'upstox_token.json')

def get_token():
    with open(TOKEN_FILE, 'r') as f:
        return json.load(f).get('access_token')

async def get_instrument_key(trading_symbol):
    """Look up instrument key from Upstox master."""
    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.read()
    
    import io
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
        instruments = json.load(f)
    
    # Build lookup
    for inst in instruments:
        ts = inst.get('trading_symbol', '')
        if ts == trading_symbol:
            return inst.get('instrument_key'), inst
    
    return None, None

async def test_api_range(symbol, from_date, to_date):
    """Test API with specific date range."""
    print(f"Testing symbol: {symbol}")
    print(f"Date range: {from_date} to {to_date}")
    print("-" * 60)
    
    token = get_token()
    if not token:
        print("No token found!")
        return
    
    # Get instrument key
    inst_key, _ = await get_instrument_key(symbol)
    
    if not inst_key:
        print(f"No instrument key found for {symbol}")
        return
    
    print(f"Found instrument key: {inst_key}")
    
    # Try API call
    url = f"https://api.upstox.com/v2/historical-candle/{inst_key}/1minute/{to_date}/{from_date}"
    print(f"API URL: {url}")
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(f"Response status: {resp.status}")
            text = await resp.text()
            try:
                data = json.loads(text)
                candles = data.get('data', {}).get('candles', [])
                print(f"Candles returned: {len(candles)}")
                if candles:
                    print(f"First candle: {candles[0]}")
                    print(f"Last candle: {candles[-1]}")
            except:
                print(f"Response: {text[:500]}")

if __name__ == "__main__":
    symbol = "BANKNIFTY FUT 30 DEC 25"
    today = date.today()
    
    # Test different date ranges
    test_cases = [
        (today - timedelta(days=30), today),  # What backfill uses
        (today - timedelta(days=4), today),   # Just last 4 days
        (date(2025, 11, 29), date(2025, 12, 2)),  # Specific range
    ]
    
    for from_d, to_d in test_cases:
        asyncio.run(test_api_range(symbol, from_d, to_d))
        print("\n" + "=" * 80 + "\n")
