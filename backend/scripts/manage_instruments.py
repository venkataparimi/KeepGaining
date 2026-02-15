import argparse
import asyncio
import sys
import os
import io
import gzip
import json
import urllib.request
import requests
from datetime import date, datetime
from typing import List, Optional
from decimal import Decimal

# Add backend to path (robust method)
current_dir = os.path.dirname(os.path.abspath(__file__))
# If script is in backend/scripts/manage_instruments.py, backend/ is 2 levels up
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir)

from sqlalchemy import select, text
from app.db.session import get_db_context, AsyncSessionLocal
from app.db.models.instrument import InstrumentMaster, FutureMaster, OptionMaster

# --- Subcommand Handlers ---

async def inspect_upstox(args):
    """Downloads and inspects the Upstox instrument dump."""
    url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
    print(f"Downloading {url}...")
    
    try:
        # Use a simpler download for inspection (no async stream needed for CLI tool simplicity check)
        with urllib.request.urlopen(url) as response:
            compressed_file = io.BytesIO(response.read())
            decompressed_file = gzip.GzipFile(fileobj=compressed_file)
            data = json.load(decompressed_file)
            
        print(f"Downloaded {len(data)} instruments.")
        
        matches = []
        count = 0
        
        for item in data:
            # Filter by Segment
            if args.segment and item.get('segment') != args.segment:
                continue
                
            # Filter by Type (CE, PE, FUT, EQ)
            itype = item.get('instrument_type')
            if args.type and itype != args.type:
                continue
                
            # Filter by Symbol/Name (partial match)
            name = item.get('name', '')
            ts = item.get('trading_symbol', '')
            query = args.query.upper() if args.query else ""
            
            if query and (query not in name and query not in ts):
                continue
                
            # Filter by Expiry Month/Year
            if args.expiry:
                # Expected format MM-YYYY
                exp_ms = item.get('expiry')
                if not exp_ms:
                    continue
                try:
                    exp_date = datetime.fromtimestamp(exp_ms / 1000).date()
                    target_pair = args.expiry.split('-')
                    if len(target_pair) == 2:
                        t_month, t_year = int(target_pair[0]), int(target_pair[1])
                        if exp_date.month != t_month or exp_date.year != t_year:
                            continue
                except:
                    continue

            matches.append(item)
            count += 1
            if args.limit and count >= args.limit:
                break
        
        print(f"\nFound {len(matches)} matches (showing max {args.limit}):")
        for m in matches:
            expiry_str = "N/A"
            if m.get('expiry'):
                expiry_str = datetime.fromtimestamp(m.get('expiry') / 1000).date()
            print(f"  {m.get('trading_symbol')} | Type: {m.get('instrument_type')} | Strike: {m.get('strike_price')} | Expiry: {expiry_str}")

    except Exception as e:
        print(f"Error inspecting Upstox data: {e}")


async def inspect_db(args):
    """Inspects instruments in the local database."""
    async with get_db_context() as db:
        print("Inspecting Database...")
        
        # Build Query
        stmt = select(InstrumentMaster)
        
        if args.symbol:
            stmt = stmt.where(InstrumentMaster.trading_symbol.like(f"%{args.symbol}%"))
            
        if args.segment:
            stmt = stmt.where(InstrumentMaster.segment == args.segment)
            
        if args.type:
            stmt = stmt.where(InstrumentMaster.instrument_type == args.type)
            
        stmt = stmt.limit(args.limit)
        
        result = await db.execute(stmt)
        instruments = result.scalars().all()
        
        print(f"Found {len(instruments)} records:")
        for i in instruments:
            print(f"  [{i.instrument_type}] {i.trading_symbol} (ID: {i.instrument_id})")
            
            # Show details if requested
            if args.details:
                if i.instrument_type in ['FUTURE', 'FUT']:
                    fm_stmt = select(FutureMaster).where(FutureMaster.instrument_id == i.instrument_id)
                    fm = await db.scalar(fm_stmt)
                    if fm:
                        print(f"    Warning: FutureMaster found. Expiry: {fm.expiry_date}, UnderlyingID: {fm.underlying_instrument_id}")
                
                elif i.instrument_type == 'OPTION':
                    om_stmt = select(OptionMaster).where(OptionMaster.instrument_id == i.instrument_id)
                    om = await db.scalar(om_stmt)
                    if om:
                        print(f"    Option: {om.option_type} {om.strike_price} Exp: {om.expiry_date}")


async def repair_futures(args):
    """Links orphaned FutureMaster records to their underlying."""
    async with get_db_context() as db:
        print("Running Future Linkage Repair...")
        
        # Find Futures without underlying link
        stmt = select(FutureMaster).where(FutureMaster.underlying_instrument_id == None)
        result = await db.execute(stmt)
        futures = result.scalars().all()
        
        print(f"Found {len(futures)} futures with missing underlying linkage.")
        
        count = 0
        for f in futures:
            # Get Instrument to know the symbol
            im_stmt = select(InstrumentMaster).where(InstrumentMaster.instrument_id == f.instrument_id)
            im = await db.scalar(im_stmt)
            
            if not im or not im.underlying:
                continue
                
            underlying_symbol = im.underlying
            
            # Find the underlying master (Index or Equity)
            # Special case for NIFTY
            if underlying_symbol == 'NIFTY':
                underlying_symbol = 'NIFTY 50'
            elif underlying_symbol == 'BANKNIFTY':
                underlying_symbol = 'NIFTY BANK'
                
            u_stmt = select(InstrumentMaster).where(
                InstrumentMaster.trading_symbol == underlying_symbol,
                InstrumentMaster.instrument_type.in_(['INDEX', 'EQUITY'])
            )
            u_im = await db.scalar(u_stmt)
            
            if u_im:
                f.underlying_instrument_id = u_im.instrument_id
                count += 1
            else:
                if args.verbose:
                    print(f"  Could not find underlying '{underlying_symbol}' for {im.trading_symbol}")

        if args.dry_run:
            print(f"[Dry Run] Would have linked {count} futures.")
        else:
            await db.commit()
            print(f"Successfully linked {count} futures.")


