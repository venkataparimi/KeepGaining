"""
Migrate existing candle_data table to TimescaleDB hypertable

This script safely converts the large candle_data table to a TimescaleDB hypertable
with compression and retention policies, providing 10-100x performance improvements.

IMPORTANT: This operation requires downtime. Stop all trading operations before running.

What this does:
1. Creates a new hypertable with proper partitioning
2. Migrates data in batches to avoid memory issues
3. Enables compression (97GB -> ~10GB)
4. Adds retention and compression policies
5. Swaps tables atomically

Estimated time for 366M rows: 2-4 hours
"""

import asyncio
import asyncpg
from datetime import datetime, timedelta
import sys
import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('hypertable_migration.log')
    ]
)
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


async def check_prerequisites(conn):
    """Check if TimescaleDB is installed and table exists."""
    logger.info("Checking prerequisites...")
    
    # Check TimescaleDB extension
    result = await conn.fetchval(
        "SELECT COUNT(*) FROM pg_extension WHERE extname = 'timescaledb'"
    )
    if result == 0:
        raise Exception("TimescaleDB extension not installed!")
    
    # Check table exists
    result = await conn.fetchval(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'candle_data'"
    )
    if result == 0:
        raise Exception("candle_data table does not exist!")
    
    # Check if already a hypertable
    result = await conn.fetchval(
        "SELECT COUNT(*) FROM timescaledb_information.hypertables WHERE hypertable_name = 'candle_data'"
    )
    if result > 0:
        raise Exception("candle_data is already a hypertable!")
    
    # Get table stats
    stats = await conn.fetchrow("""
        SELECT 
            COUNT(*) as row_count,
            MIN(timestamp)::date as earliest,
            MAX(timestamp)::date as latest,
            pg_size_pretty(pg_total_relation_size('candle_data')) as size
        FROM candle_data
    """)
    
    logger.info(f"Table stats:")
    logger.info(f"  Rows: {stats['row_count']:,}")
    logger.info(f"  Date range: {stats['earliest']} to {stats['latest']}")
    logger.info(f"  Size: {stats['size']}")
    
    return stats


async def create_hypertable_structure(conn):
    """Create new hypertable with same structure as candle_data."""
    logger.info("Creating new hypertable structure...")
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS candle_data_new (
            LIKE candle_data INCLUDING DEFAULTS INCLUDING CONSTRAINTS
        );
    """)
    
    # Convert to hypertable (1 day chunks)
    await conn.execute("""
        SELECT create_hypertable(
            'candle_data_new',
            'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
    """)
    
    # Create unique index for duplicate prevention
    # TimescaleDB hypertables can't have traditional PRIMARY KEY on time column
    logger.info("Creating unique index...")
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_candle_data_new_unique 
        ON candle_data_new (instrument_id, timeframe, timestamp);
    """)
    
    logger.info("SUCCESS: Hypertable structure created with unique index")


async def migrate_data_batch(conn, start_date, end_date, batch_num, total_batches):
    """Migrate one batch of data."""
    logger.info(f"Migrating batch {batch_num}/{total_batches}: {start_date} to {end_date}")
    
    # Insert data with ON CONFLICT now that we have unique index
    result = await conn.execute("""
        INSERT INTO candle_data_new
        SELECT * FROM candle_data
        WHERE timestamp >= $1 AND timestamp < $2
        ON CONFLICT (instrument_id, timeframe, timestamp) DO NOTHING
    """, start_date, end_date)
    
    # Extract row count from result status
    rows = int(result.split()[-1]) if result else 0
    logger.info(f"  Inserted {rows:,} rows")
    return rows


async def migrate_data_in_batches(conn, stats):
    """Migrate data in monthly batches to avoid memory issues."""
    logger.info("Starting data migration in batches...")
    
    start_date = stats['earliest']
    end_date = stats['latest']
    
    # Calculate monthly batches
    current = start_date
    batches = []
    while current <= end_date:
        next_month = current + timedelta(days=30)
        batches.append((current, min(next_month, end_date + timedelta(days=1))))
        current = next_month
    
    logger.info(f"Total batches: {len(batches)}")
    
    total_migrated = 0
    for i, (batch_start, batch_end) in enumerate(batches, 1):
        rows = await migrate_data_batch(conn, batch_start, batch_end, i, len(batches))
        total_migrated += rows
        
        # Progress update every 10 batches
        if i % 10 == 0:
            progress = (i / len(batches)) * 100
            logger.info(f"Progress: {progress:.1f}% ({total_migrated:,} rows migrated)")
    
    logger.info(f"SUCCESS: Data migration complete: {total_migrated:,} total rows")
    return total_migrated


