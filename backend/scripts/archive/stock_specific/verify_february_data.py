"""
Verify February data completeness across all stocks
Checks for gaps in February data for all equity instruments
"""
import asyncio
import asyncpg
from datetime import datetime

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

async def check_february_data():
    """Check February data completeness for all equity stocks"""
    pool = await asyncpg.create_pool(DB_URL)
    
    # Check Feb 2022, 2023, 2024, 2025
    years = [2022, 2023, 2024, 2025]
    
    async with pool.acquire() as conn:
        print("=" * 80)
        print("FEBRUARY DATA COMPLETENESS CHECK")
        print("=" * 80)
        
        for year in years:
            print(f"\n📅 February {year}")
            print("-" * 80)
            
            # Get all equity instruments
            instruments = await conn.fetch("""
                SELECT instrument_id, trading_symbol
                FROM instrument_master
                WHERE instrument_type = 'EQUITY'
                ORDER BY trading_symbol
            """)
            
            total_stocks = len(instruments)
            stocks_with_feb_data = 0
            stocks_missing_feb_data = []
            
            for inst in instruments:
                inst_id = inst['instrument_id']
                symbol = inst['trading_symbol']
                
                # Check if there's any data in February of this year
                feb_data = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as candle_count,
                        MIN(timestamp) as earliest,
                        MAX(timestamp) as latest
                    FROM candle_data
                    WHERE instrument_id = $1
                    AND EXTRACT(YEAR FROM timestamp) = $2
                    AND EXTRACT(MONTH FROM timestamp) = 2
                """, inst_id, year)
                
                if feb_data['candle_count'] > 0:
                    stocks_with_feb_data += 1
                else:
                    # Check if stock has any data at all
                    any_data = await conn.fetchval("""
                        SELECT COUNT(*) FROM candle_data WHERE instrument_id = $1
                    """, inst_id)
                    
                    if any_data > 0:
                        stocks_missing_feb_data.append(symbol)
            
            print(f"Total stocks: {total_stocks}")
            print(f"Stocks with Feb {year} data: {stocks_with_feb_data}")
            print(f"Stocks missing Feb {year} data: {len(stocks_missing_feb_data)}")
            
            if stocks_missing_feb_data and len(stocks_missing_feb_data) <= 20:
                print(f"Missing: {', '.join(stocks_missing_feb_data)}")
            
            # Check for gaps in February (days with no data)
            feb_gaps = await conn.fetch("""
                WITH feb_dates AS (
                    SELECT generate_series(
                        $1::date,
                        $2::date,
                        '1 day'::interval
                    )::date as trading_date
                ),
                trading_days AS (
                    SELECT DISTINCT DATE(timestamp) as trading_date
                    FROM candle_data cd
                    JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                    WHERE im.instrument_type = 'EQUITY'
                    AND EXTRACT(YEAR FROM cd.timestamp) = $3
                    AND EXTRACT(MONTH FROM cd.timestamp) = 2
                )
                SELECT fd.trading_date
                FROM feb_dates fd
                LEFT JOIN trading_days td ON fd.trading_date = td.trading_date
                WHERE td.trading_date IS NULL
                AND EXTRACT(DOW FROM fd.trading_date) NOT IN (0, 6)  -- Exclude weekends
                ORDER BY fd.trading_date
            """, f"{year}-02-01", f"{year}-02-29" if year % 4 == 0 else f"{year}-02-28", year)
            
            if feb_gaps:
                gap_dates = [str(row['trading_date']) for row in feb_gaps]
                print(f"⚠️  Days with no data: {', '.join(gap_dates)}")
            else:
                print(f"✅ No gaps detected in February {year}")
    
    await pool.close()

if __name__ == "__main__":
    asyncio.run(check_february_data())
