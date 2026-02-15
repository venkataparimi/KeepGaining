
import asyncio
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy import select, distinct
from app.db.session import get_db_context
from app.db.models.instrument import InstrumentMaster

async def main():
    async with get_db_context() as db:
        stmt = select(distinct(InstrumentMaster.instrument_type))
        result = await db.execute(stmt)
        types = result.scalars().all()
        print(f"Distinct Instrument Types: {types}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")
