
import asyncio
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy import select, func
from app.db.session import get_db_context
from app.db.models.instrument import InstrumentMaster, FutureMaster

async def main():
    async with get_db_context() as db:
        # Count InstrumentMaster by type
        stmt = select(InstrumentMaster.instrument_type, func.count()).group_by(InstrumentMaster.instrument_type)
        res = await db.execute(stmt)
        print("InstrumentMaster Counts:")
        for row in res.all():
            print(f"  {row[0]}: {row[1]}")
            
        # Count FutureMaster
        stmt = select(func.count()).select_from(FutureMaster)
        res = await db.scalar(stmt)
        print(f"\nFutureMaster Count: {res}")
        
        # Count FutureMaster with underlying
        stmt = select(func.count()).select_from(FutureMaster).where(FutureMaster.underlying_instrument_id.is_not(None))
        res = await db.scalar(stmt)
        print(f"FutureMaster with Underlying: {res}")
        
        # Print valid samples
        print("\nSample Futures (trading_symbol):")
        stmt = select(InstrumentMaster.trading_symbol).where(InstrumentMaster.instrument_type == 'FUTURES').limit(5)
        res = await db.scalars(stmt)
        for s in res:
            print(f"  {s}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
