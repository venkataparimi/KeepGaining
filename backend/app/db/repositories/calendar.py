"""
Calendar Repository
KeepGaining Trading Platform

Data access layer for calendar and master data.
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, or_, select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import BaseRepository
from app.db.models.calendar import (
    ExpiryCalendar,
    HolidayCalendar,
    LotSizeHistory,
    FOBanList,
    MasterDataRefreshLog,
)


class ExpiryCalendarRepository(BaseRepository[ExpiryCalendar]):
    """Repository for expiry calendar data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(ExpiryCalendar, session)
    
    async def get_next_expiry(
        self,
        underlying: str,
        instrument_type: str = "OPTIONS",
        as_of_date: Optional[date] = None,
    ) -> Optional[ExpiryCalendar]:
        """Get next expiry date for an underlying."""
        as_of = as_of_date or date.today()
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.underlying_symbol == underlying,
                    self.model.instrument_type == instrument_type,
                    self.model.expiry_date >= as_of,
                )
            )
            .order_by(self.model.expiry_date)
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_upcoming_expiries(
        self,
        underlying: str,
        instrument_type: str = "OPTIONS",
        count: int = 5,
        as_of_date: Optional[date] = None,
    ) -> List[ExpiryCalendar]:
        """Get upcoming expiry dates."""
        as_of = as_of_date or date.today()
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.underlying_symbol == underlying,
                    self.model.instrument_type == instrument_type,
                    self.model.expiry_date >= as_of,
                )
            )
            .order_by(self.model.expiry_date)
            .limit(count)
        )
        return list(result.scalars().all())
    
    async def get_weekly_expiries(
        self,
        underlying: str,
        start_date: date,
        end_date: date,
    ) -> List[ExpiryCalendar]:
        """Get weekly expiry dates in a range."""
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.underlying_symbol == underlying,
                    self.model.expiry_type == "WEEKLY",
                    self.model.expiry_date >= start_date,
                    self.model.expiry_date <= end_date,
                )
            )
            .order_by(self.model.expiry_date)
        )
        return list(result.scalars().all())
    
    async def get_monthly_expiries(
        self,
        underlying: str,
        year: int,
    ) -> List[ExpiryCalendar]:
        """Get monthly expiry dates for a year."""
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.underlying_symbol == underlying,
                    self.model.expiry_type == "MONTHLY",
                    self.model.expiry_date >= start,
                    self.model.expiry_date <= end,
                )
            )
            .order_by(self.model.expiry_date)
        )
        return list(result.scalars().all())
    
    async def is_expiry_date(
        self,
        check_date: date,
        underlying: Optional[str] = None,
    ) -> bool:
        """Check if a date is an expiry date."""
        conditions = [self.model.expiry_date == check_date]
        
        if underlying:
            conditions.append(self.model.underlying_symbol == underlying)
        
        result = await self.session.execute(
            select(func.count())
            .select_from(self.model)
            .where(and_(*conditions))
        )
        count = result.scalar()
        return count > 0
    
    async def get_expiry_dates_for_year(
        self,
        year: int,
        underlying: Optional[str] = None,
        instrument_type: Optional[str] = None,
    ) -> List[date]:
        """Get all expiry dates for a year."""
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        
        conditions = [
            self.model.expiry_date >= start,
            self.model.expiry_date <= end,
        ]
        
        if underlying:
            conditions.append(self.model.underlying_symbol == underlying)
        if instrument_type:
            conditions.append(self.model.instrument_type == instrument_type)
        
        result = await self.session.execute(
            select(self.model.expiry_date)
            .where(and_(*conditions))
            .distinct()
            .order_by(self.model.expiry_date)
        )
        return [row[0] for row in result.fetchall()]


