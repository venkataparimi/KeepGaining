#!/usr/bin/env python3
"""Test API download for a specific instrument."""
import asyncio
import aiohttp
import json
import os
from datetime import date, datetime, timedelta

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSTOX_TOKEN_FILE = os.path.join(BACKEND_DIR, 'data', 'upstox_token.json')

def get_upstox_token():
    if os.path.exists(UPSTOX_TOKEN_FILE):
        with open(UPSTOX_TOKEN_FILE, 'r') as f:
            data = json.load(f)
            return data.get('access_token')
    return None

async def test_download():
    token = get_upstox_token()
    if not token:
        print("No Upstox token found!")
        return
    
    # Test with BANKNIFTY FUT
    instrument_key = "NSE_FO|49508"  # BANKNIFTY FUT 30 DEC 25
    from_date = date(2025, 11, 1)
    to_date = date(2025, 12, 2)
    
    print(f"Testing download for instrument_key: {instrument_key}")
    print(f"Date range: {from_date} to {to_date}")
    
    url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/1minute/{to_date.strftime('%Y-%m-%d')}/{from_date.strftime('%Y-%m-%d')}"
    
    print(f"URL: {url}")
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            print(f"Response status: {response.status}")
            data = await response.json()
            print(f"Response: {json.dumps(data, indent=2)[:2000]}")
            
            candles = data.get('data', {}).get('candles', [])
            print(f"\nTotal candles returned: {len(candles)}")
            
            if candles:
                print(f"First candle: {candles[0]}")
                print(f"Last candle: {candles[-1]}")

if __name__ == '__main__':
    asyncio.run(test_download())
