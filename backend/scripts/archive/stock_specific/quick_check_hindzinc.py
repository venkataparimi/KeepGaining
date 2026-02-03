"""
Quick check for HINDZINC candle data
"""
import asyncio
import asyncpg

async def check_hindzinc():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    print("🔍 Checking HINDZINC data in candle_data table...")
    print()
    
    # Check if HINDZINC data exists
    query = """
        SELECT 
            COUNT(*) as total_candles,
            MIN(timestamp) as first_date,
            MAX(timestamp) as last_date,
            COUNT(DISTINCT DATE(timestamp)) as trading_days
        FROM candle_data cd
        JOIN instrument_master im ON cd.instrument_id = im.instrument_id
        WHERE im.underlying = 'HINDZINC'
    """
    
    result = await conn.fetchrow(query)
    
    if result['total_candles'] > 0:
        print("✅ HINDZINC DATA EXISTS!")
        print(f"   Total Candles: {result['total_candles']:,}")
        print(f"   Date Range: {result['first_date']} to {result['last_date']}")
        print(f"   Trading Days: {result['trading_days']}")
        print()
        
        # Check Dec 1, 2025 specifically
        dec1_query = """
            SELECT 
                im.trading_symbol,
                COUNT(*) as candles
            FROM candle_data cd
            JOIN instrument_master im ON cd.instrument_id = im.instrument_id
            WHERE im.underlying = 'HINDZINC'
            AND DATE(cd.timestamp) = '2025-12-01'
            GROUP BY im.trading_symbol
            ORDER BY im.trading_symbol
        """
        
        dec1_data = await conn.fetch(dec1_query)
        
        if dec1_data:
            print("✅ December 1, 2025 data available:")
            for row in dec1_data[:10]:
                print(f"   {row['trading_symbol']}: {row['candles']} candles")
            
            if len(dec1_data) > 10:
                print(f"   ... and {len(dec1_data) - 10} more instruments")
        else:
            print("❌ No data for December 1, 2025")
    else:
        print("❌ NO HINDZINC DATA FOUND")
        print("\nNeed to backfill HINDZINC candle data")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_hindzinc())
