"""Debug script to check what instruments are being selected."""

import asyncio
import asyncpg
import re
from datetime import date, timedelta

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

def parse_expiry(symbol):
    """Parse expiry date from trading symbol."""
    # Pattern like NIFTY 05 DEC 24 25200 CE
    patterns = [
        r'(\d{2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})',
        r'(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})'
    ]
    months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    for p in patterns:
        m = re.search(p, symbol.upper())
        if m:
            day, month, year = int(m.group(1)), months[m.group(2)], 2000 + int(m.group(3))
            return date(year, month, day)
    return None


async def check():
    conn = await asyncpg.connect(DB_URL)
    today = date.today()
    future_cutoff = today + timedelta(days=60)
    
    print(f"Today: {today}")
    print(f"Cutoff: {future_cutoff}")
    print()
    
    # Get sample instruments
    rows = await conn.fetch('''
        SELECT trading_symbol, instrument_type, underlying
        FROM instrument_master 
        WHERE instrument_type IN ('FUTURES', 'CE', 'PE')
        AND is_active = true
        LIMIT 30
    ''')
    
    print("Sample instruments:")
    print("-" * 80)
    current_count = 0
    for r in rows:
        sym = r['trading_symbol']
        exp = parse_expiry(sym)
        in_range = exp and today <= exp <= future_cutoff
        if in_range:
            current_count += 1
        status = "CURRENT" if in_range else ("EXPIRED" if exp and exp < today else "")
        print(f"{sym:50} | Exp: {exp} | {status}")
    
    print()
    print(f"Found {current_count} in current range out of {len(rows)} checked")
    
    # Count total current expiry instruments
    all_rows = await conn.fetch('''
        SELECT trading_symbol
        FROM instrument_master 
        WHERE instrument_type IN ('FUTURES', 'CE', 'PE')
        AND is_active = true
    ''')
    
    total_current = 0
    for r in all_rows:
        exp = parse_expiry(r['trading_symbol'])
        if exp and today <= exp <= future_cutoff:
            total_current += 1
    
    print(f"\nTotal instruments with current expiry (next 60 days): {total_current}")
    print(f"Total F&O instruments in DB: {len(all_rows)}")
    
    await conn.close()


if __name__ == "__main__":
    asyncio.run(check())
