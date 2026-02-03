"""
Domain Models - Calendar & Master Data
KeepGaining Trading Platform

SQLAlchemy models for:
- Expiry Calendar
- Holiday Calendar
- Lot Size History
- F&O Ban List
- Master Data Refresh Log
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from sqlalchemy import (
    String, Integer, Boolean, Date, DateTime, Numeric, 
    Text, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ExpiryCalendar(Base):
    """
    Expiry dates for derivatives.
    
    Tracks weekly and monthly expiries for all F&O instruments.
    """
    __tablename__ = "expiry_calendar"
    
    expiry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    underlying: Mapped[str] = mapped_column(String(50), nullable=False)  # NIFTY, BANKNIFTY, RELIANCE
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_type: Mapped[str] = mapped_column(String(10), nullable=False)  # WEEKLY, MONTHLY
    segment: Mapped[str] = mapped_column(String(10), nullable=False)  # NFO, BFO, MCX
    is_trading_day: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('underlying', 'expiry_date', 'segment', name='uq_expiry'),
        Index('idx_expiry_date', 'expiry_date'),
        Index('idx_expiry_underlying', 'underlying'),
    )


class HolidayCalendar(Base):
    """
    Market holidays by exchange.
    
    Tracks full and half-day holidays for trading decisions.
    """
    __tablename__ = "holiday_calendar"
    
    holiday_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)  # NSE, BSE, MCX
    holiday_name: Mapped[Optional[str]] = mapped_column(String(100))
    holiday_type: Mapped[Optional[str]] = mapped_column(String(20))  # FULL, MORNING, EVENING
    segments_affected: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))  # ['EQ', 'FO', 'CD']
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('date', 'exchange', name='uq_holiday'),
        Index('idx_holiday_date', 'date'),
        Index('idx_holiday_exchange', 'exchange'),
    )


class LotSizeHistory(Base):
    """
    Historical lot size changes.
    
    Tracks lot size changes over time for accurate backtesting.
    """
    __tablename__ = "lot_size_history"
    
    history_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    underlying: Mapped[str] = mapped_column(String(50), nullable=False)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date)  # NULL = current lot size
    segment: Mapped[str] = mapped_column(String(10), nullable=False)  # NFO, BFO, MCX
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_lot_underlying', 'underlying'),
        Index('idx_lot_effective', 'effective_date'),
    )


class FOBanList(Base):
    """
    F&O securities under ban.
    
    Tracks stocks in F&O ban due to exceeding MWPL.
    """
    __tablename__ = "fo_ban_list"
    
    ban_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    underlying: Mapped[str] = mapped_column(String(50), nullable=False)
    ban_date: Mapped[date] = mapped_column(Date, nullable=False)
    mwpl_percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))  # Market-wide position limit %
    is_banned: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('underlying', 'ban_date', name='uq_ban'),
        Index('idx_ban_date', 'ban_date'),
        Index('idx_ban_underlying', 'underlying'),
    )


class MasterDataRefreshLog(Base):
    """
    Audit log for master data updates.
    
    Tracks symbol master refreshes, expiry updates, etc.
    """
    __tablename__ = "master_data_refresh_log"
    
    log_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)  # SYMBOL_MASTER, EXPIRY, HOLIDAY, LOT_SIZE
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # FYERS, UPSTOX, NSE
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # SUCCESS, FAILED, PARTIAL
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_added: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_refresh_type', 'data_type'),
        Index('idx_refresh_status', 'status'),
        Index('idx_refresh_time', 'started_at'),
    )
