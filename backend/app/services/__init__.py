"""
Services Layer
KeepGaining Trading Platform

Business logic and service orchestration.

This module contains all the core trading services that work together
in an event-driven architecture:

Data Layer:
    - DataFeedOrchestrator: Coordinates multiple data sources
    - CandleBuilderService: Aggregates ticks into candles
    - IndicatorService: Computes technical indicators

Trading Layer:
    - StrategyEngine: Evaluates strategies and generates signals
    - RiskManager: Pre-trade validation and capital protection
    - PositionManager: Tracks positions with SL/target monitoring
    - OrderManager: Order lifecycle and broker integration

Event Flow:
    TickEvent → CandleEvent → IndicatorEvent → SignalEvent → OrderEvent
"""

from app.services.event_publisher import EventPublisher
from app.services.event_subscriber import EventSubscriberManager, subscriber

# Candle Builder
from app.services.candle_builder import (
    CandleBuilder,
    CandleBuilderService,
)

# Indicator Service
from app.services.indicator_service import (
    IndicatorService,
)

# Strategy Engine
from app.services.strategy_engine import (
    BaseStrategy,
    VolumeRocketStrategy,
    StrategyEngine,
    StrategyRegistry,
    Signal,
    SignalType,
    SignalStrength,
    create_strategy_engine,
)

# Risk Manager
from app.services.risk_manager import (
    RiskManager,
    RiskConfig,
    RiskCheckResponse,
    RiskCheckResult,
    RiskViolationType,
    create_risk_manager,
)

# Position Manager
from app.services.position_manager import (
    Position,
    PositionManager,
    PositionState,
    PositionSide,
    ExitReason,
    TrailingStopConfig,
    create_position_manager,
)

# Order Manager
from app.services.order_manager import (
    Order,
    OrderManager,
    OrderType,
    OrderSide,
    OrderStatus,
    ProductType,
    PaperBrokerAdapter,
    create_order_manager,
)

# Data Orchestrator
from app.services.data_orchestrator import (
    DataFeedOrchestrator,
    SymbolSubscription,
    SubscriptionPriority,
    DataSourceType,
    create_data_orchestrator,
)


__all__ = [
    # Event system
    "EventPublisher",
    "EventSubscriberManager",
    "subscriber",
    
    # Candle Builder
    "CandleBuilder",
    "CandleBuilderService",
    
    # Indicator Service
    "IndicatorService",
    
    # Strategy Engine
    "BaseStrategy",
    "VolumeRocketStrategy",
    "StrategyEngine",
    "StrategyRegistry",
    "Signal",
    "SignalType",
    "SignalStrength",
    "create_strategy_engine",
    
    # Risk Manager
    "RiskManager",
    "RiskConfig",
    "RiskCheckResponse",
    "RiskCheckResult",
    "RiskViolationType",
    "create_risk_manager",
    
    # Position Manager
    "Position",
    "PositionManager",
    "PositionState",
    "PositionSide",
    "ExitReason",
    "TrailingStopConfig",
    "create_position_manager",
    
    # Order Manager
    "Order",
    "OrderManager",
    "OrderType",
    "OrderSide",
    "OrderStatus",
    "ProductType",
    "PaperBrokerAdapter",
    "create_order_manager",
    
    # Data Orchestrator
    "DataFeedOrchestrator",
    "SymbolSubscription",
    "SubscriptionPriority",
    "DataSourceType",
    "create_data_orchestrator",
]
