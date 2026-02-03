from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, Float
from sqlalchemy.sql import func
from app.db.base import Base

class BrokerConfig(Base):
    """Broker configuration and credentials"""
    __tablename__ = "broker_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Broker details
    broker_name = Column(String(50), nullable=False)  # fyers, zerodha, upstox
    is_active = Column(Boolean, default=True)
    is_primary = Column(Boolean, default=False)
    
    # Credentials (encrypted in production)
    api_key = Column(String(255))
    api_secret = Column(String(255))
    user_id = Column(String(255))
    
    # Configuration
    config = Column(JSON)  # Broker-specific settings
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class BrokerHealthCheck(Base):
    """Broker health check results"""
    __tablename__ = "broker_health_checks"
    
    id = Column(Integer, primary_key=True, index=True)
    broker_name = Column(String(50), nullable=False)
    
    # Health status
    is_healthy = Column(Boolean, default=True)
    status_code = Column(Integer)
    response_time_ms = Column(Float)
    
    # Check details
    check_type = Column(String(50))  # connectivity, auth, rate_limit
    error_message = Column(String(500))
    
    # Timestamp
    checked_at = Column(DateTime(timezone=True), server_default=func.now())

class BrokerApiUsage(Base):
    """Track API usage and rate limits"""
    __tablename__ = "broker_api_usage"
    
    id = Column(Integer, primary_key=True, index=True)
    broker_name = Column(String(50), nullable=False)
    
    # Usage metrics
    endpoint = Column(String(255))
    request_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    
    # Rate limiting
    rate_limit = Column(Integer)  # Max requests per period
    rate_limit_remaining = Column(Integer)
    rate_limit_reset_at = Column(DateTime(timezone=True))
    
    # Timestamp
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
