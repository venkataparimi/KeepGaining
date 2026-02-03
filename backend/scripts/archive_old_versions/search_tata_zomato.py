"""Search TATA and ZOMATO."""
import aiohttp, asyncio, gzip, json

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get('https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz') as r:
            d = gzip.decompress(await r.read())
            data = json.loads(d)
            equities = [i for i in data if i.get('instrument_type') == 'EQ']
            
            # Search for TATA
            tata = [i for i in equities if 'TATA' in i.get('trading_symbol', '').upper()]
            print('TATA stocks:')
            for t in tata:
                print(f"  {t['trading_symbol']} -> {t['instrument_key']}")
            
            # Search for ZOMATO
            zom = [i for i in equities if 'ZOM' in i.get('name', '').upper() or 'ZOM' in i.get('trading_symbol', '').upper()]
            print('\nZOMATO:')
            for z in zom:
                print(f"  {z['trading_symbol']} -> {z['instrument_key']} ({z['name']})")
            
            # If not found, try broader search in name
            if not zom:
                print("Searching in all data (not just EQ)...")
                all_zom = [i for i in data if 'ZOMATO' in i.get('name', '').upper() or 'ZOMATO' in i.get('trading_symbol', '').upper()]
                for z in all_zom[:5]:
                    print(f"  {z['trading_symbol']} -> {z['instrument_key']} ({z.get('instrument_type')})")

asyncio.run(main())
