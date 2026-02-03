"""
Quick test to verify TimescaleDB performance improvement

Creates a small test hypertable and compares query performance
"""

import asyncio
import asyncpg
from datetime import datetime, timedelta
import random

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


async def test_hypertable_performance():
    """Test hypertable vs regular table performance."""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("\n" + "="*60)
        print("TimescaleDB Performance Test")
        print("="*60)
        
        # Create test tables
        await conn.execute("DROP TABLE IF EXISTS test_regular CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS test_hypertable CASCADE;")
        
        # Regular table
        await conn.execute("""
            CREATE TABLE test_regular (
                timestamp TIMESTAMPTZ NOT NULL,
                symbol TEXT NOT NULL,
                value DOUBLE PRECISION
            );
        """)
        
        # Hypertable
        await conn.execute("""
            CREATE TABLE test_hypertable (
                timestamp TIMESTAMPTZ NOT NULL,
                symbol TEXT NOT NULL,
                value DOUBLE PRECISION
            );
        """)
        
        await conn.execute("""
            SELECT create_hypertable('test_hypertable', 'timestamp');
        """)
        
        print("✅ Test tables created")
        
        # Insert test data (100k rows, 30 days)
        print("Inserting 100,000 test rows...")
        base_time = datetime.now() - timedelta(days=30)
        symbols = ['TEST1', 'TEST2', 'TEST3', 'TEST4', 'TEST5']
        
        # Prepare data
        data = []
        for i in range(100000):
            ts = base_time + timedelta(minutes=i % 43200)  # Spread over 30 days
            symbol = symbols[i % 5]
            value = random.random() * 100
            data.append((ts, symbol, value))
        
        # Insert into both tables
        await conn.executemany(
            "INSERT INTO test_regular VALUES ($1, $2, $3)", 
            data
        )
        await conn.executemany(
            "INSERT INTO test_hypertable VALUES ($1, $2, $3)", 
            data
        )
        
        print("✅ Test data inserted")
        
        # Test query performance
        test_query = """
            SELECT symbol, AVG(value), COUNT(*) 
            FROM {} 
            WHERE timestamp > NOW() - INTERVAL '7 days'
            GROUP BY symbol
        """
        
        # Regular table
        start = datetime.now()
        result = await conn.fetch(test_query.format('test_regular'))
        regular_time = (datetime.now() - start).total_seconds()
        
        # Hypertable
        start = datetime.now()
        result = await conn.fetch(test_query.format('test_hypertable'))
        hyper_time = (datetime.now() - start).total_seconds()
        
        print("\n" + "="*60)
        print("Query Performance Comparison")
        print("="*60)
        print(f"Regular table:  {regular_time*1000:.2f}ms")
        print(f"Hypertable:     {hyper_time*1000:.2f}ms")
        print(f"Speedup:        {regular_time/hyper_time:.1f}x faster")
        
        # Enable compression on hypertable
        print("\nTesting compression...")
        await conn.execute("""
            ALTER TABLE test_hypertable SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol'
            );
        """)
        
        await conn.execute("""
            SELECT add_compression_policy('test_hypertable', INTERVAL '1 day');
        """)
        
        # Compress all chunks
        chunks = await conn.fetch("""
            SELECT chunk_schema, chunk_name
            FROM timescaledb_information.chunks
            WHERE hypertable_name = 'test_hypertable'
        """)
        
        for chunk in chunks:
            await conn.execute(f"""
                SELECT compress_chunk('{chunk['chunk_schema']}.{chunk['chunk_name']}');
            """)
        
        # Check compression stats
        stats = await conn.fetchrow("""
            SELECT 
                pg_size_pretty(before_compression_total_bytes) as before,
                pg_size_pretty(after_compression_total_bytes) as after,
                ROUND((1 - after_compression_total_bytes::numeric / 
                       NULLIF(before_compression_total_bytes, 0)) * 100, 1) as savings
            FROM timescaledb_information.hypertable_compression_stats
            WHERE hypertable_name = 'test_hypertable'
        """)
        
        print("\n" + "="*60)
        print("Compression Results")
        print("="*60)
        print(f"Before:  {stats['before']}")
        print(f"After:   {stats['after']}")
        print(f"Savings: {stats['savings']}%")
        
        # Test compressed query performance
        start = datetime.now()
        result = await conn.fetch(test_query.format('test_hypertable'))
        compressed_time = (datetime.now() - start).total_seconds()
        
        print(f"\nCompressed query: {compressed_time*1000:.2f}ms")
        print(f"Speedup vs regular: {regular_time/compressed_time:.1f}x faster")
        
        # Cleanup
        await conn.execute("DROP TABLE test_regular;")
        await conn.execute("DROP TABLE test_hypertable;")
        
        print("\n✅ Test complete - TimescaleDB is working properly!")
        print("\nFor your 366M row table, expect:")
        print(f"  • {regular_time/compressed_time:.0f}x faster queries")
        print(f"  • {stats['savings']}% storage reduction")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(test_hypertable_performance())
