import asyncio
import aiohttp
import json
import sys

async def test_expired_api():
    # Load token
    import os
    token_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'upstox_token.json')
    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            data = json.load(f)
            token = data.get('access_token')
    else:
        print("No token found")
        return
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    # Test 1: Try to get expiries without parameters
    print("Test 1: GET /v2/expired-instruments/expiries (no params)")
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.upstox.com/v2/expired-instruments/expiries", headers=headers) as response:
            print(f"Status: {response.status}")
            text = await response.text()
            print(f"Response: {text[:500]}")
    
    print("\n" + "="*60 + "\n")
    
    # Test 2: Try with instrument_type parameter
    print("Test 2: GET /v2/expired-instruments/expiries?instrument_type=OPTIDX")
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.upstox.com/v2/expired-instruments/expiries",
            headers=headers,
            params={'instrument_type': 'OPTIDX'}
        ) as response:
            print(f"Status: {response.status}")
            text = await response.text()
            print(f"Response: {text[:500]}")
    
    print("\n" + "="*60 + "\n")
    
    # Test 3: Try the regular historical candle API (non-expired)
    print("Test 3: GET /v2/historical-candle (regular API)")
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.upstox.com/v2/historical-candle/NSE_INDEX|Nifty 50/1minute/2025-12-13/2025-12-12",
            headers=headers
        ) as response:
            print(f"Status: {response.status}")
            if response.status == 200:
                data = await response.json()
                candles = data.get('data', {}).get('candles', [])
                print(f"Got {len(candles)} candles")
            else:
                text = await response.text()
                print(f"Response: {text[:500]}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_expired_api())
