#!/usr/bin/env python3
"""Check active/upcoming F&O contracts."""

import asyncio
import asyncpg
from datetime import datetime

async def check_active():
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    
    # Check future_master for upcoming expiries
    query = '''
    SELECT im.underlying, fm.expiry_date, COUNT(*) as cnt
    FROM future_master fm
    JOIN instrument_master im ON fm.instrument_id = im.instrument_id
    WHERE fm.expiry_date >= CURRENT_DATE
    GROUP BY 1, 2
    ORDER BY 2, 1
    '''
    rows = await conn.fetch(query)
    
    print('UPCOMING/ACTIVE FUTURES (from future_master):')
    print('=' * 60)
    if rows:
        for r in rows:
            underlying = r['underlying']
            expiry = r['expiry_date']
            cnt = r['cnt']
            print(f"  {underlying:<15} Expiry: {expiry} ({cnt} contracts)")
    else:
        print("  No upcoming futures found in future_master")
    
    # Check option_master for upcoming expiries
    query2 = '''
    SELECT im.underlying, om.expiry_date, COUNT(*) as cnt
    FROM option_master om
    JOIN instrument_master im ON om.instrument_id = im.instrument_id
    WHERE om.expiry_date >= CURRENT_DATE
    GROUP BY 1, 2
    ORDER BY 2, 1
    LIMIT 30
    '''
    rows2 = await conn.fetch(query2)
    
    print()
    print('UPCOMING/ACTIVE OPTIONS (from option_master, first 30):')
    print('=' * 60)
    if rows2:
        for r in rows2:
            underlying = r['underlying']
            expiry = r['expiry_date']
            cnt = r['cnt']
            print(f"  {underlying:<15} Expiry: {expiry} ({cnt} strikes)")
    else:
        print("  No upcoming options found in option_master")
    
    # Check what expiry dates we have data for
    query3 = '''
    SELECT 
        im.underlying,
        im.instrument_type,
        MAX(cd.timestamp)::date as latest_data
    FROM candle_data cd
    JOIN instrument_master im ON cd.instrument_id = im.instrument_id
    WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
    AND im.underlying IN ('NIFTY', 'BANKNIFTY', 'FINNIFTY')
    GROUP BY 1, 2
    ORDER BY 1, 2
    '''
    rows3 = await conn.fetch(query3)
    
    print()
    print('LATEST DATA FOR INDEX F&O:')
    print('=' * 60)
    for r in rows3:
        print(f"  {r['underlying']:<15} {r['instrument_type']:<10} Latest: {r['latest_data']}")
    
    # Check how many instrument_master entries have candle data
    query4 = '''
    SELECT 
        im.instrument_type,
        COUNT(DISTINCT im.instrument_id) as in_master,
        COUNT(DISTINCT cd.instrument_id) as with_data
    FROM instrument_master im
    LEFT JOIN candle_data cd ON im.instrument_id = cd.instrument_id
    GROUP BY 1
    ORDER BY 1
    '''
    rows4 = await conn.fetch(query4)
    
    print()
    print('COVERAGE: Instruments in Master vs With Data:')
    print('=' * 60)
    print(f"{'Type':<12} {'In Master':>12} {'With Data':>12} {'Coverage':>12}")
    print('-' * 60)
    for r in rows4:
        itype = r['instrument_type'] or 'NULL'
        master = r['in_master']
        data = r['with_data']
        pct = (data / master * 100) if master > 0 else 0
        print(f"{itype:<12} {master:>12,} {data:>12,} {pct:>11.1f}%")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_active())
