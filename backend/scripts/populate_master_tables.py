"""
Populate master tables (option_master, future_master, index_constituents)
from instrument_master data.
"""
import asyncio
import asyncpg
import re
import uuid
from datetime import date
from typing import Optional, Tuple

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

def parse_option_details(trading_symbol: str) -> Optional[Tuple[str, float, str, date]]:
    """
    Parse trading symbol to extract option details.
    Example: "BANKNIFTY 51200 PE 30 DEC 25" -> (BANKNIFTY, 51200.0, PE, 2025-12-30)
    """
    # Pattern: UNDERLYING STRIKE TYPE DD MMM YY
    match = re.match(r'^(.+?)\s+(\d+(?:\.\d+)?)\s+(CE|PE)\s+(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})$', trading_symbol)
    if match:
        underlying, strike, opt_type, day, month, year = match.groups()
        month_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
        expiry = date(2000 + int(year), month_map[month], int(day))
        return underlying.strip(), float(strike), opt_type, expiry
    return None

def parse_future_details(trading_symbol: str) -> Optional[Tuple[str, date]]:
    """
    Parse trading symbol to extract future details.
    Example: "BANKNIFTY FUT 30 DEC 25" -> (BANKNIFTY, 2025-12-30)
    """
    # Pattern: UNDERLYING FUT DD MMM YY
    match = re.match(r'^(.+?)\s+FUT\s+(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})$', trading_symbol)
    if match:
        underlying, day, month, year = match.groups()
        month_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
        expiry = date(2000 + int(year), month_map[month], int(day))
        return underlying.strip(), expiry
    
    # Fallback: UNDERLYING25MMFUT pattern
    match = re.match(r'^(.+?)(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)FUT$', trading_symbol)
    if match:
        underlying, year, month = match.groups()
        month_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
        # Last Thursday of month approximation
        expiry = date(2000 + int(year), month_map[month], 28)
        return underlying.strip(), expiry
    
    return None

def get_expiry_type(expiry_date: date, underlying: str) -> str:
    """Determine expiry type (WEEKLY/MONTHLY) based on underlying."""
    # Index options typically have weekly expiries
    # Stock options typically have monthly expiries
    index_underlyings = {'NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX'}
    
    if underlying.upper() in index_underlyings:
        # Check if it's last Thursday of month (approximately monthly)
        # For simplicity, assume week-based logic
        return 'WEEKLY'
    else:
        return 'MONTHLY'

async def populate_option_master(conn):
    """Populate option_master from instrument_master."""
    print("\n=== Populating option_master ===")
    
    # Get all options from instrument_master
    options = await conn.fetch('''
        SELECT instrument_id, trading_symbol, underlying, lot_size
        FROM instrument_master
        WHERE instrument_type IN ('CE', 'PE')
    ''')
    
    print(f"Found {len(options)} options to process")
    
    # Get underlying instrument IDs
    underlyings = await conn.fetch('''
        SELECT instrument_id, trading_symbol
        FROM instrument_master
        WHERE instrument_type IN ('INDEX', 'EQUITY')
    ''')
    underlying_map = {r['trading_symbol']: r['instrument_id'] for r in underlyings}
    
    # Prepare insert data
    records = []
    skipped = 0
    
    for opt in options:
        details = parse_option_details(opt['trading_symbol'])
        if not details:
            skipped += 1
            continue
        
        underlying_name, strike, opt_type, expiry = details
        underlying_id = underlying_map.get(underlying_name)
        expiry_type = get_expiry_type(expiry, underlying_name)
        
        records.append((
            uuid.uuid4(),
            opt['instrument_id'],
            underlying_id,
            strike,
            opt_type,
            expiry,
            expiry_type,
            opt['lot_size'] or 1
        ))
    
    print(f"Prepared {len(records)} records, skipped {skipped}")
    
    if records:
        # Clear existing and insert (cascade to handle FK constraints)
        await conn.execute('TRUNCATE option_master CASCADE')
        
        await conn.executemany('''
            INSERT INTO option_master 
            (option_id, instrument_id, underlying_instrument_id, strike_price, option_type, expiry_date, expiry_type, lot_size)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ''', records)
        
        print(f"Inserted {len(records)} records into option_master")
    
    return len(records)

