#!/usr/bin/env python3
"""
Download Expired F&O Historical Data using Upstox Expired Instruments API

This script downloads historical data for expired options/futures contracts
from specific expiry dates (e.g., May 2022).

Usage:
    python backfill_expired_data.py --expiry 2022-05-26 --underlying NIFTY
"""

import asyncio
import asyncpg
import aiohttp
import argparse
import json
import sys
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

# Upstox API endpoints for expired instruments
EXPIRED_EXPIRIES_URL = "https://api.upstox.com/v2/expired-instruments/expiries"
EXPIRED_OPTIONS_URL = "https://api.upstox.com/v2/expired-instruments/option/contract"
EXPIRED_FUTURES_URL = "https://api.upstox.com/v2/expired-instruments/future/contract"
EXPIRED_CANDLE_URL = "https://api.upstox.com/v2/expired-instruments/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"


def get_upstox_token() -> str:
    """Load Upstox access token."""
    import os
    token_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'upstox_token.json')
    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            data = json.load(f)
            return data.get('access_token')
    return None


async def get_expired_expiries(token: str, instrument_type: str = "OPTIDX") -> List[str]:
    """
    Get list of available expired expiry dates.
    
    Args:
        instrument_type: OPTIDX (index options), OPTSTK (stock options), FUTIDX, FUTSTK
    """
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    params = {'instrument_type': instrument_type}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(EXPIRED_EXPIRIES_URL, headers=headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                expiries = data.get('data', {}).get('expiries', [])
                logger.info(f"Found {len(expiries)} expired expiries for {instrument_type}")
                return expiries
            else:
                logger.error(f"Failed to get expiries: {response.status}")
                return []


async def get_expired_option_contracts(
    token: str,
    expiry_date: str,
    underlying: str = "NIFTY",
    instrument_type: str = "OPTIDX"
) -> List[Dict]:
    """
    Get all option contracts for a specific expiry.
    
    Args:
        expiry_date: Format YYYY-MM-DD
        underlying: NIFTY, BANKNIFTY, etc.
        instrument_type: OPTIDX or OPTSTK
    """
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    params = {
        'instrument_type': instrument_type,
        'expiry_date': expiry_date,
        'underlying': underlying
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(EXPIRED_OPTIONS_URL, headers=headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                contracts = data.get('data', [])
                logger.info(f"Found {len(contracts)} contracts for {underlying} expiry {expiry_date}")
                return contracts
            else:
                error_text = await response.text()
                logger.error(f"Failed to get contracts: {response.status} - {error_text}")
                return []


async def download_expired_candles(
    token: str,
    instrument_key: str,
    from_date: date,
    to_date: date,
    interval: str = "1minute"
) -> List[Dict]:
    """Download historical candles for an expired instrument."""
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    from_str = from_date.strftime('%Y-%m-%d')
    to_str = to_date.strftime('%Y-%m-%d')
    
    url = EXPIRED_CANDLE_URL.format(
        instrument_key=instrument_key,
        interval=interval,
        to_date=to_str,
        from_date=from_str
    )
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                candles = data.get('data', {}).get('candles', [])
                
                result = []
                for candle in candles:
                    result.append({
                        'timestamp': datetime.fromisoformat(candle[0].replace('Z', '+00:00')),
                        'open': float(candle[1]),
                        'high': float(candle[2]),
                        'low': float(candle[3]),
                        'close': float(candle[4]),
                        'volume': int(candle[5]),
                        'oi': int(candle[6]) if len(candle) > 6 else 0
                    })
                return result
            
            elif response.status == 429:
                logger.warning(f"Rate limited, waiting 10s...")
                await asyncio.sleep(10)
                return []
            
            else:
                logger.error(f"Failed to download candles: {response.status}")
                return []


async def save_candles_to_db(conn, instrument_id, candles: List[Dict], timeframe: str = '1m') -> int:
    """Save candles to database."""
    if not candles:
        return 0
    
    records = [
        (
            instrument_id,
            timeframe,
            candle['timestamp'],
            candle['open'],
            candle['high'],
            candle['low'],
            candle['close'],
            candle['volume'],
            candle.get('oi', 0)
        )
        for candle in candles
    ]
    
    try:
        temp_table = f"temp_candles_{instrument_id.hex}"
        await conn.execute(f"CREATE TEMP TABLE IF NOT EXISTS {temp_table} (LIKE candle_data INCLUDING DEFAULTS)")
        await conn.execute(f"TRUNCATE {temp_table}")
        
        await conn.copy_records_to_table(
            temp_table,
            records=records,
            columns=['instrument_id', 'timeframe', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi']
        )
        
        result = await conn.execute(f'''
            INSERT INTO candle_data (instrument_id, timeframe, timestamp, open, high, low, close, volume, oi)
            SELECT instrument_id, timeframe, timestamp, open, high, low, close, volume, oi
            FROM {temp_table}
            ON CONFLICT (instrument_id, timeframe, timestamp) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                oi = EXCLUDED.oi
        ''')
        
        await conn.execute(f"DROP TABLE {temp_table}")
        
        count = int(result.split()[-1]) if result else len(records)
        return count
        
    except Exception as e:
        logger.error(f"Failed to save candles: {e}")
        return 0


async def main():
    parser = argparse.ArgumentParser(description='Download expired F&O historical data')
    parser.add_argument('--expiry', help='Expiry date (YYYY-MM-DD), e.g., 2022-05-26')
    parser.add_argument('--underlying', default='NIFTY', help='Underlying symbol (NIFTY, BANKNIFTY, etc.)')
    parser.add_argument('--type', default='OPTIDX', choices=['OPTIDX', 'OPTSTK', 'FUTIDX', 'FUTSTK'], help='Instrument type')
    parser.add_argument('--list-expiries', action='store_true', help='List available expiries and exit')
    
    args = parser.parse_args()
    
    token = get_upstox_token()
    if not token:
        logger.error("No Upstox token found. Please authenticate first.")
        return
    
    # List expiries if requested
    if args.list_expiries:
        expiries = await get_expired_expiries(token, args.type)
        print(f"\nAvailable expired expiries for {args.type}:")
        for exp in sorted(expiries, reverse=True)[:20]:  # Show last 20
            print(f"  {exp}")
        return
    
    # Validate expiry is provided for download
    if not args.expiry:
        parser.error("--expiry is required when not using --list-expiries")
        return
    
    # Get contracts for the specified expiry
    logger.info(f"Fetching contracts for {args.underlying} expiry {args.expiry}...")
    contracts = await get_expired_option_contracts(token, args.expiry, args.underlying, args.type)
    
    if not contracts:
        logger.error("No contracts found")
        return
    
    logger.info(f"Found {len(contracts)} contracts. Starting download...")
    
    # Connect to database
    conn = await asyncpg.connect(DB_URL)
    
    # Download data for each contract
    expiry_date = datetime.strptime(args.expiry, '%Y-%m-%d').date()
    from_date = expiry_date - timedelta(days=60)  # 60 days before expiry
    to_date = expiry_date
    
    total_candles = 0
    successful = 0
    
    for i, contract in enumerate(contracts):
        instrument_key = contract.get('instrument_key')
        trading_symbol = contract.get('trading_symbol')
        
        # Check if we have this instrument in our DB
        inst_id = await conn.fetchval(
            "SELECT instrument_id FROM instrument_master WHERE trading_symbol = $1",
            trading_symbol
        )
        
        if not inst_id:
            logger.warning(f"[{i+1}/{len(contracts)}] {trading_symbol} not in database, skipping")
            continue
        
        # Download candles
        logger.info(f"[{i+1}/{len(contracts)}] Downloading {trading_symbol}...")
        candles = await download_expired_candles(token, instrument_key, from_date, to_date)
        
        if candles:
            saved = await save_candles_to_db(conn, inst_id, candles)
            total_candles += saved
            successful += 1
            print(f"[{i+1}/{len(contracts)}] {trading_symbol:<40} | +{saved} candles")
        else:
            print(f"[{i+1}/{len(contracts)}] {trading_symbol:<40} | No data")
        
        # Rate limiting
        await asyncio.sleep(0.1)  # 10 calls/sec max
    
    await conn.close()
    
    print(f"\nCompleted:")
    print(f"  Successful: {successful}/{len(contracts)}")
    print(f"  Total candles: {total_candles:,}")


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
