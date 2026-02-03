"""
Unified Backtest Runner
KeepGaining Trading Platform

Orchestrates all backtesting components:
- Single run backtests
- Walk-forward validation
- Monte Carlo robustness testing
- Multi-strategy comparison

Provides a unified interface for all backtesting needs.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Type, Union
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
import json
import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger

from app.backtest.enhanced_engine import BacktestEngine, BacktestConfig, Trade
from app.backtest.walk_forward import (
    WalkForwardEngine,
    WalkForwardConfig,
    WalkForwardResult,
    WalkForwardType,
)
from app.backtest.monte_carlo import (
    MonteCarloSimulator,
    MonteCarloResult,
    SimulationType,
    TradeRecord,
)
from app.strategies.base import BaseStrategy, Signal


class BacktestMode(str, Enum):
    """Backtest execution modes."""
    SINGLE = "single"                 # Single backtest run
    WALK_FORWARD = "walk_forward"     # Walk-forward validation
    MONTE_CARLO = "monte_carlo"       # Monte Carlo robustness
    COMPARISON = "comparison"         # Multi-strategy comparison
    FULL = "full"                     # All of the above


@dataclass
class BacktestReport:
    """Comprehensive backtest report."""
    
    # Identification
    strategy_name: str
    symbols: List[str]
    start_date: date
    end_date: date
    run_timestamp: datetime = field(default_factory=datetime.now)
    
    # Mode-specific results
    single_result: Optional[Dict[str, Any]] = None
    walk_forward_result: Optional[Dict[str, Any]] = None
    monte_carlo_result: Optional[Dict[str, Any]] = None
    
    # Summary metrics
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    total_return: float = 0.0
    
    # Robustness scores
    walk_forward_efficiency: float = 0.0  # OOS vs IS performance
    monte_carlo_confidence: float = 0.0   # P(profit)
    path_dependency: float = 0.0          # Trade order sensitivity
    
    # Trade data
    trades: List[Dict[str, Any]] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strategy_name": self.strategy_name,
            "symbols": self.symbols,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "run_timestamp": self.run_timestamp.isoformat(),
            "summary": {
                "total_trades": self.total_trades,
                "win_rate": round(self.win_rate, 4),
                "profit_factor": round(self.profit_factor, 4),
                "sharpe_ratio": round(self.sharpe_ratio, 4),
                "max_drawdown": round(self.max_drawdown, 4),
                "total_return": round(self.total_return, 4),
            },
            "robustness": {
                "walk_forward_efficiency": round(self.walk_forward_efficiency, 4),
                "monte_carlo_confidence": round(self.monte_carlo_confidence, 4),
                "path_dependency": round(self.path_dependency, 4),
            },
            "single_result": self.single_result,
            "walk_forward_result": self.walk_forward_result,
            "monte_carlo_result": self.monte_carlo_result,
            "trades": self.trades,
            "equity_curve": self.equity_curve,
        }
    
    def save(self, path: Union[str, Path], format: str = "json") -> Path:
        """Save report to file."""
        path = Path(path)
        
        if format == "json":
            with open(path, "w") as f:
                json.dump(self.to_dict(), f, indent=2, default=str)
        elif format == "csv":
            # Save trades as CSV
            trades_path = path.with_suffix(".trades.csv")
            pd.DataFrame(self.trades).to_csv(trades_path, index=False)
            
            # Save equity curve as CSV
            equity_path = path.with_suffix(".equity.csv")
            pd.DataFrame(self.equity_curve).to_csv(equity_path, index=False)
            
            # Save summary as JSON
            summary_path = path.with_suffix(".summary.json")
            with open(summary_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2, default=str)
            
            return summary_path
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        return path


@dataclass
class ComparisonReport:
    """Multi-strategy comparison report."""
    
    strategies: List[str]
    symbols: List[str]
    start_date: date
    end_date: date
    
    # Results per strategy
    results: Dict[str, BacktestReport] = field(default_factory=dict)
    
    # Rankings
    rankings: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    # Best strategy per metric
    best_by_sharpe: str = ""
    best_by_return: str = ""
    best_by_drawdown: str = ""
    best_by_consistency: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategies": self.strategies,
            "symbols": self.symbols,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "results": {k: v.to_dict() for k, v in self.results.items()},
            "rankings": self.rankings,
            "best_strategies": {
                "sharpe": self.best_by_sharpe,
                "return": self.best_by_return,
                "drawdown": self.best_by_drawdown,
                "consistency": self.best_by_consistency,
            },
        }


class BacktestRunner:
    """
    Unified backtest orchestrator.
    
    Provides a single interface for all backtesting needs:
    - Run single backtests
    - Walk-forward validation
    - Monte Carlo robustness testing
    - Multi-strategy comparison
    
    Usage:
        runner = BacktestRunner(config=BacktestConfig())
        
        # Single backtest
        report = runner.run_single(strategy, symbols, start, end)
        
        # Walk-forward
        report = runner.run_walk_forward(strategy, symbols, start, end)
        
        # Full analysis
        report = runner.run_full(strategy, symbols, start, end)
        
        # Compare strategies
        comparison = runner.compare(strategies, symbols, start, end)
    """
    
    def __init__(
        self,
        config: Optional[BacktestConfig] = None,
        data_loader: Optional[Any] = None,  # Callable to load data
        output_dir: Optional[Path] = None,
    ):
        """
        Initialize backtest runner.
        
        Args:
            config: Backtest configuration
            data_loader: Optional function to load market data
            output_dir: Directory for saving reports
        """
        self.config = config or BacktestConfig()
        self.data_loader = data_loader
        self.output_dir = Path(output_dir) if output_dir else Path("backtest_results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.backtest_engine = BacktestEngine(self.config)
        self.monte_carlo = MonteCarloSimulator(
            initial_capital=self.config.initial_capital,
        )
    
    def run_single(
        self,
        strategy: BaseStrategy,
        data: pd.DataFrame,
        symbols: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> BacktestReport:
        """
        Run a single backtest.
        
        Args:
            strategy: Strategy instance to test
            data: DataFrame with market data (timestamp, symbol, OHLCV, indicators)
            symbols: Optional list of symbols (derived from data if not provided)
            start_date: Start date (derived from data if not provided)
            end_date: End date (derived from data if not provided)
            
        Returns:
            BacktestReport with results
        """
        logger.info(f"Running single backtest for {strategy.name}")
        
        # Derive parameters from data if not provided
        if symbols is None:
            symbols = data["symbol"].unique().tolist() if "symbol" in data.columns else ["UNKNOWN"]
        if start_date is None:
            start_date = data.index.min().date() if isinstance(data.index, pd.DatetimeIndex) else date.today()
        if end_date is None:
            end_date = data.index.max().date() if isinstance(data.index, pd.DatetimeIndex) else date.today()
        
        # Reset engine
        self.backtest_engine = BacktestEngine(self.config)
        
        # Run strategy on data
        trades = self._run_strategy_on_data(strategy, data)
        
        # Calculate metrics
        metrics = self.backtest_engine.calculate_metrics()
        
        # Build report
        report = BacktestReport(
            strategy_name=strategy.name,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            single_result=metrics,
            total_trades=metrics.get("total_trades", 0),
            win_rate=metrics.get("win_rate", 0.0),
            profit_factor=metrics.get("profit_factor", 0.0),
            sharpe_ratio=metrics.get("sharpe_ratio", 0.0),
            max_drawdown=metrics.get("max_drawdown_percent", 0.0),
            total_return=metrics.get("total_return_percent", 0.0),
            trades=[self._trade_to_dict(t) for t in self.backtest_engine.trades],
            equity_curve=self.backtest_engine.equity_curve,
        )
        
        logger.info(f"Single backtest complete: {report.total_trades} trades, {report.total_return:.2f}% return")
        return report
    
    def run_walk_forward(
        self,
        strategy: BaseStrategy,
        data: pd.DataFrame,
        training_days: int = 180,
        testing_days: int = 30,
        walk_type: WalkForwardType = WalkForwardType.ROLLING,
        optimize_metric: str = "sharpe_ratio",
        parameter_ranges: Optional[Dict[str, List[Any]]] = None,
    ) -> BacktestReport:
        """
        Run walk-forward validation.
        
        Args:
            strategy: Strategy to test
            data: Market data
            training_days: Days for in-sample training
            testing_days: Days for out-of-sample testing
            walk_type: Type of walk-forward (rolling, expanding, anchored)
            optimize_metric: Metric to optimize on training data
            parameter_ranges: Parameters to optimize
            
        Returns:
            BacktestReport with walk-forward results
        """
        logger.info(f"Running walk-forward validation for {strategy.name}")
        
        # Configure walk-forward
        wf_config = WalkForwardConfig(
            training_period_days=training_days,
            testing_period_days=testing_days,
            step_days=testing_days,
            walk_type=walk_type,
            optimize_metric=optimize_metric,
            parameter_ranges=parameter_ranges or {},
            initial_capital=self.config.initial_capital,
        )
        
        # Create strategy runner function
        def strategy_runner(
            window_data: pd.DataFrame,
            params: Dict[str, Any],
            bt_config: BacktestConfig,
        ) -> Tuple[List[Trade], Dict[str, Any]]:
            # Apply parameters to strategy
            for key, value in params.items():
                if hasattr(strategy, key):
                    setattr(strategy, key, value)
            
            # Run backtest on window
            engine = BacktestEngine(bt_config)
            trades = self._run_strategy_on_data(strategy, window_data, engine)
            metrics = engine.calculate_metrics()
            
            return trades, metrics
        
        # Run walk-forward
        wf_engine = WalkForwardEngine(wf_config, strategy_runner)
        wf_result = wf_engine.run(data)
        
        # Derive dates
        symbols = data["symbol"].unique().tolist() if "symbol" in data.columns else ["UNKNOWN"]
        start_date = data.index.min().date() if isinstance(data.index, pd.DatetimeIndex) else date.today()
        end_date = data.index.max().date() if isinstance(data.index, pd.DatetimeIndex) else date.today()
        
        # Build report
        report = BacktestReport(
            strategy_name=strategy.name,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            walk_forward_result=wf_result.combined_metrics,
            total_trades=wf_result.combined_metrics.get("total_trades", 0),
            win_rate=wf_result.combined_metrics.get("win_rate", 0.0),
            sharpe_ratio=wf_result.combined_metrics.get("sharpe_ratio", 0.0),
            max_drawdown=wf_result.combined_metrics.get("max_drawdown", 0.0),
            total_return=wf_result.combined_metrics.get("total_return", 0.0),
            walk_forward_efficiency=wf_result.efficiency_ratio,
            trades=wf_result.all_trades,
            equity_curve=wf_result.equity_curve,
        )
        
        logger.info(f"Walk-forward complete: efficiency ratio = {report.walk_forward_efficiency:.2f}")
        return report
    
    def run_monte_carlo(
        self,
        trades: List[Trade],
        simulations: int = 1000,
        sim_type: SimulationType = SimulationType.SHUFFLE,
        strategy_name: str = "Unknown",
    ) -> BacktestReport:
        """
        Run Monte Carlo robustness testing on existing trades.
        
        Args:
            trades: List of trades from a backtest
            simulations: Number of MC simulations
            sim_type: Type of simulation
            strategy_name: Name for the report
            
        Returns:
            BacktestReport with Monte Carlo results
        """
        logger.info(f"Running Monte Carlo ({sim_type.value}) with {simulations} simulations")
        
        # Convert to TradeRecords
        trade_records = [
            TradeRecord(
                pnl=t.pnl,
                pnl_percent=t.pnl_percent,
                entry_time=t.entry_time,
                exit_time=t.exit_time,
                symbol=t.symbol,
            )
            for t in trades
        ]
        
        # Run simulation
        mc_result = self.monte_carlo.run(trade_records, simulations, sim_type)
        
        # Analyze path dependency
        path_analysis = self.monte_carlo.analyze_path_dependency(trade_records, simulations // 2)
        
        # Build report
        report = BacktestReport(
            strategy_name=strategy_name,
            symbols=[],
            start_date=date.today(),
            end_date=date.today(),
            monte_carlo_result=mc_result.to_dict(),
            total_trades=len(trades),
            monte_carlo_confidence=mc_result.probability_of_profit,
            path_dependency=path_analysis["path_dependency_score"],
        )
        
        logger.info(
            f"Monte Carlo complete: P(profit)={mc_result.probability_of_profit:.1%}, "
            f"P(ruin)={mc_result.probability_of_ruin:.1%}"
        )
        return report
    
    def run_full(
        self,
        strategy: BaseStrategy,
        data: pd.DataFrame,
        mc_simulations: int = 1000,
        wf_training_days: int = 180,
        wf_testing_days: int = 30,
    ) -> BacktestReport:
        """
        Run full analysis: single + walk-forward + Monte Carlo.
        
        Args:
            strategy: Strategy to test
            data: Market data
            mc_simulations: Monte Carlo simulations
            wf_training_days: Walk-forward training period
            wf_testing_days: Walk-forward testing period
            
        Returns:
            Comprehensive BacktestReport
        """
        logger.info(f"Running full analysis for {strategy.name}")
        
        # 1. Single backtest
        single_report = self.run_single(strategy, data)
        
        # 2. Walk-forward (if enough data)
        data_days = (data.index.max() - data.index.min()).days if isinstance(data.index, pd.DatetimeIndex) else 0
        if data_days >= wf_training_days + wf_testing_days:
            wf_report = self.run_walk_forward(
                strategy, data,
                training_days=wf_training_days,
                testing_days=wf_testing_days,
            )
        else:
            wf_report = None
            logger.warning(f"Not enough data ({data_days} days) for walk-forward validation")
        
        # 3. Monte Carlo on single backtest trades
        if single_report.total_trades >= 10:
            mc_report = self.run_monte_carlo(
                self.backtest_engine.trades,
                simulations=mc_simulations,
                strategy_name=strategy.name,
            )
        else:
            mc_report = None
            logger.warning(f"Not enough trades ({single_report.total_trades}) for Monte Carlo")
        
        # Combine into comprehensive report
        report = BacktestReport(
            strategy_name=strategy.name,
            symbols=single_report.symbols,
            start_date=single_report.start_date,
            end_date=single_report.end_date,
            single_result=single_report.single_result,
            walk_forward_result=wf_report.walk_forward_result if wf_report else None,
            monte_carlo_result=mc_report.monte_carlo_result if mc_report else None,
            total_trades=single_report.total_trades,
            win_rate=single_report.win_rate,
            profit_factor=single_report.profit_factor,
            sharpe_ratio=single_report.sharpe_ratio,
            max_drawdown=single_report.max_drawdown,
            total_return=single_report.total_return,
            walk_forward_efficiency=wf_report.walk_forward_efficiency if wf_report else 0.0,
            monte_carlo_confidence=mc_report.monte_carlo_confidence if mc_report else 0.0,
            path_dependency=mc_report.path_dependency if mc_report else 0.0,
            trades=single_report.trades,
            equity_curve=single_report.equity_curve,
        )
        
        logger.info(f"Full analysis complete for {strategy.name}")
        return report
    
    def compare(
        self,
        strategies: List[BaseStrategy],
        data: pd.DataFrame,
        run_mode: BacktestMode = BacktestMode.SINGLE,
    ) -> ComparisonReport:
        """
        Compare multiple strategies.
        
        Args:
            strategies: List of strategies to compare
            data: Market data
            run_mode: What type of backtest to run for each
            
        Returns:
            ComparisonReport with rankings
        """
        logger.info(f"Comparing {len(strategies)} strategies")
        
        # Derive parameters
        symbols = data["symbol"].unique().tolist() if "symbol" in data.columns else []
        start_date = data.index.min().date() if isinstance(data.index, pd.DatetimeIndex) else date.today()
        end_date = data.index.max().date() if isinstance(data.index, pd.DatetimeIndex) else date.today()
        
        # Run backtests for each strategy
        results: Dict[str, BacktestReport] = {}
        
        for strategy in strategies:
            logger.info(f"Testing {strategy.name}...")
            
            if run_mode == BacktestMode.SINGLE:
                results[strategy.name] = self.run_single(strategy, data)
            elif run_mode == BacktestMode.WALK_FORWARD:
                results[strategy.name] = self.run_walk_forward(strategy, data)
            elif run_mode == BacktestMode.FULL:
                results[strategy.name] = self.run_full(strategy, data)
            else:
                results[strategy.name] = self.run_single(strategy, data)
        
        # Calculate rankings
        rankings = self._calculate_rankings(results)
        
        # Find best strategies
        best_by_sharpe = max(results.keys(), key=lambda k: results[k].sharpe_ratio)
        best_by_return = max(results.keys(), key=lambda k: results[k].total_return)
        best_by_drawdown = min(results.keys(), key=lambda k: results[k].max_drawdown)
        best_by_consistency = max(results.keys(), key=lambda k: results[k].walk_forward_efficiency)
        
        comparison = ComparisonReport(
            strategies=[s.name for s in strategies],
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            results=results,
            rankings=rankings,
            best_by_sharpe=best_by_sharpe,
            best_by_return=best_by_return,
            best_by_drawdown=best_by_drawdown,
            best_by_consistency=best_by_consistency,
        )
        
        logger.info(f"Comparison complete. Best by Sharpe: {best_by_sharpe}")
        return comparison
    
    def _run_strategy_on_data(
        self,
        strategy: BaseStrategy,
        data: pd.DataFrame,
        engine: Optional[BacktestEngine] = None,
    ) -> List[Trade]:
        """
        Run strategy on market data.
        
        Override this method to customize how data is fed to strategies.
        """
        engine = engine or self.backtest_engine
        
        # Group data by symbol if multiple symbols
        if "symbol" in data.columns:
            symbols = data["symbol"].unique()
        else:
            symbols = ["UNKNOWN"]
        
        # Iterate through candles chronologically
        for idx, row in data.iterrows():
            # Convert row to candle dict
            candle = {
                "timestamp": idx if isinstance(idx, datetime) else row.get("timestamp"),
                "symbol": row.get("symbol", symbols[0]),
                "open": row.get("open", row.get("Open")),
                "high": row.get("high", row.get("High")),
                "low": row.get("low", row.get("Low")),
                "close": row.get("close", row.get("Close")),
                "volume": row.get("volume", row.get("Volume", 0)),
            }
            
            # Get signal from strategy
            try:
                signal = strategy.on_candle(candle)
                
                if signal:
                    # Execute trade (simplified - full implementation would track positions)
                    if signal.signal_type.value in ["LONG_ENTRY", "SHORT_ENTRY"]:
                        # Entry signal
                        from app.backtest.enhanced_engine import OrderSide
                        side = OrderSide.BUY if "LONG" in signal.signal_type.value else OrderSide.SELL
                        
                        engine.execute_trade(
                            entry_time=candle["timestamp"],
                            exit_time=candle["timestamp"] + timedelta(hours=1),  # Placeholder
                            symbol=candle["symbol"],
                            side=side,
                            entry_price=signal.entry_price,
                            exit_price=signal.target_price or signal.entry_price * 1.01,
                        )
            except Exception as e:
                logger.warning(f"Strategy error at {idx}: {e}")
                continue
        
        return engine.trades
    
    def _trade_to_dict(self, trade: Trade) -> Dict[str, Any]:
        """Convert Trade to dictionary."""
        return {
            "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
            "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
            "symbol": trade.symbol,
            "side": trade.side.value if hasattr(trade.side, "value") else trade.side,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "quantity": trade.quantity,
            "pnl": trade.pnl,
            "pnl_percent": trade.pnl_percent,
            "commission": trade.commission,
            "slippage": trade.slippage,
        }
    
    def _calculate_rankings(
        self,
        results: Dict[str, BacktestReport],
    ) -> Dict[str, Dict[str, int]]:
        """Calculate rankings for each metric."""
        metrics = ["sharpe_ratio", "total_return", "max_drawdown", "win_rate", "profit_factor"]
        rankings = {name: {} for name in results.keys()}
        
        for metric in metrics:
            # Sort strategies by metric
            sorted_strategies = sorted(
                results.keys(),
                key=lambda k: getattr(results[k], metric, 0),
                reverse=(metric != "max_drawdown"),  # Lower drawdown is better
            )
            
            for rank, strategy in enumerate(sorted_strategies, 1):
                rankings[strategy][metric] = rank
        
        return rankings


def quick_backtest(
    strategy: BaseStrategy,
    data: pd.DataFrame,
    mode: str = "single",
    **kwargs,
) -> BacktestReport:
    """
    Quick utility function for running backtests.
    
    Args:
        strategy: Strategy to test
        data: Market data DataFrame
        mode: 'single', 'walk_forward', 'monte_carlo', or 'full'
        **kwargs: Additional arguments for the specific mode
        
    Returns:
        BacktestReport
    """
    runner = BacktestRunner()
    
    if mode == "single":
        return runner.run_single(strategy, data, **kwargs)
    elif mode == "walk_forward":
        return runner.run_walk_forward(strategy, data, **kwargs)
    elif mode == "full":
        return runner.run_full(strategy, data, **kwargs)
    else:
        return runner.run_single(strategy, data, **kwargs)
