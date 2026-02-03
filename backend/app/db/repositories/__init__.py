"""
Repository Layer
KeepGaining Trading Platform

Provides data access abstractions for all domain models.
"""

# Instrument repositories
from app.db.repositories.instrument import (
    InstrumentRepository,
    EquityRepository,
    FutureRepository,
    OptionRepository,
    SectorRepository,
    IndexConstituentRepository,
)

# Time series repositories
from app.db.repositories.timeseries import (
    CandleRepository,
    IndicatorRepository,
    OptionGreeksRepository,
    OptionChainSnapshotRepository,
)

# Trading repositories
from app.db.repositories.trading import (
    StrategyConfigRepository,
    StrategyDefinitionRepository,
    OrderRepository,
    TradeRepository,
    PositionRepository,
)

# Calendar repositories
from app.db.repositories.calendar import (
    ExpiryCalendarRepository,
    HolidayCalendarRepository,
    LotSizeHistoryRepository,
    FOBanListRepository,
    MasterDataRefreshLogRepository,
)

__all__ = [
    # Instrument
    "InstrumentRepository",
    "EquityRepository",
    "FutureRepository",
    "OptionRepository",
    "SectorRepository",
    "IndexConstituentRepository",
    # Time series
    "CandleRepository",
    "IndicatorRepository",
    "OptionGreeksRepository",
    "OptionChainSnapshotRepository",
    # Trading
    "StrategyConfigRepository",
    "StrategyDefinitionRepository",
    "OrderRepository",
    "TradeRepository",
    "PositionRepository",
    # Calendar
    "ExpiryCalendarRepository",
    "HolidayCalendarRepository",
    "LotSizeHistoryRepository",
    "FOBanListRepository",
    "MasterDataRefreshLogRepository",
]
