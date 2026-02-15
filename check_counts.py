
import asyncio
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy import select, func
from app.db.session import get_db_context
from app.db.models.instrument import InstrumentMaster

async def main():
    async with get_db_context() as db:
        for type_ in ['FUTURES', 'FUT']:
            stmt = select(func.count()).where(InstrumentMaster.instrument_type == type_)
            count = await db.scalar(stmt)
            print(f"Type '{type_}': {count} records")
            
            # Sample
            if count > 0:
                sample_stmt = select(InstrumentMaster.trading_symbol, InstrumentMaster.underlying).where(InstrumentMaster.instrument_type == type_).limit(5)
                samples = await db.execute(sample_stmt)
                print(f"  Samples: {samples.all()}")
        
        # Check NIFTY futures
        stmt = select(InstrumentMaster.trading_symbol, InstrumentMaster.instrument_type).where(
            InstrumentMaster.trading_symbol.like('%NIFTY%FUT%')
        )
        res = await db.execute(stmt)
        print(f"\nNIFTY Futures found: {res.all()}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")
