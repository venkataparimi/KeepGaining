import asyncio
import sys
import os
from dotenv import load_dotenv

# Load .env
load_dotenv('c:/sources/KeepGaining/.env')

# Add project root and backend to PYTHONPATH
sys.path.append('c:/sources/KeepGaining')
sys.path.append('c:/sources/KeepGaining/backend')

from app.services.market_service import market_service

async def main():
    print("Testing MarketService (Real-Time Data)...")
    
    try:
        # Test Sector Performance
        print("\n--- Fetching Sector Performance ---")
        sectors = await market_service.get_sector_performance()
        if sectors:
            print(f"Success! Retrieved {len(sectors)} sectors.")
            for s in sectors[:3]:
                print(f"{s['sector']}: {s['change_percent']}%")
        else:
            print("Warning: No sector data returned (Market might be closed or API issue)")

        # Test F&O Movers
        print("\n--- Fetching F&O Movers ---")
        movers = await market_service.get_fno_movers()
        if movers['top_gainers']:
            print("Success! Retrieved F&O movers.")
            print("Top Gainer:", movers['top_gainers'][0])
        else:
            print("Warning: No F&O data returned")
            
    except Exception as e:
        print(f"\nFAILURE: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
