
import asyncio
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy import select
from app.db.session import get_db_context
from app.db.models.instrument import InstrumentMaster, OptionMaster

async def main():
    async with get_db_context() as db:
        # Find underlying ID for ADANIENT
        stmt = select(InstrumentMaster.instrument_id).where(InstrumentMaster.trading_symbol == 'ADANIENT')
        underlying_id = await db.scalar(stmt)
        
        if not underlying_id:
            print("ADANIENT not found")
            return

        print(f"ADANIENT ID: {underlying_id}")
        
        # Check OptionMaster for this underlying
        stmt = select(OptionMaster).where(
            OptionMaster.underlying_instrument_id == underlying_id
        ).limit(20)
        
        result = await db.execute(stmt)
        options = result.scalars().all()
        
        print("Sample Options:")
        for opt in options:
            print(f"Strike: {opt.strike_price} (Type: {type(opt.strike_price)}), Expiry: {opt.expiry_date}, Type: {opt.option_type}")
            
        # Check specifically for decimals
        # In SQL, we can check for non-integer strikes
        # But let's just do it in python for this sample
        
        print("\nChecking for non-integer strikes...")
        stmt = select(OptionMaster.strike_price).where(
            OptionMaster.underlying_instrument_id == underlying_id
        )
        res = await db.execute(stmt)
        strikes = res.scalars().all()
        
        non_ints = [s for s in strikes if float(s) % 1 != 0]
        print(f"Found {len(non_ints)} non-integer strikes out of {len(strikes)}")
        if non_ints:
            print(f"Sample non-ints: {non_ints[:10]}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
