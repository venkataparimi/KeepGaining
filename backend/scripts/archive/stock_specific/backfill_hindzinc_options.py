"""
Backfill HINDZINC Options Data
Focus on Dec 2025 to analyze the trade
"""
import asyncio
import asyncpg
from datetime import datetime, date, timedelta
import sys
sys.path.append('..')

async def backfill_hindzinc_options():
    """Backfill HINDZINC options for December 2025"""
    
    print("=" * 80)
    print("📥 BACKFILLING HINDZINC OPTIONS DATA")
    print("=" * 80)
    print()
    
    # Connect to database
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Check what we need to backfill
    print("1. Checking HINDZINC options in instrument_master...")
    
    options_query = """
        SELECT 
            instrument_id,
            trading_symbol,
            instrument_type,
            strike,
            expiry
        FROM instrument_master
        WHERE underlying = 'HINDZINC'
        AND instrument_type IN ('CE', 'PE')
        AND expiry >= '2025-12-01'
        AND expiry <= '2025-12-31'
        ORDER BY expiry, strike, instrument_type
    """
    
    options = await conn.fetch(options_query)
    
    if not options:
        print("❌ No HINDZINC options found in instrument_master for Dec 2025")
        print("\nThis means we need to:")
        print("  1. First update instrument_master with Dec 2025 options")
        print("  2. Then backfill the candle data")
        print()
        print("Let me check if we have ANY HINDZINC options...")
        
        all_options = await conn.fetch("""
            SELECT 
                instrument_type,
                COUNT(*) as count,
                MIN(expiry) as min_expiry,
                MAX(expiry) as max_expiry
            FROM instrument_master
            WHERE underlying = 'HINDZINC'
            AND instrument_type IN ('CE', 'PE')
            GROUP BY instrument_type
        """)
        
        if all_options:
            print("\n✅ Found HINDZINC options:")
            for opt in all_options:
                print(f"   {opt['instrument_type']}: {opt['count']} contracts")
                print(f"      Expiry range: {opt['min_expiry']} to {opt['max_expiry']}")
        else:
            print("\n❌ NO HINDZINC OPTIONS AT ALL in instrument_master")
            print("\nNeed to run instrument master update first!")
        
        await conn.close()
        return
    
    print(f"✅ Found {len(options)} HINDZINC options for Dec 2025")
    print()
    
    # Show sample
    print("Sample options:")
    for opt in options[:10]:
        print(f"   {opt['trading_symbol']} (Strike: {opt['strike']}, Expiry: {opt['expiry']})")
    
    if len(options) > 10:
        print(f"   ... and {len(options) - 10} more")
    
    print()
    
    # Find 500 CE specifically
    ce_500 = [o for o in options if o['instrument_type'] == 'CE' and o['strike'] == 500]
    
    if ce_500:
        print(f"✅ Found {len(ce_500)} x 500 CE options:")
        for ce in ce_500:
            print(f"   {ce['trading_symbol']} (ID: {ce['instrument_id']}, Expiry: {ce['expiry']})")
    else:
        print("❌ No 500 CE found")
    
    print()
    
    await conn.close()
    
    print("=" * 80)
    print("📊 NEXT STEPS")
    print("=" * 80)
    print()
    
    if not options:
        print("STEP 1: Update instrument_master")
        print("  Run: python backend/scripts/update_instrument_master.py")
        print()
        print("STEP 2: Backfill candle data")
        print("  Run: python backend/scripts/backfill_hindzinc_options.py")
    else:
        print("✅ Instrument master is ready")
        print()
        print("STEP 2: Backfill candle data")
        print("  We need to fetch historical data from your data provider")
        print("  for these instruments")
        print()
        print("Options:")
        print("  A. Use existing backfill_all_data.py script")
        print("  B. Create specific HINDZINC options backfill")
        print("  C. Use data provider API directly")

if __name__ == "__main__":
    asyncio.run(backfill_hindzinc_options())
