"""
Check if we have HINDZINC options (CE/PE) candle data
"""
import asyncio
import asyncpg

async def check_hindzinc_options():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    print("=" * 80)
    print("🔍 CHECKING HINDZINC OPTIONS DATA")
    print("=" * 80)
    print()
    
    # Check for CE/PE instruments
    print("1. Checking instrument_master for HINDZINC options...")
    options_query = """
        SELECT instrument_type, COUNT(*) as count
        FROM instrument_master
        WHERE underlying = 'HINDZINC'
        GROUP BY instrument_type
        ORDER BY instrument_type
    """
    
    instruments = await conn.fetch(options_query)
    
    if instruments:
        print("✅ HINDZINC instruments in master:")
        for inst in instruments:
            print(f"   {inst['instrument_type']}: {inst['count']} instruments")
    
    print()
    
    # Check for CE/PE candle data
    print("2. Checking candle_data for HINDZINC options...")
    candle_query = """
        SELECT 
            im.instrument_type,
            COUNT(*) as total_candles,
            COUNT(DISTINCT DATE(cd.timestamp)) as trading_days,
            MIN(cd.timestamp) as first_date,
            MAX(cd.timestamp) as last_date
        FROM candle_data cd
        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
        WHERE im.underlying = 'HINDZINC'
        AND im.instrument_type IN ('CE', 'PE')
        GROUP BY im.instrument_type
    """
    
    candle_data = await conn.fetch(candle_query)
    
    if candle_data:
        print("✅ HINDZINC OPTIONS CANDLE DATA EXISTS!")
        print()
        for data in candle_data:
            print(f"   {data['instrument_type']}:")
            print(f"      Total Candles: {data['total_candles']:,}")
            print(f"      Trading Days: {data['trading_days']}")
            print(f"      Date Range: {data['first_date']} to {data['last_date']}")
            print()
    else:
        print("❌ NO OPTIONS CANDLE DATA FOUND")
        print()
    
    # Check specifically for 500 CE on Dec 1
    print("3. Checking for 500 CE on December 1, 2025...")
    dec1_query = """
        SELECT 
            im.trading_symbol,
            im.instrument_id,
            COUNT(*) as candles
        FROM candle_data cd
        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
        WHERE im.underlying = 'HINDZINC'
        AND im.instrument_type = 'CE'
        AND im.trading_symbol LIKE '%500CE%'
        AND DATE(cd.timestamp) = '2025-12-01'
        GROUP BY im.trading_symbol, im.instrument_id
        ORDER BY im.trading_symbol
    """
    
    dec1_data = await conn.fetch(dec1_query)
    
    if dec1_data:
        print("✅ FOUND 500 CE DATA FOR DEC 1!")
        print()
        for row in dec1_data:
            print(f"   {row['trading_symbol']}")
            print(f"      Instrument ID: {row['instrument_id']}")
            print(f"      Candles: {row['candles']}")
            
            # Get actual price data
            price_query = """
                SELECT 
                    timestamp,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM candle_data
                WHERE instrument_id = $1
                AND DATE(timestamp) = '2025-12-01'
                ORDER BY timestamp
                LIMIT 5
            """
            
            prices = await conn.fetch(price_query, row['instrument_id'])
            
            if prices:
                print(f"\n      Sample prices:")
                for p in prices:
                    print(f"         {p['timestamp']}: Open={p['open']}, Close={p['close']}, Vol={p['volume']}")
            
            print()
    else:
        print("❌ NO 500 CE DATA FOR DEC 1")
        print()
        
        # Check what CE options we have
        print("   Checking what CE options exist...")
        all_ce_query = """
            SELECT DISTINCT im.trading_symbol
            FROM instrument_master im
            WHERE im.underlying = 'HINDZINC'
            AND im.instrument_type = 'CE'
            ORDER BY im.trading_symbol
            LIMIT 20
        """
        
        all_ce = await conn.fetch(all_ce_query)
        if all_ce:
            print(f"   Found {len(all_ce)} CE options:")
            for ce in all_ce:
                print(f"      {ce['trading_symbol']}")
    
    await conn.close()
    
    print()
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    
    if candle_data:
        print("\n✅ WE HAVE OPTIONS DATA!")
        print("\nThis means we can:")
        print("  ✓ Analyze the exact 500 CE trade")
        print("  ✓ See actual premium movement")
        print("  ✓ Reverse-engineer the strategy precisely")
        print("  ✓ Backtest on real option data")
    else:
        print("\n❌ NO OPTIONS DATA")
        print("\nWe only have FUTURES data")
        print("Need to backfill options candle data")

if __name__ == "__main__":
    asyncio.run(check_hindzinc_options())
