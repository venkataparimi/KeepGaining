#!/usr/bin/env python3
"""
Finish incomplete hypertable migration by copying missing rows and swapping tables.

This script:
1. Finds rows in candle_data that don't exist in candle_data_new
2. Copies them using efficient batch processing
3. Verifies row counts match
4. Swaps the tables

Run after migrate_to_hypertable.py has completed data migration but failed on verification.
"""

import asyncio
import asyncpg
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://user:password@localhost:5432/keepgaining"


async def find_missing_rows_count(conn):
    """Count rows that exist in original but not in new table."""
    logger.info("Counting missing rows...")
    
    count = await conn.fetchval("""
        SELECT COUNT(*)
        FROM candle_data old
        WHERE NOT EXISTS (
            SELECT 1 
            FROM candle_data_new new
            WHERE new.instrument_id = old.instrument_id
            AND new.timeframe = old.timeframe
            AND new.timestamp = old.timestamp
        )
    """)
    
    return count


async def copy_missing_rows_in_batches(conn):
    """Copy missing rows in time-based batches to avoid long queries."""
    logger.info("Copying missing rows in batches...")
    
    # Get date range of missing data
    date_range = await conn.fetchrow("""
        SELECT 
            MIN(timestamp)::date as min_date,
            MAX(timestamp)::date as max_date
        FROM candle_data old
        WHERE NOT EXISTS (
            SELECT 1 
            FROM candle_data_new new
            WHERE new.instrument_id = old.instrument_id
            AND new.timeframe = old.timeframe
            AND new.timestamp = old.timestamp
        )
    """)
    
    if not date_range or date_range['min_date'] is None:
        logger.info("No missing rows found!")
        return 0
    
    logger.info(f"Missing data date range: {date_range['min_date']} to {date_range['max_date']}")
    
    # Copy in daily batches
    total_copied = 0
    current_date = date_range['min_date']
    
    while current_date <= date_range['max_date']:
        next_date = current_date + timedelta(days=1)
        
        # Copy one day of missing data (using NOT EXISTS to find missing rows)
        result = await conn.execute("""
            INSERT INTO candle_data_new (
                instrument_id, timeframe, timestamp, open, high, low, close, volume
            )
            SELECT 
                old.instrument_id, old.timeframe, old.timestamp, 
                old.open, old.high, old.low, old.close, old.volume
            FROM candle_data old
            WHERE old.timestamp >= $1
            AND old.timestamp < $2
            AND NOT EXISTS (
                SELECT 1 
                FROM candle_data_new new
                WHERE new.instrument_id = old.instrument_id
                AND new.timeframe = old.timeframe
                AND new.timestamp = old.timestamp
            )
        """, current_date, next_date)
        
        copied = result
        
        copied = result
        
        if copied:
            # Parse INSERT result like "INSERT 0 123"
            copied_count = int(copied.split()[-1]) if copied and copied.startswith('INSERT') else 0
            if copied_count > 0:
                total_copied += copied_count
                logger.info(f"  Copied {copied_count:,} rows for {current_date}")
        
        current_date = next_date
    
    return total_copied


async def verify_row_counts(conn):
    """Verify both tables have same row count."""
    logger.info("Verifying row counts...")
    
    counts = await conn.fetch("""
        SELECT 'candle_data' as table_name, COUNT(*) as rows 
        FROM candle_data
        UNION ALL
        SELECT 'candle_data_new', COUNT(*) 
        FROM candle_data_new
    """)
    
    for row in counts:
        logger.info(f"  {row['table_name']}: {row['rows']:,} rows")
    
    original_count = counts[0]['rows']
    new_count = counts[1]['rows']
    
    if original_count == new_count:
        logger.info("SUCCESS: Row counts match!")
        return True
    else:
        diff = abs(original_count - new_count)
        logger.warning(f"WARNING: Row counts differ by {diff:,} rows")
        return False


async def swap_tables(conn):
    """Swap the tables by renaming."""
    logger.info("Swapping tables...")
    
    # Rename in transaction
    await conn.execute("BEGIN;")
    try:
        await conn.execute("ALTER TABLE candle_data RENAME TO candle_data_old;")
        await conn.execute("ALTER TABLE candle_data_new RENAME TO candle_data;")
        await conn.execute("COMMIT;")
        logger.info("SUCCESS: Tables swapped!")
        logger.info("  candle_data (old) -> candle_data_old")
        logger.info("  candle_data_new -> candle_data (active)")
    except Exception as e:
        await conn.execute("ROLLBACK;")
        raise e


async def main():
    logger.info("=" * 70)
    logger.info("Finishing Hypertable Migration")
    logger.info("=" * 70)
    
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # Step 1: Check current state
        await verify_row_counts(conn)
        
        # Step 2: Count missing rows
        missing_count = await find_missing_rows_count(conn)
        logger.info(f"\nMissing rows to copy: {missing_count:,}")
        
        if missing_count == 0:
            logger.info("No missing rows - proceeding to swap tables")
        else:
            # Step 3: Copy missing rows
            logger.info("\nNote: This may take several minutes for large datasets...")
            copied = await copy_missing_rows_in_batches(conn)
            logger.info(f"Copied {copied:,} rows")
            
            # Step 4: Verify again
            matches = await verify_row_counts(conn)
            
            if not matches:
                logger.error("ERROR: Row counts still don't match!")
                logger.error("Manual investigation required.")
                return
        
        # Step 5: Swap tables
        print("\nReady to swap tables.")
        response = input("This will make candle_data_new the active table. Continue? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Swap cancelled")
            return
        
        await swap_tables(conn)
        
        logger.info("\n" + "=" * 70)
        logger.info("MIGRATION COMPLETE!")
        logger.info("=" * 70)
        logger.info("The hypertable is now active as 'candle_data'")
        logger.info("Old table backed up as 'candle_data_old'")
        logger.info("\nYou can drop the backup later with:")
        logger.info("  DROP TABLE candle_data_old CASCADE;")
        
    except Exception as e:
        logger.error(f"\nERROR: {e}")
        logger.error("Migration not completed")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    from datetime import timedelta
    asyncio.run(main())
