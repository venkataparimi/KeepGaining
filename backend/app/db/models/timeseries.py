"""
Domain Models - Time Series Data
KeepGaining Trading Platform

SQLAlchemy models for:
- Candle Data (OHLCV)
- Indicator Data
- Option Greeks
- Option Chain Snapshot
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Any, Dict
from uuid import UUID

from sqlalchemy import (
    String, Integer, BigInteger, SmallInteger, Boolean, 
    DateTime, Numeric, Text, ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class CandleData(Base):
    """
    OHLCV candle data with composite primary key.
    
    Optimized for time-series queries with proper indexing.
    """
    __tablename__ = "candle_data"
    
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
        primary_key=True,
    )
    timeframe: Mapped[str] = mapped_column(String(5), primary_key=True)  # 1m, 5m, 15m, 1h, 1d
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    
    open: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    oi: Mapped[Optional[int]] = mapped_column(BigInteger)  # Open Interest for derivatives
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_candle_time', 'timestamp'),
        Index('idx_candle_instrument_time', 'instrument_id', 'timestamp'),
    )


class IndicatorData(Base):
    """
    Pre-computed indicator values.
    
    Stored separately from candles for flexibility and performance.
    """
    __tablename__ = "indicator_data"
    
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
        primary_key=True,
    )
    timeframe: Mapped[str] = mapped_column(String(5), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    
    # Moving Averages
    sma_9: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    sma_20: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    sma_50: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    sma_200: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ema_9: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ema_21: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ema_50: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ema_200: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    
    # Volume Weighted MAs
    vwap: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    vwma_20: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    vwma_22: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))  # Custom fast VWMA (Fibonacci)
    vwma_31: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))  # Custom slow VWMA (Fibonacci)
    
    # Momentum Indicators
    rsi_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    macd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    macd_signal: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    macd_histogram: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    stoch_k: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    stoch_d: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    cci: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    williams_r: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    
    # Volatility
    atr_14: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    bb_upper: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    bb_middle: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    bb_lower: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    
    # Trend
    adx: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    plus_di: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    minus_di: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    supertrend: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    supertrend_direction: Mapped[Optional[int]] = mapped_column(SmallInteger)  # 1=up, -1=down
    
    # Pivot Points (Classic)
    pivot_point: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    pivot_r1: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    pivot_r2: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    pivot_r3: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    pivot_s1: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    pivot_s2: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    pivot_s3: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    
    # Camarilla Pivot Points
    cam_r4: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    cam_r3: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    cam_r2: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    cam_r1: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    cam_s1: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    cam_s2: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    cam_s3: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    cam_s4: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    
    # Volume Analysis
    obv: Mapped[Optional[int]] = mapped_column(BigInteger)
    volume_sma_20: Mapped[Optional[int]] = mapped_column(BigInteger)
    volume_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_indicator_time', 'timestamp'),
    )


class OptionGreeks(Base):
    """Option Greeks and IV for options analysis."""
    __tablename__ = "option_greeks"
    
    option_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("option_master.option_id"),
        primary_key=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    
    underlying_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    option_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    iv: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))  # Implied Volatility
    delta: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 6))
    gamma: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 6))
    theta: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 6))
    vega: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 6))
    rho: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 6))
    oi: Mapped[Optional[int]] = mapped_column(BigInteger)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    bid: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    ask: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    option: Mapped["OptionMaster"] = relationship(back_populates="greeks")
    
    __table_args__ = (
        Index('idx_greeks_time', 'timestamp'),
    )


class OptionChainSnapshot(Base):
    """Full option chain snapshot for an underlying."""
    __tablename__ = "option_chain_snapshot"
    
    snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    underlying_instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
        nullable=False,
    )
    expiry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    underlying_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    
    # Full chain as JSONB for flexibility
    chain_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    
    # Aggregated metrics
    pcr_oi: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))  # Put-Call Ratio (OI)
    pcr_volume: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))  # Put-Call Ratio (Volume)
    max_pain: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    iv_skew: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_chain_underlying', 'underlying_instrument_id'),
        Index('idx_chain_expiry', 'expiry_date'),
        Index('idx_chain_time', 'timestamp'),
    )


# Forward reference
from app.db.models.instrument import OptionMaster
