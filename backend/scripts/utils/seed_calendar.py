"""
Calendar Data Seed Script
KeepGaining Trading Platform

Populates:
- NSE/BSE holidays for 2025-2026
- Expiry calendar for major indices
- Lot sizes for F&O stocks
"""

import asyncio
from datetime import date, timedelta
from typing import List, Dict, Any

from loguru import logger

# Add parent to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import directly, avoiding circular imports
from app.db.session import get_db_context
from app.db.models.calendar import (
    ExpiryCalendar,
    HolidayCalendar,
    LotSizeHistory,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert


# =============================================================================
# NSE Holidays 2025
# Source: NSE Circular
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

# NSE Holidays 2026 (Tentative - to be updated when NSE publishes)
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
# Source: NSE Circulars
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
    "ULTRACEMCO": 50,
    "NESTLEIND": 25,
    "TECHM": 400,
    "INDUSINDBK": 400,
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
    "GRASIM": 325,
    "CIPLA": 650,
    "DIVISLAB": 125,
    "BRITANNIA": 100,
    "EICHERMOT": 125,
    "APOLLOHOSP": 125,
    "HEROMOTOCO": 150,
    "BAJAJFINSV": 500,
    "SHREECEM": 25,
    "VEDL": 2300,
    "HINDALCO": 1075,
    "TATACONSUM": 550,
    "DABUR": 1250,
    "PIDILITIND": 250,
    "SIEMENS": 75,
    "HAVELLS": 400,
    "AMBUJACEM": 900,
    "GODREJCP": 450,
    "DLF": 825,
    "BOSCHLTD": 25,
    "ACC": 250,
    "MCDOWELL-N": 250,
    "INDIGO": 225,
    "ADANIENT": 250,
    "BPCL": 1800,
    "MOTHERSON": 6300,
    "TATAPOWER": 2700,
    "BANKBARODA": 2850,
    "PNB": 6000,
    "ZOMATO": 4600,
    "HAL": 150,
    "BEL": 2500,
    "IRCTC": 500,
    "PAYTM": 750,
    "NYKAA": 850,
    "POLICYBZR": 1000,
    "DELHIVERY": 1650,
    "LICI": 550,
    "ADANIGREEN": 500,
    "ADANIPOWER": 1400,
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
    "NBCC": 6000,
    "SAIL": 4200,
    "GAIL": 4100,
    "HINDPETRO": 1850,
    "NMDC": 3100,
    "NHPC": 7000,
    "SJVN": 5500,
    "PETRONET": 3000,
    "CONCOR": 700,
    "NATIONALUM": 4000,
    "OIL": 2250,
    "GMRAIRPORT": 8500,
    "INDUSTOWER": 2650,
    "ABCAPITAL": 2000,
    "ABB": 125,
    "PAGEIND": 15,
    "MFSL": 450,
    "PERSISTENT": 100,
    "COFORGE": 100,
    "LTIM": 100,
    "OFSS": 75,
    "MPHASIS": 175,
    "LTTS": 100,
    "NAVINFLUOR": 50,
    "DEEPAKNTR": 200,
    "PIIND": 125,
    "ATUL": 50,
    "CHAMBLFERT": 1500,
    "GNFC": 900,
    "COROMANDEL": 350,
    "UBL": 275,
    "COLPAL": 200,
    "MARICO": 800,
    "TATAELXSI": 75,
    "DIXON": 50,
    "POLYCAB": 100,
    "VOLTAS": 325,
    "WHIRLPOOL": 300,
    "CROMPTON": 1350,
    "BLUESTARCO": 275,
    "CUMMINSIND": 225,
    "THERMAX": 150,
    "KAJARIACER": 500,
    "SUPREMEIND": 100,
    "ASTRAL": 250,
    "APLAPOLLO": 275,
    "RATNAMANI": 150,
    "JKCEMENT": 175,
    "RAMCOCEM": 450,
    "DALBHARAT": 275,
    "SYNGENE": 650,
    "BIOCON": 1700,
    "LAURUSLABS": 1050,
    "AUROPHARMA": 450,
    "ALKEM": 100,
    "TORNTPHARM": 100,
    "IPCALAB": 400,
    "GLENMARK": 425,
    "NATCOPHARM": 350,
    "MRF": 5,
    "BALKRISIND": 200,
    "APOLLOTYRE": 1400,
    "CEATLTD": 200,
    "EXIDEIND": 1350,
    "AMARAJABAT": 700,
    "ASHOKLEY": 3000,
    "ESCORTS": 150,
    "SONACOMS": 650,
    "BHARATFORG": 550,
    "SCHAEFFLER": 100,
    "SKFINDIA": 75,
    "TIMKEN": 125,
    "SUNDARMFIN": 200,
    "CHOLAFIN": 450,
    "MUTHOOTFIN": 350,
    "MANAPPURAM": 3250,
    "SBICARD": 625,
    "HDFCAMC": 175,
    "ICICIGI": 275,
    "ICICIPRULI": 900,
    "HDFCLIFE": 800,
    "SBILIFE": 400,
    "PVR": 475,
    "NAUKRI": 75,
    "ZEEL": 3900,
    "JINDALSTEL": 500,
    "TVSMOTOR": 275,
    "OBEROIRLTY": 250,
    "LODHA": 450,
    "GODREJPROP": 225,
    "PRESTIGE": 300,
    "PHOENIXLTD": 325,
    "SUNTV": 500,
    "SRF": 175,
    "AARTIIND": 700,
    "CLEAN": 350,
    "IEX": 2750,
    "MCX": 175,
    "CAMS": 150,
    "CDSL": 400,
    "KPITTECH": 350,
    "CYIENT": 300,
    "ZENTECH": 450,
    "MINDACORP": 1000,
    "FEDERALBNK": 4000,
    "RBLBANK": 3500,
    "BANDHANBNK": 3500,
    "AUBANK": 650,
    "MAHABANK": 10500,
    "SWANENERGY": 750,
    "NIACL": 3000,
    "GICRE": 1550,
    "STARHEALTH": 900,
    "MAXHEALTH": 700,
    "FORTIS": 1250,
    "METROBRAND": 875,
    "DEVYANI": 3700,
    "JUBLFOOD": 800,
    "VBL": 250,
    "MANYAVAR": 325,
    "CAMPUS": 950,
    "RAYMOND": 300,
    "PGHL": 150,
    "HONAUT": 10,
    "3MINDIA": 15,
    "GRINDWELL": 200,
    "CARBORUNIV": 400,
}


