"""
Setup TimescaleDB Hypertables
Run this after tables are created to convert them to hypertables.
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import engine
from app.core.config import settings


async def check_table_exists(table_name: str) -> bool:
    """Check if a table exists."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = :table_name
                );
                """
            ),
            {"table_name": table_name}
        )
        return result.scalar()


async def setup_hypertable(table_name: str, time_column: str = "timestamp"):
    """Convert a table to TimescaleDB hypertable."""
    print(f"\n🔧 Setting up {table_name}...")
    
    # Check if table exists
    if not await check_table_exists(table_name):
        print(f"⚠️ Table {table_name} does not exist, skipping...")
        return
    
    async with engine.begin() as conn:
        # Check if already a hypertable
        result = await conn.execute(
            text(
                """
                SELECT COUNT(*) FROM timescaledb_information.hypertables 
                WHERE hypertable_name = :table_name;
                """
            ),
            {"table_name": table_name}
        )
        
        if result.scalar() > 0:
            print(f"✅ {table_name} is already a hypertable")
            return
        
        # Convert to hypertable
        await conn.execute(
            text(
                f"""
                SELECT create_hypertable(
                    '{table_name}', 
                    '{time_column}',
                    chunk_time_interval => INTERVAL '1 day',
                    if_not_exists => TRUE
                );
                """
            )
        )
        print(f"✅ Created hypertable: {table_name}")
        
        # Enable compression
        await conn.execute(
            text(
                f"""
                ALTER TABLE {table_name} SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'symbol'
                );
                """
            )
        )
        print(f"✅ Enabled compression for: {table_name}")
        
        # Add compression policy (compress data older than 7 days)
        await conn.execute(
            text(
                f"""
                SELECT add_compression_policy(
                    '{table_name}',
                    INTERVAL '7 days',
                    if_not_exists => TRUE
                );
                """
            )
        )
        print(f"✅ Added compression policy: {table_name}")
        
        # Add retention policy (keep 2 years)
        await conn.execute(
            text(
                f"""
                SELECT add_retention_policy(
                    '{table_name}',
                    INTERVAL '2 years',
                    if_not_exists => TRUE
                );
                """
            )
        )
        print(f"✅ Added retention policy: {table_name}")


async def main():
    """Setup all TimescaleDB hypertables."""
    print("=" * 60)
    print("TimescaleDB Hypertable Setup")
    print("=" * 60)
    
    # Tables to convert
    tables = [
        "market_data",
        "ohlcv_1m",
        "ohlcv_5m",
        "ohlcv_15m",
        "ohlcv_daily",
    ]
    
    try:
        for table in tables:
            await setup_hypertable(table)
        
        # Show hypertable status
        print("\n" + "=" * 60)
        print("Hypertable Status:")
        print("=" * 60)
        
        async with engine.begin() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT 
                        hypertable_name,
                        num_chunks,
                        compression_enabled,
                        tablespaces
                    FROM timescaledb_information.hypertables
                    ORDER BY hypertable_name;
                    """
                )
            )
            
            for row in result:
                print(f"\n📊 {row[0]}")
                print(f"   Chunks: {row[1]}")
                print(f"   Compression: {'Enabled' if row[2] else 'Disabled'}")
        
        print("\n" + "=" * 60)
        print("✅ TimescaleDB setup complete!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
