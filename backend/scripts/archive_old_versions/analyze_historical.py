"""
Analyze historical data availability and identify what can be backfilled.
"""
import asyncio
import asyncpg
from datetime import date, timedelta
from collections import defaultdict

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def analyze_historical_availability():
    conn = await asyncpg.connect(DB_URL)
    
    print("=" * 70)
    print("HISTORICAL DATA AVAILABILITY ANALYSIS")
    print("=" * 70)
    
    # 1. Check earliest data we have for each instrument type
    print("\n=== EARLIEST DATA BY INSTRUMENT TYPE ===")
    earliest = await conn.fetch('''
        SELECT 
            m.instrument_type,
            MIN(s.first_date) as earliest_data,
            MAX(s.last_date) as latest_data,
            COUNT(*) as instruments_with_data
        FROM candle_data_summary s
        JOIN instrument_master m ON s.instrument_id = m.instrument_id
        GROUP BY m.instrument_type
        ORDER BY m.instrument_type
    ''')
    for r in earliest:
        print(f"  {r['instrument_type']:10} {r['earliest_data']} to {r['latest_data']} ({r['instruments_with_data']} instruments)")
    
    # 2. Check F&O expiry date ranges
    print("\n=== F&O EXPIRY DATE RANGES (from instrument symbols) ===")
    expiry_ranges = await conn.fetch('''
        SELECT 
            instrument_type,
            MIN(trading_symbol) as sample_earliest,
            MAX(trading_symbol) as sample_latest,
            COUNT(*) as total
        FROM instrument_master
        WHERE instrument_type IN ('CE', 'PE', 'FUTURES')
        GROUP BY instrument_type
    ''')
    for r in expiry_ranges:
        print(f"  {r['instrument_type']:10} Total: {r['total']}")
    
    # 3. Analyze missing instruments by expiry month
    print("\n=== MISSING F&O INSTRUMENTS BY EXPIRY MONTH ===")
    missing = await conn.fetch('''
        SELECT 
            m.instrument_type,
            m.trading_symbol,
            m.underlying
        FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE s.instrument_id IS NULL
        AND m.instrument_type IN ('CE', 'PE', 'FUTURES')
        ORDER BY m.instrument_type, m.trading_symbol
    ''')
    
    # Parse expiry dates from symbols
    import re
    month_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    
    by_expiry_month = defaultdict(lambda: defaultdict(int))
    for r in missing:
        match = re.search(r'(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})$', r['trading_symbol'])
        if match:
            day, month, year = match.groups()
            expiry_key = f"20{year}-{month_map[month]:02d}"
            by_expiry_month[r['instrument_type']][expiry_key] += 1
    
    for itype in ['FUTURES', 'CE', 'PE']:
        if itype in by_expiry_month:
            print(f"\n  {itype}:")
            for exp_month in sorted(by_expiry_month[itype].keys()):
                print(f"    {exp_month}: {by_expiry_month[itype][exp_month]} missing")
    
    # 4. Check the 7 missing equities
    print("\n=== MISSING EQUITY ANALYSIS ===")
    missing_eq = await conn.fetch('''
        SELECT 
            m.instrument_id,
            m.trading_symbol,
            m.exchange,
            m.isin,
            m.is_active
        FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type = 'EQUITY' AND s.instrument_id IS NULL
    ''')
    for r in missing_eq:
        print(f"  {r['trading_symbol']:20} Exchange: {r['exchange']} ISIN: {r['isin']} Active: {r['is_active']}")
    
    # 5. Check what underlyings have F&O data
    print("\n=== UNDERLYINGS WITH F&O CANDLE DATA ===")
    underlyings = await conn.fetch('''
        SELECT DISTINCT m.underlying, m.instrument_type, COUNT(*) as count
        FROM instrument_master m
        JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type IN ('CE', 'PE', 'FUTURES')
        GROUP BY m.underlying, m.instrument_type
        ORDER BY m.underlying, m.instrument_type
    ''')
    
    underlying_summary = defaultdict(dict)
    for r in underlyings:
        underlying_summary[r['underlying']][r['instrument_type']] = r['count']
    
    print(f"  {'Underlying':<20} {'FUTURES':>10} {'CE':>10} {'PE':>10}")
    print("  " + "-" * 52)
    for ul in sorted(underlying_summary.keys())[:30]:  # Top 30
        fut = underlying_summary[ul].get('FUTURES', 0)
        ce = underlying_summary[ul].get('CE', 0)
        pe = underlying_summary[ul].get('PE', 0)
        print(f"  {ul:<20} {fut:>10} {ce:>10} {pe:>10}")
    
    # 6. Check current expiry instruments that still need data TODAY
    print("\n=== CURRENT EXPIRY INSTRUMENTS NEEDING TODAY'S DATA ===")
    today = date.today()
    current_expiry = await conn.fetch('''
        SELECT DISTINCT expiry_date, underlying
        FROM expiry_calendar
        WHERE expiry_date >= $1 AND expiry_date <= $1 + 7
        ORDER BY expiry_date, underlying
    ''', today)
    
    print(f"  Expiries in next 7 days:")
    for exp in current_expiry[:10]:
        print(f"    {exp['underlying']:15} {exp['expiry_date']}")
    
    # Check how many current expiry instruments have stale data
    stale_current = await conn.fetch('''
        SELECT COUNT(*) as cnt
        FROM candle_data_summary s
        JOIN instrument_master m ON s.instrument_id = m.instrument_id
        WHERE m.instrument_type IN ('CE', 'PE', 'FUTURES')
        AND s.last_date < $1
    ''', today - timedelta(days=1))
    print(f"\n  F&O instruments with stale data (not updated since yesterday): {stale_current[0]['cnt']}")
    
    # 7. Summary of what CAN be backfilled
    print("\n" + "=" * 70)
    print("BACKFILL RECOMMENDATIONS")
    print("=" * 70)
    
    # Count instruments that are for FUTURE expiries (can definitely be fetched)
    future_expiry_missing = 0
    past_expiry_missing = 0
    
    for r in missing:
        match = re.search(r'(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})$', r['trading_symbol'])
        if match:
            day, month, year = match.groups()
            expiry = date(2000 + int(year), month_map[month], int(day))
            if expiry >= today:
                future_expiry_missing += 1
            else:
                past_expiry_missing += 1
    
    print(f"""
1. FUTURE EXPIRY F&O (CAN fetch from Upstox):
   - {future_expiry_missing} instruments with expiry >= today
   - These should be retrievable via API

2. PAST EXPIRY F&O (CANNOT fetch - historical):
   - {past_expiry_missing} instruments already expired
   - Upstox does not provide historical expired contract data
   - Would need alternative data source (NSE historical, paid vendors)

3. MISSING EQUITIES (7 stocks):
   - Need to check symbol mapping / renamed tickers
   - May need manual investigation

4. STALE DATA REFRESH:
   - {stale_current[0]['cnt']} F&O instruments need today's data update
   - Run: python backfill_all_data.py --mode current
""")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(analyze_historical_availability())
