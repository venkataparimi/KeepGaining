"""Quick test script for calendar service."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.calendar_service import CalendarService
from app.db.session import AsyncSessionLocal


async def test():
    async with AsyncSessionLocal() as db:
        svc = CalendarService(db)
        
        # Test today's summary
        print("=" * 60)
        print("Today's Summary:")
        print("=" * 60)
        summary = await svc.get_today_summary()
        for key, value in summary.items():
            print(f"  {key}: {value}")
        
        # Test holidays for 2025
        print("\n" + "=" * 60)
        print("Holidays 2025:")
        print("=" * 60)
        holidays = await svc.get_holidays(2025)
        for h in holidays[:10]:
            print(f"  {h['date']}: {h['name']} ({h['exchange']})")
        print(f"  ... and {len(holidays) - 10} more")
        
        # Test current expiry
        print("\n" + "=" * 60)
        print("Current Expiries:")
        print("=" * 60)
        for underlying in ["NIFTY", "BANKNIFTY", "SENSEX"]:
            expiry = await svc.get_current_expiry(underlying)
            if expiry:
                print(f"  {underlying}: {expiry.expiry_date} ({expiry.days_to_expiry} days)")
            else:
                print(f"  {underlying}: No expiry found")
        
        # Test lot size
        print("\n" + "=" * 60)
        print("Lot Sizes:")
        print("=" * 60)
        for symbol in ["RELIANCE", "TCS", "NIFTY", "BANKNIFTY"]:
            lot_size = await svc.get_lot_size(symbol)
            print(f"  {symbol}: {lot_size}")
        
        print("\n✓ Calendar service test completed!")


if __name__ == "__main__":
    asyncio.run(test())
