
import asyncio
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy import select, func
from app.db.session import get_db_context
from app.db.models.instrument import InstrumentMaster
from app.db.models.timeseries import CandleData

async def main():
    async with get_db_context() as db:
        # Get instrument_id
        result = await db.execute(select(InstrumentMaster.instrument_id).where(InstrumentMaster.trading_symbol == 'NIFTY 50'))
        instrument_id = result.scalar_one_or_none()
        
        if not instrument_id:
            print("Instrument NIFTY 50 not found.")
            return

        # Count candles
        count = await db.scalar(select(func.count()).where(CandleData.instrument_id == instrument_id))
        print(f"Candles for NIFTY 50: {count}")
        
        # Get last candle
        if count > 0:
            last_candle = await db.scalar(select(CandleData).where(CandleData.instrument_id == instrument_id).order_by(CandleData.timestamp.desc()).limit(1))
            print(f"Last candle: {last_candle.timestamp}")
            
            first_candle = await db.scalar(select(CandleData).where(CandleData.instrument_id == instrument_id).order_by(CandleData.timestamp.asc()).limit(1))
            print(f"First candle: {first_candle.timestamp}")

if __name__ == "__main__":
    asyncio.run(main())
