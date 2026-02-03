"""Find missing stocks in Upstox."""
import aiohttp
import asyncio
import gzip
import json

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get("https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz") as r:
            d = gzip.decompress(await r.read())
            data = json.loads(d)
            
            # Find EQ type instruments
            equities = [i for i in data if i.get('instrument_type') == 'EQ']
            print(f"Total EQ instruments: {len(equities)}")
            
            # Search terms for each missing stock
            searches = {
                "GMRINFRA": ["GMR", "GMRAIR", "GMRP"],
                "LARSENTOUB": ["LARSEN", "LT", "L&T"],
                "NATCOPHARMA": ["NATCO"],
                "PEL": ["PIRAMAL", "PEL"],
                "PVR": ["PVR", "INOX", "PVRINOX"],
                "TATAMOTORS": ["TATAMOTORS", "TATAMTR", "TATAMOTOR"],
                "ZOMATO": ["ZOMATO"],
            }
            
            for stock, terms in searches.items():
                print(f"\n{stock}:")
                found = False
                for term in terms:
                    matches = [i for i in equities if term.upper() == i.get('trading_symbol', '').upper()]
                    if matches:
                        for m in matches:
                            print(f"  EXACT: {m.get('trading_symbol')} -> {m.get('instrument_key')} ({m.get('name')})")
                            found = True
                    else:
                        # Partial match
                        partial = [i for i in equities if term.upper() in i.get('trading_symbol', '').upper() or term.upper() in i.get('name', '').upper()]
                        for m in partial[:3]:
                            print(f"  PARTIAL ({term}): {m.get('trading_symbol')} -> {m.get('instrument_key')} ({m.get('name')})")
                            found = True
                if not found:
                    print(f"  NOT FOUND")

asyncio.run(main())
