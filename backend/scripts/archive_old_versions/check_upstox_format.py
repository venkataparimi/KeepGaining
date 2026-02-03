#!/usr/bin/env python3
"""Check Upstox instrument key formats."""
import asyncio
import aiohttp
import gzip
import io
import json

async def check():
    async with aiohttp.ClientSession() as session:
        # Download NSE instruments
        print("Downloading NSE instruments from Upstox...")
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                    data = json.loads(f.read().decode('utf-8'))
                
                print(f"Total NSE instruments: {len(data)}")
                
                # Find equity samples - look for EQ in instrument_key
                equities = [d for d in data if 'NSE_EQ|' in d.get('instrument_key', '')][:5]
                print("\nSample EQUITY from Upstox:")
                for e in equities:
                    print(f"  trading_symbol: {e.get('trading_symbol')}, instrument_key: {e.get('instrument_key')}")
                
                # Find index samples
                indices = [d for d in data if 'INDEX' in d.get('instrument_key', '')][:5]
                print("\nSample INDEX from Upstox:")
                for i in indices:
                    print(f"  trading_symbol: {i.get('trading_symbol')}, instrument_key: {i.get('instrument_key')}")
        
        # Download NFO instruments
        print("\nDownloading NFO instruments from Upstox...")
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NFO.json.gz"
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                    data = json.loads(f.read().decode('utf-8'))
                
                print(f"Total NFO instruments: {len(data)}")
                
                # Find futures samples
                futures = [d for d in data if d.get('instrument_type') == 'FUT'][:5]
                print("\nSample FUTURES from Upstox:")
                for f in futures:
                    print(f"  trading_symbol: {f.get('trading_symbol')}, instrument_key: {f.get('instrument_key')}")
                
                # Find BANKNIFTY options
                bn_opts = [d for d in data if 'BANKNIFTY' in d.get('trading_symbol', '') and d.get('instrument_type') in ('CE', 'PE')][:5]
                print("\nSample BANKNIFTY OPTIONS from Upstox:")
                for o in bn_opts:
                    print(f"  trading_symbol: {o.get('trading_symbol')}, instrument_key: {o.get('instrument_key')}, type: {o.get('instrument_type')}")
                
                # Check what keys are available
                if data:
                    print("\nSample instrument keys available:")
                    print(f"  Keys: {list(data[0].keys())}")

if __name__ == '__main__':
    asyncio.run(check())
