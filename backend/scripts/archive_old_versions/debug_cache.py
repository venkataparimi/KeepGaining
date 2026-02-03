"""Debug script to verify instrument key cache."""

import asyncio
import aiohttp
import gzip
import json
import io

async def check_cache():
    # Download NSE instruments
    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
        async with session.get(url) as response:
            content = await response.read()
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                data = json.loads(f.read().decode('utf-8'))
    
    # Build cache
    cache = {}
    for item in data:
        ts = item.get('trading_symbol', '')
        ik = item.get('instrument_key', '')
        if ts and ik:
            cache[ts] = ik
    
    print(f"Cache has {len(cache)} entries from {len(data)} instruments")
    
    # Test lookups
    test_symbols = [
        "BANKNIFTY FUT 30 DEC 25",
        "NIFTY FUT 30 DEC 25",
        "BANKNIFTY 51200 CE 30 DEC 25",
        "NIFTY 24000 CE 30 DEC 25",
        # Try with random symbols that might be in DB
        "AAVAS",  # Equity
        "NIFTY 50",  # Index
    ]
    
    print("\nLooking up test symbols:")
    for sym in test_symbols:
        key = cache.get(sym)
        print(f"  {sym:40} -> {key or 'NOT FOUND'}")
    
    # Count by segment
    segments = {}
    for item in data:
        seg = item.get('segment', 'UNKNOWN')
        segments[seg] = segments.get(seg, 0) + 1
    
    print("\nInstruments by segment:")
    for seg, count in sorted(segments.items()):
        print(f"  {seg}: {count}")


if __name__ == "__main__":
    asyncio.run(check_cache())
