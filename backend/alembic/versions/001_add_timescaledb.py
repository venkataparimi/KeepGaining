"""Add TimescaleDB extension and convert OHLCV tables to hypertables

Revision ID: 001_add_timescaledb
Revises: 
Create Date: 2025-12-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250106_001_timescaledb'
down_revision = '20241203_001'  # Run after pivot/CPR migration
branch_labels = None
depends_on = None


def upgrade():
    """
    1. Enable TimescaleDB extension
    2. Convert OHLCV tables to hypertables
    3. Add compression policies
    4. Create continuous aggregations for indicators
    """
    
    # 1. Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
    
    # 2. Convert market_data/ohlcv tables to hypertables (if they exist)
    # Check if tables exist first
    conn = op.get_bind()
    
    # List of tables to convert (add your actual OHLCV table names)
    tables_to_convert = [
        ('market_data', 'timestamp'),
        ('ohlcv_1m', 'timestamp'),
        ('ohlcv_5m', 'timestamp'),
        ('ohlcv_15m', 'timestamp'),
        ('ohlcv_daily', 'timestamp'),
    ]
    
    for table_name, time_column in tables_to_convert:
        # Check if table exists
        result = conn.execute(sa.text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = '{table_name}'
            );
        """))
        
        if result.scalar():
            print(f"Converting {table_name} to hypertable...")
            try:
                # Convert to hypertable
                op.execute(f"""
                    SELECT create_hypertable(
                        '{table_name}', 
                        '{time_column}',
                        chunk_time_interval => INTERVAL '1 day',
                        if_not_exists => TRUE
                    );
                """)
                
                # Add compression policy (compress data older than 7 days)
                op.execute(f"""
                    ALTER TABLE {table_name} SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = 'symbol'
                    );
                """)
                
                op.execute(f"""
                    SELECT add_compression_policy(
                        '{table_name}', 
                        INTERVAL '7 days',
                        if_not_exists => TRUE
                    );
                """)
                
                # Add data retention policy (keep 2 years)
                op.execute(f"""
                    SELECT add_retention_policy(
                        '{table_name}', 
                        INTERVAL '2 years',
                        if_not_exists => TRUE
                    );
                """)
                
                print(f"✅ {table_name} converted to hypertable with compression and retention")
                
            except Exception as e:
                print(f"⚠️ Could not convert {table_name}: {e}")
        else:
            print(f"ℹ️ Table {table_name} does not exist, skipping...")
    
    # 3. Create continuous aggregations for common indicators
    # Example: 1-minute SMA-20 (adjust table name as needed)
    try:
        op.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_1m_sma20
            WITH (timescaledb.continuous) AS
            SELECT 
                symbol,
                time_bucket('1 minute', timestamp) AS bucket,
                AVG(close) OVER (
                    PARTITION BY symbol 
                    ORDER BY time_bucket('1 minute', timestamp)
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) as sma_20,
                AVG(volume) OVER (
                    PARTITION BY symbol 
                    ORDER BY time_bucket('1 minute', timestamp)
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) as vol_20
            FROM market_data
            GROUP BY symbol, bucket, close, volume
            WITH NO DATA;
        """)
        
        # Add refresh policy (refresh every 1 minute)
        op.execute("""
            SELECT add_continuous_aggregate_policy('ohlcv_1m_sma20',
                start_offset => INTERVAL '1 hour',
                end_offset => INTERVAL '1 minute',
                schedule_interval => INTERVAL '1 minute',
                if_not_exists => TRUE
            );
        """)
        
        print("✅ Created continuous aggregation for SMA-20")
    except Exception as e:
        print(f"⚠️ Could not create continuous aggregation: {e}")


def downgrade():
    """
    Remove TimescaleDB features (use with caution)
    """
    
    # Drop continuous aggregations
    op.execute("DROP MATERIALIZED VIEW IF EXISTS ohlcv_1m_sma20 CASCADE;")
    
    # Note: Cannot easily revert hypertables to regular tables
    # You would need to create new tables and copy data
    print("⚠️ Hypertables cannot be easily reverted. Manual intervention required.")
    
    # Drop extension (will fail if hypertables exist)
    # op.execute("DROP EXTENSION IF EXISTS timescaledb CASCADE;")
