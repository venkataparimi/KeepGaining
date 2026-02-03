"""
Calendar API Routes
KeepGaining Trading Platform

Endpoints for:
- Holiday calendar management
- Expiry calendar management
- F&O ban list
- Lot size information
- Trading hours and status
"""

from datetime import date, datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from loguru import logger

from app.services.calendar_service import (
    CalendarService,
    get_calendar_service,
    ExpiryInfo,
)


router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class HolidayCreate(BaseModel):
    """Holiday creation request."""
    date: date
    exchange: str = Field(..., description="NSE, BSE, or MCX")
    name: str
    type: str = Field("FULL", description="FULL, MORNING, or EVENING")
    segments_affected: Optional[List[str]] = None


class HolidayResponse(BaseModel):
    """Holiday response."""
    date: str
    exchange: str
    name: Optional[str]
    type: Optional[str]
    segments_affected: Optional[List[str]]


class ExpiryResponse(BaseModel):
    """Expiry information response."""
    underlying: str
    expiry_date: str
    expiry_type: str
    segment: str
    days_to_expiry: int
    is_current_week: bool
    is_current_month: bool


class LotSizeCreate(BaseModel):
    """Lot size creation request."""
    underlying: str
    lot_size: int
    effective_date: date
    segment: str = "NFO"


class LotSizeResponse(BaseModel):
    """Lot size response."""
    underlying: str
    lot_size: int


class TradingHoursResponse(BaseModel):
    """Trading hours response."""
    exchange: str
    segment: str
    open_time: str
    close_time: str
    pre_open_start: Optional[str]
    pre_open_end: Optional[str]


class CalendarSummaryResponse(BaseModel):
    """Daily calendar summary."""
    date: str
    is_trading_day: bool
    market_status: str
    time_to_open: Optional[str]
    time_to_close: Optional[str]
    expiring_today: List[str]
    upcoming_expiries: List[dict]
    banned_stocks: List[str]
    banned_count: int


class BulkHolidaysRequest(BaseModel):
    """Bulk holiday addition request."""
    holidays: List[HolidayCreate]


class BulkExpiriesRequest(BaseModel):
    """Bulk expiry generation request."""
    underlying: str
    from_date: date
    to_date: date
    include_weekly: bool = True
    include_monthly: bool = True


class BanListUpdate(BaseModel):
    """Ban list update request."""
    date: date
    banned_stocks: List[str]


# =============================================================================
# Calendar Summary Endpoints
# =============================================================================

@router.get("/summary", response_model=CalendarSummaryResponse)
async def get_calendar_summary():
    """
    Get comprehensive calendar summary for today.
    
    Returns trading status, expiries, banned stocks, market hours.
    """
    service = get_calendar_service()
    summary = await service.get_today_summary()
    return CalendarSummaryResponse(**summary)


@router.get("/status")
async def get_market_status(
    exchange: str = Query("NSE", description="Exchange: NSE, BSE, MCX"),
    segment: str = Query("EQ", description="Segment: EQ, FO, CD"),
):
    """
    Get current market status.
    
    Returns whether market is open and time to open/close.
    """
    service = get_calendar_service()
    
    today = date.today()
    is_trading = await service.is_trading_day(today, exchange, segment)
    is_open = service.is_market_open(exchange, segment)
    
    return {
        "date": today.isoformat(),
        "exchange": exchange,
        "segment": segment,
        "is_trading_day": is_trading,
        "is_market_open": is_open,
        "time_to_open": str(service.time_to_market_open(exchange, segment)) if service.time_to_market_open(exchange, segment) else None,
        "time_to_close": str(service.time_to_market_close(exchange, segment)) if service.time_to_market_close(exchange, segment) else None,
    }


@router.get("/trading-hours", response_model=TradingHoursResponse)
async def get_trading_hours(
    exchange: str = Query("NSE", description="Exchange: NSE, BSE, MCX"),
    segment: str = Query("EQ", description="Segment: EQ, FO, CD"),
):
    """Get trading hours for an exchange and segment."""
    service = get_calendar_service()
    hours = service.get_trading_hours(exchange, segment)
    
    return TradingHoursResponse(
        exchange=hours.exchange,
        segment=hours.segment,
        open_time=hours.open_time.isoformat(),
        close_time=hours.close_time.isoformat(),
        pre_open_start=hours.pre_open_start.isoformat() if hours.pre_open_start else None,
        pre_open_end=hours.pre_open_end.isoformat() if hours.pre_open_end else None,
    )


# =============================================================================
# Holiday Endpoints
# =============================================================================

