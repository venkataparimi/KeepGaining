#!/usr/bin/env python3
"""Check specific instrument keys from Upstox."""
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
                
                # Find RELIANCE
                reliance = [d for d in data if d.get('trading_symbol') == 'RELIANCE']
                print("\nRELIANCE from Upstox:")
                for r in reliance:
                    print(f"  trading_symbol: {r.get('trading_symbol')}, instrument_key: {r.get('instrument_key')}")
                    print(f"  All keys: {list(r.keys())}")
                    print(f"  Full data: {r}")
                
                # Find NIFTY 50 index
                nifty = [d for d in data if 'NIFTY 50' in d.get('trading_symbol', '')]
                print("\nNIFTY 50 related from Upstox:")
                for n in nifty[:3]:
                    print(f"  trading_symbol: {n.get('trading_symbol')}, instrument_key: {n.get('instrument_key')}")
                
                # Find NIFTY BANK
                nb = [d for d in data if 'BANK' in d.get('trading_symbol', '') and 'NIFTY' in d.get('trading_symbol', '')]
                print("\nNIFTY BANK related from Upstox:")
                for n in nb[:3]:
                    print(f"  trading_symbol: {n.get('trading_symbol')}, instrument_key: {n.get('instrument_key')}")
        
        # Download NFO instruments  
        print("\nDownloading NFO instruments from Upstox...")
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NFO.json.gz"
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                    data = json.loads(f.read().decode('utf-8'))
                
                print(f"Total NFO instruments: {len(data)}")
                
                # Find BANKNIFTY FUT
                bn_fut = [d for d in data if 'BANKNIFTY' in d.get('trading_symbol', '') and 'FUT' in d.get('instrument_type', '')][:3]
                print("\nSample BANKNIFTY FUT from Upstox:")
                for f in bn_fut:
                    print(f"  trading_symbol: {f.get('trading_symbol')}, instrument_key: {f.get('instrument_key')}")
                
                # Find BANKNIFTY CE
                bn_ce = [d for d in data if 'BANKNIFTY' in d.get('trading_symbol', '') and d.get('instrument_type') == 'CE'][:3]
                print("\nSample BANKNIFTY CE from Upstox:")
                for o in bn_ce:
                    print(f"  trading_symbol: {o.get('trading_symbol')}, instrument_key: {o.get('instrument_key')}")
                
                # Find NIFTY CE 
                nifty_ce = [d for d in data if d.get('trading_symbol', '').startswith('NIFTY') and d.get('instrument_type') == 'CE'][:3]
                print("\nSample NIFTY CE from Upstox:")
                for o in nifty_ce:
                    print(f"  trading_symbol: {o.get('trading_symbol')}, instrument_key: {o.get('instrument_key')}")
                
                # Check first instrument structure
                if data:
                    print(f"\nFirst instrument keys: {list(data[0].keys())}")
                    print(f"First instrument: {data[0]}")

if __name__ == '__main__':
    asyncio.run(check())
