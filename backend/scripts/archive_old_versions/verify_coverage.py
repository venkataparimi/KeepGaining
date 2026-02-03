"""Verify data coverage using fast summary view."""
import asyncio
import asyncpg

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def verify():
    conn = await asyncpg.connect(DB_URL)
    
    print('=== DATA VERIFICATION (USING FAST SUMMARY VIEW) ===')
    print()
    
    # Total instruments with data
    total = await conn.fetchval('SELECT count(*) FROM candle_data_summary')
    print(f'Total instruments with data: {total:,}')
    
    # Total candles
    candles = await conn.fetchval('SELECT SUM(candle_count) FROM candle_data_summary')
    print(f'Total candles: {candles:,}')
    
    # Recent data (last 7 days)
    recent = await conn.fetchval('''
        SELECT count(*) FROM candle_data_summary 
        WHERE last_date >= CURRENT_DATE - 7
    ''')
    print(f'Instruments updated in last 7 days: {recent:,}')
    
    # Current F&O coverage
    print()
    print('=== CURRENT F&O COVERAGE ===')
    fo_stats = await conn.fetch('''
        SELECT m.instrument_type, 
               count(*) as total_instruments,
               count(s.instrument_id) as with_data,
               count(*) - count(s.instrument_id) as missing
        FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type IN ('CE', 'PE', 'FUTURES')
        GROUP BY m.instrument_type
        ORDER BY m.instrument_type
    ''')
    for row in fo_stats:
        pct = row['with_data'] / row['total_instruments'] * 100 if row['total_instruments'] > 0 else 0
        print(f"  {row['instrument_type']}: {row['with_data']:,}/{row['total_instruments']:,} ({pct:.1f}%)")
    
    # Equity/Index coverage
    print()
    print('=== EQUITY/INDEX COVERAGE ===')
    eq_stats = await conn.fetch('''
        SELECT m.instrument_type, 
               count(*) as total,
               count(s.instrument_id) as with_data
        FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type IN ('EQ', 'INDEX')
        GROUP BY m.instrument_type
    ''')
    for row in eq_stats:
        pct = row['with_data'] / row['total'] * 100 if row['total'] > 0 else 0
        print(f"  {row['instrument_type']}: {row['with_data']:,}/{row['total']:,} ({pct:.1f}%)")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(verify())