@router.get("/holidays", response_model=List[HolidayResponse])
async def get_holidays(
    year: int = Query(..., description="Year to get holidays for"),
    exchange: str = Query("NSE", description="Exchange: NSE, BSE, MCX"),
):
    """Get all holidays for a year."""
    service = get_calendar_service()
    holidays = await service.get_holidays(year, exchange)
    return [HolidayResponse(**h) for h in holidays]


@router.get("/is-trading-day")
async def check_trading_day(
    check_date: date = Query(..., description="Date to check (YYYY-MM-DD)"),
    exchange: str = Query("NSE", description="Exchange: NSE, BSE, MCX"),
    segment: str = Query("EQ", description="Segment: EQ, FO, CD"),
):
    """Check if a specific date is a trading day."""
    service = get_calendar_service()
    is_trading = await service.is_trading_day(check_date, exchange, segment)
    
    return {
        "date": check_date.isoformat(),
        "exchange": exchange,
        "segment": segment,
        "is_trading_day": is_trading,
    }


@router.get("/next-trading-day")
async def get_next_trading_day(
    from_date: Optional[date] = Query(None, description="Starting date (default: today)"),
    exchange: str = Query("NSE", description="Exchange: NSE, BSE, MCX"),
):
    """Get the next trading day after a given date."""
    service = get_calendar_service()
    
    if from_date is None:
        from_date = date.today()
    
    next_day = await service.get_next_trading_day(from_date, exchange)
    
    return {
        "from_date": from_date.isoformat(),
        "next_trading_day": next_day.isoformat(),
        "days_away": (next_day - from_date).days,
    }


@router.post("/holidays", response_model=dict)
async def add_holiday(holiday: HolidayCreate):
    """Add a single holiday."""
    service = get_calendar_service()
    
    success = await service.add_holiday(
        holiday_date=holiday.date,
        exchange=holiday.exchange,
        name=holiday.name,
        holiday_type=holiday.type,
        segments_affected=holiday.segments_affected,
    )
    
    return {
        "success": success,
        "message": f"Holiday added: {holiday.name} on {holiday.date}",
    }


@router.post("/holidays/bulk", response_model=dict)
async def bulk_add_holidays(request: BulkHolidaysRequest):
    """Bulk add holidays."""
    service = get_calendar_service()
    
    holidays = [
        {
            "date": h.date,
            "exchange": h.exchange,
            "name": h.name,
            "type": h.type,
            "segments_affected": h.segments_affected,
        }
        for h in request.holidays
    ]
    
    count = await service.bulk_add_holidays(holidays)
    
    return {
        "success": True,
        "count": count,
        "message": f"Added {count} holidays",
    }


# =============================================================================
# Expiry Endpoints
# =============================================================================

@router.get("/expiries", response_model=List[ExpiryResponse])
async def get_expiries(
    underlying: str = Query(..., description="Underlying: NIFTY, BANKNIFTY, RELIANCE, etc."),
    from_date: Optional[date] = Query(None, description="Start date"),
    to_date: Optional[date] = Query(None, description="End date"),
    expiry_type: Optional[str] = Query(None, description="WEEKLY or MONTHLY"),
):
    """Get expiry dates for an underlying."""
    service = get_calendar_service()
    
    expiries = await service.get_expiries(
        underlying=underlying,
        from_date=from_date,
        to_date=to_date,
        expiry_type=expiry_type,
    )
    
    return [
        ExpiryResponse(
            underlying=e.underlying,
            expiry_date=e.expiry_date.isoformat(),
            expiry_type=e.expiry_type.value,
            segment=e.segment,
            days_to_expiry=e.days_to_expiry,
            is_current_week=e.is_current_week,
            is_current_month=e.is_current_month,
        )
        for e in expiries
    ]


@router.get("/expiry/current", response_model=Optional[ExpiryResponse])
async def get_current_expiry(
    underlying: str = Query(..., description="Underlying: NIFTY, BANKNIFTY, etc."),
    expiry_type: str = Query("WEEKLY", description="WEEKLY or MONTHLY"),
):
    """Get current (nearest) expiry for an underlying."""
    service = get_calendar_service()
    
    expiry = await service.get_current_expiry(underlying, expiry_type)
    
    if not expiry:
        return None
    
    return ExpiryResponse(
        underlying=expiry.underlying,
        expiry_date=expiry.expiry_date.isoformat(),
        expiry_type=expiry.expiry_type.value,
        segment=expiry.segment,
        days_to_expiry=expiry.days_to_expiry,
        is_current_week=expiry.is_current_week,
        is_current_month=expiry.is_current_month,
    )


