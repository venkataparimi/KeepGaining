"""
Calendar Service - Market Calendar Management
KeepGaining Trading Platform

Handles:
- Holiday calendar for NSE/BSE/MCX
- Expiry calendar for F&O instruments
- F&O ban list tracking
- Lot size history
- Trading day validation

Key Features:
- Pre-market calendar refresh
- Holiday-adjusted expiry calculation
- Trading hours validation
- Upcoming expiry alerts
"""

from datetime import date, datetime, time, timedelta
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from dataclasses import dataclass

from sqlalchemy import select, and_, or_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from loguru import logger

from app.db.models.calendar import (
    ExpiryCalendar,
    HolidayCalendar,
    LotSizeHistory,
    FOBanList,
    MasterDataRefreshLog,
)
from app.db.session import get_db_context


class Exchange(str, Enum):
    """Supported exchanges."""
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"


class Segment(str, Enum):
    """Market segments."""
    EQ = "EQ"      # Equity cash
    FO = "FO"      # Equity F&O
    NFO = "NFO"    # NSE F&O
    BFO = "BFO"    # BSE F&O  
    CD = "CD"      # Currency derivatives
    MCX = "MCX"    # Commodity


class ExpiryType(str, Enum):
    """Expiry types."""
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class HolidayType(str, Enum):
    """Holiday types."""
    FULL = "FULL"           # Full day closed
    MORNING = "MORNING"     # Morning session closed
    EVENING = "EVENING"     # Evening session closed


@dataclass
class TradingHours:
    """Market trading hours."""
    exchange: str
    segment: str
    open_time: time
    close_time: time
    pre_open_start: Optional[time] = None
    pre_open_end: Optional[time] = None


@dataclass
class ExpiryInfo:
    """Expiry information."""
    underlying: str
    expiry_date: date
    expiry_type: ExpiryType
    segment: str
    days_to_expiry: int
    is_current_week: bool
    is_current_month: bool


# Standard trading hours
TRADING_HOURS: Dict[str, TradingHours] = {
    "NSE_EQ": TradingHours(
        exchange="NSE",
        segment="EQ",
        open_time=time(9, 15),
        close_time=time(15, 30),
        pre_open_start=time(9, 0),
        pre_open_end=time(9, 8),
    ),
    "NSE_FO": TradingHours(
        exchange="NSE",
        segment="FO",
        open_time=time(9, 15),
        close_time=time(15, 30),
    ),
    "BSE_EQ": TradingHours(
        exchange="BSE",
        segment="EQ",
        open_time=time(9, 15),
        close_time=time(15, 30),
        pre_open_start=time(9, 0),
        pre_open_end=time(9, 8),
    ),
    "MCX": TradingHours(
        exchange="MCX",
        segment="MCX",
        open_time=time(9, 0),
        close_time=time(23, 30),
    ),
}


# Expiry day mapping (as of 2025)
# Index weekly/monthly expiries moved to Tuesday
EXPIRY_DAYS: Dict[str, Dict[str, int]] = {
    # Underlying -> {expiry_type -> weekday (0=Monday, 6=Sunday)}
    "NIFTY": {"WEEKLY": 1, "MONTHLY": 1},       # Tuesday
    "BANKNIFTY": {"WEEKLY": 1, "MONTHLY": 1},   # Tuesday  
    "FINNIFTY": {"MONTHLY": 1},                  # Tuesday (monthly only)
    "MIDCPNIFTY": {"WEEKLY": 1, "MONTHLY": 1},  # Tuesday
    "SENSEX": {"WEEKLY": 3, "MONTHLY": 3},      # Thursday (BSE)
    "BANKEX": {"MONTHLY": 3},                    # Thursday (BSE)
    "STOCK": {"MONTHLY": 3},                     # Thursday (last Thursday of month)
}


