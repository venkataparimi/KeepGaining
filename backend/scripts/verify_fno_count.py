import asyncio
import asyncpg

async def check():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Check all available methods to count F&O stocks
    
    # Method 1: From option_master
    om_count = await pool.fetchval("""
        SELECT COUNT(DISTINCT symbol) 
        FROM option_master
    """)
    print(f"Option Master - Distinct Symbols: {om_count}")
    
    # Method 2: From instrument_master (underlying)
    im_underlying = await pool.fetchval("""
        SELECT COUNT(DISTINCT underlying) 
        FROM instrument_master 
        WHERE instrument_type IN ('CE', 'PE')
          AND underlying IS NOT NULL
          AND underlying != ''
    """)
    print(f"Instrument Master - Distinct Underlying: {im_underlying}")
    
    # Method 3: From instrument_master (equity with options)
    equity_with_options = await pool.fetchval("""
        SELECT COUNT(DISTINCT trading_symbol) 
        FROM instrument_master 
        WHERE instrument_type = 'EQUITY'
          AND EXISTS (
              SELECT 1 FROM option_master om 
              WHERE om.symbol = trading_symbol
          )
    """)
    print(f"Equity stocks with options in option_master: {equity_with_options}")
    
    # Method 4: Check what generate_strategy_trades.py uses
    original_query = await pool.fetchval("""
        SELECT COUNT(DISTINCT im.trading_symbol)
        FROM instrument_master im
        WHERE im.instrument_type = 'EQUITY'
          AND im.segment = 'EQ'
          AND EXISTS (
              SELECT 1 FROM instrument_master im2
              WHERE im2.underlying = im.trading_symbol
                AND im2.instrument_type IN ('CE', 'PE')
          )
    """)
    print(f"Original strategy query (with candle data check): {original_query}")
    
    # Method 5: Without candle data requirement
    without_candle_check = await pool.fetchval("""
        SELECT COUNT(DISTINCT im.trading_symbol)
        FROM instrument_master im
        WHERE im.instrument_type = 'EQUITY'
          AND im.segment = 'EQ'
          AND EXISTS (
              SELECT 1 FROM instrument_master im2
              WHERE im2.underlying = im.trading_symbol
                AND im2.instrument_type IN ('CE', 'PE')
          )
    """)
    print(f"Equity with option universe (no candle filter): {without_candle_check}")
    
    # Get the full list from option_master
    symbols = await pool.fetch("""
        SELECT DISTINCT symbol FROM option_master ORDER BY symbol
    """)
    print(f"\nTotal unique stocks in option_master: {len(symbols)}")
    print(f"First 20: {', '.join([s['symbol'] for s in symbols[:20]])}")
    
    await pool.close()

asyncio.run(check())