@router.get("/expiry/next", response_model=Optional[ExpiryResponse])
async def get_next_expiry(
    underlying: str = Query(..., description="Underlying: NIFTY, BANKNIFTY, etc."),
    expiry_type: str = Query("WEEKLY", description="WEEKLY or MONTHLY"),
):
    """Get next expiry after current."""
    service = get_calendar_service()
    
    expiry = await service.get_next_expiry(underlying, expiry_type)
    
    if not expiry:
        return None
    
    return ExpiryResponse(
        underlying=expiry.underlying,
        expiry_date=expiry.expiry_date.isoformat(),
        expiry_type=expiry.expiry_type.value,
        segment=expiry.segment,
        days_to_expiry=expiry.days_to_expiry,
        is_current_week=expiry.is_current_week,
        is_current_month=expiry.is_current_month,
    )


@router.post("/expiries/generate", response_model=dict)
async def generate_and_add_expiries(request: BulkExpiriesRequest):
    """
    Generate expiry dates for an underlying and add to database.
    
    Calculates expiries based on rules and adjusts for holidays.
    """
    service = get_calendar_service()
    
    # Generate expiries
    expiries = await service.generate_expiries(
        underlying=request.underlying,
        from_date=request.from_date,
        to_date=request.to_date,
        include_weekly=request.include_weekly,
        include_monthly=request.include_monthly,
    )
    
    # Add to database
    count = await service.bulk_add_expiries(expiries)
    
    return {
        "success": True,
        "underlying": request.underlying,
        "count": count,
        "expiries": [
            {
                "date": e["expiry_date"].isoformat(),
                "type": e["expiry_type"],
            }
            for e in expiries
        ],
    }


# =============================================================================
# F&O Ban List Endpoints
# =============================================================================

@router.get("/ban-list", response_model=List[str])
async def get_ban_list(
    check_date: Optional[date] = Query(None, description="Date to check (default: today)"),
):
    """Get list of stocks in F&O ban."""
    service = get_calendar_service()
    banned = await service.get_banned_stocks(check_date)
    return banned


@router.get("/is-banned")
async def check_if_banned(
    underlying: str = Query(..., description="Stock symbol to check"),
    check_date: Optional[date] = Query(None, description="Date to check (default: today)"),
):
    """Check if a stock is in F&O ban."""
    service = get_calendar_service()
    is_banned = await service.is_banned(underlying, check_date)
    
    return {
        "underlying": underlying.upper(),
        "date": (check_date or date.today()).isoformat(),
        "is_banned": is_banned,
    }


@router.post("/ban-list", response_model=dict)
async def update_ban_list(request: BanListUpdate):
    """Update F&O ban list for a date."""
    service = get_calendar_service()
    count = await service.update_ban_list(request.banned_stocks, request.date)
    
    return {
        "success": True,
        "date": request.date.isoformat(),
        "count": count,
        "banned_stocks": [s.upper() for s in request.banned_stocks],
    }


# =============================================================================
# Lot Size Endpoints
# =============================================================================

@router.get("/lot-size")
async def get_lot_size(
    underlying: str = Query(..., description="Underlying symbol"),
    as_of_date: Optional[date] = Query(None, description="Date for historical lookup"),
):
    """Get lot size for an underlying."""
    service = get_calendar_service()
    lot_size = await service.get_lot_size(underlying, as_of_date)
    
    if lot_size is None:
        raise HTTPException(
            status_code=404,
            detail=f"Lot size not found for {underlying}",
        )
    
    return {
        "underlying": underlying.upper(),
        "lot_size": lot_size,
        "as_of_date": (as_of_date or date.today()).isoformat(),
    }


@router.get("/lot-sizes", response_model=dict)
async def get_all_lot_sizes():
    """Get current lot sizes for all underlyings."""
    service = get_calendar_service()
    lot_sizes = await service.get_all_lot_sizes()
    return lot_sizes


@router.post("/lot-size", response_model=dict)
async def update_lot_size(lot_size: LotSizeCreate):
    """Update lot size for an underlying."""
    service = get_calendar_service()
    
    success = await service.update_lot_size(
        underlying=lot_size.underlying,
        new_lot_size=lot_size.lot_size,
        effective_date=lot_size.effective_date,
        segment=lot_size.segment,
    )
    
    return {
        "success": success,
        "message": f"Lot size updated for {lot_size.underlying}: {lot_size.lot_size}",
    }


@router.post("/lot-sizes/bulk", response_model=dict)
async def bulk_add_lot_sizes(lot_sizes: List[LotSizeCreate]):
    """Bulk add lot sizes."""
    service = get_calendar_service()
    
    data = [
        {
            "underlying": ls.underlying,
            "lot_size": ls.lot_size,
            "effective_date": ls.effective_date,
            "segment": ls.segment,
        }
        for ls in lot_sizes
    ]
    
    count = await service.bulk_add_lot_sizes(data)
    
    return {
        "success": True,
        "count": count,
        "message": f"Added {count} lot sizes",
    }