async def verify_api(args):
    """Verifies Key API Endpoints."""
    base_url = args.url.rstrip('/')
    print(f"Verifying API at {base_url}...")
    
    # 1. Check Symbols
    try:
        print("Checking /symbols (OPTION)...", end=" ")
        resp = requests.get(f"{base_url}/api/master/symbols", params={"instrument_type": "OPTION"})
        resp.raise_for_status()
        data = resp.json()
        if len(data) > 0 and ("NIFTY 50" in data or "ADANIENT" in data or "NIFTY" in data):
            print("OK")
        else:
            print(f"WARNING (Found {len(data)} items)")
    except Exception as e:
        print(f"FAIL: {e}")

    # 2. Check Expiries
    try:
        print("Checking /expiries (NIFTY 50 OPTION)...", end=" ")
        resp = requests.get(f"{base_url}/api/master/expiries", params={"underlying": "NIFTY 50", "instrument_type": "OPTION"})
        resp.raise_for_status()
        expiries = resp.json()
        if len(expiries) > 0:
            print(f"OK ({len(expiries)} dates)")
        else:
            print("WARNING (No expiries)")
    except Exception as e:
        print(f"FAIL: {e}")

    # 3. Check Option Chain (Integer Formatting)
    expiry = None
    if 'expiries' in locals() and expiries:
        # Try to find a recent/future expiry
        for e in expiries:
            if "2026" in e: 
                expiry = e
                break
        if not expiry: expiry = expiries[0]

    if expiry:
        try:
            print(f"Checking /option-chain (NIFTY 50, {expiry})...", end=" ")
            resp = requests.get(f"{base_url}/api/master/option-chain", params={"underlying": "NIFTY 50", "expiry_date": expiry})
            resp.raise_for_status()
            chain = resp.json()
            
            integers = sum(1 for x in chain if isinstance(x['strike_price'], int))
            floats = sum(1 for x in chain if isinstance(x['strike_price'], float))
            
            if integers > 0 and len(chain) > 0:
                print(f"OK (Ints: {integers}, Floats: {floats})")
            else:
                print(f"WARNING (Ints: {integers}, Floats: {floats})")
        except Exception as e:
            print(f"FAIL: {e}")
            
    # 4. Check Futures Contract
    try:
        print("Checking /futures-contract (NIFTY 50)...", end=" ")
        # Get future expiry first
        resp = requests.get(f"{base_url}/api/master/expiries", params={"underlying": "NIFTY 50", "instrument_type": "FUTURE"})
        f_expiries = resp.json()
        if f_expiries:
            f_exp = f_expiries[0]
            resp = requests.get(f"{base_url}/api/master/futures-contract", params={"underlying": "NIFTY 50", "expiry_date": f_exp})
            if resp.status_code == 200:
                print(f"OK ({resp.json().get('trading_symbol')})")
            else:
                print(f"FAIL ({resp.status_code})")
        else:
            print("SKIP (No future expiries)")
    except Exception as e:
        print(f"FAIL: {e}")


# --- Main Entry Point ---

def main():
    parser = argparse.ArgumentParser(description="KeepGaining Instrument Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # inspect-upstox
    p_upstox = subparsers.add_parser("inspect-upstox", help="Inspect remote Upstox dump")
    p_upstox.add_argument("--query", help="Filter by name/symbol")
    p_upstox.add_argument("--segment", default="NSE_FO", help="Filter by segment (default: NSE_FO)")
    p_upstox.add_argument("--type", help="Filter by instrument type (CE, PE, FUT, EQ)")
    p_upstox.add_argument("--expiry", help="Filter by expiry (MM-YYYY)")
    p_upstox.add_argument("--limit", type=int, default=10, help="Max results to show")
    
    # inspect-db
    p_db = subparsers.add_parser("inspect-db", help="Inspect local database")
    p_db.add_argument("--symbol", help="Filter by trading symbol")
    p_db.add_argument("--type", help="Filter by type (OPTION, FUTURE, INDEX, EQUITY)")
    p_db.add_argument("--segment", help="Filter by segment")
    p_db.add_argument("--limit", type=int, default=20, help="Max results")
    p_db.add_argument("--details", action="store_true", help="Show extended details")

    # repair-futures
    p_repair = subparsers.add_parser("repair-futures", help="Fix missing underlying links in FutureMaster")
    p_repair.add_argument("--dry-run", action="store_true", help="Don't commit changes")
    p_repair.add_argument("--verbose", action="store_true", help="Show skip reasons")

    # verify-api
    p_verify = subparsers.add_parser("verify-api", help="Verify backend API endpoints")
    p_verify.add_argument("--url", default="http://localhost:8001", help="Base URL (default: http://localhost:8001)")

    args = parser.parse_args()
    
    if args.command == "inspect-upstox":
        asyncio.run(inspect_upstox(args))
    elif args.command == "inspect-db":
        asyncio.run(inspect_db(args))
    elif args.command == "repair-futures":
        asyncio.run(repair_futures(args))
    elif args.command == "verify-api":
        asyncio.run(verify_api(args))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
