from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Enum, JSON, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.base import Base

class InstrumentType(str, enum.Enum):
    EQUITY = "EQUITY"
    OPTION = "OPTION"
    FUTURE = "FUTURE"
    INDEX = "INDEX"

class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class Instrument(Base):
    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True, nullable=False)
    exchange = Column(String, nullable=False)
    type = Column(String, nullable=False)  # Enum: InstrumentType
    lot_size = Column(Integer, default=1)
    tick_size = Column(Float, default=0.05)
    is_active = Column(Boolean, default=True)
    
    market_data = relationship("MarketData", back_populates="instrument")

class MarketData(Base):
    __tablename__ = "market_data"

    # Composite primary key handled by TimescaleDB usually, but for ORM:
    time = Column(DateTime(timezone=True), primary_key=True, nullable=False)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), primary_key=True, nullable=False)
    
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False)
    
    instrument = relationship("Instrument", back_populates="market_data")

class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)
    version = Column(String, default="1.0.0")
    config = Column(JSON)  # Parameters
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    trades = relationship("Trade", back_populates="strategy")

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False)
    
    order_id = Column(String, index=True) # Broker Order ID
    side = Column(String, nullable=False) # BUY/SELL
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default=OrderStatus.PENDING)
    pnl = Column(Float, nullable=True)
    
    strategy = relationship("Strategy", back_populates="trades")
    instrument = relationship("Instrument")

class Signal(Base):
    __tablename__ = "signals"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False)
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    signal_type = Column(String, nullable=False) # BUY/SELL
    strength = Column(Float)
    metadata_json = Column(JSON)
