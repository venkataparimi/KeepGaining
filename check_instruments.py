
import asyncio
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy import select
from app.db.session import get_db_context
from app.db.models.instrument import InstrumentMaster

async def main():
    async with get_db_context() as db:
        result = await db.execute(select(InstrumentMaster.trading_symbol, InstrumentMaster.instrument_type).where(InstrumentMaster.instrument_type == 'INDEX').limit(10))
        instruments = result.all()
        print("Available INDEX instruments:")
        for i in instruments:
            print(f"Symbol: {i.trading_symbol}, Type: {i.instrument_type}")

if __name__ == "__main__":
    asyncio.run(main())
