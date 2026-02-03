from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, Index
from sqlalchemy.sql import func
from app.db.base import Base

class CandleData(Base):
    """Store OHLCV candle data with pre-computed indicators"""
    __tablename__ = "candle_data"
    
    # Primary key
    id = Column(BigInteger, primary_key=True, index=True)
    
    # Candle identification
    symbol = Column(String(50), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)  # 1m, 5m, 15m, 1h, 1d
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # OHLCV data
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False)
    
    # Moving Averages
    sma_9 = Column(Float)
    sma_20 = Column(Float)
    sma_50 = Column(Float)
    sma_200 = Column(Float)
    ema_9 = Column(Float)
    ema_21 = Column(Float)
    ema_50 = Column(Float)
    ema_200 = Column(Float)
    
    # Momentum Indicators
    rsi_14 = Column(Float)
    rsi_9 = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_histogram = Column(Float)
    stoch_k = Column(Float)
    stoch_d = Column(Float)
    
    # Volatility Indicators
    bb_upper = Column(Float)
    bb_middle = Column(Float)
    bb_lower = Column(Float)
    atr_14 = Column(Float)
    
    # Trend Indicators
    supertrend = Column(Float)
    supertrend_direction = Column(Integer)  # 1 = uptrend, -1 = downtrend
    adx = Column(Float)
    
    # Standard Pivot Points (Classic)
    pivot_point = Column(Float)
    pivot_r1 = Column(Float)
    pivot_r2 = Column(Float)
    pivot_r3 = Column(Float)
    pivot_s1 = Column(Float)
    pivot_s2 = Column(Float)
    pivot_s3 = Column(Float)
    
    # Fibonacci Pivot Points
    fib_pivot = Column(Float)
    fib_r1 = Column(Float)
    fib_r2 = Column(Float)
    fib_r3 = Column(Float)
    fib_s1 = Column(Float)
    fib_s2 = Column(Float)
    fib_s3 = Column(Float)
    
    # Camarilla Pivot Points
    cam_r4 = Column(Float)
    cam_r3 = Column(Float)
    cam_r2 = Column(Float)
    cam_r1 = Column(Float)
    cam_s1 = Column(Float)
    cam_s2 = Column(Float)
    cam_s3 = Column(Float)
    cam_s4 = Column(Float)
    
    # Volume Indicators
    vwap = Column(Float)
    vwma_20 = Column(Float)  # Standard VWMA
    vwma_22 = Column(Float)  # Custom fast VWMA (Fibonacci-based)
    vwma_31 = Column(Float)  # Custom slow VWMA (Fibonacci-based)
    vwma_50 = Column(Float)  # Long-term VWMA
    obv = Column(BigInteger)  # On-Balance Volume
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Composite indexes for fast queries
    __table_args__ = (
        Index('idx_symbol_timeframe_timestamp', 'symbol', 'timeframe', 'timestamp'),
        Index('idx_timestamp_symbol', 'timestamp', 'symbol'),
    )


class IndicatorCache(Base):
    """Cache for frequently accessed indicator combinations"""
    __tablename__ = "indicator_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)
    cache_key = Column(String(100), nullable=False, index=True)  # e.g., "ema_cross_9_21"
    cache_data = Column(String)  # JSON string of pre-computed signals
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_cache_lookup', 'symbol', 'timeframe', 'cache_key'),
    )
