"""Explore F&O instruments from Upstox."""
import asyncio
import aiohttp
import json
import gzip
from datetime import datetime

async def get_fo_instruments():
    url = 'https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = gzip.decompress(await resp.read())
            instruments = json.loads(data)
            
            # NSE_FO instruments
            fo = [i for i in instruments if i.get('segment') == 'NSE_FO']
            
            # Group by type
            types = {}
            for i in fo:
                t = i.get('instrument_type', 'UNKNOWN')
                types[t] = types.get(t, 0) + 1
            print('NSE_FO by type:')
            for t, c in sorted(types.items()):
                print(f'  {t}: {c}')
            
            # Futures only
            futures = [i for i in fo if i.get('instrument_type') == 'FUT']
            print(f'\nTotal Futures: {len(futures)}')
            
            # NIFTY futures
            nifty_fut = [i for i in futures if i.get('underlying_symbol') == 'NIFTY']
            print(f'\nNIFTY Futures ({len(nifty_fut)}):')
            for f in sorted(nifty_fut, key=lambda x: x.get('expiry', 0)):
                expiry_ts = f.get('expiry', 0) / 1000
                expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%Y-%m-%d')
                key = f.get('instrument_key')
                sym = f.get('trading_symbol')
                print(f"  {sym}: {expiry_date} - Key: {key}")
            
            # BANKNIFTY futures
            bn_fut = [i for i in futures if i.get('underlying_symbol') == 'BANKNIFTY']
            print(f'\nBANKNIFTY Futures ({len(bn_fut)}):')
            for f in sorted(bn_fut, key=lambda x: x.get('expiry', 0)):
                expiry_ts = f.get('expiry', 0) / 1000
                expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%Y-%m-%d')
                print(f"  {f.get('trading_symbol')}: {expiry_date}")
            
            # All unique underlyings for futures
            underlyings = set(f.get('underlying_symbol') for f in futures)
            print(f'\nUnique underlyings ({len(underlyings)}):')
            for u in sorted(underlyings)[:20]:
                count = len([f for f in futures if f.get('underlying_symbol') == u])
                print(f"  {u}: {count} contracts")
            
            return fo

if __name__ == "__main__":
    asyncio.run(get_fo_instruments())
