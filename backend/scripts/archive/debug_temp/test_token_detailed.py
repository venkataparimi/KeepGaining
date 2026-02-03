"""
Test token with detailed header debugging
"""
import asyncio
import aiohttp
import json
from pathlib import Path

TOKEN_FILE = Path(__file__).parent.parent / 'data' / 'upstox_token.json'

async def test_with_debug():
    with open(TOKEN_FILE) as f:
        token_data = json.load(f)
        token = token_data['access_token']
    
    print("=" * 70)
    print("DETAILED TOKEN TEST")
    print("=" * 70)
    print(f"\nToken: {token[:30]}...{token[-30:]}")
    print(f"Token length: {len(token)}")
    
    # Build authorization header
    auth_header = f'Bearer {token}'
    print(f"\nAuth header: {auth_header[:50]}...{auth_header[-30:]}")
    print(f"Auth header length: {len(auth_header)}")
    
    async with aiohttp.ClientSession() as session:
        # Test with Profile API
        url = "https://api.upstox.com/v2/user/profile"
        headers = {
            'Authorization': auth_header,
            'Accept': 'application/json'
        }
        
        print(f"\n📡 Calling: {url}")
        print(f"Headers: {headers}")
        
        async with session.get(url, headers=headers) as resp:
            print(f"\n📥 Response:")
            print(f"  Status: {resp.status}")
            print(f"  Headers: {dict(resp.headers)}")
            
            text = await resp.text()
            print(f"  Body: {text[:500]}")
            
            if resp.status == 200:
                print("\n✅ SUCCESS! Token is working!")
            elif resp.status == 401:
                print("\n❌ 401 Unauthorized")
                print("\nPossible issues:")
                print("1. Token has actually expired (despite JWT showing otherwise)")
                print("2. Token was revoked")
                print("3. API access not enabled on account")
                print("4. Wrong API key/secret used during token generation")
                
                # Try to parse error
                try:
                    error_data = json.loads(text)
                    print(f"\nError details: {json.dumps(error_data, indent=2)}")
                except:
                    pass

if __name__ == "__main__":
    asyncio.run(test_with_debug())
