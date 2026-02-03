import asyncio
import os
import json
import sys
from dotenv import load_dotenv

# Load .env
load_dotenv('c:/sources/KeepGaining/.env')

# Add project root to PYTHONPATH
sys.path.append('c:/sources/KeepGaining')

from backend.app.comet.mcp_client import comet_client

async def main():
    print("Testing Comet with Anthropic...")
    
    # Verify key is present
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        print("ERROR: ANTHROPIC_API_KEY not found in .env")
        return
    print(f"Key found: {key[:5]}...")
    
    # Run analysis
    try:
        result = await comet_client.analyze({
            "type": "breakout_confirm", 
            "symbol": "RELIANCE", 
            "price": 2500,
            "event": "Breakout above resistance"
        })
        
        print("\n--- Analysis Result ---")
        print(json.dumps(result, indent=2))
        
        if result.get("data_freshness") == "unavailable":
            print("\nWARNING: Received fallback response (Service Unavailable)")
        else:
            print("\nSUCCESS: Received AI-generated analysis")
            
    except Exception as e:
        print(f"\nFAILURE: {e}")

if __name__ == "__main__":
    asyncio.run(main())
