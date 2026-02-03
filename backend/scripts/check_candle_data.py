"""
Check what candle data exists in the database
"""
import asyncio
import asyncpg

async def check_candle_data():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    print("=" * 80)
    print("🔍 CHECKING CANDLE DATA AVAILABILITY")
    print("=" * 80)
    print()
    
    # Check what tables exist
    print("1. Checking available tables...")
    tables = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    
    print(f"Found {len(tables)} tables:")
    for t in tables:
        print(f"   - {t['table_name']}")
    
    print()
    
    # Check for candle-related tables
    candle_tables = [t['table_name'] for t in tables if 'candle' in t['table_name'].lower()]
    
    if candle_tables:
        print(f"✅ Found {len(candle_tables)} candle tables:")
        for ct in candle_tables:
            print(f"   - {ct}")
            
            # Check row count
            count_query = f"SELECT COUNT(*) as count FROM {ct}"
            result = await conn.fetchrow(count_query)
            print(f"     Rows: {result['count']:,}")
            
            if result['count'] > 0:
                # Check date range
                date_query = f"SELECT MIN(timestamp) as min_date, MAX(timestamp) as max_date FROM {ct}"
                dates = await conn.fetchrow(date_query)
                print(f"     Date range: {dates['min_date']} to {dates['max_date']}")
    else:
        print("❌ NO CANDLE TABLES FOUND")
        print()
        print("This means we need to backfill ALL candle data!")
    
    print()
    
    # Check instrument_master
    print("2. Checking instrument_master...")
    inst_count = await conn.fetchrow("SELECT COUNT(*) as count FROM instrument_master")
    print(f"   Total instruments: {inst_count['count']:,}")
    
    # Check HINDZINC specifically
    hindzinc = await conn.fetch("""
        SELECT instrument_type, COUNT(*) as count
        FROM instrument_master
        WHERE underlying = 'HINDZINC'
        GROUP BY instrument_type
    """)
    
    if hindzinc:
        print(f"\n   HINDZINC instruments:")
        for h in hindzinc:
            print(f"     {h['instrument_type']}: {h['count']}")
    
    await conn.close()
    
    print()
    print("=" * 80)
    print("📊 CONCLUSION")
    print("=" * 80)
    
    if not candle_tables:
        print("\n❌ CANDLE DATA IS COMPLETELY MISSING")
        print("\nWe need to backfill:")
        print("  1. Equity candles (spot prices)")
        print("  2. F&O candles (option prices)")
        print("\nThis will enable:")
        print("  ✓ Strategy backtesting")
        print("  ✓ Pattern analysis")
        print("  ✓ Historical trade reconstruction")
    else:
        print("\n✅ CANDLE TABLES EXIST")
        print("\nNext: Check if HINDZINC data is available")

if __name__ == "__main__":
    asyncio.run(check_candle_data())
