#!/usr/bin/env python3
"""
Comprehensive Data Gap Analysis and Backfill Script - Fixed Version

This script:
1. Analyzes current data coverage for all instrument types
2. Identifies missing data for current expiries (parses from trading_symbol)
3. Identifies historical data gaps (past 14 months)
4. Creates a backfill plan
"""

import asyncio
import asyncpg
import os
import sys
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


def parse_expiry_from_symbol(trading_symbol: str) -> Optional[date]:
    """
    Extract expiry date from trading symbol.
    Examples:
    - 'BANKNIFTY FUT 24 FEB 26' -> 2026-02-24
    - 'BANKNIFTY 57000 PE 29 SEP 26' -> 2026-09-29
    - 'NIFTY 24500 CE 04 DEC 25' -> 2025-12-04
    """
    months = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }
    
    # Pattern: DD MMM YY at end of symbol
    pattern = r'(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})$'
    match = re.search(pattern, trading_symbol.upper())
    
    if match:
        day = int(match.group(1))
        month = months[match.group(2)]
        year = 2000 + int(match.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def parse_strike_from_symbol(trading_symbol: str) -> Optional[float]:
    """Extract strike price from option symbol."""
    # Pattern: UNDERLYING STRIKE CE/PE DATE
    pattern = r'(\d+(?:\.\d+)?)\s+(?:CE|PE)\s+\d{1,2}\s+'
    match = re.search(pattern, trading_symbol.upper())
    if match:
        return float(match.group(1))
    return None


async def get_connection():
    """Get database connection."""
    return await asyncpg.connect(DB_URL)


async def analyze_data_coverage(conn) -> Dict[str, Any]:
    """Get comprehensive data coverage analysis."""
    
    # Overall summary
    summary = await conn.fetchrow('''
        SELECT 
            COUNT(*) as total_candles,
            COUNT(DISTINCT instrument_id) as instruments_with_data,
            MIN(timestamp)::date as earliest,
            MAX(timestamp)::date as latest
        FROM candle_data
    ''')
    
    # By instrument type
    by_type = await conn.fetch('''
        SELECT 
            im.instrument_type,
            COUNT(DISTINCT im.instrument_id) as master_count,
            COUNT(DISTINCT cd.instrument_id) as with_data,
            COALESCE(SUM(cd.cnt), 0) as candles,
            MIN(cd.min_ts)::date as from_date,
            MAX(cd.max_ts)::date as to_date
        FROM instrument_master im
        LEFT JOIN (
            SELECT instrument_id, COUNT(*) as cnt, MIN(timestamp) as min_ts, MAX(timestamp) as max_ts
            FROM candle_data
            GROUP BY instrument_id
        ) cd ON im.instrument_id = cd.instrument_id
        GROUP BY 1
        ORDER BY 4 DESC
    ''')
    
    return {
        'total_candles': summary['total_candles'],
        'instruments_with_data': summary['instruments_with_data'],
        'date_range': (summary['earliest'], summary['latest']),
        'by_type': [dict(r) for r in by_type]
    }


async def analyze_current_expiries(conn) -> Dict[str, Any]:
    """Analyze data for current and upcoming expiries."""
    
    today = date.today()
    future_cutoff = today + timedelta(days=60)
    
    # Get all F&O instruments and their data status
    query = '''
        SELECT 
            im.instrument_id,
            im.trading_symbol,
            im.instrument_type,
            im.underlying,
            EXISTS (
                SELECT 1 FROM candle_data cd WHERE cd.instrument_id = im.instrument_id
            ) as has_data,
            (
                SELECT COUNT(*) FROM candle_data cd WHERE cd.instrument_id = im.instrument_id
            ) as candle_count,
            (
                SELECT MAX(timestamp)::date FROM candle_data cd WHERE cd.instrument_id = im.instrument_id
            ) as last_data_date
        FROM instrument_master im
        WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
    '''
    rows = await conn.fetch(query)
    
    # Parse expiry and filter to current expiries
    result = {
        'current_expiries': defaultdict(lambda: {
            'futures': {'total': 0, 'with_data': 0, 'missing': []},
            'ce': {'total': 0, 'with_data': 0, 'missing': []},
            'pe': {'total': 0, 'with_data': 0, 'missing': []}
        }),
        'missing_count': 0,
        'outdated_count': 0
    }
    
    for r in rows:
        expiry = parse_expiry_from_symbol(r['trading_symbol'])
        if not expiry or expiry < today or expiry > future_cutoff:
            continue
        
        underlying = r['underlying'] or 'UNKNOWN'
        inst_type = r['instrument_type'].lower()
        
        expiry_key = f"{underlying}|{expiry.strftime('%Y-%m-%d')}"
        
        if inst_type == 'futures':
            key = 'futures'
        elif inst_type == 'ce':
            key = 'ce'
        else:
            key = 'pe'
        
        result['current_expiries'][expiry_key][key]['total'] += 1
        
        if r['has_data']:
            result['current_expiries'][expiry_key][key]['with_data'] += 1
            # Check if data is outdated (more than 1 day behind)
            if r['last_data_date'] and r['last_data_date'] < today - timedelta(days=1):
                result['outdated_count'] += 1
        else:
            result['current_expiries'][expiry_key][key]['missing'].append(r['trading_symbol'])
            result['missing_count'] += 1
    
    return result


async def analyze_historical_by_month(conn, months_back: int = 14) -> Dict[str, Any]:
    """Analyze data coverage by month for the past N months."""
    
    start_date = date.today() - timedelta(days=months_back * 30)
    
    query = '''
        SELECT 
            DATE_TRUNC('month', cd.timestamp)::date as month,
            im.instrument_type,
            COUNT(DISTINCT im.instrument_id) as instruments,
            COUNT(*) as candles
        FROM candle_data cd
        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
        WHERE cd.timestamp >= $1
        GROUP BY 1, 2
        ORDER BY 1, 2
    '''
    rows = await conn.fetch(query, start_date)
    
    # Organize by month
    result = defaultdict(lambda: {'EQUITY': 0, 'INDEX': 0, 'FUTURES': 0, 'CE': 0, 'PE': 0})
    instruments = defaultdict(lambda: {'EQUITY': 0, 'INDEX': 0, 'FUTURES': 0, 'CE': 0, 'PE': 0})
    
    for r in rows:
        result[r['month']][r['instrument_type']] = r['candles']
        instruments[r['month']][r['instrument_type']] = r['instruments']
    
    return {
        'candles_by_month': dict(result),
        'instruments_by_month': dict(instruments)
    }


async def analyze_equity_gaps(conn) -> Dict[str, Any]:
    """Check equity data for gaps."""
    
    query = '''
        SELECT 
            im.trading_symbol,
            MIN(cd.timestamp)::date as data_from,
            MAX(cd.timestamp)::date as data_to,
            COUNT(*) as candles
        FROM instrument_master im
        JOIN candle_data cd ON im.instrument_id = cd.instrument_id
        WHERE im.instrument_type = 'EQUITY'
        GROUP BY im.instrument_id, im.trading_symbol
        ORDER BY trading_symbol
    '''
    rows = await conn.fetch(query)
    
    today = date.today()
    target_start = date(2022, 1, 3)
    
    gaps = []
    for r in rows:
        issues = []
        if r['data_from'] > target_start + timedelta(days=30):
            issues.append(f"Late start: {r['data_from']}")
        if r['data_to'] < today - timedelta(days=3):
            issues.append(f"Outdated: last data {r['data_to']}")
        
        if issues:
            gaps.append({
                'symbol': r['trading_symbol'],
                'from': r['data_from'],
                'to': r['data_to'],
                'candles': r['candles'],
                'issues': issues
            })
    
    return {
        'total_stocks': len(rows),
        'stocks_with_gaps': len(gaps),
        'gaps': gaps
    }


async def analyze_fo_by_underlying(conn) -> Dict[str, Any]:
    """Analyze F&O data coverage by underlying."""
    
    query = '''
        SELECT 
            im.underlying,
            im.instrument_type,
            COUNT(DISTINCT im.instrument_id) as total_instruments,
            COUNT(DISTINCT CASE WHEN cd.instrument_id IS NOT NULL THEN im.instrument_id END) as with_data,
            COALESCE(SUM(cd.candle_count), 0) as candles,
            MIN(cd.min_ts)::date as data_from,
            MAX(cd.max_ts)::date as data_to
        FROM instrument_master im
        LEFT JOIN (
            SELECT instrument_id, COUNT(*) as candle_count, MIN(timestamp) as min_ts, MAX(timestamp) as max_ts
            FROM candle_data
            GROUP BY instrument_id
        ) cd ON im.instrument_id = cd.instrument_id
        WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
        AND im.underlying IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 2
    '''
    rows = await conn.fetch(query)
    
    result = defaultdict(dict)
    for r in rows:
        result[r['underlying']][r['instrument_type']] = {
            'total': r['total_instruments'],
            'with_data': r['with_data'],
            'missing': r['total_instruments'] - r['with_data'],
            'candles': r['candles'],
            'data_from': r['data_from'],
            'data_to': r['data_to']
        }
    
    return dict(result)


async def get_instruments_missing_data(conn) -> List[Dict[str, Any]]:
    """Get list of instruments that need data download."""
    
    query = '''
        SELECT 
            im.instrument_id,
            im.trading_symbol,
            im.exchange,
            im.instrument_type,
            im.underlying
        FROM instrument_master im
        LEFT JOIN (
            SELECT DISTINCT instrument_id FROM candle_data
        ) cd ON im.instrument_id = cd.instrument_id
        WHERE cd.instrument_id IS NULL
        AND im.instrument_type IN ('FUTURES', 'CE', 'PE', 'EQUITY', 'INDEX')
        AND im.is_active = true
    '''
    rows = await conn.fetch(query)
    return [dict(r) for r in rows]


async def get_instruments_with_outdated_data(conn, days_threshold: int = 3) -> List[Dict[str, Any]]:
    """Get instruments whose data is outdated."""
    
    cutoff = date.today() - timedelta(days=days_threshold)
    
    query = '''
        SELECT 
            im.instrument_id,
            im.trading_symbol,
            im.exchange,
            im.instrument_type,
            im.underlying,
            MAX(cd.timestamp)::date as last_data
        FROM instrument_master im
        JOIN candle_data cd ON im.instrument_id = cd.instrument_id
        WHERE im.is_active = true
        GROUP BY im.instrument_id, im.trading_symbol, im.exchange, im.instrument_type, im.underlying
        HAVING MAX(cd.timestamp)::date < $1
    '''
    rows = await conn.fetch(query, cutoff)
    return [dict(r) for r in rows]


async def print_comprehensive_report(conn):
    """Print a comprehensive data gap report."""
    
    print("=" * 120)
    print("COMPREHENSIVE DATA GAP ANALYSIS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Today's Date: {date.today()}")
    print("=" * 120)
    
    # 1. Overall summary
    coverage = await analyze_data_coverage(conn)
    
    print(f"\n{'='*40} OVERALL DATABASE STATUS {'='*40}")
    print(f"  Total Candles:         {coverage['total_candles']:>15,}")
    print(f"  Instruments with Data: {coverage['instruments_with_data']:>15,}")
    print(f"  Date Range:            {coverage['date_range'][0]} to {coverage['date_range'][1]}")
    
    print(f"\n{'='*40} DATA BY INSTRUMENT TYPE {'='*40}")
    print(f"{'Type':<12} {'In Master':>12} {'With Data':>12} {'Missing':>12} {'Candles':>18} {'From':>12} {'To':>12}")
    print("-" * 100)
    
    for r in coverage['by_type']:
        missing = r['master_count'] - r['with_data']
        print(f"{r['instrument_type'] or 'NULL':<12} {r['master_count']:>12,} {r['with_data']:>12,} {missing:>12,} {r['candles']:>18,} {str(r['from_date'] or 'N/A'):>12} {str(r['to_date'] or 'N/A'):>12}")
    
    # 2. Current expiries analysis
    print(f"\n\n{'='*40} CURRENT EXPIRIES (Next 60 days) {'='*40}")
    
    current_exp = await analyze_current_expiries(conn)
    
    # Group by underlying
    by_underlying = defaultdict(list)
    for key, data in current_exp['current_expiries'].items():
        underlying, expiry = key.split('|')
        by_underlying[underlying].append((expiry, data))
    
    # Sort and print
    for underlying in sorted(by_underlying.keys()):
        print(f"\n  {underlying}:")
        expiries = sorted(by_underlying[underlying], key=lambda x: x[0])
        for expiry, data in expiries[:5]:  # Show first 5 expiries
            fut = data['futures']
            ce = data['ce']
            pe = data['pe']
            
            fut_status = f"FUT: {fut['with_data']}/{fut['total']}" if fut['total'] > 0 else ""
            ce_status = f"CE: {ce['with_data']}/{ce['total']}" if ce['total'] > 0 else ""
            pe_status = f"PE: {pe['with_data']}/{pe['total']}" if pe['total'] > 0 else ""
            
            status_parts = [s for s in [fut_status, ce_status, pe_status] if s]
            print(f"    {expiry}: {', '.join(status_parts)}")
    
    print(f"\n  Total instruments missing data: {current_exp['missing_count']:,}")
    print(f"  Total instruments with outdated data: {current_exp['outdated_count']:,}")
    
    # 3. Historical data by month
    print(f"\n\n{'='*40} MONTHLY DATA COVERAGE (Past 14 Months) {'='*40}")
    
    historical = await analyze_historical_by_month(conn, 14)
    
    print(f"\n{'Month':<12}", end='')
    for itype in ['EQUITY', 'INDEX', 'FUTURES', 'CE', 'PE']:
        print(f"{itype:>15}", end='')
    print()
    print("-" * 90)
    
    for month in sorted(historical['candles_by_month'].keys())[-14:]:
        print(f"{month.strftime('%Y-%m'):<12}", end='')
        for itype in ['EQUITY', 'INDEX', 'FUTURES', 'CE', 'PE']:
            candles = historical['candles_by_month'][month].get(itype, 0)
            print(f"{candles:>15,}", end='')
        print()
    
    # 4. Equity gaps
    print(f"\n\n{'='*40} EQUITY DATA GAPS {'='*40}")
    
    equity_gaps = await analyze_equity_gaps(conn)
    print(f"  Total stocks: {equity_gaps['total_stocks']}")
    print(f"  Stocks with gaps: {equity_gaps['stocks_with_gaps']}")
    
    if equity_gaps['gaps']:
        print(f"\n  Stocks needing attention:")
        for gap in equity_gaps['gaps'][:10]:
            print(f"    {gap['symbol']}: {', '.join(gap['issues'])}")
    
    # 5. F&O by underlying summary
    print(f"\n\n{'='*40} F&O COVERAGE BY UNDERLYING {'='*40}")
    
    fo_data = await analyze_fo_by_underlying(conn)
    
    # Separate indices and stocks
    indices = {'NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'NIFTYNXT50', 'SENSEX', 'BANKEX'}
    
    print(f"\n  INDEX F&O:")
    print(f"  {'Underlying':<15} {'FUT Total':>10} {'FUT Data':>10} {'CE Total':>10} {'CE Data':>10} {'PE Total':>10} {'PE Data':>10}")
    print(f"  {'-'*75}")
    
    for underlying in sorted(indices):
        if underlying in fo_data:
            data = fo_data[underlying]
            fut = data.get('FUTURES', {})
            ce = data.get('CE', {})
            pe = data.get('PE', {})
            print(f"  {underlying:<15} {fut.get('total', 0):>10} {fut.get('with_data', 0):>10} {ce.get('total', 0):>10} {ce.get('with_data', 0):>10} {pe.get('total', 0):>10} {pe.get('with_data', 0):>10}")
    
    print(f"\n  STOCK F&O (Top 20 by candle count):")
    print(f"  {'Underlying':<15} {'FUT Total':>10} {'FUT Data':>10} {'CE Total':>10} {'CE Data':>10} {'PE Total':>10} {'PE Data':>10}")
    print(f"  {'-'*75}")
    
    stock_fo = {k: v for k, v in fo_data.items() if k not in indices}
    # Sort by total candles
    sorted_stocks = sorted(stock_fo.items(), 
                          key=lambda x: sum(t.get('candles', 0) for t in x[1].values()), 
                          reverse=True)[:20]
    
    for underlying, data in sorted_stocks:
        fut = data.get('FUTURES', {})
        ce = data.get('CE', {})
        pe = data.get('PE', {})
        print(f"  {underlying:<15} {fut.get('total', 0):>10} {fut.get('with_data', 0):>10} {ce.get('total', 0):>10} {ce.get('with_data', 0):>10} {pe.get('total', 0):>10} {pe.get('with_data', 0):>10}")
    
    # 6. Summary of what needs to be done
    missing_instruments = await get_instruments_missing_data(conn)
    outdated_instruments = await get_instruments_with_outdated_data(conn, 3)
    
    print(f"\n\n{'='*40} BACKFILL REQUIREMENTS {'='*40}")
    print(f"\n  Instruments with NO data:      {len(missing_instruments):,}")
    print(f"  Instruments with OUTDATED data: {len(outdated_instruments):,}")
    
    # Categorize missing instruments
    missing_by_type = defaultdict(int)
    for inst in missing_instruments:
        missing_by_type[inst['instrument_type']] += 1
    
    print(f"\n  Missing by type:")
    for itype, count in sorted(missing_by_type.items()):
        print(f"    {itype}: {count:,}")
    
    # Categorize outdated instruments
    outdated_by_type = defaultdict(int)
    for inst in outdated_instruments:
        outdated_by_type[inst['instrument_type']] += 1
    
    print(f"\n  Outdated by type:")
    for itype, count in sorted(outdated_by_type.items()):
        print(f"    {itype}: {count:,}")
    
    print(f"\n\n{'='*40} RECOMMENDATIONS {'='*40}")
    print("""
    1. PRIORITY HIGH - Current Expiry Options/Futures
       - Download data for all active F&O contracts expiring in next 60 days
       - Use Upstox historical_candle_data API for each instrument
    
    2. PRIORITY MEDIUM - Equity Data Refresh
       - Update equity data to latest date for all 200 F&O stocks
       - Download from last available date to today
    
    3. PRIORITY MEDIUM - Historical Index Options
       - Backfill NIFTY/BANKNIFTY options from October 2023
       - Use Upstox expired contracts API
    
    4. PRIORITY LOW - Historical Stock F&O
       - Backfill stock futures/options from October 2023
       - This is a large dataset, do in batches by underlying
    """)


async def main():
    """Main entry point."""
    conn = await get_connection()
    
    try:
        await print_comprehensive_report(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
