import os
import asyncio
import httpx
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CODE = "TCa9UD"

async def exchange_code():
    api_key = os.getenv('UPSTOX_CLIENT_ID')
    api_secret = os.getenv('UPSTOX_CLIENT_SECRET')
    redirect_uri = os.getenv('UPSTOX_REDIRECT_URI')
    
    print(f"Exchanging code: {CODE}")
    print(f"API Key: {api_key[:8]}...")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.upstox.com/v2/login/authorization/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={
                "code": CODE,
                "client_id": api_key,
                "client_secret": api_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=30.0
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token", "")
            print()
            print("=" * 50)
            print("SUCCESS! Access token obtained!")
            print("=" * 50)
            if len(token) > 40:
                print(f"Token: {token[:30]}...{token[-10:]}")
            else:
                print(f"Token: {token}")
            print(f"User ID: {data.get('user_id', 'N/A')}")
            print(f"Email: {data.get('email', 'N/A')}")
            
            # Save token
            os.makedirs("data", exist_ok=True)
            data["saved_at"] = datetime.now().isoformat()
            data["auth_mode"] = "manual"
            with open("data/upstox_token.json", "w") as f:
                json.dump(data, f, indent=2)
            print()
            print("Token saved to data/upstox_token.json")
        else:
            print(f"Failed: {response.text}")

asyncio.run(exchange_code())
