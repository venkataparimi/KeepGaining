#!/usr/bin/env python3
"""Analyze data coverage and identify gaps."""

import asyncio
import asyncpg
from datetime import datetime, timedelta

async def analyze():
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    
    # Check what instrument types exist in master
    query = '''
    SELECT DISTINCT instrument_type, COUNT(*) as cnt
    FROM instrument_master 
    GROUP BY 1
    ORDER BY 2 DESC
    '''
    rows = await conn.fetch(query)
    print("=" * 70)
    print("DATA ANALYSIS REPORT")
    print("=" * 70)
    print("\nInstrument Master Summary:")
    print("-" * 40)
    for r in rows:
        print(f"  {r['instrument_type'] or 'NULL'}: {r['cnt']:,}")
    
    # Check candle_data breakdown by joining with instrument_master
    query2 = '''
    SELECT 
        im.instrument_type, 
        COUNT(cd.*) as candles,
        COUNT(DISTINCT im.trading_symbol) as instruments,
        MIN(cd.timestamp)::date as from_date,
        MAX(cd.timestamp)::date as to_date
    FROM candle_data cd
    JOIN instrument_master im ON cd.instrument_id = im.instrument_id
    GROUP BY 1
    ORDER BY 2 DESC
    '''
    rows2 = await conn.fetch(query2)
    print("\nCandle Data by Instrument Type:")
    print("-" * 70)
    print(f"{'Type':<12} {'Candles':>15} {'Instruments':>12} {'From':>12} {'To':>12}")
    print("-" * 70)
    for r in rows2:
        print(f"{r['instrument_type']:<12} {r['candles']:>15,} {r['instruments']:>12,} {str(r['from_date']):>12} {str(r['to_date']):>12}")
    
    total_candles = sum(r['candles'] for r in rows2)
    print("-" * 70)
    print(f"{'TOTAL':<12} {total_candles:>15,}")
    
    # Get detailed F&O breakdown
    query3 = '''
    SELECT 
        im.underlying,
        im.instrument_type,
        COUNT(cd.*) as candles,
        COUNT(DISTINCT im.trading_symbol) as contracts,
        MIN(cd.timestamp)::date as from_date,
        MAX(cd.timestamp)::date as to_date
    FROM candle_data cd
    JOIN instrument_master im ON cd.instrument_id = im.instrument_id
    WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
    GROUP BY 1, 2
    ORDER BY 1, 2
    '''
    rows3 = await conn.fetch(query3)
    
    # Separate index and stock F&O
    indices = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'NIFTYNXT50', 'SENSEX', 'BANKEX']
    
    print("\n" + "=" * 70)
    print("INDEX F&O DATA:")
    print("-" * 70)
    print(f"{'Underlying':<12} {'Type':<10} {'Contracts':>10} {'Candles':>15} {'From':>12} {'To':>12}")
    print("-" * 70)
    
    index_data = [r for r in rows3 if r['underlying'] in indices]
    for r in sorted(index_data, key=lambda x: (x['underlying'], x['instrument_type'])):
        print(f"{r['underlying']:<12} {r['instrument_type']:<10} {r['contracts']:>10,} {r['candles']:>15,} {str(r['from_date']):>12} {str(r['to_date']):>12}")
    
    print("\n" + "=" * 70)
    print("STOCK F&O DATA (Top 20 by candles):")
    print("-" * 70)
    
    stock_data = [r for r in rows3 if r['underlying'] not in indices and r['underlying'] != 'OTHER']
    stock_by_underlying = {}
    for r in stock_data:
        u = r['underlying']
        if u not in stock_by_underlying:
            stock_by_underlying[u] = {'FUTURES': 0, 'CE': 0, 'PE': 0, 'total': 0}
        stock_by_underlying[u][r['instrument_type']] = r['candles']
        stock_by_underlying[u]['total'] += r['candles']
    
    print(f"{'Stock':<15} {'Futures':>15} {'CE':>15} {'PE':>15} {'Total':>15}")
    print("-" * 70)
    for stock, data in sorted(stock_by_underlying.items(), key=lambda x: -x[1]['total'])[:20]:
        print(f"{stock:<15} {data['FUTURES']:>15,} {data['CE']:>15,} {data['PE']:>15,} {data['total']:>15,}")
    
    print(f"\n... and {len(stock_by_underlying) - 20} more stocks with F&O data")
    
    # Calculate totals
    total_stock_futures = sum(r['candles'] for r in stock_data if r['instrument_type'] == 'FUTURES')
    total_stock_ce = sum(r['candles'] for r in stock_data if r['instrument_type'] == 'CE')
    total_stock_pe = sum(r['candles'] for r in stock_data if r['instrument_type'] == 'PE')
    
    print(f"\nStock F&O Totals:")
    print(f"  Futures: {total_stock_futures:,} candles")
    print(f"  CE:      {total_stock_ce:,} candles")
    print(f"  PE:      {total_stock_pe:,} candles")
    
    # Check equity coverage
    query4 = '''
    SELECT 
        COUNT(DISTINCT im.trading_symbol) as stocks_with_data,
        MIN(cd.timestamp)::date as from_date,
        MAX(cd.timestamp)::date as to_date
    FROM candle_data cd
    JOIN instrument_master im ON cd.instrument_id = im.instrument_id
    WHERE im.instrument_type = 'EQUITY'
    '''
    eq = await conn.fetchrow(query4)
    
    print("\n" + "=" * 70)
    print("EQUITY DATA:")
    print("-" * 70)
    print(f"  Stocks with data: {eq['stocks_with_data']}")
    print(f"  Date range: {eq['from_date']} to {eq['to_date']}")
    
    # Check what's MISSING
    print("\n" + "=" * 70)
    print("PENDING DATA (What needs to be downloaded):")
    print("=" * 70)
    
    # Check date range for stock F&O
    stock_fo_dates = '''
    SELECT 
        MIN(cd.timestamp)::date as from_date,
        MAX(cd.timestamp)::date as to_date
    FROM candle_data cd
    JOIN instrument_master im ON cd.instrument_id = im.instrument_id
    WHERE im.instrument_type = 'FUTURES'
    AND im.underlying NOT IN ('NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'NIFTYNXT50')
    '''
    stk_dates = await conn.fetchrow(stock_fo_dates)
    
    print(f"\n1. STOCK F&O Historical (Expired Contracts):")
    print(f"   Current range: {stk_dates['from_date']} to {stk_dates['to_date']}")
    print(f"   PENDING: Data before {stk_dates['from_date']} (need Jan 2022 - {stk_dates['from_date']})")
    
    # Check index options
    idx_opts = '''
    SELECT im.underlying, im.instrument_type, MIN(cd.timestamp)::date as from_date, MAX(cd.timestamp)::date as to_date
    FROM candle_data cd
    JOIN instrument_master im ON cd.instrument_id = im.instrument_id
    WHERE im.underlying IN ('NIFTY', 'BANKNIFTY', 'FINNIFTY')
    AND im.instrument_type IN ('CE', 'PE')
    GROUP BY 1, 2
    ORDER BY 1, 2
    '''
    idx_opt_rows = await conn.fetch(idx_opts)
    
    print(f"\n2. INDEX OPTIONS Historical:")
    for r in idx_opt_rows:
        print(f"   {r['underlying']} {r['instrument_type']}: {r['from_date']} to {r['to_date']}")
        if r['from_date'] > datetime(2022, 1, 1).date():
            print(f"      PENDING: Data before {r['from_date']}")
    
    # Check index futures
    idx_fut = '''
    SELECT im.underlying, MIN(cd.timestamp)::date as from_date, MAX(cd.timestamp)::date as to_date
    FROM candle_data cd
    JOIN instrument_master im ON cd.instrument_id = im.instrument_id
    WHERE im.underlying IN ('NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'NIFTYNXT50')
    AND im.instrument_type = 'FUTURES'
    GROUP BY 1
    ORDER BY 1
    '''
    idx_fut_rows = await conn.fetch(idx_fut)
    
    print(f"\n3. INDEX FUTURES Historical:")
    for r in idx_fut_rows:
        print(f"   {r['underlying']}: {r['from_date']} to {r['to_date']}")
        if r['from_date'] > datetime(2022, 1, 1).date():
            print(f"      PENDING: Data before {r['from_date']}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(analyze())