class HolidayCalendarRepository(BaseRepository[HolidayCalendar]):
    """Repository for holiday calendar data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(HolidayCalendar, session)
    
    async def is_trading_holiday(
        self,
        check_date: date,
        exchange: str = "NSE",
        segment: Optional[str] = None,
    ) -> bool:
        """Check if a date is a trading holiday."""
        conditions = [
            self.model.holiday_date == check_date,
            self.model.exchange == exchange,
            self.model.is_full_day == True,
        ]
        
        if segment:
            conditions.append(
                or_(
                    self.model.segment.is_(None),
                    self.model.segment == segment,
                )
            )
        
        result = await self.session.execute(
            select(func.count())
            .select_from(self.model)
            .where(and_(*conditions))
        )
        count = result.scalar()
        return count > 0
    
    async def get_holidays_for_year(
        self,
        year: int,
        exchange: str = "NSE",
    ) -> List[HolidayCalendar]:
        """Get all holidays for a year."""
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.exchange == exchange,
                    self.model.holiday_date >= start,
                    self.model.holiday_date <= end,
                )
            )
            .order_by(self.model.holiday_date)
        )
        return list(result.scalars().all())
    
    async def get_upcoming_holidays(
        self,
        count: int = 5,
        exchange: str = "NSE",
        as_of_date: Optional[date] = None,
    ) -> List[HolidayCalendar]:
        """Get upcoming holidays."""
        as_of = as_of_date or date.today()
        
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.exchange == exchange,
                    self.model.holiday_date >= as_of,
                )
            )
            .order_by(self.model.holiday_date)
            .limit(count)
        )
        return list(result.scalars().all())
    
    async def get_trading_days(
        self,
        start_date: date,
        end_date: date,
        exchange: str = "NSE",
    ) -> List[date]:
        """Get all trading days in a date range."""
        # Get holidays
        holidays = await self.session.execute(
            select(self.model.holiday_date)
            .where(
                and_(
                    self.model.exchange == exchange,
                    self.model.holiday_date >= start_date,
                    self.model.holiday_date <= end_date,
                    self.model.is_full_day == True,
                )
            )
        )
        holiday_dates = {row[0] for row in holidays.fetchall()}
        
        # Generate all days and exclude weekends and holidays
        trading_days = []
        current = start_date
        
        while current <= end_date:
            # Monday = 0, Sunday = 6
            if current.weekday() < 5 and current not in holiday_dates:
                trading_days.append(current)
            current += timedelta(days=1)
        
        return trading_days
    
    async def get_next_trading_day(
        self,
        from_date: Optional[date] = None,
        exchange: str = "NSE",
    ) -> date:
        """Get the next trading day."""
        current = from_date or date.today()
        
        for _ in range(10):  # Max 10 days lookahead
            current += timedelta(days=1)
            
            # Skip weekends
            if current.weekday() >= 5:
                continue
            
            # Check if holiday
            is_holiday = await self.is_trading_holiday(current, exchange)
            if not is_holiday:
                return current
        
        # Fallback
        return current
    
    async def get_previous_trading_day(
        self,
        from_date: Optional[date] = None,
        exchange: str = "NSE",
    ) -> date:
        """Get the previous trading day."""
        current = from_date or date.today()
        
        for _ in range(10):  # Max 10 days lookback
            current -= timedelta(days=1)
            
            # Skip weekends
            if current.weekday() >= 5:
                continue
            
            # Check if holiday
            is_holiday = await self.is_trading_holiday(current, exchange)
            if not is_holiday:
                return current
        
        # Fallback
        return current


class LotSizeHistoryRepository(BaseRepository[LotSizeHistory]):
    """Repository for lot size history."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(LotSizeHistory, session)
    
    async def get_current_lot_size(
        self,
        symbol: str,
        as_of_date: Optional[date] = None,
    ) -> Optional[int]:
        """Get current lot size for a symbol."""
        as_of = as_of_date or date.today()
        
        result = await self.session.execute(
            select(self.model.lot_size)
            .where(
                and_(
                    self.model.symbol == symbol,
                    self.model.effective_from <= as_of,
                    or_(
                        self.model.effective_to.is_(None),
                        self.model.effective_to >= as_of,
                    ),
                )
            )
            .order_by(self.model.effective_from.desc())
            .limit(1)
        )
        row = result.fetchone()
        return row[0] if row else None
    
    async def get_lot_size_history(
        self,
        symbol: str,
    ) -> List[LotSizeHistory]:
        """Get lot size change history for a symbol."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.symbol == symbol)
            .order_by(self.model.effective_from.desc())
        )
        return list(result.scalars().all())
    
    async def get_symbols_with_lot_changes(
        self,
        start_date: date,
        end_date: date,
    ) -> List[str]:
        """Get symbols that had lot size changes in a date range."""
        result = await self.session.execute(
            select(self.model.symbol)
            .where(
                and_(
                    self.model.effective_from >= start_date,
                    self.model.effective_from <= end_date,
                )
            )
            .distinct()
        )
        return [row[0] for row in result.fetchall()]


class FOBanListRepository(BaseRepository[FOBanList]):
    """Repository for F&O ban list data."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(FOBanList, session)
    
    async def is_in_ban(
        self,
        symbol: str,
        check_date: Optional[date] = None,
    ) -> bool:
        """Check if a symbol is in F&O ban."""
        as_of = check_date or date.today()
        
        result = await self.session.execute(
            select(func.count())
            .select_from(self.model)
            .where(
                and_(
                    self.model.symbol == symbol,
                    self.model.ban_date == as_of,
                )
            )
        )
        count = result.scalar()
        return count > 0
    
    async def get_banned_stocks(
        self,
        ban_date: Optional[date] = None,
    ) -> List[FOBanList]:
        """Get all stocks in F&O ban for a date."""
        as_of = ban_date or date.today()
        
        result = await self.session.execute(
            select(self.model)
            .where(self.model.ban_date == as_of)
            .order_by(self.model.symbol)
        )
        return list(result.scalars().all())
    
    async def get_ban_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> List[FOBanList]:
        """Get ban history for a symbol."""
        result = await self.session.execute(
            select(self.model)
            .where(
                and_(
                    self.model.symbol == symbol,
                    self.model.ban_date >= start_date,
                    self.model.ban_date <= end_date,
                )
            )
            .order_by(self.model.ban_date)
        )
        return list(result.scalars().all())
    
    async def get_frequently_banned(
        self,
        days: int = 30,
        min_ban_days: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get stocks frequently in ban."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        result = await self.session.execute(
            select(self.model.symbol, func.count(self.model.id).label("ban_count"))
            .where(
                and_(
                    self.model.ban_date >= start_date,
                    self.model.ban_date <= end_date,
                )
            )
            .group_by(self.model.symbol)
            .having(func.count(self.model.id) >= min_ban_days)
            .order_by(func.count(self.model.id).desc())
        )
        
        return [
            {"symbol": row[0], "ban_days": row[1]}
            for row in result.fetchall()
        ]


