"""
Detailed analysis of what data needs to be populated.
"""
import asyncio
import asyncpg
from datetime import date, timedelta
import re

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

def extract_expiry_from_symbol(symbol):
    """Extract expiry date from trading symbol like 'BANKNIFTY 51200 PE 30 DEC 25'"""
    match = re.search(r'(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})$', symbol)
    if match:
        day, month, year = match.groups()
        month_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
        return date(2000 + int(year), month_map[month], int(day))
    return None

async def analyze_gaps():
    conn = await asyncpg.connect(DB_URL)
    
    print('=' * 70)
    print('DETAILED DATA GAP ANALYSIS')
    print('=' * 70)
    
    # 1. Find instruments without any data
    print('\n=== INSTRUMENTS WITHOUT ANY CANDLE DATA ===')
    no_data = await conn.fetch('''
        SELECT m.instrument_type, count(*) as cnt
        FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE s.instrument_id IS NULL
        GROUP BY m.instrument_type
        ORDER BY cnt DESC
    ''')
    total_missing = 0
    for r in no_data:
        print(f"  {r['instrument_type']:10} {r['cnt']:>6} instruments")
        total_missing += r['cnt']
    print(f"  {'TOTAL':10} {total_missing:>6} instruments")
    
    # 2. Check current expiry using expiry_calendar
    print('\n=== CURRENT EXPIRY ANALYSIS ===')
    
    # Get current weekly expiry
    current_expiries = await conn.fetch('''
        SELECT underlying, expiry_date FROM expiry_calendar 
        WHERE expiry_date >= CURRENT_DATE
        ORDER BY expiry_date
        LIMIT 10
    ''')
    print(f"  Upcoming expiries:")
    for exp in current_expiries[:5]:
        print(f"    {exp['underlying']:15} {exp['expiry_date']}")
    
    # 3. Check equity data completeness
    print('\n=== EQUITY DATA STATUS ===')
    eq_status = await conn.fetch('''
        SELECT 
            m.trading_symbol,
            s.first_date,
            s.last_date,
            s.candle_count
        FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type = 'EQUITY'
        ORDER BY s.candle_count DESC NULLS LAST
        LIMIT 10
    ''')
    print("  Top 10 equities with most data:")
    for r in eq_status:
        candles = r['candle_count'] or 0
        range_str = f"{r['first_date']} to {r['last_date']}" if r['first_date'] else "NO DATA"
        print(f"    {r['trading_symbol']:15} {candles:>8} candles  ({range_str})")
    
    # Missing equities
    missing_eq = await conn.fetch('''
        SELECT m.trading_symbol
        FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type = 'EQUITY' AND s.instrument_id IS NULL
    ''')
    if missing_eq:
        print(f"\n  Missing equity data ({len(missing_eq)} stocks):")
        for r in missing_eq[:10]:
            print(f"    - {r['trading_symbol']}")
        if len(missing_eq) > 10:
            print(f"    ... and {len(missing_eq) - 10} more")
    
    # 4. Check index data completeness
    print('\n=== INDEX DATA STATUS ===')
    idx_status = await conn.fetch('''
        SELECT 
            m.trading_symbol,
            s.first_date,
            s.last_date,
            s.candle_count
        FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type = 'INDEX'
        ORDER BY s.candle_count DESC NULLS LAST
    ''')
    for r in idx_status:
        candles = r['candle_count'] or 0
        range_str = f"{r['first_date']} to {r['last_date']}" if r['first_date'] else "NO DATA"
        print(f"    {r['trading_symbol']:15} {candles:>8} candles  ({range_str})")
    
    # 5. Check empty master tables that need population
    print('\n=== MASTER TABLES NEEDING POPULATION ===')
    
    # option_master
    om_count = await conn.fetchval('SELECT count(*) FROM option_master')
    if om_count == 0:
        opt_in_master = await conn.fetchval('''
            SELECT count(*) FROM instrument_master WHERE instrument_type IN ('CE', 'PE')
        ''')
        print(f"  option_master: EMPTY (should have {opt_in_master} options from instrument_master)")
    else:
        print(f"  option_master: {om_count} rows")
    
    # future_master
    fm_count = await conn.fetchval('SELECT count(*) FROM future_master')
    if fm_count == 0:
        fut_in_master = await conn.fetchval('''
            SELECT count(*) FROM instrument_master WHERE instrument_type = 'FUTURES'
        ''')
        print(f"  future_master: EMPTY (should have {fut_in_master} futures from instrument_master)")
    else:
        print(f"  future_master: {fm_count} rows")
    
    # index_constituents
    ic_count = await conn.fetchval('SELECT count(*) FROM index_constituents')
    if ic_count == 0:
        print(f"  index_constituents: EMPTY (should have NIFTY 50, NIFTY NEXT 50, etc. constituents)")
    else:
        print(f"  index_constituents: {ic_count} rows")
    
    # 6. Summary of what needs to be done
    print('\n' + '=' * 70)
    print('ACTION ITEMS SUMMARY')
    print('=' * 70)
    
    actions = []
    
    # Candle data actions
    if total_missing > 0:
        actions.append(f"1. BACKFILL CANDLE DATA: {total_missing} instruments need candle data")
    
    # Indicator actions
    ind_count = await conn.fetchval('SELECT count(*) FROM indicator_data')
    if ind_count == 0:
        actions.append("2. COMPUTE INDICATORS: indicator_data is empty (0 rows)")
    
    # Option greeks
    greeks_count = await conn.fetchval('SELECT count(*) FROM option_greeks')
    if greeks_count == 0:
        actions.append("3. COMPUTE OPTION GREEKS: option_greeks is empty (0 rows)")
    
    # Master table population
    if om_count == 0:
        actions.append("4. POPULATE option_master: Denormalized option reference data")
    if fm_count == 0:
        actions.append("5. POPULATE future_master: Denormalized future reference data")
    if ic_count == 0:
        actions.append("6. POPULATE index_constituents: NIFTY 50, BANK NIFTY components")
    
    for action in actions:
        print(action)
    
    # 7. Backfill time estimates
    print('\n' + '=' * 70)
    print('BACKFILL TIME ESTIMATES')
    print('=' * 70)
    
    # Based on observed rates: ~100 instruments/minute for backfill
    missing_ce = await conn.fetchval('''
        SELECT count(*) FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type = 'CE' AND s.instrument_id IS NULL
    ''')
    missing_pe = await conn.fetchval('''
        SELECT count(*) FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type = 'PE' AND s.instrument_id IS NULL
    ''')
    missing_fut = await conn.fetchval('''
        SELECT count(*) FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type = 'FUTURES' AND s.instrument_id IS NULL
    ''')
    missing_eq_count = await conn.fetchval('''
        SELECT count(*) FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type = 'EQUITY' AND s.instrument_id IS NULL
    ''')
    
    rate = 100  # instruments per minute (observed rate)
    
    print(f"  Missing CE options:  {missing_ce:>6} (~{missing_ce // rate} minutes)")
    print(f"  Missing PE options:  {missing_pe:>6} (~{missing_pe // rate} minutes)")
    print(f"  Missing futures:     {missing_fut:>6} (~{missing_fut // rate} minutes)")
    print(f"  Missing equities:    {missing_eq_count:>6} (~{missing_eq_count // rate} minutes)")
    print(f"  ─────────────────────────────────────")
    total = missing_ce + missing_pe + missing_fut + missing_eq_count
    print(f"  TOTAL:               {total:>6} (~{total // rate} minutes / ~{total // rate // 60:.1f} hours)")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(analyze_gaps())
