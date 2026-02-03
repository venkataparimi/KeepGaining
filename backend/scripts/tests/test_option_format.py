"""Test option symbol format"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime, timedelta
from app.brokers.fyers import FyersBroker
from loguru import logger

async def test():
    broker = FyersBroker()
    
    # Test the format you provided
    test_symbol = "NSE:SBIN25NOV980CE"
    
    logger.info(f"Testing: {test_symbol}")
    
    try:
        df = await broker.get_historical_data(
            symbol=test_symbol,
            resolution="1",
            start_date=datetime.now() - timedelta(days=7),
            end_date=datetime.now()
        )
        
        if not df.empty:
            logger.success(f"✓ SUCCESS! Got {len(df)} candles")
            logger.success(f"Format confirmed: NSE:STOCK25NOVSTRIKEOPTIONTYPE")
            return True
        else:
            logger.warning("Empty data")
            return False
    except Exception as e:
        logger.error(f"Failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test())
