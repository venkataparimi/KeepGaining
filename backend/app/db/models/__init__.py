"""
Database Models Package
KeepGaining Trading Platform

Exports all SQLAlchemy models for the application.
"""

# Import Base
from app.db.base import Base

# Import all models from their respective modules
from app.db.models.instrument import (
    InstrumentMaster,
    EquityMaster,
    FutureMaster,
    OptionMaster,
    SectorMaster,
    IndexConstituents,
)

from app.db.models.timeseries import (
    CandleData,
    IndicatorData,
    OptionGreeks,
    OptionChainSnapshot,
)

from app.db.models.broker import (
    BrokerSymbolMapping,
    BrokerConfig,
    RateLimitTracker,
)

from app.db.models.calendar import (
    ExpiryCalendar,
    HolidayCalendar,
    LotSizeHistory,
    FOBanList,
    MasterDataRefreshLog,
)

from app.db.models.trading import (
    StrategyConfig,
    StrategyDefinition,
    Order,
    Trade,
    Position,
    OrderLog,
)

from app.db.models.audit import (
    SignalLog,
    SystemEventLog,
    DailyPnL,
)

# Legacy models removed - use InstrumentMaster and CandleData instead
# Instrument = InstrumentMaster (alias)
# MarketData → CandleData
Instrument = InstrumentMaster
MarketData = CandleData  # Alias for backward compatibility


# Enums for backward compatibility
from enum import Enum

class InstrumentType(str, Enum):
    EQUITY = "EQUITY"
    OPTION = "OPTION"
    FUTURE = "FUTURE"
    INDEX = "INDEX"

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PLACED = "PLACED"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


__all__ = [
    # Base
    "Base",
    
    # Enums
    "InstrumentType",
    "OrderSide",
    "OrderStatus",
    "PositionSide",
    "PositionStatus",
    
    # Legacy Aliases (backward compatibility)
    "Instrument",  # Alias for InstrumentMaster
    "MarketData",  # Alias for CandleData
    
    # Instrument Models
    "InstrumentMaster",
    "EquityMaster",
    "FutureMaster",
    "OptionMaster",
    "SectorMaster",
    "IndexConstituents",
    
    # Time Series Models
    "CandleData",
    "IndicatorData",
    "OptionGreeks",
    "OptionChainSnapshot",
    
    # Broker Models
    "BrokerSymbolMapping",
    "BrokerConfig",
    "RateLimitTracker",
    
    # Calendar Models
    "ExpiryCalendar",
    "HolidayCalendar",
    "LotSizeHistory",
    "FOBanList",
    "MasterDataRefreshLog",
    
    # Trading Models
    "StrategyConfig",
    "StrategyDefinition",
    "Order",
    "Trade",
    "Position",
    "OrderLog",
    
    # Audit Models
    "SignalLog",
    "SystemEventLog",
    "DailyPnL",
]
