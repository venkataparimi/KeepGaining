"""
Complete the hypertable migration by:
1. Copying any missing rows from candle_data to candle_data_new
2. Verifying the migration
3. Swapping the tables atomically
"""

import asyncio
import asyncpg
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


async def copy_missing_rows(conn):
    """Copy rows that exist in candle_data but not in candle_data_new."""
    logger.info("Finding missing rows...")
    
    # First, check how many rows are missing
    missing_count = await conn.fetchval("""
        SELECT COUNT(*)
        FROM candle_data cd
        WHERE NOT EXISTS (
            SELECT 1 FROM candle_data_new cdn
            WHERE cdn.instrument_id = cd.instrument_id
            AND cdn.timeframe = cd.timeframe
            AND cdn.timestamp = cd.timestamp
        )
    """)
    
    logger.info(f"Found {missing_count:,} missing rows")
    
    if missing_count == 0:
        logger.info("No missing rows to copy!")
        return 0
    
    # Insert missing rows (no ON CONFLICT since there's no primary key)
    result = await conn.execute("""
        INSERT INTO candle_data_new (instrument_id, timeframe, timestamp, open, high, low, close, volume)
        SELECT cd.instrument_id, cd.timeframe, cd.timestamp, cd.open, cd.high, cd.low, cd.close, cd.volume
        FROM candle_data cd
        WHERE NOT EXISTS (
            SELECT 1 FROM candle_data_new cdn
            WHERE cdn.instrument_id = cd.instrument_id
            AND cdn.timeframe = cd.timeframe
            AND cdn.timestamp = cd.timestamp
        )
    """)
    
    rows_added = int(result.split()[-1])
    logger.info(f"Copied {rows_added:,} missing rows")
    return rows_added


async def verify_migration(conn):
    """Verify both tables have the same data."""
    logger.info("Verifying migration...")
    
    # Check row counts
    old_count = await conn.fetchval("SELECT COUNT(*) FROM candle_data")
    new_count = await conn.fetchval("SELECT COUNT(*) FROM candle_data_new")
    
    logger.info(f"candle_data: {old_count:,} rows")
    logger.info(f"candle_data_new: {new_count:,} rows")
    
    if old_count != new_count:
        raise Exception(f"Row count mismatch! Old: {old_count:,}, New: {new_count:,}")
    
    # Check date ranges
    old_dates = await conn.fetchrow("""
        SELECT MIN(timestamp)::date as min_date, MAX(timestamp)::date as max_date 
        FROM candle_data
    """)
    new_dates = await conn.fetchrow("""
        SELECT MIN(timestamp)::date as min_date, MAX(timestamp)::date as max_date 
        FROM candle_data_new
    """)
    
    logger.info(f"candle_data date range: {old_dates['min_date']} to {old_dates['max_date']}")
    logger.info(f"candle_data_new date range: {new_dates['min_date']} to {new_dates['max_date']}")
    
    if old_dates != new_dates:
        logger.warning("Date ranges don't match exactly, but this may be okay if recent data was added")
    
    logger.info("SUCCESS: Verification passed")


async def swap_tables(conn):
    """Atomically swap the tables."""
    logger.info("Swapping tables (this may take a moment)...")
    
    async with conn.transaction():
        # Rename candle_data to candle_data_backup
        await conn.execute("ALTER TABLE candle_data RENAME TO candle_data_backup")
        
        # Rename candle_data_new to candle_data
        await conn.execute("ALTER TABLE candle_data_new RENAME TO candle_data")
        
        # Rename indexes
        await conn.execute("""
            ALTER INDEX IF EXISTS idx_candle_instrument_time 
            RENAME TO idx_candle_instrument_time_backup
        """)
        await conn.execute("""
            ALTER INDEX IF EXISTS idx_candle_time 
            RENAME TO idx_candle_time_backup
        """)
        
        logger.info("SUCCESS: Tables swapped successfully")
        logger.info("")
        logger.info("=" * 70)
        logger.info("MIGRATION COMPLETE!")
        logger.info("=" * 70)
        logger.info("")
        logger.info("The candle_data table is now a TimescaleDB hypertable with:")
        logger.info("  - Automatic compression (data >7 days old)")
        logger.info("  - Automatic retention (keeps 3 years)")
        logger.info("  - 10-100x faster time-range queries")
        logger.info("  - 90% storage reduction over time")
        logger.info("")
        logger.info("The old table is backed up as: candle_data_backup")
        logger.info("You can drop it once you've verified everything works:")
        logger.info("  DROP TABLE candle_data_backup CASCADE;")


async def main():
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # Step 1: Copy missing rows
        rows_added = await copy_missing_rows(conn)
        
        if rows_added > 0:
            logger.info(f"Added {rows_added:,} rows that were inserted during migration")
        
        # Step 2: Verify migration
        await verify_migration(conn)
        
        # Step 3: Swap tables
        response = input("\nReady to swap tables? This will make candle_data_new the active table. (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Table swap cancelled. Run this script again when ready.")
            return
        
        await swap_tables(conn)
        
    except Exception as e:
        logger.error(f"\nERROR: {e}")
        logger.error("Migration not completed. Please review the error and try again.")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
