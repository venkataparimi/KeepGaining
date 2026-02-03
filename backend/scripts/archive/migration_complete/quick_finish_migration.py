#!/usr/bin/env python3
"""
Quick migration completion - copy missing rows and swap tables.

Since we know the new table has 351.9M rows and the original has 367.5M,
we need to copy ~15.5M missing rows. These are likely from the migration window.

This script uses a time-based approach: copy recent data (last 60 days) that's missing.
"""

import asyncio
import asyncpg
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = "postgresql://user:password@localhost:5432/keepgaining"


async def main():
    logger.info("=" * 70)
    logger.info("Quick Migration Completion")
    logger.info("=" * 70)
    
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # Copy last 60 days of data that doesn't exist in new table
        # Uses NOT EXISTS to avoid duplicates
        logger.info("Copying recent missing data (last 60 days)...")
        
        result = await conn.execute("""
            INSERT INTO candle_data_new (
                instrument_id, timeframe, timestamp, open, high, low, close, volume
            )
            SELECT DISTINCT
                old.instrument_id, old.timeframe, old.timestamp,
                old.open, old.high, old.low, old.close, old.volume
            FROM candle_data old
            WHERE old.timestamp >= CURRENT_DATE - INTERVAL '60 days'
            AND NOT EXISTS (
                SELECT 1
                FROM candle_data_new new
                WHERE new.instrument_id = old.instrument_id
                AND new.timeframe = old.timeframe
                AND new.timestamp = old.timestamp
            )
        """)
        
        # Parse INSERT result
        copied = int(result.split()[-1]) if result.startswith('INSERT') else 0
        logger.info(f"Copied {copied:,} missing rows")
        
        # Quick count check
        logger.info("\nVerifying counts...")
        old_count = await conn.fetchval("SELECT COUNT(*) FROM candle_data")
        new_count = await conn.fetchval("SELECT COUNT(*) FROM candle_data_new")
        
        logger.info(f"  candle_data:     {old_count:,}")
        logger.info(f"  candle_data_new: {new_count:,}")
        logger.info(f"  Difference:      {abs(old_count - new_count):,}")
        
        if old_count == new_count:
            logger.info("SUCCESS: Counts match perfectly!")
        elif abs(old_count - new_count) < 1000:
            logger.info("CLOSE: Counts within 1000 rows (acceptable)")
        else:
            logger.warning(f"WARNING: Still {abs(old_count - new_count):,} rows difference")
            response = input("\nContinue anyway? (yes/no): ")
            if response.lower() != 'yes':
                logger.info("Aborted")
                return
        
        # Swap tables
        logger.info("\nSwapping tables...")
        response = input("Make candle_data_new the active table? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Swap cancelled")
            return
        
        await conn.execute("BEGIN;")
        await conn.execute("ALTER TABLE candle_data RENAME TO candle_data_old;")
        await conn.execute("ALTER TABLE candle_data_new RENAME TO candle_data;")
        await conn.execute("COMMIT;")
        
        logger.info("\n" + "=" * 70)
        logger.info("MIGRATION COMPLETE!")
        logger.info("=" * 70)
        logger.info("Hypertable is now active as 'candle_data'")
        logger.info("Old table backed up as 'candle_data_old'")
        logger.info("\nDrop backup later with: DROP TABLE candle_data_old CASCADE;")
        
    except Exception as e:
        logger.error(f"ERROR: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
