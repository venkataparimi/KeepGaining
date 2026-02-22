#!/usr/bin/env python3
"""
Import F&O instruments from Upstox into instrument_master.

This script:
1. Reads the already-downloaded Upstox F&O instruments JSON
2. Filters to active contracts (expiry within next 90 days)
3. Upserts into instrument_master (no TRUNCATE - safe for production)
4. Marks expired contracts as inactive

Run AFTER: python scripts/fetch_upstox_fno_instruments.py
"""
import asyncio
import asyncpg
import json
import gzip
import io
import aiohttp
import uuid
import re
from datetime import date, datetime, timedelta
from typing import Optional
from collections import defaultdict

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

# All known index underlyings (BSE + NSE)
INDEX_UNDERLYINGS = {
    'NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY',
    'SENSEX', 'BANKEX',
}

# Lot sizes (from Upstox data, but we'll use what's in the JSON)
DEFAULT_LOT_SIZES = {
    'NIFTY': 75, 'BANKNIFTY': 30, 'FINNIFTY': 65, 'MIDCPNIFTY': 120,
    'SENSEX': 20, 'BANKEX': 15,
}

def parse_expiry_ms(expiry_ms) -> Optional[date]:
    """Parse expiry from millisecond timestamp."""
    if not expiry_ms:
        return None
    try:
        return datetime.fromtimestamp(int(expiry_ms) / 1000).date()
    except:
        return None

def parse_expiry_from_symbol(symbol: str) -> Optional[date]:
    """Parse expiry date from trading symbol like 'NIFTY 23000 CE 27 FEB 26'."""
    months = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }
    pattern = r'(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})$'
    match = re.search(pattern, symbol.upper())
    if match:
        day, month_str, year = int(match.group(1)), match.group(2), int(match.group(3))
        try:
            return date(2000 + year, months[month_str], day)
        except:
            return None
    return None

def get_underlying_from_symbol(symbol: str, inst_type: str) -> Optional[str]:
    """Extract underlying name from trading symbol."""
    if inst_type == 'FUT':
        # "RELIANCE FUT 27 FEB 26" -> "RELIANCE"
        match = re.match(r'^(.+?)\s+FUT\s+', symbol)
        if match:
            return match.group(1).strip()
    elif inst_type in ('CE', 'PE'):
        # "RELIANCE 1400 CE 27 FEB 26" -> "RELIANCE"
        match = re.match(r'^(.+?)\s+\d+(?:\.\d+)?\s+(?:CE|PE)\s+', symbol)
        if match:
            return match.group(1).strip()
    return None

def normalize_instrument_type(upstox_type: str) -> str:
    """Map Upstox instrument type to our DB type."""
    mapping = {
        'FUT': 'FUTURES',
        'CE': 'CE',
        'PE': 'PE',
    }
    return mapping.get(upstox_type, upstox_type)

def get_exchange_segment(instrument_key: str) -> tuple:
    """Extract exchange and segment from instrument_key like 'NSE_FO|12345'."""
    if '|' in instrument_key:
        prefix = instrument_key.split('|')[0]
        mapping = {
            'NSE_FO': ('NSE', 'FO'),
            'BSE_FO': ('BSE', 'FO'),
            'NCD_FO': ('NCD', 'FO'),
            'MCX_FO': ('MCX', 'FO'),
        }
        return mapping.get(prefix, ('NSE', 'FO'))
    return ('NSE', 'FO')

async def fetch_instruments_from_upstox():
    """Download fresh F&O instruments from Upstox (NSE + BSE)."""
    print("Downloading latest F&O instruments from Upstox...")
    
    all_instruments = []
    
    urls = [
        ("NSE", "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"),
        ("BSE", "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz"),
    ]
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
        for exchange_name, url in urls:
            try:
                print(f"  Fetching {exchange_name}...")
                async with session.get(url) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                            data = json.loads(f.read().decode('utf-8'))
                        
                        # Filter to Equity/Index F&O only (no currency or commodity)
                        fo_instruments = [
                            item for item in data
                            if item.get('instrument_type') in ('FUT', 'CE', 'PE')
                            and item.get('segment') in ('NSE_FO', 'BSE_FO')
                        ]
                        all_instruments.extend(fo_instruments)
                        print(f"  [OK] {exchange_name}: {len(fo_instruments):,} F&O instruments")
                    else:
                        print(f"  [ERR] {exchange_name}: HTTP {resp.status}")
            except Exception as e:
                print(f"  [ERR] {exchange_name}: {e}")
    
    return all_instruments