# =============================================================================
# Main Seeding Functions
# =============================================================================

async def seed_holidays():
    """Seed holiday calendar."""
    logger.info("Seeding holiday calendar...")
    
    all_holidays = NSE_HOLIDAYS_2025 + NSE_HOLIDAYS_2026
    
    # Add BSE holidays (same as NSE for simplicity)
    bse_holidays = []
    for h in all_holidays:
        bse_holidays.append({
            **h,
            "exchange": "BSE",
        })
    
    all_holidays.extend(bse_holidays)
    
    async with get_db_context() as db:
        count = 0
        for h in all_holidays:
            stmt = pg_insert(HolidayCalendar).values(
                date=h["date"],
                exchange=h["exchange"],
                holiday_name=h.get("name"),
                holiday_type=h.get("type", "FULL"),
            ).on_conflict_do_update(
                constraint="uq_holiday",
                set_={
                    "holiday_name": h.get("name"),
                    "holiday_type": h.get("type", "FULL"),
                }
            )
            await db.execute(stmt)
            count += 1
        
        await db.commit()
    
    logger.info(f"✓ Added {count} holidays")
    return count


async def seed_holidays():
    """Seed holiday calendar."""
    logger.info("Seeding holiday calendar...")
    
    all_holidays = NSE_HOLIDAYS_2025 + NSE_HOLIDAYS_2026
    
    # Add BSE holidays (same as NSE for simplicity)
    bse_holidays = []
    for h in all_holidays:
        bse_holidays.append({
            **h,
            "exchange": "BSE",
        })
    
    all_holidays.extend(bse_holidays)
    
    async with get_db_context() as db:
        count = 0
        for h in all_holidays:
            stmt = pg_insert(HolidayCalendar).values(
                date=h["date"],
                exchange=h["exchange"],
                holiday_name=h.get("name"),
                holiday_type=h.get("type", "FULL"),
            ).on_conflict_do_update(
                constraint="uq_holiday",
                set_={
                    "holiday_name": h.get("name"),
                    "holiday_type": h.get("type", "FULL"),
                }
            )
            await db.execute(stmt)
            count += 1
        
        await db.commit()
    
    logger.info(f"✓ Added {count} holidays")
    return count


def get_last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Get the last occurrence of a weekday in a month."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    
    last_day = next_month - timedelta(days=1)
    days_back = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=days_back)


async def generate_expiries_simple(underlying: str, from_date: date, to_date: date) -> List[Dict]:
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


async def seed_expiries():
    """Generate and seed expiry calendar."""
    logger.info("Seeding expiry calendar...")
    
    indices = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]
    from_date = date(2025, 1, 1)
    to_date = date(2026, 12, 31)
    
    total_count = 0
    
    async with get_db_context() as db:
        for underlying in indices:
            expiries = await generate_expiries_simple(underlying, from_date, to_date)
            
            for e in expiries:
                stmt = pg_insert(ExpiryCalendar).values(
                    underlying=e["underlying"],
                    expiry_date=e["expiry_date"],
                    expiry_type=e["expiry_type"],
                    segment=e["segment"],
                ).on_conflict_do_nothing()
                await db.execute(stmt)
                total_count += 1
            
            logger.info(f"  Added {len(expiries)} expiries for {underlying}")
        
        await db.commit()
    
    logger.info(f"✓ Added {total_count} total expiries")
    return total_count


async def seed_lot_sizes():
    """Seed lot sizes."""
    logger.info("Seeding lot sizes...")
    
    effective_date = date(2025, 1, 1)
    count = 0
    
    async with get_db_context() as db:
        for underlying, lot_size in FO_LOT_SIZES.items():
            segment = "BFO" if underlying in ["SENSEX", "BANKEX"] else "NFO"
            
            lot = LotSizeHistory(
                underlying=underlying.upper(),
                lot_size=lot_size,
                effective_date=effective_date,
                segment=segment,
            )
            db.add(lot)
            count += 1
        
        await db.commit()
    
    logger.info(f"✓ Added {count} lot sizes")
    return count


async def main():
    """Run all seeding operations."""
    logger.info("=" * 60)
    logger.info("Starting Calendar Data Seed")
    logger.info("=" * 60)
    
    try:
        await seed_holidays()
        await seed_expiries()
        await seed_lot_sizes()
        
        logger.info("=" * 60)
        logger.info("✓ Calendar data seeding completed!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())
