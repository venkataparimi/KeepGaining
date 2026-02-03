"""
Comprehensive data completeness check for KeepGaining database.
Uses indexed views and tables for fast verification.
"""
import asyncio
import asyncpg
from datetime import date, timedelta

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

async def check_data():
    conn = await asyncpg.connect(DB_URL)
    
    print('=' * 70)
    print('DATA COMPLETENESS CHECK')
    print('=' * 70)
    
    # 1. Candle data coverage using fast summary view
    print('\n=== CANDLE DATA COVERAGE (from summary view) ===')
    summary = await conn.fetchrow('''
        SELECT 
            count(*) as instruments_with_data,
            SUM(candle_count) as total_candles,
            MIN(first_date) as earliest_date,
            MAX(last_date) as latest_date
        FROM candle_data_summary
    ''')
    print(f"Instruments with data: {summary['instruments_with_data']:,}")
    print(f"Total candles: {summary['total_candles']:,}")
    print(f"Date range: {summary['earliest_date']} to {summary['latest_date']}")
    
    # 2. Check by instrument type
    print('\n=== COVERAGE BY INSTRUMENT TYPE ===')
    by_type = await conn.fetch('''
        SELECT 
            m.instrument_type,
            count(DISTINCT m.instrument_id) as total_instruments,
            count(DISTINCT s.instrument_id) as with_data,
            count(DISTINCT m.instrument_id) - count(DISTINCT s.instrument_id) as missing
        FROM instrument_master m
        LEFT JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        GROUP BY m.instrument_type
        ORDER BY m.instrument_type
    ''')
    for r in by_type:
        pct = r['with_data'] / r['total_instruments'] * 100 if r['total_instruments'] > 0 else 0
        print(f"  {r['instrument_type']:10} {r['with_data']:>6}/{r['total_instruments']:<6} ({pct:5.1f}%%) - {r['missing']} missing")
    
    # 3. Check stale data (not updated in last 7 days)
    print('\n=== STALE DATA (not updated in 7+ days) ===')
    stale = await conn.fetch('''
        SELECT 
            m.instrument_type,
            count(*) as stale_count
        FROM candle_data_summary s
        JOIN instrument_master m ON s.instrument_id = m.instrument_id
        WHERE s.last_date < CURRENT_DATE - 7
        GROUP BY m.instrument_type
        ORDER BY stale_count DESC
    ''')
    if stale:
        for r in stale:
            print(f"  {r['instrument_type']:10} {r['stale_count']:>6} instruments")
    else:
        print("  None - all data is recent")
    
    # 4. Check master data tables
    print('\n=== MASTER DATA TABLES ===')
    master_tables = [
        ('instrument_master', None),
        ('equity_master', None),
        ('option_master', None),
        ('future_master', None),
        ('sector_master', None),
        ('expiry_calendar', 'expiry_date >= CURRENT_DATE'),
        ('holiday_calendar', 'date >= CURRENT_DATE'),
        ('fo_ban_list', 'ban_date = CURRENT_DATE'),
        ('lot_size_history', None),
        ('index_constituents', None),
        ('broker_symbol_mapping', None),
    ]
    
    for table, condition in master_tables:
        try:
            if condition:
                count = await conn.fetchval(f'SELECT count(*) FROM {table} WHERE {condition}')
                print(f"  {table:30} {count:>8} (filtered)")
            else:
                count = await conn.fetchval(f'SELECT count(*) FROM {table}')
                print(f"  {table:30} {count:>8}")
        except Exception as e:
            print(f"  {table:30} ERROR: {e}")
    
    # 5. Check trading data tables
    print('\n=== TRADING DATA TABLES ===')
    trading_tables = [
        ('strategy_config', None),
        ('strategy_definition', None),
        ('orders', None),
        ('trades', None),
        ('positions', None),
        ('signal_log', None),
        ('daily_pnl', None),
    ]
    
    for table, _ in trading_tables:
        try:
            count = await conn.fetchval(f'SELECT count(*) FROM {table}')
            print(f"  {table:30} {count:>8}")
        except Exception as e:
            print(f"  {table:30} ERROR: {e}")
    
    # 6. Check indicator data
    print('\n=== INDICATOR DATA ===')
    ind_count = await conn.fetchval('SELECT count(*) FROM indicator_data')
    print(f"  indicator_data rows: {ind_count:,}")
    if ind_count > 0:
        ind_instruments = await conn.fetchval('SELECT count(DISTINCT instrument_id) FROM indicator_data')
        print(f"  instruments with indicators: {ind_instruments:,}")
    
    # 7. Check option greeks
    print('\n=== OPTION GREEKS ===')
    greeks_count = await conn.fetchval('SELECT count(*) FROM option_greeks')
    print(f"  option_greeks rows: {greeks_count:,}")
    
    # 8. Check option chain snapshots
    print('\n=== OPTION CHAIN SNAPSHOTS ===')
    chain_count = await conn.fetchval('SELECT count(*) FROM option_chain_snapshot')
    print(f"  option_chain_snapshot rows: {chain_count:,}")
    
    # 9. Missing critical data alerts
    print('\n' + '=' * 70)
    print('MISSING DATA ALERTS')
    print('=' * 70)
    
    alerts = []
    
    # Check if we have equity data
    eq_with_data = await conn.fetchval('''
        SELECT count(*) FROM instrument_master m
        JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type = 'EQ'
    ''')
    eq_total = await conn.fetchval("SELECT count(*) FROM instrument_master WHERE instrument_type = 'EQ'")
    if eq_total > 0 and eq_with_data == 0:
        alerts.append(f"❌ NO EQUITY DATA: 0/{eq_total} equities have candle data")
    elif eq_total > 0 and eq_with_data < eq_total * 0.5:
        alerts.append(f"⚠️ LOW EQUITY COVERAGE: {eq_with_data}/{eq_total} equities have data")
    
    # Check if we have index data
    idx_with_data = await conn.fetchval('''
        SELECT count(*) FROM instrument_master m
        JOIN candle_data_summary s ON m.instrument_id = s.instrument_id
        WHERE m.instrument_type = 'INDEX'
    ''')
    idx_total = await conn.fetchval("SELECT count(*) FROM instrument_master WHERE instrument_type = 'INDEX'")
    if idx_total > 0 and idx_with_data == 0:
        alerts.append(f"❌ NO INDEX DATA: 0/{idx_total} indices have candle data")
    elif idx_total > 0 and idx_with_data < idx_total:
        alerts.append(f"⚠️ MISSING INDEX DATA: {idx_with_data}/{idx_total} indices have data")
    
    # Check expiry calendar
    future_expiries = await conn.fetchval('''
        SELECT count(*) FROM expiry_calendar WHERE expiry_date >= CURRENT_DATE
    ''')
    if future_expiries == 0:
        alerts.append("❌ NO FUTURE EXPIRIES: expiry_calendar needs population")
    
    # Check holiday calendar
    future_holidays = await conn.fetchval('''
        SELECT count(*) FROM holiday_calendar WHERE date >= CURRENT_DATE
    ''')
    if future_holidays == 0:
        alerts.append("⚠️ NO FUTURE HOLIDAYS: holiday_calendar may need update")
    
    # Check broker symbol mapping
    mapping_count = await conn.fetchval('SELECT count(*) FROM broker_symbol_mapping')
    if mapping_count == 0:
        alerts.append("❌ NO BROKER MAPPINGS: broker_symbol_mapping is empty")
    
    # Check indicator data
    if ind_count == 0:
        alerts.append("⚠️ NO INDICATOR DATA: indicators need computation")
    
    if alerts:
        for alert in alerts:
            print(alert)
    else:
        print("✅ All critical data is present")
    
    await conn.close()
    print('\n' + '=' * 70)

if __name__ == '__main__':
    asyncio.run(check_data())
