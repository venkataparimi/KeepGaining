#!/usr/bin/env python3
"""
Quick script to check migration progress.
Run this periodically to see how many rows have been migrated.
"""

import asyncio
import asyncpg

DB_URL = "postgresql://user:password@localhost:5432/keepgaining"

async def main():
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # Check if table exists
        exists = await conn.fetchval("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_name = 'candle_data_new'
        """)
        
        if not exists:
            print("❌ candle_data_new does not exist yet")
            return
        
        # Get counts
        result = await conn.fetchrow("""
            SELECT 
                (SELECT COUNT(*) FROM candle_data) as original,
                (SELECT COUNT(*) FROM candle_data_new) as migrated
        """)
        
        original = result['original']
        migrated = result['migrated']
        
        # Get date ranges
        dates = await conn.fetchrow("""
            SELECT 
                MIN(timestamp)::date as earliest,
                MAX(timestamp)::date as latest
            FROM candle_data_new
        """)
        
        percent = (migrated / original * 100) if original > 0 else 0
        remaining = original - migrated
        
        print(f"\n{'='*70}")
        print(f"Migration Progress")
        print(f"{'='*70}")
        print(f"Original table:  {original:>15,} rows")
        print(f"Migrated:        {migrated:>15,} rows ({percent:.1f}%)")
        print(f"Remaining:       {remaining:>15,} rows")
        
        if dates and dates['earliest']:
            print(f"\nDate range migrated: {dates['earliest']} to {dates['latest']}")
        
        if migrated == original:
            print("\n✅ MIGRATION COMPLETE!")
        elif migrated > 0:
            print(f"\n⏳ Migration in progress...")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