class MasterDataRefreshLogRepository(BaseRepository[MasterDataRefreshLog]):
    """Repository for master data refresh tracking."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(MasterDataRefreshLog, session)
    
    async def get_last_refresh(
        self,
        data_type: str,
        source: Optional[str] = None,
    ) -> Optional[MasterDataRefreshLog]:
        """Get last successful refresh for a data type."""
        conditions = [
            self.model.data_type == data_type,
            self.model.status == "SUCCESS",
        ]
        
        if source:
            conditions.append(self.model.source == source)
        
        result = await self.session.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.refresh_timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def log_refresh(
        self,
        data_type: str,
        source: str,
        status: str,
        records_updated: int = 0,
        error_message: Optional[str] = None,
    ) -> MasterDataRefreshLog:
        """Log a master data refresh."""
        log_entry = MasterDataRefreshLog(
            data_type=data_type,
            source=source,
            refresh_timestamp=datetime.now(),
            status=status,
            records_updated=records_updated,
            error_message=error_message,
        )
        
        self.session.add(log_entry)
        await self.session.commit()
        await self.session.refresh(log_entry)
        
        return log_entry
    
    async def needs_refresh(
        self,
        data_type: str,
        max_age_hours: int = 24,
    ) -> bool:
        """Check if data type needs refresh."""
        last_refresh = await self.get_last_refresh(data_type)
        
        if not last_refresh:
            return True
        
        age = datetime.now() - last_refresh.refresh_timestamp
        return age.total_seconds() > (max_age_hours * 3600)
    
    async def get_refresh_history(
        self,
        data_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[MasterDataRefreshLog]:
        """Get refresh history."""
        query = select(self.model).order_by(
            self.model.refresh_timestamp.desc()
        ).limit(limit)
        
        if data_type:
            query = query.where(self.model.data_type == data_type)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())


__all__ = [
    "ExpiryCalendarRepository",
    "HolidayCalendarRepository",
    "LotSizeHistoryRepository",
    "FOBanListRepository",
    "MasterDataRefreshLogRepository",
]
