"""
Test if the current token works with regular Upstox APIs
"""
import asyncio
import aiohttp
import json
from pathlib import Path

TOKEN_FILE = Path(__file__).parent.parent / 'data' / 'upstox_token.json'

async def test_token():
    with open(TOKEN_FILE) as f:
        token_data = json.load(f)
        token = token_data['access_token']
    
    print(f"Testing token: {token[:50]}...")
    print(f"User: {token_data.get('user_name')}")
    print(f"Saved at: {token_data.get('saved_at')}")
    print()
    
    async with aiohttp.ClientSession() as session:
        # Test 1: Get Profile (should always work)
        print("Test 1: Get Profile")
        url = "https://api.upstox.com/v2/user/profile"
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        
        async with session.get(url) as resp:
            print(f"  Status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print(f"  ✅ Profile: {data.get('data', {}).get('user_name')}")
            else:
                text = await resp.text()
                print(f"  ❌ Error: {text[:200]}")
        
        print()
        
        # Test 2: Regular Historical Candle (should work)
        print("Test 2: Regular Historical Candle API")
        url = "https://api.upstox.com/v2/historical-candle/NSE_EQ|INE002A01018/1minute/2024-12-16/2024-12-15"
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        
        async with session.get(url) as resp:
            print(f"  Status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                candles = data.get('data', {}).get('candles', [])
                print(f"  ✅ Got {len(candles)} candles")
            else:
                text = await resp.text()
                print(f"  ❌ Error: {text[:200]}")
        
        print()
        
        # Test 3: Expired Instruments Expiries
        print("Test 3: Expired Instruments API")
        from urllib.parse import quote
        instrument_key = quote('NSE_INDEX|Nifty 50')
        url = f"https://api.upstox.com/v2/expired-instruments/expiries?instrument_key={instrument_key}"
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        
        async with session.get(url) as resp:
            print(f"  Status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                expiries = data.get('data', [])
                print(f"  ✅ Got {len(expiries)} expiries")
                if expiries:
                    print(f"  Recent: {expiries[:5]}")
            else:
                text = await resp.text()
                print(f"  ❌ Error: {text[:300]}")
                if resp.status == 401:
                    print("\n  💡 This suggests:")
                    print("     - Token is valid but Expired Instruments API needs special access")
                    print("     - Contact Upstox support to enable this API")
                    print("     - Email: support@upstox.com")

if __name__ == "__main__":
    asyncio.run(test_token())
