"""
Simple Calendar Data Seed Script
Standalone script to populate calendar data
"""

import asyncio
from datetime import date, timedelta
from typing import List, Dict, Any

# Basic imports - no app dependencies
import sys
from pathlib import Path

# Setup path
backend_path = str(Path(__file__).parent.parent)
sys.path.insert(0, backend_path)

# Now load environment
from dotenv import load_dotenv
load_dotenv(Path(backend_path) / ".env")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
import os

# Get database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://user:password@localhost:5432/keepgaining"
)

print(f"Using database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")

# Create engine
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# =============================================================================
# NSE Holidays 2025
# =============================================================================

NSE_HOLIDAYS_2025 = [
    {"date": date(2025, 2, 26), "name": "Mahashivratri", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 3, 14), "name": "Holi", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 3, 31), "name": "Id-Ul-Fitr (Ramadan)", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 4, 10), "name": "Shri Mahavir Jayanti", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 4, 14), "name": "Dr. Baba Saheb Ambedkar Jayanti", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 4, 18), "name": "Good Friday", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 5, 1), "name": "Maharashtra Day", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 6, 7), "name": "Bakri Id", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 8, 15), "name": "Independence Day", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 8, 16), "name": "Parsi New Year", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 8, 27), "name": "Ganesh Chaturthi", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 10, 2), "name": "Mahatma Gandhi Jayanti / Dussehra", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 10, 21), "name": "Diwali Laxmi Pujan", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 10, 22), "name": "Diwali Balipratipada", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 11, 5), "name": "Prakash Gurpurab Sri Guru Nanak Dev", "exchange": "NSE", "type": "FULL"},
    {"date": date(2025, 12, 25), "name": "Christmas", "exchange": "NSE", "type": "FULL"},
]

NSE_HOLIDAYS_2026 = [
    {"date": date(2026, 1, 26), "name": "Republic Day", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 2, 16), "name": "Mahashivratri", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 3, 3), "name": "Holi", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 3, 20), "name": "Id-Ul-Fitr", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 4, 2), "name": "Shri Mahavir Jayanti", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 4, 3), "name": "Good Friday", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 4, 14), "name": "Dr. Ambedkar Jayanti", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 5, 1), "name": "Maharashtra Day", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 5, 27), "name": "Bakri Id", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 8, 15), "name": "Independence Day", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 8, 17), "name": "Ganesh Chaturthi", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 10, 2), "name": "Mahatma Gandhi Jayanti", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 10, 19), "name": "Dussehra", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 11, 9), "name": "Diwali", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 11, 10), "name": "Diwali Balipratipada", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 11, 24), "name": "Guru Nanak Jayanti", "exchange": "NSE", "type": "FULL"},
    {"date": date(2026, 12, 25), "name": "Christmas", "exchange": "NSE", "type": "FULL"},
]


# =============================================================================
# F&O Lot Sizes (as of Nov 2025)
# =============================================================================