async def populate_future_master(conn):
    """Populate future_master from instrument_master."""
    print("\n=== Populating future_master ===")
    
    # Get all futures from instrument_master
    futures = await conn.fetch('''
        SELECT instrument_id, trading_symbol, underlying, lot_size
        FROM instrument_master
        WHERE instrument_type = 'FUTURES'
    ''')
    
    print(f"Found {len(futures)} futures to process")
    
    # Get underlying instrument IDs
    underlyings = await conn.fetch('''
        SELECT instrument_id, trading_symbol
        FROM instrument_master
        WHERE instrument_type IN ('INDEX', 'EQUITY')
    ''')
    underlying_map = {r['trading_symbol']: r['instrument_id'] for r in underlyings}
    
    # Prepare insert data
    records = []
    skipped = 0
    
    for fut in futures:
        details = parse_future_details(fut['trading_symbol'])
        if not details:
            skipped += 1
            continue
        
        underlying_name, expiry = details
        underlying_id = underlying_map.get(underlying_name)
        
        records.append((
            uuid.uuid4(),
            fut['instrument_id'],
            underlying_id,
            expiry,
            fut['lot_size'] or 1,
            'STOCK' if underlying_name not in ('NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY') else 'INDEX'
        ))
    
    print(f"Prepared {len(records)} records, skipped {skipped}")
    
    if records:
        # Clear existing and insert (cascade to handle FK constraints)
        await conn.execute('TRUNCATE future_master CASCADE')
        
        await conn.executemany('''
            INSERT INTO future_master 
            (future_id, instrument_id, underlying_instrument_id, expiry_date, lot_size, contract_type)
            VALUES ($1, $2, $3, $4, $5, $6)
        ''', records)
        
        print(f"Inserted {len(records)} records into future_master")
    
    return len(records)

async def populate_index_constituents(conn):
    """Populate index_constituents with NIFTY 50, BANK NIFTY, etc."""
    print("\n=== Populating index_constituents ===")
    
    # NIFTY 50 constituents (as of Dec 2024 - you should update this list periodically)
    nifty50_stocks = [
        'ADANIPORTS', 'ASIANPAINT', 'AXISBANK', 'BAJAJ-AUTO', 'BAJAJFINSV',
        'BAJFINANCE', 'BHARTIARTL', 'BPCL', 'BRITANNIA', 'CIPLA',
        'COALINDIA', 'DRREDDY', 'EICHERMOT', 'GRASIM', 'HCLTECH',
        'HDFC', 'HDFCBANK', 'HDFCLIFE', 'HEROMOTOCO', 'HINDALCO',
        'HINDUNILVR', 'ICICIBANK', 'INDUSINDBK', 'INFY', 'ITC',
        'JSWSTEEL', 'KOTAKBANK', 'LT', 'M&M', 'MARUTI',
        'NESTLEIND', 'NTPC', 'ONGC', 'POWERGRID', 'RELIANCE',
        'SBILIFE', 'SBIN', 'SHREECEM', 'SUNPHARMA', 'TATACONSUM',
        'TATAMOTORS', 'TATASTEEL', 'TCS', 'TECHM', 'TITAN',
        'ULTRACEMCO', 'UPL', 'WIPRO'
    ]
    
    # NIFTY BANK constituents
    banknifty_stocks = [
        'AUBANK', 'AXISBANK', 'BANDHANBNK', 'BANKBARODA', 'FEDERALBNK',
        'HDFCBANK', 'ICICIBANK', 'IDFCFIRSTB', 'INDUSINDBK', 'KOTAKBANK',
        'PNB', 'SBIN'
    ]
    
    # Get index instrument IDs
    indices = await conn.fetch('''
        SELECT instrument_id, trading_symbol
        FROM instrument_master
        WHERE instrument_type = 'INDEX'
    ''')
    index_map = {r['trading_symbol']: r['instrument_id'] for r in indices}
    
    # Get equity instrument IDs
    equities = await conn.fetch('''
        SELECT instrument_id, trading_symbol
        FROM instrument_master
        WHERE instrument_type = 'EQUITY'
    ''')
    equity_map = {r['trading_symbol']: r['instrument_id'] for r in equities}
    
    records = []
    today = date.today()
    
    # NIFTY 50
    nifty_id = index_map.get('NIFTY 50')
    if nifty_id:
        for stock in nifty50_stocks:
            stock_id = equity_map.get(stock)
            if stock_id:
                records.append((
                    uuid.uuid4(),
                    nifty_id,
                    stock_id,
                    2.0,  # Default weight (would need actual weights)
                    today,
                    None
                ))
    
    # NIFTY BANK
    banknifty_id = index_map.get('NIFTY BANK')
    if banknifty_id:
        for stock in banknifty_stocks:
            stock_id = equity_map.get(stock)
            if stock_id:
                records.append((
                    uuid.uuid4(),
                    banknifty_id,
                    stock_id,
                    8.33,  # Default equal weight
                    today,
                    None
                ))
    
    print(f"Prepared {len(records)} constituent records")
    
    if records:
        await conn.execute('TRUNCATE index_constituents CASCADE')
        
        await conn.executemany('''
            INSERT INTO index_constituents 
            (id, index_instrument_id, constituent_instrument_id, weight, effective_date, end_date)
            VALUES ($1, $2, $3, $4, $5, $6)
        ''', records)
        
        print(f"Inserted {len(records)} records into index_constituents")
    
    return len(records)

async def main():
    conn = await asyncpg.connect(DB_URL)
    
    print("=" * 60)
    print("POPULATING MASTER TABLES")
    print("=" * 60)
    
    try:
        opt_count = await populate_option_master(conn)
        fut_count = await populate_future_master(conn)
        idx_count = await populate_index_constituents(conn)
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"option_master:      {opt_count:>6} records")
        print(f"future_master:      {fut_count:>6} records")
        print(f"index_constituents: {idx_count:>6} records")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
