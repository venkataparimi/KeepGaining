import asyncio
import asyncpg

async def check_policybazaar():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    # Check for Policybazaar stock
    result = await conn.fetch("""
        SELECT trading_symbol, instrument_type, is_active
        FROM instrument_master 
        WHERE trading_symbol LIKE '%POLICY%' 
           OR trading_symbol LIKE '%PBFIN%'
           OR trading_symbol = 'PB'
        ORDER BY trading_symbol
    """)
    
    if result:
        print("Found Policybazaar stocks:")
        for r in result:
            print(f"  {r['trading_symbol']:<20} {r['instrument_type']:<10} Active: {r['is_active']}")
    else:
        print("Policybazaar stock not found in database")
        print("\nSearching for similar symbols...")
        
        # Search for PB-related stocks
        result2 = await conn.fetch("""
            SELECT trading_symbol, instrument_type 
            FROM instrument_master 
            WHERE trading_symbol LIKE 'PB%'
            AND instrument_type = 'EQUITY'
            ORDER BY trading_symbol
            LIMIT 10
        """)
        
        if result2:
            print("\nPB-related stocks:")
            for r in result2:
                print(f"  {r['trading_symbol']:<20} {r['instrument_type']}")
    
    await conn.close()

asyncio.run(check_policybazaar())