FO_LOT_SIZES = {
    # Index Options
    "NIFTY": 25,
    "BANKNIFTY": 15,
    "FINNIFTY": 25,
    "MIDCPNIFTY": 50,
    "SENSEX": 10,
    "BANKEX": 15,
    
    # Stock Options (Top F&O stocks)
    "RELIANCE": 250,
    "TCS": 175,
    "HDFCBANK": 550,
    "INFY": 400,
    "ICICIBANK": 700,
    "HINDUNILVR": 300,
    "ITC": 1600,
    "SBIN": 750,
    "BHARTIARTL": 475,
    "KOTAKBANK": 400,
    "LT": 150,
    "AXISBANK": 625,
    "ASIANPAINT": 300,
    "MARUTI": 75,
    "TITAN": 225,
    "SUNPHARMA": 350,
    "BAJFINANCE": 125,
    "HCLTECH": 350,
    "WIPRO": 1500,
    "TATAMOTORS": 575,
    "DRREDDY": 125,
    "POWERGRID": 2700,
    "NTPC": 2250,
    "ONGC": 3175,
    "M&M": 350,
    "JSWSTEEL": 550,
    "TATASTEEL": 5500,
    "ADANIPORTS": 625,
    "COALINDIA": 2100,
    "CIPLA": 650,
    "BRITANNIA": 100,
    "EICHERMOT": 125,
    "APOLLOHOSP": 125,
    "HEROMOTOCO": 150,
    "BAJAJFINSV": 500,
    "HINDALCO": 1075,
    "TATACONSUM": 550,
    "DABUR": 1250,
    "DLF": 825,
    "ACC": 250,
    "INDIGO": 225,
    "ADANIENT": 250,
    "BPCL": 1800,
    "TATAPOWER": 2700,
    "BANKBARODA": 2850,
    "PNB": 6000,
    "ZOMATO": 4600,
    "HAL": 150,
    "BEL": 2500,
    "IRCTC": 500,
    "LICI": 550,
    "TRENT": 175,
    "ZYDUSLIFE": 700,
    "CANBK": 2700,
    "IDFCFIRSTB": 7500,
    "IDEA": 70000,
    "IRFC": 4900,
    "IOC": 4800,
    "PFC": 1300,
    "RECLTD": 1450,
    "BHEL": 3200,
    "SAIL": 4200,
    "GAIL": 4100,
    "HINDPETRO": 1850,
    "NMDC": 3100,
    "NHPC": 7000,
    "INDUSTOWER": 2650,
    "ABB": 125,
    "PAGEIND": 15,
    "PERSISTENT": 100,
    "COFORGE": 100,
    "LTIM": 100,
    "MPHASIS": 175,
    "LTTS": 100,
    "DEEPAKNTR": 200,
    "PIIND": 125,
    "COLPAL": 200,
    "MARICO": 800,
    "TATAELXSI": 75,
    "DIXON": 50,
    "POLYCAB": 100,
    "VOLTAS": 325,
    "CROMPTON": 1350,
    "CUMMINSIND": 225,
    "ASTRAL": 250,
    "APLAPOLLO": 275,
    "BIOCON": 1700,
    "LAURUSLABS": 1050,
    "AUROPHARMA": 450,
    "ALKEM": 100,
    "TORNTPHARM": 100,
    "IPCALAB": 400,
    "GLENMARK": 425,
    "MRF": 5,
    "BALKRISIND": 200,
    "APOLLOTYRE": 1400,
    "CEATLTD": 200,
    "EXIDEIND": 1350,
    "ASHOKLEY": 3000,
    "ESCORTS": 150,
    "BHARATFORG": 550,
    "SUNDARMFIN": 200,
    "CHOLAFIN": 450,
    "MUTHOOTFIN": 350,
    "MANAPPURAM": 3250,
    "SBICARD": 625,
    "HDFCAMC": 175,
    "HDFCLIFE": 800,
    "SBILIFE": 400,
    "JINDALSTEL": 500,
    "TVSMOTOR": 275,
    "OBEROIRLTY": 250,
    "GODREJPROP": 225,
    "SRF": 175,
    "IEX": 2750,
    "MCX": 175,
    "CAMS": 150,
    "CDSL": 400,
    "KPITTECH": 350,
    "FEDERALBNK": 4000,
    "RBLBANK": 3500,
    "BANDHANBNK": 3500,
    "AUBANK": 650,
    "FORTIS": 1250,
    "JUBLFOOD": 800,
    "VBL": 250,
}


def get_last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Get the last occurrence of a weekday in a month."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    
    last_day = next_month - timedelta(days=1)
    days_back = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=days_back)


def generate_expiries_simple(underlying: str, from_date: date, to_date: date) -> List[Dict]:
    """Generate expiry dates for an underlying."""
    expiries = []
    
    # Expiry days (as of 2025): Tuesday for indices, Thursday for stocks
    EXPIRY_DAYS = {
        "NIFTY": {"WEEKLY": 1, "MONTHLY": 1},       # Tuesday
        "BANKNIFTY": {"WEEKLY": 1, "MONTHLY": 1},   # Tuesday  
        "FINNIFTY": {"MONTHLY": 1},                  # Tuesday (monthly only)
        "MIDCPNIFTY": {"WEEKLY": 1, "MONTHLY": 1},  # Tuesday
        "SENSEX": {"WEEKLY": 3, "MONTHLY": 3},      # Thursday (BSE)
        "BANKEX": {"MONTHLY": 3},                    # Thursday (BSE)
    }
    
    expiry_config = EXPIRY_DAYS.get(underlying.upper(), {})
    if not expiry_config:
        return []
    
    current = from_date
    seen_dates = set()
    
    while current <= to_date:
        # Weekly expiry
        if "WEEKLY" in expiry_config:
            weekly_day = expiry_config["WEEKLY"]
            days_until_expiry = (weekly_day - current.weekday()) % 7
            expiry_date = current + timedelta(days=days_until_expiry)
            
            if from_date <= expiry_date <= to_date and expiry_date not in seen_dates:
                seen_dates.add(expiry_date)
                expiries.append({
                    "underlying": underlying.upper(),
                    "expiry_date": expiry_date,
                    "expiry_type": "WEEKLY",
                    "segment": "BFO" if underlying.upper() in ["SENSEX", "BANKEX"] else "NFO",
                })
        
        # Monthly expiry (last occurrence of expiry day in month)
        if "MONTHLY" in expiry_config and current.day <= 7:
            monthly_day = expiry_config["MONTHLY"]
            last_day = get_last_weekday_of_month(current.year, current.month, monthly_day)
            
            if from_date <= last_day <= to_date and last_day not in seen_dates:
                seen_dates.add(last_day)
                expiries.append({
                    "underlying": underlying.upper(),
                    "expiry_date": last_day,
                    "expiry_type": "MONTHLY",
                    "segment": "BFO" if underlying.upper() in ["SENSEX", "BANKEX"] else "NFO",
                })
        
        current += timedelta(days=7)
    
    return expiries


