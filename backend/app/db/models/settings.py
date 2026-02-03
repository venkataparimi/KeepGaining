from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from app.db.base import Base


class SystemSettings(Base):
    """Global system settings"""
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(String(500), nullable=True)
    value_type = Column(String(50), default="string")  # string, number, boolean, json
    category = Column(String(100), default="general")
    description = Column(String(500))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RiskSettings(Base):
    """Risk management settings"""
    __tablename__ = "risk_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Capital limits
    max_capital_per_trade = Column(Float, default=50000.0)
    max_capital_per_day = Column(Float, default=200000.0)
    max_open_positions = Column(Integer, default=5)
    
    # Loss limits
    max_loss_per_trade = Column(Float, default=2000.0)
    max_loss_per_day = Column(Float, default=10000.0)
    max_drawdown_percent = Column(Float, default=5.0)
    
    # Position sizing
    default_position_size_percent = Column(Float, default=5.0)  # % of capital
    default_stop_loss_percent = Column(Float, default=1.0)
    default_take_profit_percent = Column(Float, default=2.0)
    
    # Trading restrictions
    allow_overnight_positions = Column(Boolean, default=False)
    allow_options_trading = Column(Boolean, default=True)
    allow_futures_trading = Column(Boolean, default=True)
    
    # Timestamps
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NotificationSettings(Base):
    """Notification preferences"""
    __tablename__ = "notification_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Email settings
    email_enabled = Column(Boolean, default=False)
    email_address = Column(String(255))
    email_on_trade = Column(Boolean, default=True)
    email_on_error = Column(Boolean, default=True)
    email_daily_summary = Column(Boolean, default=True)
    
    # Webhook settings
    webhook_enabled = Column(Boolean, default=False)
    webhook_url = Column(String(500))
    
    # Push notifications
    push_enabled = Column(Boolean, default=False)
    
    # Timestamps
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
