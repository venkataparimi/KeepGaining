"""
Quick migration completion - copy recent data only
"""
import asyncio
import asyncpg
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


async def main():
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # Check current counts
        old_count = await conn.fetchval("SELECT COUNT(*) FROM candle_data")
        new_count = await conn.fetchval("SELECT COUNT(*) FROM candle_data_new")
        
        logger.info(f"candle_data: {old_count:,} rows")
        logger.info(f"candle_data_new: {new_count:,} rows")
        logger.info(f"Difference: {old_count - new_count:,} rows")
        
        # Copy last 30 days of data (this should cover what was added during migration)
        cutoff_date = datetime.now() - timedelta(days=30)
        logger.info(f"\nCopying recent data since {cutoff_date.date()}...")
        
        result = await conn.execute(f"""
            INSERT INTO candle_data_new (instrument_id, timeframe, timestamp, open, high, low, close, volume)
            SELECT DISTINCT instrument_id, timeframe, timestamp, open, high, low, close, volume
            FROM candle_data
            WHERE timestamp >= '{cutoff_date}'
        """)
        
        rows_added = int(result.split()[-1]) if result else 0
        logger.info(f"Inserted {rows_added:,} rows from recent data")
        
        # Check new counts
        new_count_after = await conn.fetchval("SELECT COUNT(*) FROM candle_data_new")
        logger.info(f"\ncandle_data_new after insert: {new_count_after:,} rows")
        logger.info(f"New difference: {old_count - new_count_after:,} rows")
        
        if old_count == new_count_after:
            logger.info("\n✓ Row counts match! Ready to swap tables.")
            
            response = input("\nSwap tables now? (yes/no): ")
            if response.lower() == 'yes':
                async with conn.transaction():
                    await conn.execute("ALTER TABLE candle_data RENAME TO candle_data_backup")
                    await conn.execute("ALTER TABLE candle_data_new RENAME TO candle_data")
                    
                logger.info("\n" + "="*70)
                logger.info("MIGRATION COMPLETE!")
                logger.info("="*70)
                logger.info("\ncandle_data is now a TimescaleDB hypertable!")
                logger.info("Old table backed up as: candle_data_backup")
        else:
            logger.warning(f"\nStill {old_count - new_count_after:,} rows missing.")
            logger.warning("The difference may be from historical data added between migrations.")
            logger.warning("You can either:")
            logger.warning("  1. Accept the difference and swap tables")
            logger.warning("  2. Investigate which specific historical data is missing")
            
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
