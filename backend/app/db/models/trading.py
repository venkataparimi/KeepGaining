"""
Domain Models - Trading & Strategy
KeepGaining Trading Platform

SQLAlchemy models for:
- Strategy Config
- Strategy Definition
- Orders
- Trades
- Positions
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional, Any, Dict, List
from uuid import UUID

from sqlalchemy import (
    String, Integer, Boolean, Date, DateTime, Time, Numeric, 
    Text, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class StrategyConfig(Base):
    """
    Strategy configuration and parameters.
    
    Defines trading parameters, risk limits, and execution settings.
    """
    __tablename__ = "strategy_config"
    
    strategy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    strategy_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)  # INTRADAY, SWING, POSITIONAL
    description: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(20), default='1.0.0')
    
    # Trading Parameters
    instruments: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)  # Allowed instruments
    timeframes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)  # ['1m', '5m', '15m']
    entry_time_start: Mapped[Optional[time]] = mapped_column(Time)
    entry_time_end: Mapped[Optional[time]] = mapped_column(Time)
    exit_time: Mapped[Optional[time]] = mapped_column(Time)  # Force exit time
    
    # Risk Parameters
    max_positions: Mapped[int] = mapped_column(Integer, default=5)
    position_size_type: Mapped[str] = mapped_column(String(20), default='FIXED')  # FIXED, PERCENT, RISK_BASED
    position_size_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    default_sl_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    default_target_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    max_loss_per_day: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    max_loss_per_trade: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    trailing_sl_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trailing_sl_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    
    # Execution Settings
    order_type: Mapped[str] = mapped_column(String(20), default='MARKET')  # MARKET, LIMIT
    product_type: Mapped[str] = mapped_column(String(20), default='INTRADAY')  # INTRADAY, DELIVERY, MARGIN
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_paper_trading: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    definitions: Mapped[List["StrategyDefinition"]] = relationship(back_populates="strategy")
    orders: Mapped[List["Order"]] = relationship(back_populates="strategy")
    positions: Mapped[List["Position"]] = relationship(back_populates="strategy")
    
    __table_args__ = (
        Index('idx_strategy_active', 'is_active'),
        Index('idx_strategy_type', 'strategy_type'),
    )


class StrategyDefinition(Base):
    """
    Strategy logic and conditions.
    
    Stores entry/exit conditions in structured format for UI editing.
    """
    __tablename__ = "strategy_definition"
    
    definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    strategy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_config.strategy_id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Trading Parameters
    instrument_types: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)  # ["INDEX_OPTION", "STOCK_OPTION"]
    allowed_instruments: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)  # Specific or "ALL"
    timeframes: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)  # ["5m", "15m"]
    trading_sessions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)  # Market hour restrictions
    
    # Entry Conditions (structured JSON for UI)
    entry_conditions: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    entry_logic: Mapped[Optional[str]] = mapped_column(Text)  # Human-readable
    
    # Exit Conditions
    exit_conditions: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    exit_logic: Mapped[Optional[str]] = mapped_column(Text)
    
    # Risk Parameters (override strategy_config)
    default_sl_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    default_target_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    max_positions: Mapped[Optional[int]] = mapped_column(Integer)
    position_size_type: Mapped[Optional[str]] = mapped_column(String(20))
    position_size_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    
    # Metadata
    tags: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    backtested: Mapped[bool] = mapped_column(Boolean, default=False)
    backtest_results: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    strategy: Mapped["StrategyConfig"] = relationship(back_populates="definitions")
    
    __table_args__ = (
        Index('idx_definition_strategy', 'strategy_id'),
        Index('idx_definition_active', 'is_active'),
    )


class Order(Base):
    """
    Order records with full lifecycle tracking.
    """
    __tablename__ = "orders"
    
    order_id: Mapped[UUID] = mapped_column(
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
    
    # Order Details
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)  # MARKET, LIMIT, SL, SL-M
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY, SELL
    product_type: Mapped[str] = mapped_column(String(20), nullable=False)  # INTRADAY, DELIVERY, MARGIN
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))  # For limit orders
    trigger_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))  # For SL orders
    
    # Broker Details
    broker_name: Mapped[Optional[str]] = mapped_column(String(20))
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(50))
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='PENDING')
    # PENDING, PLACED, OPEN, PARTIAL, FILLED, CANCELLED, REJECTED
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timestamps
    placed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    strategy: Mapped[Optional["StrategyConfig"]] = relationship(back_populates="orders")
    trades: Mapped[List["Trade"]] = relationship(back_populates="order")
    logs: Mapped[List["OrderLog"]] = relationship(back_populates="order")
    
    __table_args__ = (
        Index('idx_order_strategy', 'strategy_id'),
        Index('idx_order_instrument', 'instrument_id'),
        Index('idx_order_status', 'status'),
        Index('idx_order_broker', 'broker_name', 'broker_order_id'),
        Index('idx_order_created', 'created_at'),
    )


class Trade(Base):
    """
    Trade execution records.
    """
    __tablename__ = "trades"
    
    trade_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orders.order_id"),
        nullable=False,
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
    
    # Trade Details
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY, SELL
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    
    # Broker Details
    broker_name: Mapped[Optional[str]] = mapped_column(String(20))
    broker_trade_id: Mapped[Optional[str]] = mapped_column(String(50))
    exchange_trade_id: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Timestamps
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    order: Mapped["Order"] = relationship(back_populates="trades")
    
    __table_args__ = (
        Index('idx_trade_order', 'order_id'),
        Index('idx_trade_strategy', 'strategy_id'),
        Index('idx_trade_instrument', 'instrument_id'),
        Index('idx_trade_executed', 'executed_at'),
    )


class Position(Base):
    """
    Active and closed positions.
    """
    __tablename__ = "positions"
    
    position_id: Mapped[UUID] = mapped_column(
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
    
    # Position Details
    side: Mapped[str] = mapped_column(String(5), nullable=False)  # LONG, SHORT
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    
    # Risk Management
    stop_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    target: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    trailing_sl: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    
    # P&L
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='OPEN')  # OPEN, CLOSED
    
    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    strategy: Mapped[Optional["StrategyConfig"]] = relationship(back_populates="positions")
    
    __table_args__ = (
        Index('idx_position_strategy', 'strategy_id'),
        Index('idx_position_instrument', 'instrument_id'),
        Index('idx_position_status', 'status'),
        Index('idx_position_opened', 'opened_at'),
    )


class OrderLog(Base):
    """
    Order state change audit log.
    """
    __tablename__ = "order_log"
    
    log_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orders.order_id"),
        nullable=False,
    )
    
    # State Change
    previous_status: Mapped[Optional[str]] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    change_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Broker Response
    broker_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    
    # Metadata
    changed_by: Mapped[Optional[str]] = mapped_column(String(50))  # SYSTEM, BROKER, USER
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    order: Mapped["Order"] = relationship(back_populates="logs")
    
    __table_args__ = (
        Index('idx_orderlog_order', 'order_id'),
        Index('idx_orderlog_time', 'created_at'),
    )
