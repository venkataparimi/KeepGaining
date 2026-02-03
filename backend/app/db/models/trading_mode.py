from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SQLEnum, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import enum

class TradingMode(str, enum.Enum):
    PAPER = "paper"
    LIVE = "live"

class TradingSession(Base):
    """Trading session tracking paper vs live mode"""
    __tablename__ = "trading_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    
    # Mode configuration
    mode = Column(SQLEnum(TradingMode), default=TradingMode.PAPER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Session metadata
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))
    started_by = Column(String(255))
    
    # Capital tracking
    initial_capital = Column(Float, default=100000.0)
    current_capital = Column(Float, default=100000.0)
    
    # Session statistics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)

class TradingModeSwitch(Base):
    """Audit log for mode switches"""
    __tablename__ = "trading_mode_switches"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    
    # Switch details
    from_mode = Column(SQLEnum(TradingMode), nullable=False)
    to_mode = Column(SQLEnum(TradingMode), nullable=False)
    switched_at = Column(DateTime(timezone=True), server_default=func.now())
    switched_by = Column(String(255))
    
    # Reason and approval
    reason = Column(String(500))
    requires_approval = Column(Boolean, default=True)
    approved = Column(Boolean, default=False)
    approved_by = Column(String(255))
    approved_at = Column(DateTime(timezone=True))
