#!/usr/bin/env python3
"""Verify we can match trading symbols and get instrument keys."""
import asyncio
import aiohttp
import gzip
import io
import json
import asyncpg

async def build_cache():
    """Build cache from NSE file only (F&O are also there)."""
    cache = {}
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        print(f"Downloading from {url}...")
        
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                    data = json.loads(f.read().decode('utf-8'))
                
                print(f"Downloaded {len(data)} instruments")
                
                # Build cache by trading_symbol
                for item in data:
                    ts = item.get('trading_symbol', '')
                    ik = item.get('instrument_key', '')
                    if ts and ik:
                        cache[ts] = ik
                        cache[ts.upper()] = ik
                
                print(f"Cache has {len(cache)} entries")
    
    return cache, data

async def check_match():
    # Build cache
    cache, raw_data = await build_cache()
    
    # Connect to our DB
    conn = await asyncpg.connect('postgresql://user:password@localhost:5432/keepgaining')
    
    # Get sample instruments from our DB
    print("\n" + "="*80)
    print("Testing matches for instruments in our DB:")
    print("="*80)
    
    # Test equities
    rows = await conn.fetch("""
        SELECT trading_symbol FROM instrument_master 
        WHERE instrument_type = 'EQUITY' LIMIT 5
    """)
    print("\nEQUITY matches:")
    for r in rows:
        ts = r['trading_symbol']
        ik = cache.get(ts, "NOT FOUND")
        print(f"  {ts}: {ik}")
    
    # Test index
    rows = await conn.fetch("""
        SELECT trading_symbol FROM instrument_master 
        WHERE instrument_type = 'INDEX' LIMIT 5
    """)
    print("\nINDEX matches:")
    for r in rows:
        ts = r['trading_symbol']
        ik = cache.get(ts, "NOT FOUND")
        print(f"  {ts}: {ik}")
    
    # Test F&O
    rows = await conn.fetch("""
        SELECT trading_symbol FROM instrument_master 
        WHERE instrument_type IN ('CE', 'PE', 'FUTURES') LIMIT 10
    """)
    print("\nF&O matches:")
    for r in rows:
        ts = r['trading_symbol']
        ik = cache.get(ts, "NOT FOUND")
        print(f"  {ts}: {ik}")
    
    await conn.close()
    
    # Check what F&O symbols look like in Upstox
    print("\n" + "="*80)
    print("Sample F&O instruments from Upstox (NSE file):")
    print("="*80)
    fo_samples = [d for d in raw_data if d.get('segment') == 'NSE_FO'][:10]
    for s in fo_samples:
        print(f"  {s.get('trading_symbol')}: {s.get('instrument_key')}")

if __name__ == '__main__':
    asyncio.run(check_match())
