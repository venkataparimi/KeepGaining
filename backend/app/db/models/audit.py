"""
Domain Models - Audit & Logging
KeepGaining Trading Platform

SQLAlchemy models for:
- Signal Log
- System Event Log
- Daily P&L
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Any, Dict, List
from uuid import UUID

from sqlalchemy import (
    String, Integer, Boolean, Date, DateTime, Numeric, 
    Text, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SignalLog(Base):
    """
    Trading signal audit log.
    
    Records all generated signals with context.
    """
    __tablename__ = "signal_log"
    
    signal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    strategy_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_config.strategy_id"),
    )
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
        nullable=False,
    )
    
    # Signal Details
    signal_type: Mapped[str] = mapped_column(String(20), nullable=False)  # ENTRY_LONG, ENTRY_SHORT, EXIT
    signal_strength: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))  # 0-100
    timeframe: Mapped[Optional[str]] = mapped_column(String(5))
    conditions_met: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)  # Which conditions triggered
    indicator_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)  # Snapshot of indicators
    
    # Market Context
    market_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    bid: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    ask: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    
    # Execution
    was_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_reason: Mapped[Optional[str]] = mapped_column(Text)  # Why it was/wasn't executed
    order_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True))
    
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_signal_strategy', 'strategy_id'),
        Index('idx_signal_instrument', 'instrument_id'),
        Index('idx_signal_type', 'signal_type'),
        Index('idx_signal_time', 'generated_at'),
    )


class SystemEventLog(Base):
    """
    System event audit log.
    
    Records system lifecycle events, errors, warnings.
    """
    __tablename__ = "system_event_log"
    
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # STARTUP, SHUTDOWN, ERROR, WARNING, BROKER_CONNECT, BROKER_DISCONNECT, etc.
    event_source: Mapped[Optional[str]] = mapped_column(String(100))  # Component
    severity: Mapped[str] = mapped_column(String(20), default='INFO')  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)  # Additional structured data
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_event_type', 'event_type'),
        Index('idx_event_severity', 'severity'),
        Index('idx_event_time', 'created_at'),
    )


class DailyPnL(Base):
    """
    Daily P&L aggregation.
    
    Performance tracking by day and strategy.
    """
    __tablename__ = "daily_pnl"
    
    pnl_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    strategy_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_config.strategy_id"),
    )
    
    # P&L Summary
    gross_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    brokerage: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    taxes: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    net_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    
    # Trade Statistics
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    max_drawdown: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    max_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    
    # Capital
    opening_capital: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    closing_capital: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('date', 'strategy_id', name='uq_daily_pnl'),
        Index('idx_pnl_date', 'date'),
        Index('idx_pnl_strategy', 'strategy_id'),
    )
