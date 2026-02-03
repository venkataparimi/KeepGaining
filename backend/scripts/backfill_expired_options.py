"""
Backfill EXPIRED F&O data using Upstox Expired Instruments API
Supports Options and Futures.
Auto-inserts missing instruments into instrument_master.
Schema adjusted to match DB.
"""
import asyncio
import aiohttp
import asyncpg
import json
import uuid
from datetime import datetime, timedelta
from calendar import monthrange
from pathlib import Path
from urllib.parse import quote
from typing import Optional

# Add backend root to sys.path for app imports
import sys
import os
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from app.brokers.upstox_auth_automation import UpstoxAuthAutomation

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

# Instrument key mapping (Defaults)
INSTRUMENT_KEYS = {
    'NIFTY': 'NSE_INDEX|Nifty 50',
    'BANKNIFTY': 'NSE_INDEX|Nifty Bank',
    'FINNIFTY': 'NSE_INDEX|Nifty Fin Service',
    'MIDCPNIFTY': 'NSE_INDEX|NIFTY MID SELECT',
    'SENSEX': 'BSE_INDEX|SENSEX',
    'BANKEX': 'BSE_INDEX|BANKEX'
}

async def get_token():
    """Get a fresh Upstox token using automation if possible."""
    auth = UpstoxAuthAutomation()
    try:
        token = await auth.get_fresh_token()
        # Verify it actually works (401 check)
        if not await auth.validate_token():
            print("⚠️ Saved token invalid at API level. Forcing automated refresh...")
            token = await auth.get_fresh_token(force=True)
        return token
    except Exception as e:
        print(f"⚠️ Auto-refresh failed: {e}")
        # Fallback to reading file directly as a last resort
        token_file = Path(__file__).parent.parent / 'data' / 'upstox_token.json'
        if token_file.exists():
            with open(token_file) as f:
                return json.load(f)['access_token']
        raise

async def get_expired_expiries(session, token, instrument_key):
    """Get list of available expired expiries"""
    url = f"https://api.upstox.com/v2/expired-instruments/expiries?instrument_key={quote(instrument_key)}"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('data', [])
            else:
                text = await resp.text()
                print(f"❌ Error {resp.status} fetching expiries: {text[:200]}")
                return []
    except Exception as e:
        print(f"❌ Exception fetching expiries: {e}")
        return []

async def get_expired_option_contracts(session, token, instrument_key, expiry, option_type):
    """Get expired option contracts for a specific expiry"""
    url = f"https://api.upstox.com/v2/expired-instruments/option/contract?instrument_key={quote(instrument_key)}&expiry_date={expiry}&option_type={option_type}"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('data', [])
            else:
                text = await resp.text()
                print(f"❌ Error {resp.status} fetching options: {text[:200]}")
                return []
    except Exception as e:
        print(f"❌ Exception fetching options: {e}")
        return []

async def get_expired_future_contracts(session, token, instrument_key, expiry):
    """Get expired future contracts for a specific expiry"""
    url = f"https://api.upstox.com/v2/expired-instruments/future/contract?instrument_key={quote(instrument_key)}&expiry_date={expiry}"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('data', [])
            else:
                text = await resp.text()
                print(f"❌ Error {resp.status} fetching futures: {text[:200]}")
                return []
    except Exception as e:
        print(f"❌ Exception fetching futures: {e}")
        return []

async def download_expired_historical_candle(session, expired_instrument_key, from_date, to_date, token):
    """Download historical candles for an EXPIRED instrument"""
    url = f"https://api.upstox.com/v2/expired-instruments/historical-candle/{quote(expired_instrument_key)}/1minute/{to_date}/{from_date}"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('data', {}).get('candles', [])
            else:
                return []
    except Exception as e:
        return []

