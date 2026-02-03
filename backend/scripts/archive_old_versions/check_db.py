"""Check database structure"""
import asyncio
from sqlalchemy import text
from app.db.session import get_db_context

async def check_tables():
    async with get_db_context() as db:
        # Sample instruments - use correct column names
        result = await db.execute(text("SELECT instrument_id, trading_symbol, exchange, instrument_type FROM instrument_master WHERE instrument_type = 'EQ' LIMIT 10"))
        rows = result.fetchall()
        print(f"Sample EQUITY instruments:")
        for r in rows:
            print(f"  {r}")
        
        # Check indicator_data
        print(f"\n---")
        result = await db.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'indicator_data' ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        print(f"indicator_data columns: {cols}")
        
        result = await db.execute(text("SELECT COUNT(*) FROM indicator_data"))
        cnt = result.scalar()
        print(f"indicator_data count: {cnt:,}")
        
        # Join candles with instruments to see what we have
        print(f"\n--- Candle Data Summary ---")
        result = await db.execute(text("""
            SELECT im.instrument_type, COUNT(*) as cnt
            FROM candle_data cd
            JOIN instrument_master im ON cd.instrument_id = im.instrument_id
            GROUP BY im.instrument_type
            ORDER BY cnt DESC
        """))
        for r in result.fetchall():
            print(f"  {r[0]}: {r[1]:,}")

asyncio.run(check_tables())
