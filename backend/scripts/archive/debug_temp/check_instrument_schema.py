"""
Check instrument_master schema and find HINDZINC options
"""
import asyncio
import asyncpg

async def check_schema():
    conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    print("Checking instrument_master schema...")
    
    # Get column names
    columns = await conn.fetch("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'instrument_master'
        ORDER BY ordinal_position
    """)
    
    print("\nColumns in instrument_master:")
    for col in columns:
        print(f"   {col['column_name']}: {col['data_type']}")
    
    # Check HINDZINC data
    print("\n\nChecking HINDZINC instruments...")
    hindzinc = await conn.fetch("""
        SELECT *
        FROM instrument_master
        WHERE underlying = 'HINDZINC'
        LIMIT 5
    """)
    
    if hindzinc:
        print(f"\nFound {len(hindzinc)} HINDZINC instruments (showing first 5):")
        for inst in hindzinc:
            print(f"\n   {dict(inst)}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_schema())
