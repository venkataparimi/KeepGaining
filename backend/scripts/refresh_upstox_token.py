"""
Refresh Upstox Access Token

This script guides you through refreshing your Upstox access token.
Upstox tokens expire after 24 hours and need to be refreshed daily.
"""
import os
import sys
from pathlib import Path
import asyncio
import httpx
import json
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

load_dotenv()

async def refresh_token():
    """Guide user through Upstox token refresh"""
    
    api_key = os.getenv('UPSTOX_API_KEY')
    api_secret = os.getenv('UPSTOX_API_SECRET')
    redirect_uri = os.getenv('UPSTOX_REDIRECT_URI', 'http://localhost:8000/callback')
    
    if not api_key or not api_secret:
        print("❌ Error: Upstox credentials not found in .env file")
        print("\nRequired variables:")
        print("  UPSTOX_CLIENT_ID=your_api_key")
        print("  UPSTOX_CLIENT_SECRET=your_api_secret")
        print("  UPSTOX_REDIRECT_URI=http://localhost:8000/callback")
        return
    
    print("="*70)
    print("  🔄 UPSTOX TOKEN REFRESH")
    print("="*70)
    
    # Step 1: Generate authorization URL
    auth_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?client_id={api_key}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
    )
    
    print("\n📋 STEP 1: Get Authorization Code")
    print("-"*70)
    print("\n1. Open this URL in your browser:")
    print(f"\n   {auth_url}\n")
    print("2. Login to your Upstox account")
    print("3. Grant permissions")
    print("4. You'll be redirected to a URL like:")
    print(f"   {redirect_uri}?code=XXXXXX")
    print("\n5. Copy the 'code' parameter from the URL")
    
    # Get code from user
    print("\n" + "-"*70)
    code = input("\n📝 Enter the authorization code: ").strip()
    
    if not code:
        print("❌ No code provided. Exiting...")
        return
    
    # Step 2: Exchange code for access token
    print("\n📋 STEP 2: Exchange Code for Access Token")
    print("-"*70)
    
    print(f"\n🔄 Exchanging code...")
    
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
            
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token", "")
                
                print("\n" + "="*70)
                print("✅ SUCCESS! Access token obtained!")
                print("="*70)
                
                if len(token) > 40:
                    print(f"\n🔑 Token: {token[:30]}...{token[-10:]}")
                else:
                    print(f"\n🔑 Token: {token}")
                
                print(f"👤 User ID: {data.get('user_id', 'N/A')}")
                print(f"📧 Email: {data.get('email', 'N/A')}")
                
                # Save token
                token_dir = Path(__file__).parent.parent / "data"
                token_dir.mkdir(exist_ok=True)
                token_file = token_dir / "upstox_token.json"
                
                data["saved_at"] = datetime.now().isoformat()
                data["auth_mode"] = "manual"
                
                with open(token_file, "w") as f:
                    json.dump(data, f, indent=2)
                
                print(f"\n💾 Token saved to: {token_file}")
                print(f"📅 Valid until: {datetime.now().strftime('%Y-%m-%d %H:%M')} + 24 hours")
                
                print("\n" + "="*70)
                print("✅ READY TO DOWNLOAD DATA!")
                print("="*70)
                print("\n💡 You can now run:")
                print("   python scripts/backfill_equity_data.py --symbol IEX --start 2025-12-01 --end 2025-12-07 --timeframe 5min")
                
            else:
                print(f"\n❌ Failed to get token")
                print(f"Status: {response.status_code}")
                print(f"Response: {response.text}")
                
                if response.status_code == 400:
                    error_data = response.json()
                    errors = error_data.get('errors', [])
                    if errors:
                        print("\n⚠️  Common issues:")
                        print("   - Code already used (get a new one)")
                        print("   - Code expired (valid for 5 minutes)")
                        print("   - Invalid redirect URI")
                        
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    print("\n⏰ Note: Upstox tokens expire after 24 hours")
    print("   You'll need to refresh daily for automated data downloads\n")
    
    asyncio.run(refresh_token())