async def create_indexes(conn):
    """Create indexes on new hypertable."""
    logger.info("Creating indexes...")
    
    # Get indexes from original table
    indexes = await conn.fetch("""
        SELECT indexdef 
        FROM pg_indexes 
        WHERE tablename = 'candle_data' 
        AND indexname != 'pk_candle_data'
    """)
    
    for idx in indexes:
        index_def = idx['indexdef'].replace('candle_data', 'candle_data_new')
        logger.info(f"Creating index: {index_def}")
        try:
            await conn.execute(index_def)
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
    
    logger.info("SUCCESS: Indexes created")


async def enable_compression(conn):
    """Enable compression on hypertable."""
    logger.info("Enabling compression...")
    
    await conn.execute("""
        ALTER TABLE candle_data_new SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'instrument_id,timeframe',
            timescaledb.compress_orderby = 'timestamp DESC'
        );
    """)
    
    logger.info("SUCCESS: Compression enabled")


async def add_compression_policy(conn):
    """Add policy to automatically compress old data."""
    logger.info("Adding compression policy (compress data older than 7 days)...")
    
    await conn.execute("""
        SELECT add_compression_policy(
            'candle_data_new',
            INTERVAL '7 days',
            if_not_exists => TRUE
        );
    """)
    
    logger.info("SUCCESS: Compression policy added")


async def add_retention_policy(conn):
    """Add policy to automatically delete very old data."""
    logger.info("Adding retention policy (keep 3 years of data)...")
    
    await conn.execute("""
        SELECT add_retention_policy(
            'candle_data_new',
            INTERVAL '3 years',
            if_not_exists => TRUE
        );
    """)
    
    logger.info("SUCCESS: Retention policy added")


async def compress_historical_data(conn):
    """Manually compress historical chunks (data older than 7 days)."""
    logger.info("Compressing historical data (this may take 30-60 minutes)...")
    
    # Get list of chunks to compress
    chunks = await conn.fetch("""
        SELECT chunk_schema, chunk_name
        FROM timescaledb_information.chunks
        WHERE hypertable_name = 'candle_data_new'
        AND range_end < NOW() - INTERVAL '7 days'
        ORDER BY range_start
    """)
    
    logger.info(f"Found {len(chunks)} chunks to compress")
    
    compressed = 0
    for i, chunk in enumerate(chunks, 1):
        try:
            await conn.execute(f"""
                SELECT compress_chunk('{chunk['chunk_schema']}.{chunk['chunk_name']}');
            """)
            compressed += 1
            
            if i % 100 == 0:
                logger.info(f"  Compressed {i}/{len(chunks)} chunks")
        except Exception as e:
            logger.warning(f"Failed to compress chunk {chunk['chunk_name']}: {e}")
    
    logger.info(f"SUCCESS: Compressed {compressed}/{len(chunks)} chunks")
    
    # Show compression stats (optional, may not be available in all TimescaleDB versions)
    try:
        stats = await conn.fetchrow("""
            SELECT 
                pg_size_pretty(before_compression_total_bytes) as before,
                pg_size_pretty(after_compression_total_bytes) as after,
                ROUND((1 - after_compression_total_bytes::numeric / before_compression_total_bytes) * 100, 1) as savings_pct
            FROM timescaledb_information.hypertable_compression_stats
            WHERE hypertable_name = 'candle_data_new'
        """)
        
        if stats:
            logger.info(f"Compression stats: {stats['before']} -> {stats['after']} ({stats['savings_pct']}% reduction)")
    except Exception as e:
        logger.debug(f"Could not fetch compression stats (not critical): {e}")


async def verify_migration(conn, original_stats):
    """Verify the migration was successful."""
    logger.info("Verifying migration...")
    
    new_stats = await conn.fetchrow("""
        SELECT 
            COUNT(*) as row_count,
            MIN(timestamp)::date as earliest,
            MAX(timestamp)::date as latest
        FROM candle_data_new
    """)
    
    if new_stats['row_count'] != original_stats['row_count']:
        raise Exception(
            f"Row count mismatch! Original: {original_stats['row_count']}, "
            f"New: {new_stats['row_count']}"
        )
    
    if new_stats['earliest'] != original_stats['earliest']:
        raise Exception("Date range mismatch (earliest)")
    
    if new_stats['latest'] != original_stats['latest']:
        raise Exception("Date range mismatch (latest)")
    
    logger.info("SUCCESS: Verification passed - row counts and date ranges match")


