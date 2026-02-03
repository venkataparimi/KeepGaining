"""
TimescaleDB Helper Functions

Utility functions for working with TimescaleDB hypertables and continuous aggregations.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger


class TimescaleHelper:
    """Helper class for TimescaleDB operations"""
    
    @staticmethod
    async def create_hypertable(
        session: AsyncSession,
        table_name: str,
        time_column: str = 'timestamp',
        chunk_time_interval: str = '1 day',
        if_not_exists: bool = True
    ) -> bool:
        """
        Convert a regular table to a TimescaleDB hypertable.
        
        Args:
            session: Database session
            table_name: Name of the table to convert
            time_column: Name of the timestamp column
            chunk_time_interval: Size of time chunks
            if_not_exists: Don't error if already a hypertable
            
        Returns:
            True if successful, False otherwise
        """
        try:
            query = text(f"""
                SELECT create_hypertable(
                    '{table_name}',
                    '{time_column}',
                    chunk_time_interval => INTERVAL '{chunk_time_interval}',
                    if_not_exists => {if_not_exists}
                );
            """)
            await session.execute(query)
            await session.commit()
            logger.info(f"Created hypertable: {table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create hypertable {table_name}: {e}")
            return False
    
    @staticmethod
    async def enable_compression(
        session: AsyncSession,
        table_name: str,
        segment_by: Optional[str] = 'symbol',
        order_by: Optional[str] = 'timestamp DESC'
    ) -> bool:
        """
        Enable compression on a hypertable.
        
        Args:
            session: Database session
            table_name: Name of the hypertable
            segment_by: Column to segment compression by (e.g., symbol)
            order_by: Column ordering for compression
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Set compression settings
            settings = [f"timescaledb.compress"]
            if segment_by:
                settings.append(f"timescaledb.compress_segmentby = '{segment_by}'")
            if order_by:
                settings.append(f"timescaledb.compress_orderby = '{order_by}'")
            
            query = text(f"""
                ALTER TABLE {table_name} SET (
                    {', '.join(settings)}
                );
            """)
            await session.execute(query)
            await session.commit()
            logger.info(f"Enabled compression on {table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to enable compression on {table_name}: {e}")
            return False
    
    @staticmethod
    async def add_compression_policy(
        session: AsyncSession,
        table_name: str,
        compress_after: str = '7 days'
    ) -> bool:
        """
        Add automatic compression policy.
        
        Args:
            session: Database session
            table_name: Name of the hypertable
            compress_after: Compress data older than this interval
            
        Returns:
            True if successful, False otherwise
        """
        try:
            query = text(f"""
                SELECT add_compression_policy(
                    '{table_name}',
                    INTERVAL '{compress_after}',
                    if_not_exists => TRUE
                );
            """)
            await session.execute(query)
            await session.commit()
            logger.info(f"Added compression policy to {table_name}: compress after {compress_after}")
            return True
        except Exception as e:
            logger.error(f"Failed to add compression policy to {table_name}: {e}")
            return False
    
    @staticmethod
    async def add_retention_policy(
        session: AsyncSession,
        table_name: str,
        retain_for: str = '2 years'
    ) -> bool:
        """
        Add data retention policy (auto-delete old data).
        
        Args:
            session: Database session
            table_name: Name of the hypertable
            retain_for: Keep data for this interval
            
        Returns:
            True if successful, False otherwise
        """
        try:
            query = text(f"""
                SELECT add_retention_policy(
                    '{table_name}',
                    INTERVAL '{retain_for}',
                    if_not_exists => TRUE
                );
            """)
            await session.execute(query)
            await session.commit()
            logger.info(f"Added retention policy to {table_name}: retain for {retain_for}")
            return True
        except Exception as e:
            logger.error(f"Failed to add retention policy to {table_name}: {e}")
            return False
    
    @staticmethod
    async def get_hypertables(session: AsyncSession) -> List[Dict[str, Any]]:
        """Get list of all hypertables"""
        try:
            query = text("""
                SELECT 
                    hypertable_schema,
                    hypertable_name,
                    num_chunks,
                    compression_enabled,
                    pg_size_pretty(total_bytes) as total_size
                FROM timescaledb_information.hypertables
                ORDER BY hypertable_name;
            """)
            result = await session.execute(query)
            return [dict(row._mapping) for row in result]
        except Exception as e:
            logger.error(f"Failed to get hypertables: {e}")
            return []
    
    @staticmethod
    async def get_compression_stats(
        session: AsyncSession,
        table_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get compression statistics"""
        try:
            where_clause = f"WHERE hypertable_name = '{table_name}'" if table_name else ""
            query = text(f"""
                SELECT 
                    hypertable_name,
                    pg_size_pretty(before_compression_total_bytes) as before_size,
                    pg_size_pretty(after_compression_total_bytes) as after_size,
                    round(
                        100 - (after_compression_total_bytes::numeric / 
                               NULLIF(before_compression_total_bytes, 0)::numeric) * 100, 
                        2
                    ) as compression_ratio
                FROM timescaledb_information.compression_stats
                {where_clause}
                ORDER BY hypertable_name;
            """)
            result = await session.execute(query)
            return [dict(row._mapping) for row in result]
        except Exception as e:
            logger.error(f"Failed to get compression stats: {e}")
            return []
    
    @staticmethod
    async def refresh_continuous_aggregate(
        session: AsyncSession,
        view_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> bool:
        """
        Manually refresh a continuous aggregate.
        
        Args:
            session: Database session
            view_name: Name of the continuous aggregate view
            start_time: Start of refresh window (None = earliest)
            end_time: End of refresh window (None = now)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            start = f"'{start_time.isoformat()}'" if start_time else "NULL"
            end = f"'{end_time.isoformat()}'" if end_time else "NULL"
            
            query = text(f"""
                CALL refresh_continuous_aggregate(
                    '{view_name}',
                    {start},
                    {end}
                );
            """)
            await session.execute(query)
            await session.commit()
            logger.info(f"Refreshed continuous aggregate: {view_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to refresh continuous aggregate {view_name}: {e}")
            return False


# Convenience functions for common operations

async def setup_ohlcv_hypertable(
    session: AsyncSession,
    table_name: str
) -> bool:
    """
    Complete setup for an OHLCV hypertable with compression and retention.
    
    Usage:
        await setup_ohlcv_hypertable(session, 'market_data')
    """
    helper = TimescaleHelper()
    
    # Create hypertable
    if not await helper.create_hypertable(session, table_name):
        return False
    
    # Enable compression
    if not await helper.enable_compression(session, table_name, segment_by='symbol'):
        logger.warning(f"Compression setup failed for {table_name}")
    
    # Add compression policy (compress after 7 days)
    if not await helper.add_compression_policy(session, table_name, compress_after='7 days'):
        logger.warning(f"Compression policy failed for {table_name}")
    
    # Add retention policy (keep 2 years)
    if not await helper.add_retention_policy(session, table_name, retain_for='2 years'):
        logger.warning(f"Retention policy failed for {table_name}")
    
    logger.info(f"✅ Complete TimescaleDB setup for {table_name}")
    return True


async def get_timescale_health(session: AsyncSession) -> Dict[str, Any]:
    """
    Get TimescaleDB health and statistics.
    
    Returns:
        Dictionary with health metrics
    """
    helper = TimescaleHelper()
    
    return {
        "hypertables": await helper.get_hypertables(session),
        "compression_stats": await helper.get_compression_stats(session)
    }
