import asyncio
import asyncpg

async def check():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # All F&O stocks (from options universe)
    all_fno = await pool.fetch("""
        SELECT DISTINCT underlying 
        FROM instrument_master 
        WHERE instrument_type IN ('CE', 'PE')
          AND underlying NOT IN ('NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY')
        ORDER BY underlying
    """)
    
    # Stocks we're currently scanning (have equity data)
    scanned = await pool.fetch("""
        SELECT DISTINCT im.trading_symbol
        FROM instrument_master im
        WHERE im.instrument_type = 'EQUITY'
          AND im.segment = 'EQ'
          AND EXISTS (
              SELECT 1 FROM instrument_master im2
              WHERE im2.underlying = im.trading_symbol
                AND im2.instrument_type IN ('CE', 'PE')
          )
        ORDER BY im.trading_symbol
    """)
    
    all_fno_set = {r['underlying'] for r in all_fno}
    scanned_set = {r['trading_symbol'] for r in scanned}
    
    missing = all_fno_set - scanned_set
    
    print(f"Total F&O Universe: {len(all_fno_set)}")
    print(f"Currently Scanned: {len(scanned_set)}")
    print(f"Missing: {len(missing)}")
    print(f"\nMissing stocks: {', '.join(sorted(missing)[:20])}...")
    
    await pool.close()

asyncio.run(check())
