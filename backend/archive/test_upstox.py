"""Quick test for Upstox authentication"""
import os
import asyncio
import httpx
import webbrowser
from dotenv import load_dotenv

load_dotenv()

def test_manual_oauth():
    """Test manual OAuth flow - opens browser"""
    api_key = os.getenv('UPSTOX_CLIENT_ID')
    redirect_uri = os.getenv('UPSTOX_REDIRECT_URI')
    
    print("=" * 50)
    print("Upstox Manual OAuth Test")
    print("=" * 50)
    print(f"API Key: {api_key[:8]}..." if api_key else "API Key: NOT SET")
    print(f"Redirect URI: {redirect_uri}")
    print("=" * 50)
    
    auth_url = f"https://api.upstox.com/v2/login/authorization/dialog?client_id={api_key}&redirect_uri={redirect_uri}&response_type=code"
    
    print(f"\n🌐 Opening browser for Upstox login...")
    print(f"URL: {auth_url[:80]}...")
    
    webbrowser.open(auth_url)
    
    print("\n📋 After login, copy the 'code' from the redirect URL")
    print("   Example: http://127.0.0.1:8080/callback?code=XXXXXX")
    
    code = input("\nPaste the authorization code here: ").strip()
    
    if code:
        asyncio.run(exchange_code(code))
    else:
        print("No code provided.")

async def exchange_code(code: str):
    """Exchange auth code for token"""
    api_key = os.getenv('UPSTOX_CLIENT_ID')
    api_secret = os.getenv('UPSTOX_CLIENT_SECRET')
    redirect_uri = os.getenv('UPSTOX_REDIRECT_URI')
    
    print(f"\n🔄 Exchanging code for token...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.upstox.com/v2/login/authorization/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={
                    "code": code,
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
                print("\n✅ SUCCESS! Access token obtained:")
                print(f"   Token: {token[:20]}...{token[-10:]}" if len(token) > 30 else f"   Token: {token}")
                
                # Save token
                import json
                os.makedirs("data", exist_ok=True)
                with open("data/upstox_token.json", "w") as f:
                    data["saved_at"] = __import__("datetime").datetime.now().isoformat()
                    json.dump(data, f, indent=2)
                print("\n💾 Token saved to data/upstox_token.json")
            else:
                print(f"❌ Failed: {response.text}")
                
        except Exception as e:
            print(f"❌ Error: {e}")

async def test_notification_mode():
    """Test notification mode (requires webhook configured)"""
    api_key = os.getenv('UPSTOX_CLIENT_ID')
    api_secret = os.getenv('UPSTOX_CLIENT_SECRET')
    
    print("=" * 50)
    print("Upstox Notification Mode Test")
    print("=" * 50)
    print("⚠️  Requires webhook URL configured in Upstox Developer Console")
    print("=" * 50)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.upstox.com/v3/login/auth/token/request/{api_key}",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json={"client_secret": api_secret},
            timeout=30.0
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    print("\nChoose test mode:")
    print("1. Manual OAuth (browser login)")
    print("2. Notification mode (requires webhook)")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        test_manual_oauth()
    elif choice == "2":
        asyncio.run(test_notification_mode())
    else:
        print("Invalid choice")