async def seed_holidays(session: AsyncSession):
    """Seed holiday calendar."""
    print("Seeding holiday calendar...")
    
    all_holidays = NSE_HOLIDAYS_2025 + NSE_HOLIDAYS_2026
    
    # Add BSE holidays (same as NSE for simplicity)
    bse_holidays = [{"date": h["date"], "name": h["name"], "exchange": "BSE", "type": h["type"]} for h in all_holidays]
    all_holidays.extend(bse_holidays)
    
    count = 0
    for h in all_holidays:
        try:
            await session.execute(
                text("""
                    INSERT INTO holiday_calendar (date, exchange, holiday_name, holiday_type)
                    VALUES (:date, :exchange, :name, :type)
                    ON CONFLICT (date, exchange) DO UPDATE SET
                        holiday_name = EXCLUDED.holiday_name,
                        holiday_type = EXCLUDED.holiday_type
                """),
                {"date": h["date"], "exchange": h["exchange"], "name": h["name"], "type": h["type"]}
            )
            count += 1
        except Exception as e:
            print(f"  Error adding holiday {h['name']}: {e}")
    
    await session.commit()
    print(f"✓ Added {count} holidays")
    return count


async def seed_expiries(session: AsyncSession):
    """Generate and seed expiry calendar."""
    print("Seeding expiry calendar...")
    
    indices = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]
    from_date = date(2025, 1, 1)
    to_date = date(2026, 12, 31)
    
    total_count = 0
    
    for underlying in indices:
        expiries = generate_expiries_simple(underlying, from_date, to_date)
        
        for e in expiries:
            try:
                await session.execute(
                    text("""
                        INSERT INTO expiry_calendar (underlying, expiry_date, expiry_type, segment)
                        VALUES (:underlying, :expiry_date, :expiry_type, :segment)
                        ON CONFLICT (underlying, expiry_date, segment) DO NOTHING
                    """),
                    e
                )
                total_count += 1
            except Exception as ex:
                print(f"  Error adding expiry: {ex}")
        
        print(f"  Added {len(expiries)} expiries for {underlying}")
    
    await session.commit()
    print(f"✓ Added {total_count} total expiries")
    return total_count


async def seed_lot_sizes(session: AsyncSession):
    """Seed lot sizes."""
    print("Seeding lot sizes...")
    
    effective_date = date(2025, 1, 1)
    count = 0
    
    for underlying, lot_size in FO_LOT_SIZES.items():
        segment = "BFO" if underlying in ["SENSEX", "BANKEX"] else "NFO"
        
        try:
            await session.execute(
                text("""
                    INSERT INTO lot_size_history (underlying, lot_size, effective_date, segment)
                    VALUES (:underlying, :lot_size, :effective_date, :segment)
                """),
                {"underlying": underlying, "lot_size": lot_size, "effective_date": effective_date, "segment": segment}
            )
            count += 1
        except Exception as ex:
            print(f"  Error adding lot size for {underlying}: {ex}")
    
    await session.commit()
    print(f"✓ Added {count} lot sizes")
    return count


async def main():
    """Run all seeding operations."""
    print("=" * 60)
    print("Starting Calendar Data Seed")
    print("=" * 60)
    
    try:
        async with AsyncSessionLocal() as session:
            # Test connection
            result = await session.execute(text("SELECT 1"))
            print("✓ Database connected")
            
            await seed_holidays(session)
            await seed_expiries(session)
            await seed_lot_sizes(session)
        
        print("=" * 60)
        print("✓ Calendar data seeding completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"Seeding failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