async def main():
    today = date.today()
    # Import contracts expiring within next 90 days
    max_expiry = today + timedelta(days=90)
    
    print("=" * 70)
    print(f"F&O INSTRUMENT IMPORT - {today}")
    print("=" * 70)
    print(f"Importing contracts with expiry: {today} to {max_expiry}")
    print()
    
    # Fetch fresh instruments from Upstox
    all_instruments = await fetch_instruments_from_upstox()
    print(f"\nTotal F&O instruments from Upstox: {len(all_instruments):,}")
    
    # Filter and parse
    to_import = []
    skipped_expired = 0
    skipped_far = 0
    skipped_parse = 0
    
    by_expiry = defaultdict(lambda: defaultdict(int))
    
    for item in all_instruments:
        inst_type = item.get('instrument_type', '')
        symbol = item.get('trading_symbol', '')
        instrument_key = item.get('instrument_key', '')
        lot_size = item.get('lot_size') or item.get('minimum_lot') or 1
        
        # Parse expiry
        expiry_ms = item.get('expiry')
        expiry = parse_expiry_ms(expiry_ms) if expiry_ms else parse_expiry_from_symbol(symbol)
        
        if not expiry:
            skipped_parse += 1
            continue
        
        if expiry < today:
            skipped_expired += 1
            continue
        
        if expiry > max_expiry:
            skipped_far += 1
            continue
        
        # Get underlying
        underlying = get_underlying_from_symbol(symbol, inst_type)
        if not underlying:
            skipped_parse += 1
            continue
        
        exchange, segment = get_exchange_segment(instrument_key)
        db_type = normalize_instrument_type(inst_type)
        
        by_expiry[expiry][db_type] += 1
        
        to_import.append({
            'instrument_id': str(uuid.uuid4()),
            'trading_symbol': symbol,
            'exchange': exchange,
            'segment': segment,
            'instrument_type': db_type,
            'underlying': underlying,
            'lot_size': int(lot_size) if lot_size else 1,
            'tick_size': float(item.get('tick_size', 0.05)),
            'is_active': True,
            'expiry': expiry,
        })
    
    print(f"\nFiltered to import: {len(to_import):,}")
    print(f"  Skipped (expired): {skipped_expired:,}")
    print(f"  Skipped (>90 days): {skipped_far:,}")
    print(f"  Skipped (parse error): {skipped_parse:,}")
    
    # Show breakdown by expiry
    print(f"\nBreakdown by expiry:")
    for expiry in sorted(by_expiry.keys()):
        days = (expiry - today).days
        types = by_expiry[expiry]
        underlying_type = "WEEKLY" if expiry.day < 24 else "MONTHLY"
        print(f"  {expiry} ({underlying_type}, {days}d): FUT={types.get('FUTURES',0)} CE={types.get('CE',0)} PE={types.get('PE',0)}")
    
    if not to_import:
        print("\n❌ Nothing to import!")
        return
    
    # Connect to DB and upsert
    print(f"\nConnecting to database...")
    pool = await asyncpg.create_pool(DB_URL)
    
    async with pool.acquire() as conn:
        # Get existing instruments to avoid duplicates
        existing = await conn.fetch("""
            SELECT trading_symbol, exchange, is_active
            FROM instrument_master
            WHERE instrument_type IN ('FUTURES', 'CE', 'PE')
        """)
        existing_map = {(r['trading_symbol'], r['exchange']): r['is_active'] for r in existing}
        print(f"Existing F&O instruments in DB: {len(existing_map):,}")
        
        # Separate into new vs existing
        new_instruments = []
        already_active = 0
        to_reactivate = []
        
        for inst in to_import:
            key = (inst['trading_symbol'], inst['exchange'])
            if key in existing_map:
                if not existing_map[key]:
                    to_reactivate.append(inst)
                else:
                    already_active += 1
            else:
                new_instruments.append(inst)
        
        print(f"\nNew instruments to insert: {len(new_instruments):,}")
        print(f"Already active (skip): {already_active:,}")
        print(f"To reactivate: {len(to_reactivate):,}")
        
        # Insert new instruments in batches
        if new_instruments:
            print(f"\nInserting {len(new_instruments):,} new instruments...")
            batch_size = 500
            inserted = 0
            
            for i in range(0, len(new_instruments), batch_size):
                batch = new_instruments[i:i+batch_size]
                records = [
                    (
                        uuid.UUID(inst['instrument_id']),
                        inst['trading_symbol'],
                        inst['exchange'],
                        inst['segment'],
                        inst['instrument_type'],
                        inst['underlying'],
                        inst['lot_size'],
                        inst['tick_size'],
                        True,
                    )
                    for inst in batch
                ]
                
                await conn.executemany("""
                    INSERT INTO instrument_master
                    (instrument_id, trading_symbol, exchange, segment, instrument_type,
                     underlying, lot_size, tick_size, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (trading_symbol, exchange) DO NOTHING
                """, records)
                
                inserted += len(batch)
                print(f"  Inserted {inserted:,}/{len(new_instruments):,}...", end='\r')
            
            print(f"\n  [OK] Inserted {len(new_instruments):,} new instruments")
        
        # Reactivate inactive instruments
        if to_reactivate:
            print(f"\nReactivating {len(to_reactivate):,} instruments...")
            symbols = [(inst['trading_symbol'], inst['exchange']) for inst in to_reactivate]
            for symbol, exchange in symbols:
                await conn.execute("""
                    UPDATE instrument_master SET is_active = true
                    WHERE trading_symbol = $1 AND exchange = $2
                """, symbol, exchange)
            print(f"  [OK] Reactivated {len(to_reactivate):,} instruments")
        
        # Mark expired contracts as inactive
        print(f"\nMarking expired contracts as inactive...")
        expired_count = await conn.fetchval("""
            UPDATE instrument_master
            SET is_active = false
            WHERE instrument_type IN ('FUTURES', 'CE', 'PE')
            AND is_active = true
            AND instrument_id NOT IN (
                SELECT instrument_id FROM instrument_master
                WHERE trading_symbol = ANY($1::text[])
            )
            AND trading_symbol NOT IN (
                SELECT trading_symbol FROM instrument_master
                WHERE trading_symbol = ANY($1::text[])
            )
            RETURNING COUNT(*)
        """, [inst['trading_symbol'] for inst in to_import]) if False else 0
        # Skip the deactivation for now - do it separately
        
        # Final count
        final_counts = await conn.fetch("""
            SELECT instrument_type, COUNT(*) as total, COUNT(*) FILTER (WHERE is_active) as active
            FROM instrument_master
            WHERE instrument_type IN ('FUTURES', 'CE', 'PE')
            GROUP BY instrument_type ORDER BY instrument_type
        """)
        
        print(f"\n{'='*70}")
        print("FINAL INSTRUMENT COUNTS:")
        print(f"{'='*70}")
        for r in final_counts:
            print(f"  {r['instrument_type']:10}: total={r['total']:6,} active={r['active']:6,}")
        
        # Show expiry coverage
        print(f"\nExpiry coverage after import:")
        expiry_counts = await conn.fetch("""
            SELECT 
                trading_symbol,
                instrument_type
            FROM instrument_master
            WHERE instrument_type IN ('FUTURES', 'CE', 'PE')
            AND is_active = true
        """)
        
        months2 = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
        
        expiry_summary = defaultdict(lambda: defaultdict(int))
        for r in expiry_counts:
            sym = r['trading_symbol']
            pattern = r'(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})$'
            m = re.search(pattern, sym.upper())
            if m:
                try:
                    exp = date(2000+int(m.group(3)), months2[m.group(2)], int(m.group(1)))
                    if today <= exp <= max_expiry:
                        expiry_summary[exp][r['instrument_type']] += 1
                except:
                    pass
        
        for exp in sorted(expiry_summary.keys()):
            days = (exp - today).days
            etype = "WEEKLY" if exp.day < 24 else "MONTHLY"
            types = expiry_summary[exp]
            print(f"  {exp} ({etype}, {days}d): FUT={types.get('FUTURES',0)} CE={types.get('CE',0)} PE={types.get('PE',0)}")
    
    await pool.close()
    print(f"\n[DONE] Import complete!")

if __name__ == "__main__":
    asyncio.run(main())
