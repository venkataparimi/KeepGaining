"""
Check IEX stock data availability in the database
"""
import asyncio
import asyncpg

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

async def check_iex_data():
    pool = await asyncpg.create_pool(DB_URL)
    
    async with pool.acquire() as conn:
        # Check if IEX is in instrument_master
        print("=== IEX in Instrument Master ===")
        instruments = await conn.fetch("""
            SELECT instrument_id, trading_symbol, instrument_type, is_active
            FROM instrument_master 
            WHERE trading_symbol LIKE '%IEX%'
        """)
        
        if not instruments:
            print("❌ IEX not found in instrument_master")
        else:
            for inst in instruments:
                print(f"  {inst['trading_symbol']} | Type: {inst['instrument_type']} | Active: {inst['is_active']}")
                
                # Check candle data for this instrument
                inst_id = inst['instrument_id']
                candle_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_candles,
                        MIN(timestamp) as earliest,
                        MAX(timestamp) as latest
                    FROM candle_data
                    WHERE instrument_id = $1
                """, inst_id)
                
                if candle_stats and candle_stats['total_candles'] > 0:
                    print(f"    📊 Candles: {candle_stats['total_candles']:,}")
                    print(f"    📅 From: {candle_stats['earliest']}")
                    print(f"    📅 To:   {candle_stats['latest']}")
                else:
                    print(f"    ⚠️ No candle data found")
    
    await pool.close()

if __name__ == "__main__":
    asyncio.run(check_iex_data())
