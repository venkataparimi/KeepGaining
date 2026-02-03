"""
Simple token debug - check basic info
"""
import json
import base64
from pathlib import Path
from datetime import datetime

TOKEN_FILE = Path(__file__).parent.parent / 'data' / 'upstox_token.json'

with open(TOKEN_FILE) as f:
    token_data = json.load(f)

print("=" * 70)
print("TOKEN INFO")
print("=" * 70)

print(f"\nUser: {token_data.get('user_name')}")
print(f"User ID: {token_data.get('user_id')}")
print(f"Saved at: {token_data.get('saved_at')}")

token = token_data.get('access_token')
print(f"\nToken length: {len(token)} characters")

# Try to decode JWT payload (middle part)
try:
    parts = token.split('.')
    if len(parts) == 3:
        # Decode payload (add padding if needed)
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded_bytes = base64.urlsafe_b64decode(payload)
        payload_data = json.loads(decoded_bytes)
        
        print("\nJWT Payload:")
        for key, value in payload_data.items():
            if key == 'exp':
                exp_time = datetime.fromtimestamp(value)
                now = datetime.now()
                print(f"  exp: {exp_time}")
                if exp_time > now:
                    hours_left = (exp_time - now).total_seconds() / 3600
                    print(f"  ✅ Valid for: {hours_left:.1f} hours")
                else:
                    hours_ago = (now - exp_time).total_seconds() / 3600
                    print(f"  ❌ EXPIRED {hours_ago:.1f} hours ago!")
            elif key == 'iat':
                iat_time = datetime.fromtimestamp(value)
                print(f"  iat: {iat_time}")
            else:
                print(f"  {key}: {value}")
except Exception as e:
    print(f"\n❌ Could not decode: {e}")

print("\n" + "=" * 70)
