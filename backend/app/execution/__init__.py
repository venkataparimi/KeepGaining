"""
Execution Engine Module

Components for order execution and trading management:
- OMS (Order Management System)
- Risk Manager
- Paper Trading Engine
- Trading Orchestrator
- Position Sizing
"""

from app.execution.oms import OrderManagementSystem
from app.execution.risk import RiskManager
from app.execution.paper_trading import (
    PaperTradingEngine,
    PaperTradingConfig,
    VirtualOrder,
    VirtualPosition,
    VirtualTrade,
    OrderSide,
    OrderType,
    OrderStatus,
    ProductType,
    create_paper_trading_engine,
)
from app.execution.orchestrator import (
    TradingOrchestrator,
    TradingMode,
    SystemStatus,
    TradingSession,
    OrchestratorConfig,
    get_orchestrator,
    create_orchestrator,
)
from app.execution.position_sizing import (
    PositionSizer,
    PositionSizeResult,
    SizingMethod,
    RiskParitySizing,
    ScaledSizing,
    create_position_sizer,
)

__all__ = [
    # OMS
    "OrderManagementSystem",
    "RiskManager",
    
    # Paper Trading
    "PaperTradingEngine",
    "PaperTradingConfig",
    "VirtualOrder",
    "VirtualPosition",
    "VirtualTrade",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "ProductType",
    "create_paper_trading_engine",
    
    # Orchestrator
    "TradingOrchestrator",
    "TradingMode",
    "SystemStatus",
    "TradingSession",
    "OrchestratorConfig",
    "get_orchestrator",
    "create_orchestrator",
    
    # Position Sizing
    "PositionSizer",
    "PositionSizeResult",
    "SizingMethod",
    "RiskParitySizing",
    "ScaledSizing",
    "create_position_sizer",
]
