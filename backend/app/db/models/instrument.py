"""
Domain Models - Instrument & Master Data
KeepGaining Trading Platform

SQLAlchemy models for:
- Instrument Master
- Equity Master
- Future Master
- Option Master
- Sector Master
- Index Constituents
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from sqlalchemy import (
    String, Integer, Boolean, Date, DateTime, Numeric, 
    Text, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class InstrumentMaster(Base):
    """
    Master table for all tradable instruments.
    
    Central reference for equity, index, futures, and options.
    """
    __tablename__ = "instrument_master"
    
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    trading_symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)  # NSE, BSE, NFO, BFO, MCX
    segment: Mapped[str] = mapped_column(String(20), nullable=False)   # EQ, FO, CD, COM
    instrument_type: Mapped[str] = mapped_column(String(20), nullable=False)  # EQUITY, INDEX, FUTURE, OPTION
    underlying: Mapped[Optional[str]] = mapped_column(String(50))  # For derivatives
    isin: Mapped[Optional[str]] = mapped_column(String(12))
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0.05)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    equity: Mapped[Optional["EquityMaster"]] = relationship(back_populates="instrument", uselist=False)
    futures: Mapped[List["FutureMaster"]] = relationship(
        back_populates="instrument",
        foreign_keys="FutureMaster.instrument_id"
    )
    options: Mapped[List["OptionMaster"]] = relationship(
        back_populates="instrument",
        foreign_keys="OptionMaster.instrument_id"
    )
    broker_mappings: Mapped[List["BrokerSymbolMapping"]] = relationship(back_populates="instrument")
    
    __table_args__ = (
        UniqueConstraint('trading_symbol', 'exchange', name='uq_instrument_symbol_exchange'),
        Index('idx_instrument_type', 'instrument_type'),
        Index('idx_instrument_underlying', 'underlying'),
        Index('idx_instrument_active', 'is_active'),
    )
    
    def __repr__(self) -> str:
        return f"<Instrument {self.trading_symbol}:{self.exchange}>"


class EquityMaster(Base):
    """Extended information for equity instruments."""
    __tablename__ = "equity_master"
    
    equity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    face_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    is_fno: Mapped[bool] = mapped_column(Boolean, default=False)
    fno_lot_size: Mapped[Optional[int]] = mapped_column(Integer)
    market_cap_category: Mapped[Optional[str]] = mapped_column(String(20))  # LARGE, MID, SMALL
    listing_date: Mapped[Optional[date]] = mapped_column(Date)
    is_index_constituent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    instrument: Mapped["InstrumentMaster"] = relationship(back_populates="equity")
    
    __table_args__ = (
        Index('idx_equity_fno', 'is_fno'),
        Index('idx_equity_sector', 'sector'),
    )


class FutureMaster(Base):
    """Extended information for futures contracts."""
    __tablename__ = "future_master"
    
    future_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
        nullable=False,
    )
    underlying_instrument_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
    )
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_type: Mapped[Optional[str]] = mapped_column(String(10))  # CURRENT, NEXT, FAR
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    instrument: Mapped["InstrumentMaster"] = relationship(
        back_populates="futures",
        foreign_keys=[instrument_id]
    )
    underlying: Mapped[Optional["InstrumentMaster"]] = relationship(
        foreign_keys=[underlying_instrument_id]
    )
    
    __table_args__ = (
        Index('idx_future_expiry', 'expiry_date'),
        Index('idx_future_underlying', 'underlying_instrument_id'),
    )


class OptionMaster(Base):
    """Extended information for options contracts."""
    __tablename__ = "option_master"
    
    option_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
        nullable=False,
    )
    underlying_instrument_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
    )
    strike_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    option_type: Mapped[str] = mapped_column(String(2), nullable=False)  # CE, PE
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_type: Mapped[Optional[str]] = mapped_column(String(10))  # WEEKLY, MONTHLY
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    instrument: Mapped["InstrumentMaster"] = relationship(
        back_populates="options",
        foreign_keys=[instrument_id]
    )
    underlying: Mapped[Optional["InstrumentMaster"]] = relationship(
        foreign_keys=[underlying_instrument_id]
    )
    greeks: Mapped[List["OptionGreeks"]] = relationship(back_populates="option")
    
    __table_args__ = (
        Index('idx_option_strike', 'strike_price'),
        Index('idx_option_expiry', 'expiry_date'),
        Index('idx_option_type', 'option_type'),
        Index('idx_option_underlying', 'underlying_instrument_id'),
        Index('idx_option_composite', 'underlying_instrument_id', 'strike_price', 'option_type', 'expiry_date'),
    )


class SectorMaster(Base):
    """Sector/Industry classification."""
    __tablename__ = "sector_master"
    
    sector_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    sector_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    sector_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    parent_sector_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sector_master.sector_id"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Self-referential relationship for hierarchy
    parent: Mapped[Optional["SectorMaster"]] = relationship(
        "SectorMaster",
        remote_side=[sector_id],
        backref="children"
    )


class IndexConstituents(Base):
    """Index composition and weights."""
    __tablename__ = "index_constituents"
    
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    index_instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
        nullable=False,
    )
    constituent_instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
        nullable=False,
    )
    weight: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date)  # NULL = current constituent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    index: Mapped["InstrumentMaster"] = relationship(
        foreign_keys=[index_instrument_id]
    )
    constituent: Mapped["InstrumentMaster"] = relationship(
        foreign_keys=[constituent_instrument_id]
    )
    
    __table_args__ = (
        Index('idx_constituent_index', 'index_instrument_id'),
        Index('idx_constituent_stock', 'constituent_instrument_id'),
        Index('idx_constituent_effective', 'effective_date'),
    )


# Forward reference imports
from app.db.models.broker import BrokerSymbolMapping
from app.db.models.timeseries import OptionGreeks
