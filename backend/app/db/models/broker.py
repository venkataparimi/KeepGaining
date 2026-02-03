"""
Domain Models - Broker Integration
KeepGaining Trading Platform

SQLAlchemy models for:
- Broker Symbol Mapping
- Broker Config
- Rate Limit Tracker
"""

from datetime import datetime
from typing import Optional, Any, Dict
from uuid import UUID

from sqlalchemy import (
    String, Integer, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class BrokerSymbolMapping(Base):
    """
    Maps internal instruments to broker-specific symbols.
    
    Enables multi-broker support with different symbol formats.
    """
    __tablename__ = "broker_symbol_mapping"
    
    mapping_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instrument_master.instrument_id"),
        nullable=False,
    )
    broker_name: Mapped[str] = mapped_column(String(20), nullable=False)  # FYERS, UPSTOX, ZERODHA
    broker_symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    broker_token: Mapped[Optional[str]] = mapped_column(String(50))  # Broker-specific token/ID
    exchange_code: Mapped[Optional[str]] = mapped_column(String(10))  # Broker's exchange code
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    instrument: Mapped["InstrumentMaster"] = relationship(back_populates="broker_mappings")
    
    __table_args__ = (
        UniqueConstraint('broker_name', 'broker_symbol', name='uq_broker_symbol'),
        Index('idx_mapping_instrument', 'instrument_id'),
        Index('idx_mapping_broker', 'broker_name'),
        Index('idx_mapping_broker_token', 'broker_name', 'broker_token'),
    )


class BrokerConfig(Base):
    """
    Broker configuration and credentials.
    
    Stores API keys, rate limits, and capabilities.
    """
    __tablename__ = "broker_config"
    
    config_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    broker_name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_primary_data: Mapped[bool] = mapped_column(Boolean, default=False)  # Primary for market data
    is_primary_trading: Mapped[bool] = mapped_column(Boolean, default=False)  # Primary for trading
    
    # API Configuration (encrypted in production)
    api_key: Mapped[Optional[str]] = mapped_column(String(255))
    api_secret: Mapped[Optional[str]] = mapped_column(String(255))
    user_id: Mapped[Optional[str]] = mapped_column(String(50))
    redirect_uri: Mapped[Optional[str]] = mapped_column(String(255))
    totp_secret: Mapped[Optional[str]] = mapped_column(String(100))  # For auto-login
    
    # Rate Limits
    rate_limit_per_second: Mapped[int] = mapped_column(Integer, default=10)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=200)
    rate_limit_per_day: Mapped[int] = mapped_column(Integer, default=10000)
    
    # Capabilities
    supports_websocket: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_historical: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_options: Mapped[bool] = mapped_column(Boolean, default=True)
    max_websocket_symbols: Mapped[int] = mapped_column(Integer, default=100)
    
    # Additional settings
    settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())


class RateLimitTracker(Base):
    """
    Tracks API usage for rate limiting.
    
    Prevents hitting broker rate limits.
    """
    __tablename__ = "rate_limit_tracker"
    
    tracker_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    broker_name: Mapped[str] = mapped_column(String(20), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_type: Mapped[str] = mapped_column(String(10), nullable=False)  # SECOND, MINUTE, DAY
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    last_request_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    __table_args__ = (
        Index('idx_rate_broker_endpoint', 'broker_name', 'endpoint'),
        Index('idx_rate_window', 'window_start'),
    )


# Forward reference
from app.db.models.instrument import InstrumentMaster
