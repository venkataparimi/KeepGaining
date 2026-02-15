
import asyncio
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy import select, distinct, func
from app.db.session import get_db_context
from app.db.models.instrument import InstrumentMaster

async def main():
    async with get_db_context() as db:
        # Count Options
        count = await db.scalar(select(func.count()).where(InstrumentMaster.instrument_type == 'OPTION'))
        print(f"Total Options in InstrumentMaster: {count}")
        
        # Check OptionMaster
        from app.db.models.instrument import OptionMaster
        stmt = select(OptionMaster).limit(5)
        result = await db.execute(stmt)
        opt_masters = result.scalars().all()
        print(f"Sample OptionMaster records: {len(opt_masters)}")
        for om in opt_masters:
             print(f"Option ID: {om.option_id}, Underlying ID: {om.underlying_instrument_id}")

if __name__ == "__main__":
    asyncio.run(main())