class CalendarService:
    """
    Market calendar service.
    
    Manages trading calendar, holidays, expiries, and market timing.
    """
    
    def __init__(self, db: Optional[AsyncSession] = None):
        self._db = db
        self._holidays_cache: Dict[str, set] = {}  # exchange -> set of dates
        self._cache_date: Optional[date] = None
    
    # =========================================================================
    # Holiday Management
    # =========================================================================
    
    async def is_trading_day(
        self,
        check_date: date,
        exchange: str = "NSE",
        segment: str = "EQ",
    ) -> bool:
        """
        Check if a date is a trading day.
        
        Args:
            check_date: Date to check
            exchange: Exchange (NSE, BSE, MCX)
            segment: Market segment (EQ, FO, CD)
            
        Returns:
            True if trading day, False if holiday/weekend
        """
        # Weekend check
        if check_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        # Holiday check
        async with get_db_context() as db:
            query = select(HolidayCalendar).where(
                and_(
                    HolidayCalendar.date == check_date,
                    HolidayCalendar.exchange == exchange,
                    HolidayCalendar.holiday_type == HolidayType.FULL.value,
                )
            )
            
            # Also check if segment is affected
            result = await db.execute(query)
            holiday = result.scalar_one_or_none()
            
            if holiday:
                # Check if our segment is affected
                if holiday.segments_affected:
                    return segment not in holiday.segments_affected
                return False  # Full holiday for all segments
            
            return True
    
    async def get_holidays(
        self,
        year: int,
        exchange: str = "NSE",
    ) -> List[Dict[str, Any]]:
        """
        Get all holidays for a year.
        
        Args:
            year: Year to get holidays for
            exchange: Exchange (NSE, BSE, MCX)
            
        Returns:
            List of holiday records
        """
        async with get_db_context() as db:
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
            
            query = select(HolidayCalendar).where(
                and_(
                    HolidayCalendar.date >= start_date,
                    HolidayCalendar.date <= end_date,
                    HolidayCalendar.exchange == exchange,
                )
            ).order_by(HolidayCalendar.date)
            
            result = await db.execute(query)
            holidays = result.scalars().all()
            
            return [
                {
                    "date": h.date.isoformat(),
                    "name": h.holiday_name,
                    "type": h.holiday_type,
                    "exchange": h.exchange,
                    "segments_affected": h.segments_affected,
                }
                for h in holidays
            ]
    
    async def add_holiday(
        self,
        holiday_date: date,
        exchange: str,
        name: str,
        holiday_type: str = "FULL",
        segments_affected: Optional[List[str]] = None,
    ) -> bool:
        """Add a holiday to the calendar."""
        async with get_db_context() as db:
            holiday = HolidayCalendar(
                date=holiday_date,
                exchange=exchange,
                holiday_name=name,
                holiday_type=holiday_type,
                segments_affected=segments_affected,
            )
            db.add(holiday)
            await db.commit()
            logger.info(f"Added holiday: {name} on {holiday_date} for {exchange}")
            return True
    
    async def bulk_add_holidays(
        self,
        holidays: List[Dict[str, Any]],
    ) -> int:
        """
        Bulk add holidays (upsert).
        
        Args:
            holidays: List of holiday dicts with date, exchange, name, type
            
        Returns:
            Number of holidays added/updated
        """
        async with get_db_context() as db:
            count = 0
            for h in holidays:
                stmt = pg_insert(HolidayCalendar).values(
                    date=h["date"],
                    exchange=h["exchange"],
                    holiday_name=h.get("name"),
                    holiday_type=h.get("type", "FULL"),
                    segments_affected=h.get("segments_affected"),
                ).on_conflict_do_update(
                    constraint="uq_holiday",
                    set_={
                        "holiday_name": h.get("name"),
                        "holiday_type": h.get("type", "FULL"),
                        "segments_affected": h.get("segments_affected"),
                    }
                )
                await db.execute(stmt)
                count += 1
            
            await db.commit()
            logger.info(f"Bulk added {count} holidays")
            return count
    
    async def get_next_trading_day(
        self,
        from_date: date,
        exchange: str = "NSE",
    ) -> date:
        """Get the next trading day after given date."""
        check_date = from_date + timedelta(days=1)
        max_attempts = 10  # Safety limit
        
        for _ in range(max_attempts):
            if await self.is_trading_day(check_date, exchange):
                return check_date
            check_date += timedelta(days=1)
        
        return check_date  # Fallback
    
    async def get_previous_trading_day(
        self,
        from_date: date,
        exchange: str = "NSE",
    ) -> date:
        """Get the previous trading day before given date."""
        check_date = from_date - timedelta(days=1)
        max_attempts = 10
        
        for _ in range(max_attempts):
            if await self.is_trading_day(check_date, exchange):
                return check_date
            check_date -= timedelta(days=1)
        
        return check_date
    
    # =========================================================================
    # Expiry Management
    # =========================================================================
    
    async def get_expiries(
        self,
        underlying: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        expiry_type: Optional[str] = None,
    ) -> List[ExpiryInfo]:
        """
        Get expiry dates for an underlying.
        
        Args:
            underlying: NIFTY, BANKNIFTY, RELIANCE, etc.
            from_date: Start date (default: today)
            to_date: End date (default: 3 months from now)
            expiry_type: WEEKLY or MONTHLY filter
            
        Returns:
            List of ExpiryInfo objects
        """
        if from_date is None:
            from_date = date.today()
        if to_date is None:
            to_date = from_date + timedelta(days=90)
        
        async with get_db_context() as db:
            query = select(ExpiryCalendar).where(
                and_(
                    ExpiryCalendar.underlying == underlying.upper(),
                    ExpiryCalendar.expiry_date >= from_date,
                    ExpiryCalendar.expiry_date <= to_date,
                )
            )
            
            if expiry_type:
                query = query.where(ExpiryCalendar.expiry_type == expiry_type)
            
            query = query.order_by(ExpiryCalendar.expiry_date)
            
            result = await db.execute(query)
            expiries = result.scalars().all()
            
            today = date.today()
            
            return [
                ExpiryInfo(
                    underlying=e.underlying,
                    expiry_date=e.expiry_date,
                    expiry_type=ExpiryType(e.expiry_type),
                    segment=e.segment,
                    days_to_expiry=(e.expiry_date - today).days,
                    is_current_week=self._is_current_week(e.expiry_date, today),
                    is_current_month=e.expiry_date.month == today.month and e.expiry_date.year == today.year,
                )
                for e in expiries
            ]
    
    async def get_current_expiry(
        self,
        underlying: str,
        expiry_type: str = "WEEKLY",
    ) -> Optional[ExpiryInfo]:
        """Get the current (nearest) expiry for an underlying."""
        expiries = await self.get_expiries(
            underlying=underlying,
            from_date=date.today(),
            to_date=date.today() + timedelta(days=7),
            expiry_type=expiry_type,
        )
        return expiries[0] if expiries else None
    
    async def get_next_expiry(
        self,
        underlying: str,
        expiry_type: str = "WEEKLY",
    ) -> Optional[ExpiryInfo]:
        """Get the next expiry after current."""
        expiries = await self.get_expiries(
            underlying=underlying,
            from_date=date.today() + timedelta(days=1),
            to_date=date.today() + timedelta(days=14),
            expiry_type=expiry_type,
        )
        
        # Skip if first expiry is today
        if expiries and expiries[0].expiry_date == date.today():
            return expiries[1] if len(expiries) > 1 else None
        return expiries[0] if expiries else None
    
    async def add_expiry(
        self,
        underlying: str,
        expiry_date: date,
        expiry_type: str,
        segment: str = "NFO",
    ) -> bool:
        """Add an expiry date to the calendar."""
        async with get_db_context() as db:
            expiry = ExpiryCalendar(
                underlying=underlying.upper(),
                expiry_date=expiry_date,
                expiry_type=expiry_type,
                segment=segment,
            )
            db.add(expiry)
            await db.commit()
            return True
    
    async def bulk_add_expiries(
        self,
        expiries: List[Dict[str, Any]],
    ) -> int:
        """Bulk add expiries (upsert)."""
        async with get_db_context() as db:
            count = 0
            for e in expiries:
                stmt = pg_insert(ExpiryCalendar).values(
                    underlying=e["underlying"].upper(),
                    expiry_date=e["expiry_date"],
                    expiry_type=e["expiry_type"],
                    segment=e.get("segment", "NFO"),
                ).on_conflict_do_nothing()
                await db.execute(stmt)
                count += 1
            
            await db.commit()
            logger.info(f"Bulk added {count} expiries")
            return count
    
    async def generate_expiries(
        self,
        underlying: str,
        from_date: date,
        to_date: date,
        include_weekly: bool = True,
        include_monthly: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Generate expiry dates for an underlying.
        
        Calculates expiries based on rules (Tuesday for index, Thursday for stocks)
        and adjusts for holidays.
        
        Args:
            underlying: NIFTY, BANKNIFTY, RELIANCE, etc.
            from_date: Start date
            to_date: End date
            include_weekly: Include weekly expiries
            include_monthly: Include monthly expiries
            
        Returns:
            List of expiry dicts ready for insertion
        """
        expiries = []
        underlying_upper = underlying.upper()
        
        # Determine if index or stock
        is_index = underlying_upper in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]
        
        # Get expiry day for this underlying
        expiry_config = EXPIRY_DAYS.get(underlying_upper, EXPIRY_DAYS.get("STOCK"))
        
        current = from_date
        while current <= to_date:
            # Weekly expiry
            if include_weekly and "WEEKLY" in expiry_config:
                weekly_day = expiry_config["WEEKLY"]
                # Find the expiry day of this week
                days_until_expiry = (weekly_day - current.weekday()) % 7
                expiry_date = current + timedelta(days=days_until_expiry)
                
                if from_date <= expiry_date <= to_date:
                    # Adjust for holidays
                    adjusted_date = await self._adjust_for_holiday(expiry_date, "NSE")
                    expiries.append({
                        "underlying": underlying_upper,
                        "expiry_date": adjusted_date,
                        "expiry_type": "WEEKLY",
                        "segment": "BFO" if underlying_upper in ["SENSEX", "BANKEX"] else "NFO",
                    })
            
            # Monthly expiry (last occurrence of expiry day in month)
            if include_monthly and "MONTHLY" in expiry_config:
                monthly_day = expiry_config["MONTHLY"]
                
                # Only calculate once per month (when we're in the first week)
                if current.day <= 7:
                    # Find last occurrence of expiry day in month
                    last_day = self._get_last_weekday_of_month(current.year, current.month, monthly_day)
                    
                    if from_date <= last_day <= to_date:
                        adjusted_date = await self._adjust_for_holiday(last_day, "NSE")
                        expiries.append({
                            "underlying": underlying_upper,
                            "expiry_date": adjusted_date,
                            "expiry_type": "MONTHLY",
                            "segment": "BFO" if underlying_upper in ["SENSEX", "BANKEX"] else "NFO",
                        })
            
            # Move to next week
            current += timedelta(days=7)
        
        # Remove duplicates (weekly that falls on monthly)
        seen = set()
        unique_expiries = []
        for e in expiries:
            key = (e["underlying"], e["expiry_date"])
            if key not in seen:
                seen.add(key)
                unique_expiries.append(e)
        
        return unique_expiries
    
    async def _adjust_for_holiday(self, expiry_date: date, exchange: str) -> date:
        """Adjust expiry date if it falls on a holiday (move to previous trading day)."""
        if not await self.is_trading_day(expiry_date, exchange):
            return await self.get_previous_trading_day(expiry_date, exchange)
        return expiry_date
    
    def _get_last_weekday_of_month(self, year: int, month: int, weekday: int) -> date:
        """Get the last occurrence of a weekday in a month."""
        # Start from last day of month
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        
        last_day = next_month - timedelta(days=1)
        
        # Go back to find the weekday
        days_back = (last_day.weekday() - weekday) % 7
        return last_day - timedelta(days=days_back)
    
    def _is_current_week(self, expiry_date: date, today: date) -> bool:
        """Check if expiry is in current week."""
        # Week starts on Monday
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return week_start <= expiry_date <= week_end
    
    # =========================================================================
    # F&O Ban List
    # =========================================================================
    
    async def get_banned_stocks(self, check_date: Optional[date] = None) -> List[str]:
        """Get list of stocks in F&O ban."""
        if check_date is None:
            check_date = date.today()
        
        async with get_db_context() as db:
            query = select(FOBanList.underlying).where(
                and_(
                    FOBanList.ban_date == check_date,
                    FOBanList.is_banned == True,
                )
            )
            
            result = await db.execute(query)
            return [r[0] for r in result.fetchall()]
    
    async def is_banned(self, underlying: str, check_date: Optional[date] = None) -> bool:
        """Check if a stock is in F&O ban."""
        banned_stocks = await self.get_banned_stocks(check_date)
        return underlying.upper() in banned_stocks
    
    async def update_ban_list(self, banned_stocks: List[str], ban_date: date) -> int:
        """Update the F&O ban list for a date."""
        async with get_db_context() as db:
            # Clear existing bans for this date
            await db.execute(
                delete(FOBanList).where(FOBanList.ban_date == ban_date)
            )
            
            # Add new bans
            for stock in banned_stocks:
                ban = FOBanList(
                    underlying=stock.upper(),
                    ban_date=ban_date,
                    is_banned=True,
                )
                db.add(ban)
            
            await db.commit()
            logger.info(f"Updated ban list for {ban_date}: {len(banned_stocks)} stocks")
            return len(banned_stocks)
    
    # =========================================================================
    # Lot Size Management
    # =========================================================================
    
    async def get_lot_size(
        self,
        underlying: str,
        as_of_date: Optional[date] = None,
    ) -> Optional[int]:
        """
        Get lot size for an underlying as of a date.
        
        Args:
            underlying: Stock/index symbol
            as_of_date: Date to check (for historical accuracy)
            
        Returns:
            Lot size or None if not found
        """
        if as_of_date is None:
            as_of_date = date.today()
        
        async with get_db_context() as db:
            query = select(LotSizeHistory).where(
                and_(
                    LotSizeHistory.underlying == underlying.upper(),
                    LotSizeHistory.effective_date <= as_of_date,
                    or_(
                        LotSizeHistory.end_date.is_(None),
                        LotSizeHistory.end_date > as_of_date,
                    )
                )
            ).order_by(LotSizeHistory.effective_date.desc()).limit(1)
            
            result = await db.execute(query)
            lot_info = result.scalar_one_or_none()
            
            return lot_info.lot_size if lot_info else None
    
    async def get_all_lot_sizes(self) -> Dict[str, int]:
        """Get current lot sizes for all underlyings."""
        today = date.today()
        
        async with get_db_context() as db:
            # Get latest lot size for each underlying
            subquery = (
                select(
                    LotSizeHistory.underlying,
                    func.max(LotSizeHistory.effective_date).label("max_date")
                )
                .where(LotSizeHistory.effective_date <= today)
                .group_by(LotSizeHistory.underlying)
                .subquery()
            )
            
            query = select(LotSizeHistory).join(
                subquery,
                and_(
                    LotSizeHistory.underlying == subquery.c.underlying,
                    LotSizeHistory.effective_date == subquery.c.max_date,
                )
            )
            
            result = await db.execute(query)
            lots = result.scalars().all()
            
            return {lot.underlying: lot.lot_size for lot in lots}
    
    async def update_lot_size(
        self,
        underlying: str,
        new_lot_size: int,
        effective_date: date,
        segment: str = "NFO",
    ) -> bool:
        """
        Update lot size for an underlying.
        
        Closes the previous lot size record and creates a new one.
        """
        async with get_db_context() as db:
            underlying_upper = underlying.upper()
            
            # End the current lot size
            current = await db.execute(
                select(LotSizeHistory).where(
                    and_(
                        LotSizeHistory.underlying == underlying_upper,
                        LotSizeHistory.end_date.is_(None),
                    )
                )
            )
            current_lot = current.scalar_one_or_none()
            
            if current_lot:
                current_lot.end_date = effective_date - timedelta(days=1)
            
            # Add new lot size
            new_lot = LotSizeHistory(
                underlying=underlying_upper,
                lot_size=new_lot_size,
                effective_date=effective_date,
                segment=segment,
            )
            db.add(new_lot)
            await db.commit()
            
            logger.info(f"Updated lot size for {underlying_upper}: {new_lot_size} from {effective_date}")
            return True
    
    async def bulk_add_lot_sizes(self, lot_sizes: List[Dict[str, Any]]) -> int:
        """Bulk add lot sizes."""
        async with get_db_context() as db:
            count = 0
            for ls in lot_sizes:
                lot = LotSizeHistory(
                    underlying=ls["underlying"].upper(),
                    lot_size=ls["lot_size"],
                    effective_date=ls["effective_date"],
                    segment=ls.get("segment", "NFO"),
                )
                db.add(lot)
                count += 1
            
            await db.commit()
            logger.info(f"Bulk added {count} lot sizes")
            return count
    
    # =========================================================================
    # Trading Hours
    # =========================================================================
    
    def get_trading_hours(self, exchange: str = "NSE", segment: str = "EQ") -> TradingHours:
        """Get trading hours for exchange/segment."""
        key = f"{exchange}_{segment}"
        return TRADING_HOURS.get(key, TRADING_HOURS["NSE_EQ"])
    
    def is_market_open(self, exchange: str = "NSE", segment: str = "EQ") -> bool:
        """Check if market is currently open."""
        now = datetime.now()
        
        # Weekend check
        if now.weekday() >= 5:
            return False
        
        hours = self.get_trading_hours(exchange, segment)
        current_time = now.time()
        
        return hours.open_time <= current_time <= hours.close_time
    
    def time_to_market_open(self, exchange: str = "NSE", segment: str = "EQ") -> Optional[timedelta]:
        """Get time until market opens."""
        now = datetime.now()
        hours = self.get_trading_hours(exchange, segment)
        
        market_open = datetime.combine(now.date(), hours.open_time)
        
        if now < market_open:
            return market_open - now
        return None
    
    def time_to_market_close(self, exchange: str = "NSE", segment: str = "EQ") -> Optional[timedelta]:
        """Get time until market closes."""
        now = datetime.now()
        hours = self.get_trading_hours(exchange, segment)
        
        market_close = datetime.combine(now.date(), hours.close_time)
        
        if now < market_close:
            return market_close - now
        return None
    
    # =========================================================================
    # Calendar Summary
    # =========================================================================
    
    async def get_today_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive calendar summary for today.
        
        Returns:
            Dict with trading status, expiries, banned stocks, etc.
        """
        today = date.today()
        
        is_trading = await self.is_trading_day(today)
        
        # Get today's expiring instruments
        async with get_db_context() as db:
            expiry_query = select(ExpiryCalendar).where(
                ExpiryCalendar.expiry_date == today
            )
            result = await db.execute(expiry_query)
            expiring_today = [e.underlying for e in result.scalars().all()]
        
        banned_stocks = await self.get_banned_stocks(today)
        
        # Get upcoming expiries (next 7 days)
        upcoming_expiries = []
        for underlying in ["NIFTY", "BANKNIFTY", "FINNIFTY"]:
            expiries = await self.get_expiries(
                underlying=underlying,
                from_date=today,
                to_date=today + timedelta(days=7),
            )
            upcoming_expiries.extend([
                {
                    "underlying": e.underlying,
                    "date": e.expiry_date.isoformat(),
                    "type": e.expiry_type.value,
                    "days": e.days_to_expiry,
                }
                for e in expiries
            ])
        
        return {
            "date": today.isoformat(),
            "is_trading_day": is_trading,
            "market_status": "OPEN" if self.is_market_open() else "CLOSED",
            "time_to_open": str(self.time_to_market_open()) if self.time_to_market_open() else None,
            "time_to_close": str(self.time_to_market_close()) if self.time_to_market_close() else None,
            "expiring_today": expiring_today,
            "upcoming_expiries": upcoming_expiries,
            "banned_stocks": banned_stocks,
            "banned_count": len(banned_stocks),
        }


# Singleton instance
_calendar_service: Optional[CalendarService] = None


def get_calendar_service() -> CalendarService:
    """Get calendar service singleton."""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = CalendarService()
    return _calendar_service