async def backfill_expired_instrument(
    symbol: str,
    instrument_key: Optional[str] = None,
    expiry: str = None,
    instrument_type: str = 'OPTION', # OPTION or FUTURE
    option_type: str = 'CE',
    limit: int = 0
):
    """Backfill expired options/futures data"""
    
    # Get instrument key
    if not instrument_key:
        instrument_key = INSTRUMENT_KEYS.get(symbol.upper())
    
    if not instrument_key:
        print(f"❌ Unknown symbol: {symbol}. Pass instrument_key explicitly.")
        return
    
    desc = f"{symbol} {instrument_type}"
    if instrument_type == 'OPTION':
        desc += f" {option_type}"
    
    print(f"=== Backfilling Expired {desc} ===")
    print(f"Instrument Key: {instrument_key}")
    
    pool = await asyncpg.create_pool(DB_URL)
    token = await get_token()
    
    async with aiohttp.ClientSession() as session:
        # Step 1: Get available expiries if not specified
        if not expiry:
            print("\n📅 Fetching available expired expiries...")
            expiries = await get_expired_expiries(session, token, instrument_key)
            if expiries:
                print(f"\n✅ Found {len(expiries)} expired expiries:")
                for i, exp in enumerate(expiries[:20], 1):
                    print(f"  {i}. {exp}")
                if len(expiries) > 20:
                    print(f"  ... and {len(expiries) - 20} more")
                print(f"\n💡 Re-run with: --expiry YYYY-MM-DD")
                await pool.close()
                return
            else:
                print("❌ No expired expiries found or API error")
                await pool.close()
                return
        
        # Step 2: Get contracts for the specified expiry
        print(f"\n📋 Fetching contracts for expiry: {expiry}")
        contracts = []
        if instrument_type == 'OPTION':
            contracts = await get_expired_option_contracts(session, token, instrument_key, expiry, option_type)
        elif instrument_type == 'FUTURE':
            contracts = await get_expired_future_contracts(session, token, instrument_key, expiry)
        
        if not contracts:
            print(f"❌ No contracts found")
            await pool.close()
            return
        
        if limit > 0:
            contracts = contracts[:limit]
        
        print(f"✅ Found {len(contracts)} contracts\n")
        
        # Step 3: Download historical data for each contract
        total_candles = 0
        processed = 0
        
        async with pool.acquire() as conn:
            for idx, contract in enumerate(contracts, 1):
                expired_instrument_key = contract.get('instrument_key')
                trading_symbol = contract.get('trading_symbol')
                
                if not expired_instrument_key:
                    print(f"[{idx}/{len(contracts)}] ❌ No instrument key")
                    continue
                
                # Find this instrument in our database
                inst = await conn.fetchrow("""
                    SELECT instrument_id FROM instrument_master
                    WHERE trading_symbol = $1
                """, trading_symbol)
                
                inst_id = None
                
                if not inst:
                    # Insert missing instrument
                    print(f"[{idx}/{len(contracts)}] {trading_symbol:35} | ➕ Inserting missing instrument...")
                    new_id = str(uuid.uuid4())
                    
                    try:
                        # Extract details
                        exchange = contract.get('exchange', 'NSE')
                        segment = contract.get('segment', 'NSE_FO')
                        
                        # Map instrument type
                        raw_type = contract.get('instrument_type')
                        db_type = raw_type
                        if raw_type in ['FUTIDX', 'FUTSTK']:
                            db_type = 'FUTURES'
                        
                        # Note: DB lacks expiry_date, strike_price, option_type columns in instrument_master
                        # Using 'underlying' column instead of 'underlying_symbol'
                        
                        await conn.execute("""
                            INSERT INTO instrument_master 
                            (instrument_id, trading_symbol, exchange, segment, instrument_type, 
                             underlying, lot_size, tick_size, is_active, created_at, updated_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
                        """, 
                        new_id, 
                        trading_symbol, 
                        exchange, 
                        segment, 
                        db_type,
                        contract.get('underlying_symbol'),
                        int(contract.get('lot_size', 0)),
                        float(contract.get('tick_size', 0.05)),
                        False # is_active=False
                        )
                        inst_id = new_id
                    except Exception as e:
                        print(f"[{idx}/{len(contracts)}] ❌ Failed to insert: {e}")
                        continue
                else:
                    inst_id = inst['instrument_id']
                
                # Check existing data
                existing = await conn.fetchval("""
                    SELECT COUNT(*) FROM candle_data WHERE instrument_id = $1
                """, inst_id)
                
                if existing > 0:
                    print(f"[{idx}/{len(contracts)}] {trading_symbol:35} | ✅ Has {existing:,} candles")
                    continue
                
                # Download data month by month from expiry backwards
                try:
                    expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
                except ValueError:
                    print(f"❌ Invalid expiry format for {expiry}")
                    continue

                start_date = expiry_date - timedelta(days=90)  # 3 months before expiry
                
                instrument_candles = 0
                current_date = start_date
                
                while current_date < expiry_date:
                    last_day = monthrange(current_date.year, current_date.month)[1]
                    month_end = current_date.replace(day=last_day)
                    
                    if month_end > expiry_date:
                        month_end = expiry_date
                    
                    candles = await download_expired_historical_candle(
                        session, expired_instrument_key,
                        current_date.strftime('%Y-%m-%d'),
                        month_end.strftime('%Y-%m-%d'),
                        token
                    )
                    
                    if candles:
                        for c in candles:
                            ts = datetime.fromisoformat(c[0].replace('Z', '+00:00'))
                            try:
                                await conn.execute("""
                                    INSERT INTO candle_data (instrument_id, timestamp, timeframe, open, high, low, close, volume, oi)
                                    VALUES ($1, $2, '1m', $3, $4, $5, $6, $7, $8)
                                    ON CONFLICT (instrument_id, timestamp, timeframe) DO NOTHING
                                """, inst_id, ts, c[1], c[2], c[3], c[4], c[5], c[6] if len(c) > 6 else 0)
                                instrument_candles += 1
                            except:
                                pass
                    
                    current_date = month_end + timedelta(days=1)
                    await asyncio.sleep(0.3)
                
                if instrument_candles > 0:
                    print(f"[{idx}/{len(contracts)}] {trading_symbol:35} | ✅ {instrument_candles:,} candles")
                    total_candles += instrument_candles
                    processed += 1
                else:
                    print(f"[{idx}/{len(contracts)}] {trading_symbol:35} | ⏭️  No data")
        
        print(f"\n{'='*70}")
        print(f"✅ Processed {processed}/{len(contracts)} contracts")
        print(f"✅ Total candles: {total_candles:,}")
        print(f"{'='*70}")
    
    await pool.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Backfill expired F&O data')
    parser.add_argument('--symbol', default='NIFTY', help='Symbol: NIFTY, BANKNIFTY, FINNIFTY')
    parser.add_argument('--key', help='Upstox Instrument Key (overrides symbol map)')
    parser.add_argument('--expiry', help='Expiry date YYYY-MM-DD (leave empty to list)')
    parser.add_argument('--type', choices=['OPTION', 'FUTURE'], default='OPTION', help='Instrument type')
    parser.add_argument('--opttype', choices=['CE', 'PE'], default='CE', help='Option type (CE/PE)')
    parser.add_argument('--limit', type=int, default=0, help='Limit contracts (0 = all)')
    
    args = parser.parse_args()
    
    asyncio.run(backfill_expired_instrument(
        symbol=args.symbol,
        instrument_key=args.key,
        expiry=args.expiry,
        instrument_type=args.type,
        option_type=args.opttype,
        limit=args.limit
    ))
