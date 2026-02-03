"""
Backtest Module
KeepGaining Trading Platform

Provides comprehensive backtesting capabilities:
- BacktestEngine: Core execution engine with slippage, commission modeling
- EnhancedEngine: Advanced metrics (Sharpe, Sortino, drawdown)
- WalkForwardEngine: Walk-forward optimization and validation
- MonteCarloSimulator: Robustness testing via simulation
- BacktestRunner: Unified orchestrator for all backtest types
"""

# Core engine
from app.backtest.backtest_engine import (
    BacktestEngine as CoreBacktestEngine,
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestOrder,
    BacktestPosition,
    BacktestTrade,
)

# Enhanced engine with metrics
from app.backtest.enhanced_engine import (
    BacktestEngine as EnhancedBacktestEngine,
    BacktestConfig as EnhancedConfig,
    Trade,
    OrderSide,
)

# Walk-forward validation
from app.backtest.walk_forward import (
    WalkForwardEngine,
    WalkForwardConfig,
    WalkForwardResult,
    WalkForwardWindow,
    WalkForwardType,
    create_walk_forward_engine,
)

# Monte Carlo simulation
from app.backtest.monte_carlo import (
    MonteCarloSimulator,
    MonteCarloResult,
    SimulationType,
    TradeRecord,
    create_monte_carlo_simulator,
)

# Unified runner
from app.backtest.runner import (
    BacktestRunner,
    BacktestReport,
    ComparisonReport,
    BacktestMode,
    quick_backtest,
)

__all__ = [
    # Core
    "CoreBacktestEngine",
    "BacktestConfig", 
    "BacktestMetrics",
    "BacktestResult",
    "BacktestOrder",
    "BacktestPosition",
    "BacktestTrade",
    # Enhanced
    "EnhancedBacktestEngine",
    "EnhancedConfig",
    "Trade",
    "OrderSide",
    # Walk-forward
    "WalkForwardEngine",
    "WalkForwardConfig",
    "WalkForwardResult",
    "WalkForwardWindow",
    "WalkForwardType",
    "create_walk_forward_engine",
    # Monte Carlo
    "MonteCarloSimulator",
    "MonteCarloResult",
    "SimulationType",
    "TradeRecord",
    "create_monte_carlo_simulator",
    # Runner
    "BacktestRunner",
    "BacktestReport",
    "ComparisonReport",
    "BacktestMode",
    "quick_backtest",
]