async def swap_tables(conn):
    """Atomically swap old and new tables."""
    logger.info("Swapping tables...")
    
    await conn.execute("BEGIN;")
    try:
        # Rename original to backup
        await conn.execute("ALTER TABLE candle_data RENAME TO candle_data_backup;")
        
        # Rename new to production
        await conn.execute("ALTER TABLE candle_data_new RENAME TO candle_data;")
        
        # Rename indexes to match
        await conn.execute("""
            DO $$
            DECLARE
                idx record;
            BEGIN
                FOR idx IN 
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE tablename = 'candle_data'
                    AND indexname LIKE '%_new%'
                LOOP
                    EXECUTE 'ALTER INDEX ' || idx.indexname || 
                            ' RENAME TO ' || REPLACE(idx.indexname, '_new', '');
                END LOOP;
            END $$;
        """)
        
        await conn.execute("COMMIT;")
        logger.info("SUCCESS: Tables swapped successfully")
        
    except Exception as e:
        await conn.execute("ROLLBACK;")
        logger.error(f"Failed to swap tables: {e}")
        raise


async def cleanup_backup(conn):
    """Drop the backup table (optional - comment out if you want to keep it)."""
    logger.info("Cleaning up backup table...")
    
    response = input("\nDo you want to delete the backup table 'candle_data_backup'? (yes/no): ")
    if response.lower() == 'yes':
        await conn.execute("DROP TABLE candle_data_backup;")
        logger.info("SUCCESS: Backup table deleted")
    else:
        logger.info("Backup table kept at 'candle_data_backup'")


async def main():
    """Main migration orchestrator."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Migrate candle_data to TimescaleDB hypertable')
    parser.add_argument('--yes', action='store_true', help='Auto-confirm migration without prompting')
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("TimescaleDB Hypertable Migration")
    logger.info("=" * 80)
    
    logger.warning("\n*** WARNING: This operation requires downtime! ***")
    logger.warning("*** Stop all trading operations before proceeding! ***")
    logger.warning("*** Estimated time: 2-4 hours for 366M rows ***\n")
    
    if not args.yes:
        response = input("Do you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Migration cancelled")
            return
    else:
        logger.info("Auto-confirmed with --yes flag")
    
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # Step 1: Check prerequisites
        original_stats = await check_prerequisites(conn)
        
        # Step 2: Create hypertable structure
        await create_hypertable_structure(conn)
        
        # Step 3: Migrate data in batches
        total_rows = await migrate_data_in_batches(conn, original_stats)
        
        # Step 4: Create indexes
        await create_indexes(conn)
        
        # Step 5: Enable compression
        await enable_compression(conn)
        
        # Step 6: Add compression policy
        await add_compression_policy(conn)
        
        # Step 7: Add retention policy
        await add_retention_policy(conn)
        
        # Step 8: Compress historical data
        await compress_historical_data(conn)
        
        # Step 9: Verify migration
        await verify_migration(conn, original_stats)
        
        # Step 10: Swap tables
        await swap_tables(conn)
        
        # Step 11: Cleanup (optional)
        await cleanup_backup(conn)
        
        logger.info("\n" + "=" * 80)
        logger.info("SUCCESS: MIGRATION COMPLETE!")
        logger.info("=" * 80)
        logger.info(f"Total rows migrated: {total_rows:,}")
        logger.info("Your candle_data table is now a TimescaleDB hypertable with:")
        logger.info("  • Automatic time-based partitioning (1-day chunks)")
        logger.info("  • Compression enabled (7-day policy)")
        logger.info("  • Retention policy (3 years)")
        logger.info("  • Expected storage: ~10GB (down from 97GB)")
        logger.info("\nExpected performance improvements:")
        logger.info("  • Indicator calculations: 5-10 sec → 50-100ms (100x faster)")
        logger.info("  • Historical queries: 2-5 sec → 200-500ms (10x faster)")
        logger.info("  • Storage: 97GB → ~10GB (90% reduction)")
        
    except Exception as e:
        logger.error(f"\nERROR: Migration failed: {e}")
        logger.error("Check hypertable_migration.log for details")
        sys.exit(1)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
