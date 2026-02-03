import asyncio
import asyncpg

async def check():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Check available equity data
    equities = await pool.fetch('''
        SELECT im.trading_symbol, COUNT(DISTINCT DATE(cd.timestamp)) as days
        FROM instrument_master im
        JOIN candle_data cd ON cd.instrument_id = im.instrument_id
        WHERE im.instrument_type = 'EQUITY' AND im.segment = 'EQ'
        GROUP BY im.trading_symbol
        ORDER BY days DESC
        LIMIT 50
    ''')
    print(f'Total equities with data: {len(equities)}')
    print('Top 50 Equities with most data:')
    for e in equities:
        print(f"  {e['trading_symbol']}: {e['days']} days")
    
    # Check option data availability by month
    option_months = await pool.fetch('''
        SELECT DATE_TRUNC('month', cd.timestamp) as month, COUNT(DISTINCT im.underlying) as symbols
        FROM candle_data cd
        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
        WHERE im.instrument_type IN ('CE', 'PE')
        GROUP BY DATE_TRUNC('month', cd.timestamp)
        ORDER BY month DESC LIMIT 6
    ''')
    print('\nOption data by month:')
    for m in option_months:
        print(f"  {m['month'].strftime('%Y-%m')}: {m['symbols']} underlying symbols")
    
    # Check total date range
    date_range = await pool.fetchrow('''
        SELECT MIN(DATE(cd.timestamp)) as min_date, MAX(DATE(cd.timestamp)) as max_date
        FROM candle_data cd
        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
        WHERE im.instrument_type IN ('CE', 'PE')
    ''')
    print(f"\nOption data date range: {date_range['min_date']} to {date_range['max_date']}")
    
    await pool.close()

asyncio.run(check())
