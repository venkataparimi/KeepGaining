"""
Test Upstox historical data availability limits
Checks how far back we can retrieve data
"""
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from pathlib import Path

TOKEN_FILE = Path(__file__).parent.parent / 'data' / 'upstox_token.json'

async def test_historical_limits():
    with open(TOKEN_FILE) as f:
        token = json.load(f)['access_token']
    
    # Test with RELIANCE (a stable stock)
    instrument_key = "NSE_EQ|INE002A01018"  # RELIANCE
    
    test_dates = [
        ("2024-12-01", "2024-12-16", "Recent (Dec 2024)"),
        ("2024-01-01", "2024-01-31", "1 year ago (Jan 2024)"),
        ("2023-01-01", "2023-01-31", "2 years ago (Jan 2023)"),
        ("2022-01-01", "2022-01-31", "3 years ago (Jan 2022)"),
        ("2022-02-01", "2022-02-28", "Feb 2022"),
        ("2022-02-15", "2022-03-15", "Feb-Mar 2022 overlap"),
        ("2021-01-01", "2021-01-31", "4 years ago (Jan 2021)"),
    ]
    
    async with aiohttp.ClientSession() as session:
        for from_date, to_date, description in test_dates:
            url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/1minute/{to_date}/{from_date}"
            headers = {
                'Accept': 'application/json',
                'Authorization': f'Bearer {token}'
            }
            
            try:
                async with session.get(url) as resp:
                    status = resp.status
                    if status == 200:
                        data = await resp.json()
                        candles = data.get('data', {}).get('candles', [])
                        print(f"✅ {description:30} | Status: {status} | Candles: {len(candles):,}")
                    else:
                        text = await resp.text()
                        print(f"❌ {description:30} | Status: {status} | Response: {text[:100]}")
            except Exception as e:
                print(f"❌ {description:30} | Error: {e}")
            
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(test_historical_limits())
