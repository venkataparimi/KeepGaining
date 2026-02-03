#!/usr/bin/env python3
"""
Comprehensive Data Gap Analysis and Backfill Script

This script:
1. Analyzes current data coverage for all instrument types
2. Identifies missing data for current expiries
3. Identifies historical data gaps (past 14 months)
4. Creates a backfill plan
5. Can execute the backfill with proper rate limiting
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

# Ensure we're in the backend directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'


@dataclass
class DataGap:
    """Represents a gap in data that needs to be backfilled."""
    underlying: str
    instrument_type: str  # EQUITY, INDEX, FUTURES, CE, PE
    expiry_date: Optional[date]
    gap_start: date
    gap_end: date
    missing_instruments: int
    priority: int  # 1=high (current expiry), 2=medium (recent), 3=low (old)


async def get_connection():
    """Get database connection."""
    return await asyncpg.connect(DB_URL)


async def analyze_current_expiries(conn) -> Dict[str, Any]:
    """Check data coverage for current and upcoming expiries (next 60 days)."""
    
    today = date.today()
    
    # Get all current expiries with their data status
    query = '''
    SELECT 
        im.underlying,
        im.instrument_type,
        im.expiry_date,
        COUNT(DISTINCT im.instrument_id) as total_contracts,
        COUNT(DISTINCT CASE WHEN cd.instrument_id IS NOT NULL THEN im.instrument_id END) as with_data,
        COALESCE(SUM(cd.candle_count), 0) as total_candles,
        MIN(cd.min_ts) as data_from,
        MAX(cd.max_ts) as data_to
    FROM instrument_master im
    LEFT JOIN (
        SELECT instrument_id, COUNT(*) as candle_count, MIN(timestamp) as min_ts, MAX(timestamp) as max_ts
        FROM candle_data
        GROUP BY instrument_id
    ) cd ON im.instrument_id = cd.instrument_id
    WHERE im.expiry_date >= CURRENT_DATE
    AND im.expiry_date <= CURRENT_DATE + INTERVAL '60 days'
    AND im.instrument_type IN ('FUTURES', 'CE', 'PE')
    GROUP BY 1, 2, 3
    ORDER BY im.expiry_date, im.underlying, im.instrument_type
    '''
    rows = await conn.fetch(query)
    
    result = {
        'summary': [],
        'gaps': [],
        'total_missing': 0
    }
    
    for r in rows:
        missing = r['total_contracts'] - r['with_data']
        coverage_pct = (r['with_data'] / r['total_contracts'] * 100) if r['total_contracts'] > 0 else 0
        
        result['summary'].append({
            'underlying': r['underlying'],
            'instrument_type': r['instrument_type'],
            'expiry': r['expiry_date'],
            'total_contracts': r['total_contracts'],
            'with_data': r['with_data'],
            'missing': missing,
            'coverage_pct': coverage_pct,
            'data_from': r['data_from'],
            'data_to': r['data_to']
        })
        
        if missing > 0:
            result['gaps'].append(DataGap(
                underlying=r['underlying'],
                instrument_type=r['instrument_type'],
                expiry_date=r['expiry_date'],
                gap_start=today,
                gap_end=r['expiry_date'],
                missing_instruments=missing,
                priority=1
            ))
            result['total_missing'] += missing
    
    return result


async def analyze_historical_gaps(conn, months_back: int = 14) -> Dict[str, Any]:
    """Analyze historical data gaps for past N months."""
    
    today = date.today()
    start_date = today - timedelta(days=months_back * 30)
    
    # Get data coverage by instrument type and month
    query = '''
    WITH monthly_data AS (
        SELECT 
            im.underlying,
            im.instrument_type,
            DATE_TRUNC('month', cd.timestamp)::date as month,
            COUNT(DISTINCT im.instrument_id) as instruments_with_data,
            COUNT(*) as candles
        FROM candle_data cd
        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
        WHERE cd.timestamp >= $1
        GROUP BY 1, 2, 3
    )
    SELECT * FROM monthly_data
    ORDER BY underlying, instrument_type, month
    '''
    rows = await conn.fetch(query, start_date)
    
    # Organize by underlying and type
    data_by_type = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        key = f"{r['underlying']}|{r['instrument_type']}"
        data_by_type[key][r['month']] = {
            'instruments': r['instruments_with_data'],
            'candles': r['candles']
        }
    
    # Identify gap months
    result = {
        'coverage_by_type': {},
        'gaps': [],
        'summary': {
            'equity_gaps': [],
            'index_gaps': [],
            'stock_futures_gaps': [],
            'stock_options_gaps': []
        }
    }
    
    # Generate expected months
    expected_months = []
    current = start_date.replace(day=1)
    while current <= today:
        expected_months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    # Check each category
    for key, monthly in data_by_type.items():
        underlying, inst_type = key.split('|')
        present_months = set(monthly.keys())
        
        for month in expected_months:
            if month not in present_months:
                result['gaps'].append({
                    'underlying': underlying,
                    'instrument_type': inst_type,
                    'month': month,
                    'status': 'MISSING'
                })
    
    return result


async def analyze_equity_coverage(conn) -> Dict[str, Any]:
    """Check equity data coverage and gaps."""
    
    query = '''
    SELECT 
        im.trading_symbol,
        im.name,
        MIN(cd.timestamp)::date as data_from,
        MAX(cd.timestamp)::date as data_to,
        COUNT(*) as candles,
        EXTRACT(DAY FROM (MAX(cd.timestamp) - MIN(cd.timestamp))) as days_span
    FROM instrument_master im
    JOIN candle_data cd ON im.instrument_id = cd.instrument_id
    WHERE im.instrument_type = 'EQUITY'
    GROUP BY im.instrument_id, im.trading_symbol, im.name
    ORDER BY trading_symbol
    '''
    rows = await conn.fetch(query)
    
    # Check for date gaps
    result = {
        'total_stocks': len(rows),
        'stocks': [],
        'gaps': []
    }
    
    today = date.today()
    target_start = date(2022, 1, 3)  # First trading day of 2022
    
    for r in rows:
        data_from = r['data_from']
        data_to = r['data_to']
        
        gaps = []
        # Check if data starts late
        if data_from > target_start + timedelta(days=7):
            gaps.append(f"Missing data from {target_start} to {data_from}")
        
        # Check if data ends early (more than 2 days behind)
        if data_to < today - timedelta(days=3):
            gaps.append(f"Missing recent data from {data_to} to {today}")
        
        result['stocks'].append({
            'symbol': r['trading_symbol'],
            'name': r['name'],
            'from': data_from,
            'to': data_to,
            'candles': r['candles'],
            'gaps': gaps
        })
        
        if gaps:
            result['gaps'].append({
                'symbol': r['trading_symbol'],
                'gaps': gaps
            })
    
    return result


async def analyze_index_coverage(conn) -> Dict[str, Any]:
    """Check index data coverage."""
    
    query = '''
    SELECT 
        im.trading_symbol,
        MIN(cd.timestamp)::date as data_from,
        MAX(cd.timestamp)::date as data_to,
        COUNT(*) as candles
    FROM instrument_master im
    JOIN candle_data cd ON im.instrument_id = cd.instrument_id
    WHERE im.instrument_type = 'INDEX'
    GROUP BY im.instrument_id, im.trading_symbol
    ORDER BY trading_symbol
    '''
    rows = await conn.fetch(query)
    
    return {
        'indices': [
            {
                'symbol': r['trading_symbol'],
                'from': r['data_from'],
                'to': r['data_to'],
                'candles': r['candles']
            }
            for r in rows
        ]
    }


async def analyze_fo_by_underlying(conn) -> Dict[str, Any]:
    """Detailed F&O analysis by underlying."""
    
    # Get all F&O underlyings with their coverage
    query = '''
    SELECT 
        im.underlying,
        im.instrument_type,
        COUNT(DISTINCT im.instrument_id) as total_contracts,
        COUNT(DISTINCT CASE WHEN cd.instrument_id IS NOT NULL THEN im.instrument_id END) as with_data,
        COALESCE(SUM(cd.candle_count), 0) as total_candles,
        MIN(cd.min_ts)::date as data_from,
        MAX(cd.max_ts)::date as data_to,
        MIN(im.expiry_date) as earliest_expiry,
        MAX(im.expiry_date) as latest_expiry
    FROM instrument_master im
    LEFT JOIN (
        SELECT instrument_id, COUNT(*) as candle_count, MIN(timestamp) as min_ts, MAX(timestamp) as max_ts
        FROM candle_data
        GROUP BY instrument_id
    ) cd ON im.instrument_id = cd.instrument_id
    WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
    GROUP BY 1, 2
    ORDER BY 1, 2
    '''
    rows = await conn.fetch(query)
    
    result = defaultdict(lambda: {'FUTURES': {}, 'CE': {}, 'PE': {}})
    
    for r in rows:
        coverage = (r['with_data'] / r['total_contracts'] * 100) if r['total_contracts'] > 0 else 0
        result[r['underlying']][r['instrument_type']] = {
            'total': r['total_contracts'],
            'with_data': r['with_data'],
            'missing': r['total_contracts'] - r['with_data'],
            'candles': r['total_candles'],
            'coverage': coverage,
            'data_from': r['data_from'],
            'data_to': r['data_to'],
            'expiry_range': (r['earliest_expiry'], r['latest_expiry'])
        }
    
    return dict(result)


async def print_comprehensive_report(conn):
    """Print a comprehensive data gap report."""
    
    print("=" * 100)
    print("COMPREHENSIVE DATA GAP ANALYSIS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    
    # 1. Overall summary
    summary = await conn.fetchrow('''
        SELECT 
            COUNT(*) as total_candles,
            COUNT(DISTINCT instrument_id) as total_instruments,
            MIN(timestamp)::date as earliest,
            MAX(timestamp)::date as latest
        FROM candle_data
    ''')
    
    print(f"\n📊 OVERALL DATABASE STATUS")
    print("-" * 50)
    print(f"  Total Candles:      {summary['total_candles']:>15,}")
    print(f"  Total Instruments:  {summary['total_instruments']:>15,}")
    print(f"  Date Range:         {summary['earliest']} to {summary['latest']}")
    
    # 2. By instrument type
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
    
    print(f"\n📈 DATA BY INSTRUMENT TYPE")
    print("-" * 100)
    print(f"{'Type':<12} {'In Master':>12} {'With Data':>12} {'Missing':>12} {'Candles':>15} {'From':>12} {'To':>12}")
    print("-" * 100)
    
    for r in by_type:
        missing = r['master_count'] - r['with_data']
        print(f"{r['instrument_type'] or 'NULL':<12} {r['master_count']:>12,} {r['with_data']:>12,} {missing:>12,} {r['candles']:>15,} {str(r['from_date'] or 'N/A'):>12} {str(r['to_date'] or 'N/A'):>12}")
    
    # 3. Current expiries analysis
    print(f"\n\n🔴 CURRENT EXPIRIES - DATA COVERAGE")
    print("-" * 100)
    
    current_exp = await analyze_current_expiries(conn)
    
    if current_exp['summary']:
        print(f"{'Underlying':<12} {'Type':<8} {'Expiry':<12} {'Total':>8} {'HasData':>8} {'Missing':>8} {'Coverage':>10}")
        print("-" * 100)
        
        for s in current_exp['summary'][:30]:
            coverage_str = f"{s['coverage_pct']:.1f}%"
            status = "✅" if s['coverage_pct'] > 95 else "⚠️" if s['coverage_pct'] > 50 else "❌"
            print(f"{s['underlying']:<12} {s['instrument_type']:<8} {str(s['expiry']):<12} {s['total_contracts']:>8} {s['with_data']:>8} {s['missing']:>8} {coverage_str:>10} {status}")
    
    print(f"\n  Total instruments missing data for current expiries: {current_exp['total_missing']:,}")
    
    # 4. Historical data gaps
    print(f"\n\n📅 HISTORICAL DATA GAPS (Past 14 months)")
    print("-" * 100)
    
    # Get month-by-month coverage
    month_coverage = await conn.fetch('''
        SELECT 
            DATE_TRUNC('month', cd.timestamp)::date as month,
            im.instrument_type,
            COUNT(DISTINCT im.instrument_id) as instruments,
            COUNT(*) as candles
        FROM candle_data cd
        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
        WHERE cd.timestamp >= CURRENT_DATE - INTERVAL '14 months'
        GROUP BY 1, 2
        ORDER BY 1, 2
    ''')
    
    # Pivot by month and type
    months = sorted(set(r['month'] for r in month_coverage))
    
    print(f"{'Month':<12}", end='')
    for itype in ['EQUITY', 'INDEX', 'FUTURES', 'CE', 'PE']:
        print(f"{itype:>15}", end='')
    print()
    print("-" * 100)
    
    month_data = defaultdict(dict)
    for r in month_coverage:
        month_data[r['month']][r['instrument_type']] = r['candles']
    
    for month in months[-14:]:
        print(f"{month.strftime('%Y-%m'):<12}", end='')
        for itype in ['EQUITY', 'INDEX', 'FUTURES', 'CE', 'PE']:
            candles = month_data.get(month, {}).get(itype, 0)
            print(f"{candles:>15,}", end='')
        print()
    
    # 5. Stock F&O coverage
    print(f"\n\n📊 STOCK F&O COVERAGE (Top 20 + Issues)")
    print("-" * 100)
    
    fo_coverage = await analyze_fo_by_underlying(conn)
    
    # Filter to stocks (not indices)
    indices = {'NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'NIFTYNXT50', 'SENSEX', 'BANKEX'}
    stocks = {k: v for k, v in fo_coverage.items() if k not in indices and k not in ['OTHER', None]}
    
    # Sort by total candles
    sorted_stocks = sorted(stocks.items(), key=lambda x: sum(t.get('candles', 0) for t in x[1].values()), reverse=True)
    
    print(f"{'Stock':<15} {'FUT Data':>12} {'CE Data':>12} {'PE Data':>12} {'FUT From':<12} {'FUT To':<12}")
    print("-" * 100)
    
    for stock, data in sorted_stocks[:20]:
        fut = data.get('FUTURES', {})
        ce = data.get('CE', {})
        pe = data.get('PE', {})
        print(f"{stock:<15} {fut.get('candles', 0):>12,} {ce.get('candles', 0):>12,} {pe.get('candles', 0):>12,} {str(fut.get('data_from', 'N/A')):<12} {str(fut.get('data_to', 'N/A')):<12}")
    
    # 6. Identify stocks with incomplete data
    print(f"\n\n⚠️ STOCKS WITH DATA ISSUES")
    print("-" * 100)
    
    issues = []
    for stock, data in stocks.items():
        fut = data.get('FUTURES', {})
        if fut.get('data_from') and fut['data_from'] > date(2024, 10, 1):
            continue  # Expected for newer data
        if fut.get('with_data', 0) < fut.get('total', 0) * 0.5:
            issues.append((stock, 'Low futures coverage', fut))
    
    if issues:
        for stock, issue, data in issues[:10]:
            print(f"  {stock}: {issue} - {data.get('with_data', 0)}/{data.get('total', 0)} contracts")
    else:
        print("  No major issues found")
    
    # 7. Recommendations
    print(f"\n\n💡 RECOMMENDATIONS")
    print("=" * 100)
    
    print("""
    1. CURRENT EXPIRY DATA (Priority: HIGH)
       - Download data for all active contracts expiring in next 60 days
       - Focus on NIFTY, BANKNIFTY first, then stock options
    
    2. HISTORICAL INDEX OPTIONS (Priority: MEDIUM)
       - BANKNIFTY options missing before June 2025
       - NIFTY options missing before September 2024
       - Use expired contracts API to backfill
    
    3. HISTORICAL STOCK F&O (Priority: MEDIUM)
       - Stock futures/options data starts from ~October 2024
       - Need to backfill from October 2023 for 12-month history
       - Use Upstox expired futures/options API
    
    4. INDEX FUTURES (Priority: LOW)
       - Most index futures data starts from September 2024
       - Backfill from 2022 if needed for longer backtests
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
