import asyncio
import asyncpg
import sys
from datetime import date, timedelta

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

async def main():
    conn = await asyncpg.connect(DB_URL)
    
    # Check what F&O data we currently have
    print("Current F&O data coverage:")
    print("=" * 60)
    
    # Overall stats
    stats = await conn.fetch("""
        SELECT 
            im.instrument_type,
            COUNT(DISTINCT im.instrument_id) as total_instruments,
            COUNT(DISTINCT s.instrument_id) as with_data,
            MIN(s.first_date) as earliest_data,
            MAX(s.last_date) as latest_data
        FROM instrument_master im
        LEFT JOIN candle_data_summary s ON im.instrument_id = s.instrument_id
        WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
        GROUP BY im.instrument_type
        ORDER BY im.instrument_type
    """)
    
    for row in stats:
        print(f"\n{row['instrument_type']}:")
        print(f"  Total instruments: {row['total_instruments']}")
        print(f"  With data: {row['with_data']}")
        print(f"  Earliest data: {row['earliest_data']}")
        print(f"  Latest data: {row['latest_data']}")
    
    # Check for May 2022 specifically
    print("\n" + "=" * 60)
    print("May 2022 F&O instruments:")
    print("=" * 60)
    
    may_2022_start = date(2022, 5, 1)
    may_2022_end = date(2022, 5, 31)
    
    may_instruments = await conn.fetch("""
        SELECT 
            im.instrument_type,
            im.trading_symbol,
            im.is_active,
            s.first_date,
            s.last_date,
            s.candle_count
        FROM instrument_master im
        LEFT JOIN candle_data_summary s ON im.instrument_id = s.instrument_id
        WHERE im.instrument_type IN ('CE', 'PE')
        AND im.trading_symbol LIKE '%MAY 22%'
        ORDER BY im.instrument_type, im.trading_symbol
        LIMIT 20
    """)
    
    print(f"\nFound {len(may_instruments)} May 2022 instruments (showing first 20):")
    for row in may_instruments:
        status = "ACTIVE" if row['is_active'] else "EXPIRED"
        data_status = f"{row['first_date']} to {row['last_date']} ({row['candle_count']} candles)" if row['first_date'] else "NO DATA"
        print(f"  {row['trading_symbol']:<40} [{status}] {data_status}")
    
    # Count total May 2022 instruments
    total_may = await conn.fetchval("""
        SELECT COUNT(*)
        FROM instrument_master
        WHERE instrument_type IN ('CE', 'PE')
        AND trading_symbol LIKE '%MAY 22%'
    """)
    
    with_data_may = await conn.fetchval("""
        SELECT COUNT(DISTINCT im.instrument_id)
        FROM instrument_master im
        JOIN candle_data_summary s ON im.instrument_id = s.instrument_id
        WHERE im.instrument_type IN ('CE', 'PE')
        AND im.trading_symbol LIKE '%MAY 22%'
    """)
    
    print(f"\nTotal May 2022 options: {total_may}")
    print(f"With data: {with_data_may}")
    print(f"Missing data: {total_may - with_data_may}")
    
    await conn.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
