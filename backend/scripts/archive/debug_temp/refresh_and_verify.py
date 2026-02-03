"""Refresh materialized view and verify data status."""
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    
    print("Refreshing candle_data_summary materialized view...")
    await conn.execute('REFRESH MATERIALIZED VIEW candle_data_summary')
    print("Done!")
    
    print("\n=== CURRENT DATA STATUS ===")
    
    # Summary
    summary = await conn.fetchrow('''
        SELECT 
            count(*) as instruments,
            SUM(candle_count) as total_candles,
            MIN(first_date) as earliest,
            MAX(last_date) as latest
        FROM candle_data_summary
    ''')
    print(f"Instruments with data: {summary['instruments']:,}")
    print(f"Total candles: {summary['total_candles']:,}")
    print(f"Date range: {summary['earliest']} to {summary['latest']}")
    
    # By type
    print("\n=== BY INSTRUMENT TYPE ===")
    by_type = await conn.fetch('''
        SELECT 
            m.instrument_type,
            count(s.instrument_id) as with_data,
            SUM(s.candle_count) as candles
        FROM candle_data_summary s
        JOIN instrument_master m ON s.instrument_id = m.instrument_id
        GROUP BY m.instrument_type
        ORDER BY candles DESC
    ''')
    for r in by_type:
        print(f"  {r['instrument_type']:10} {r['with_data']:>6} instruments, {r['candles']:>12,} candles")
    
    # Master tables
    print("\n=== MASTER TABLES ===")
    opt = await conn.fetchval('SELECT count(*) FROM option_master')
    fut = await conn.fetchval('SELECT count(*) FROM future_master')
    idx = await conn.fetchval('SELECT count(*) FROM index_constituents')
    print(f"  option_master:      {opt:>6}")
    print(f"  future_master:      {fut:>6}")
    print(f"  index_constituents: {idx:>6}")
    
    # Indicators
    print("\n=== INDICATOR DATA ===")
    ind = await conn.fetchval('SELECT count(*) FROM indicator_data')
    print(f"  indicator_data:     {ind:>6}")
    
    await conn.close()

asyncio.run(main())
