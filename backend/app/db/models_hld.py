"""
Database Models - Aligned with HIGH_LEVEL_DESIGN.md
KeepGaining Trading Platform

This module contains all database models as specified in the HLD Section 4 (Data Model).
Designed for PostgreSQL with TimescaleDB support for time-series data.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, ForeignKey, 
    JSON, BigInteger, Text, Date, Time, SmallInteger, Numeric,
    Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
import enum

from app.db.base import Base


# =============================================================================
# ENUMS
# =============================================================================

class InstrumentType(str, enum.Enum):
    INDEX = "INDEX"
    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION = "OPTION"


class OptionType(str, enum.Enum):
    CE = "CE"  # Call
    PE = "PE"  # Put


class ExpiryType(str, enum.Enum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class ProductType(str, enum.Enum):
    MIS = "MIS"      # Intraday
    CNC = "CNC"      # Delivery (equity)
    NRML = "NRML"    # Normal (F&O overnight)


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class StrategyStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PAPER = "PAPER"
    LIVE = "LIVE"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


# =============================================================================
# MASTER DATA ENTITIES (HLD 4.1)
# =============================================================================

class InstrumentMaster(Base):
    """
    Master table for all tradeable instruments.
    HLD Section 4.1.1
    """
    __tablename__ = "instrument_master"
    
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    symbol: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(200))
    instrument_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    segment: Mapped[Optional[str]] = mapped_column(String(20))  # CASH, FO, CURRENCY, COMMODITY
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    tick_size: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    is_tradeable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    
    __table_args__ = {'extend_existing': True}
    is_fo_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    isin: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    equity_details = relationship("EquityMaster", back_populates="instrument", uselist=False)
    future_details = relationship("FutureMaster", back_populates="instrument", uselist=False)
    option_details = relationship("OptionMaster", back_populates="instrument", uselist=False)
    candles = relationship("CandleData", back_populates="instrument")
    broker_mappings = relationship("BrokerSymbolMapping", back_populates="instrument")


class SectorMaster(Base):
    """
    Sector master for categorizing equities.
    HLD Section 4.1.5
    """
    __tablename__ = "sector_master"
    
    sector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sector_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    sector_index_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id")
    )
    parent_sector_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sector_master.sector_id")
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    equities = relationship("EquityMaster", back_populates="sector")
    parent = relationship("SectorMaster", remote_side=[sector_id])


class EquityMaster(Base):
    """
    Equity-specific details.
    HLD Section 4.1.2
    """
    __tablename__ = "equity_master"
    
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), primary_key=True
    )
    sector_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sector_master.sector_id")
    )
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    free_float_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    face_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    indices: Mapped[Optional[dict]] = mapped_column(JSONB)  # Array of index memberships
    
    # Relationships
    instrument = relationship("InstrumentMaster", back_populates="equity_details")
    sector = relationship("SectorMaster", back_populates="equities")


class FutureMaster(Base):
    """
    Futures contract details.
    HLD Section 4.1.3
    """
    __tablename__ = "future_master"
    
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), primary_key=True
    )
    underlying_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), nullable=False, index=True
    )
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    expiry_type: Mapped[Optional[str]] = mapped_column(String(20))  # WEEKLY, MONTHLY, QUARTERLY
    contract_size: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Relationships
    instrument = relationship("InstrumentMaster", back_populates="future_details", foreign_keys=[instrument_id])
    underlying = relationship("InstrumentMaster", foreign_keys=[underlying_id])


class OptionMaster(Base):
    """
    Options contract details.
    HLD Section 4.1.4
    """
    __tablename__ = "option_master"
    
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), primary_key=True
    )
    underlying_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), nullable=False, index=True
    )
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    expiry_type: Mapped[Optional[str]] = mapped_column(String(20))  # WEEKLY, MONTHLY
    strike_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, index=True)
    option_type: Mapped[str] = mapped_column(String(2), nullable=False)  # CE, PE
    contract_size: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Relationships
    instrument = relationship("InstrumentMaster", back_populates="option_details", foreign_keys=[instrument_id])
    underlying = relationship("InstrumentMaster", foreign_keys=[underlying_id])
    
    # Indexes
    __table_args__ = (
        Index("idx_option_underlying_expiry", "underlying_id", "expiry_date"),
    )


class IndexConstituent(Base):
    """
    Index constituent membership with weights.
    HLD Section 4.1.6
    """
    __tablename__ = "index_constituents"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), index=True
    )
    equity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), index=True
    )
    weight: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date)


# =============================================================================
# TIME-SERIES DATA (HLD 4.2)
# =============================================================================

class CandleData(Base):
    """
    Base candle data (1-minute). TimescaleDB hypertable.
    HLD Section 4.2.1
    """
    __tablename__ = "candle_data"
    
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), 
        primary_key=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    oi: Mapped[int] = mapped_column(BigInteger, default=0)
    oi_change: Mapped[int] = mapped_column(BigInteger, default=0)
    trades_count: Mapped[Optional[int]] = mapped_column(Integer)
    vwap: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    delivery_volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    # Relationship
    instrument = relationship("InstrumentMaster", back_populates="candles")


class IndicatorData(Base):
    """
    Pre-computed indicators for various timeframes.
    HLD Section 4.2.2
    """
    __tablename__ = "indicator_data"
    
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), 
        primary_key=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    timeframe: Mapped[str] = mapped_column(String(10), primary_key=True, nullable=False)
    
    # Moving Averages
    sma_9: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    sma_20: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    sma_50: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    sma_200: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    ema_9: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    ema_21: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    ema_50: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    vwma_20: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    vwma_22: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    vwma_31: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    
    # Momentum
    rsi_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    macd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    macd_signal: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    macd_histogram: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    stoch_k: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    stoch_d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    
    # Volatility
    atr_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    bb_upper: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    bb_middle: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    bb_lower: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    bb_width: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    
    # Volume
    obv: Mapped[Optional[int]] = mapped_column(BigInteger)
    volume_sma_20: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    # Trend
    adx_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    supertrend: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    supertrend_direction: Mapped[Optional[int]] = mapped_column(SmallInteger)


class OptionGreeks(Base):
    """
    Option Greeks for options contracts.
    HLD Section 4.2.3
    """
    __tablename__ = "option_greeks"
    
    option_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"),
        primary_key=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    underlying_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    iv: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    delta: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    gamma: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    theta: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    vega: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    rho: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    intrinsic_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    extrinsic_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    bid_iv: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    ask_iv: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))


class OptionChainSnapshot(Base):
    """
    Option chain snapshot data.
    HLD Section 4.2.4
    """
    __tablename__ = "option_chain_snapshot"
    
    underlying_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"),
        primary_key=True, nullable=False
    )
    expiry_date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    strike: Mapped[Decimal] = mapped_column(Numeric(10, 2), primary_key=True, nullable=False)
    
    # Call data
    ce_ltp: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    ce_oi: Mapped[Optional[int]] = mapped_column(BigInteger)
    ce_oi_change: Mapped[Optional[int]] = mapped_column(BigInteger)
    ce_volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    ce_iv: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    ce_delta: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    
    # Put data
    pe_ltp: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    pe_oi: Mapped[Optional[int]] = mapped_column(BigInteger)
    pe_oi_change: Mapped[Optional[int]] = mapped_column(BigInteger)
    pe_volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    pe_iv: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    pe_delta: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    
    # Aggregates
    pcr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    max_pain: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))


# =============================================================================
# BROKER INTEGRATION (HLD 4.3)
# =============================================================================

class BrokerSymbolMapping(Base):
    """
    Symbol mapping between internal format and broker format.
    HLD Section 4.3.1
    """
    __tablename__ = "broker_symbol_mapping"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), nullable=False
    )
    broker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    broker_symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    broker_token: Mapped[Optional[str]] = mapped_column(String(50))
    segment: Mapped[Optional[str]] = mapped_column(String(50))
    last_verified: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    instrument = relationship("InstrumentMaster", back_populates="broker_mappings")
    
    __table_args__ = (
        UniqueConstraint("instrument_id", "broker", name="uq_instrument_broker"),
        Index("idx_broker_symbol", "broker", "broker_symbol"),
    )


class BrokerConfig(Base):
    """
    Broker configuration and capabilities.
    HLD Section 4.3.2
    """
    __tablename__ = "broker_config"
    
    broker_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=99)
    use_for_live_feed: Mapped[bool] = mapped_column(Boolean, default=False)
    use_for_historical: Mapped[bool] = mapped_column(Boolean, default=False)
    use_for_trading: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_limit_per_second: Mapped[Optional[int]] = mapped_column(Integer)
    rate_limit_per_minute: Mapped[Optional[int]] = mapped_column(Integer)
    websocket_limit: Mapped[Optional[int]] = mapped_column(Integer)
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    last_auth_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# =============================================================================
# CALENDAR DATA (HLD 4.4)
# =============================================================================

class ExpiryCalendar(Base):
    """
    Expiry calendar for derivatives.
    HLD Section 4.4.1
    """
    __tablename__ = "expiry_calendar"
    
    expiry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    underlying: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    expiry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_expiry: Mapped[date] = mapped_column(Date, nullable=False)
    actual_expiry: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    expiry_day: Mapped[Optional[str]] = mapped_column(String(20))
    is_holiday_adjusted: Mapped[bool] = mapped_column(Boolean, default=False)
    contract_start: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class HolidayCalendar(Base):
    """
    Trading holidays.
    HLD Section 4.4.2
    """
    __tablename__ = "holiday_calendar"
    
    holiday_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    holiday_name: Mapped[Optional[str]] = mapped_column(String(200))
    holiday_type: Mapped[Optional[str]] = mapped_column(String(20))  # FULL, PARTIAL
    market_open: Mapped[Optional[datetime]] = mapped_column(Time)
    market_close: Mapped[Optional[datetime]] = mapped_column(Time)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    source: Mapped[Optional[str]] = mapped_column(String(100))


class LotSizeHistory(Base):
    """
    Lot size change history for backtesting accuracy.
    HLD Section 4.4.3
    """
    __tablename__ = "lot_size_history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), index=True
    )
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FOBanList(Base):
    """
    F&O ban list tracking.
    HLD Section 4.4.4
    """
    __tablename__ = "fo_ban_list"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id"), index=True
    )
    ban_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    entry_reason: Mapped[Optional[str]] = mapped_column(String(100))
    exit_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint("instrument_id", "ban_date", name="uq_ban_instrument_date"),
    )


class MasterDataRefreshLog(Base):
    """
    Master data refresh tracking.
    HLD Section 4.4.5
    """
    __tablename__ = "master_data_refresh_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    refresh_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    records_added: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_deleted: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[Optional[str]] = mapped_column(String(20))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)


# =============================================================================
# TRADING DATA (HLD 4.5)
# =============================================================================

class StrategyConfig(Base):
    """
    Strategy configuration.
    HLD Section 4.5.1
    """
    __tablename__ = "strategy_config"
    
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[Optional[str]] = mapped_column(String(20))
    config: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    definition = relationship("StrategyDefinition", back_populates="strategy", uselist=False)
    orders = relationship("Order", back_populates="strategy")
    trades = relationship("Trade", back_populates="strategy")
    positions = relationship("Position", back_populates="strategy")


class StrategyDefinition(Base):
    """
    Strategy rules and logic definition.
    HLD Section 4.5.1.2
    """
    __tablename__ = "strategy_definition"
    
    definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_config.strategy_id"), index=True
    )
    
    # Entry conditions
    entry_rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    entry_timeframe: Mapped[Optional[str]] = mapped_column(String(10))
    entry_confirmation_tf: Mapped[Optional[str]] = mapped_column(String(10))
    
    # Exit conditions
    exit_rules: Mapped[Optional[dict]] = mapped_column(JSONB)
    sl_type: Mapped[Optional[str]] = mapped_column(String(20))
    sl_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    target_type: Mapped[Optional[str]] = mapped_column(String(20))
    target_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    trailing_sl_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trailing_sl_trigger: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    trailing_sl_step: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    
    # Position sizing
    position_size_type: Mapped[Optional[str]] = mapped_column(String(20))
    position_size_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    max_positions: Mapped[int] = mapped_column(Integer, default=1)
    
    # Filters
    instrument_filter: Mapped[Optional[dict]] = mapped_column(JSONB)
    time_filter: Mapped[Optional[dict]] = mapped_column(JSONB)
    market_filter: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # Risk overrides
    max_daily_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    max_daily_trades: Mapped[Optional[int]] = mapped_column(Integer)
    consecutive_loss_limit: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Metadata
    logic_description: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[Optional[str]] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationship
    strategy = relationship("StrategyConfig", back_populates="definition")


class Order(Base):
    """
    Order records.
    HLD Section 4.5.3
    """
    __tablename__ = "orders"
    
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_config.strategy_id")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id")
    )
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    product_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    trigger_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_fill_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    reject_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    strategy = relationship("StrategyConfig", back_populates="orders")
    instrument = relationship("InstrumentMaster")
    trades = relationship("Trade", back_populates="order")


class Trade(Base):
    """
    Trade records.
    HLD Section 4.5.4
    """
    __tablename__ = "trades"
    
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.order_id")
    )
    strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_config.strategy_id")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id")
    )
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(50))
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    entry_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    pnl_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    commission: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    status: Mapped[Optional[str]] = mapped_column(String(20))
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # Relationships
    order = relationship("Order", back_populates="trades")
    strategy = relationship("StrategyConfig", back_populates="trades")
    instrument = relationship("InstrumentMaster")


class Position(Base):
    """
    Open positions.
    HLD Section 4.5.5
    """
    __tablename__ = "positions"
    
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument_master.instrument_id")
    )
    strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_config.strategy_id")
    )
    side: Mapped[Optional[str]] = mapped_column(String(10))
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    avg_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    sl_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    target_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    trailing_sl: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    instrument = relationship("InstrumentMaster")
    strategy = relationship("StrategyConfig", back_populates="positions")


# =============================================================================
# AUDIT & LOGS (HLD 4.6)
# =============================================================================

class SignalLog(Base):
    """
    Strategy signal log.
    HLD Section 4.6.1
    """
    __tablename__ = "signal_log"
    
    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    instrument_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signal_type: Mapped[Optional[str]] = mapped_column(String(20))
    strength: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB)
    executed: Mapped[bool] = mapped_column(Boolean, default=False)


class OrderLog(Base):
    """
    Order event log.
    HLD Section 4.6.2
    """
    __tablename__ = "order_log"
    
    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[Optional[str]] = mapped_column(String(50))
    strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    instrument_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    order_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    broker_response: Mapped[Optional[dict]] = mapped_column(JSONB)
