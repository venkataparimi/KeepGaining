"""
Walk-Forward Backtesting Engine
KeepGaining Trading Platform

Walk-forward analysis divides historical data into multiple in-sample (training)
and out-of-sample (testing) periods, optimizing parameters on each training
period and validating on the subsequent test period.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Tuple
from enum import Enum
import pandas as pd
import numpy as np
from loguru import logger

from app.backtest.enhanced_engine import BacktestEngine, BacktestConfig, Trade


class WalkForwardType(str, Enum):
    """Types of walk-forward analysis."""
    ANCHORED = "anchored"  # Training window grows from start
    ROLLING = "rolling"    # Training window slides forward
    EXPANDING = "expanding"  # Same as anchored


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward analysis."""
    # Time periods
    training_period_days: int = 180  # 6 months training
    testing_period_days: int = 30   # 1 month testing
    step_days: int = 30             # Move forward by 1 month each step
    
    # Walk-forward type
    walk_type: WalkForwardType = WalkForwardType.ROLLING
    
    # Minimum requirements
    min_training_trades: int = 30   # Min trades in training for valid optimization
    min_testing_trades: int = 5     # Min trades in testing for valid results
    
    # Optimization settings
    optimize_metric: str = "sharpe_ratio"  # Metric to optimize
    parameter_ranges: Dict[str, List[Any]] = field(default_factory=dict)
    
    # Backtest config
    initial_capital: float = 100000.0
    commission_percent: float = 0.03
    slippage_percent: float = 0.05
    position_size_percent: float = 10.0


@dataclass
class WalkForwardWindow:
    """A single walk-forward window (training + testing)."""
    window_id: int
    training_start: datetime
    training_end: datetime
    testing_start: datetime
    testing_end: datetime
    
    # Results
    optimized_params: Dict[str, Any] = field(default_factory=dict)
    training_metrics: Dict[str, Any] = field(default_factory=dict)
    testing_metrics: Dict[str, Any] = field(default_factory=dict)
    training_trades: int = 0
    testing_trades: int = 0


@dataclass
class WalkForwardResult:
    """Complete walk-forward analysis results."""
    windows: List[WalkForwardWindow]
    combined_metrics: Dict[str, Any]
    equity_curve: List[Dict[str, Any]]
    all_trades: List[Dict[str, Any]]
    
    # Robustness metrics
    consistency_score: float  # % of windows that are profitable
    efficiency_ratio: float   # OOS performance / IS performance
    parameter_stability: Dict[str, float]  # Std dev of optimized params


class WalkForwardEngine:
    """
    Walk-forward backtesting engine.
    
    Performs walk-forward optimization and validation:
    1. Divides data into training and testing windows
    2. Optimizes parameters on training data
    3. Validates on out-of-sample testing data
    4. Aggregates results across all windows
    """
    
    def __init__(
        self,
        config: WalkForwardConfig,
        strategy_runner: Callable[[pd.DataFrame, Dict[str, Any], BacktestConfig], Tuple[List[Trade], Dict[str, Any]]],
    ):
        """
        Initialize walk-forward engine.
        
        Args:
            config: Walk-forward configuration
            strategy_runner: Callable that takes (data, params, backtest_config) and returns (trades, metrics)
        """
        self.config = config
        self.strategy_runner = strategy_runner
        self.windows: List[WalkForwardWindow] = []
        self.all_trades: List[Trade] = []
        
    def generate_windows(
        self,
        data_start: datetime,
        data_end: datetime,
    ) -> List[WalkForwardWindow]:
        """Generate walk-forward windows based on config."""
        windows = []
        window_id = 0
        
        current_training_start = data_start
        
        while True:
            # Calculate window boundaries
            if self.config.walk_type == WalkForwardType.ROLLING:
                training_start = current_training_start
                training_end = training_start + timedelta(days=self.config.training_period_days)
            else:  # ANCHORED or EXPANDING
                training_start = data_start
                training_end = current_training_start + timedelta(days=self.config.training_period_days)
            
            testing_start = training_end
            testing_end = testing_start + timedelta(days=self.config.testing_period_days)
            
            # Check if we've gone past the data
            if testing_end > data_end:
                break
            
            window = WalkForwardWindow(
                window_id=window_id,
                training_start=training_start,
                training_end=training_end,
                testing_start=testing_start,
                testing_end=testing_end,
            )
            windows.append(window)
            
            # Move forward
            current_training_start += timedelta(days=self.config.step_days)
            window_id += 1
        
        return windows
    
    def optimize_parameters(
        self,
        data: pd.DataFrame,
        window: WalkForwardWindow,
    ) -> Dict[str, Any]:
        """
        Optimize parameters on training data.
        
        Uses grid search over parameter_ranges to find best parameters
        according to optimize_metric.
        """
        if not self.config.parameter_ranges:
            return {}
        
        # Filter training data
        training_data = data[
            (data.index >= window.training_start) &
            (data.index < window.training_end)
        ]
        
        if len(training_data) == 0:
            logger.warning(f"No training data for window {window.window_id}")
            return {}
        
        best_params = {}
        best_metric = float('-inf')
        
        # Generate parameter combinations
        param_combinations = self._generate_param_combinations()
        
        for params in param_combinations:
            try:
                # Run strategy with these params
                backtest_config = BacktestConfig(
                    initial_capital=self.config.initial_capital,
                    commission_percent=self.config.commission_percent,
                    slippage_percent=self.config.slippage_percent,
                    position_size_percent=self.config.position_size_percent,
                )
                
                trades, metrics = self.strategy_runner(training_data, params, backtest_config)
                
                # Check minimum trades
                if len(trades) < self.config.min_training_trades:
                    continue
                
                # Get optimization metric
                metric_value = metrics.get(self.config.optimize_metric, 0)
                
                if metric_value > best_metric:
                    best_metric = metric_value
                    best_params = params.copy()
                    
            except Exception as e:
                logger.warning(f"Error with params {params}: {e}")
                continue
        
        return best_params
    
    def _generate_param_combinations(self) -> List[Dict[str, Any]]:
        """Generate all parameter combinations from ranges."""
        if not self.config.parameter_ranges:
            return [{}]
        
        # Simple grid search implementation
        import itertools
        
        keys = list(self.config.parameter_ranges.keys())
        values = [self.config.parameter_ranges[k] for k in keys]
        
        combinations = []
        for combo in itertools.product(*values):
            combinations.append(dict(zip(keys, combo)))
        
        return combinations
    
    def run_window(
        self,
        data: pd.DataFrame,
        window: WalkForwardWindow,
        params: Dict[str, Any],
    ) -> WalkForwardWindow:
        """Run a single walk-forward window."""
        backtest_config = BacktestConfig(
            initial_capital=self.config.initial_capital,
            commission_percent=self.config.commission_percent,
            slippage_percent=self.config.slippage_percent,
            position_size_percent=self.config.position_size_percent,
        )
        
        # Run on training period (for metrics)
        training_data = data[
            (data.index >= window.training_start) &
            (data.index < window.training_end)
        ]
        
        if len(training_data) > 0:
            training_trades, training_metrics = self.strategy_runner(
                training_data, params, backtest_config
            )
            window.training_trades = len(training_trades)
            window.training_metrics = training_metrics
        
        # Run on testing period (out-of-sample)
        testing_data = data[
            (data.index >= window.testing_start) &
            (data.index <= window.testing_end)
        ]
        
        if len(testing_data) > 0:
            testing_trades, testing_metrics = self.strategy_runner(
                testing_data, params, backtest_config
            )
            window.testing_trades = len(testing_trades)
            window.testing_metrics = testing_metrics
            
            # Add trades to all_trades
            self.all_trades.extend(testing_trades)
        
        window.optimized_params = params
        
        return window
    
    def run(self, data: pd.DataFrame) -> WalkForwardResult:
        """
        Run complete walk-forward analysis.
        
        Args:
            data: DataFrame with datetime index containing market data
            
        Returns:
            WalkForwardResult with all windows and combined metrics
        """
        if data.index.dtype != 'datetime64[ns]':
            data.index = pd.to_datetime(data.index)
        
        data_start = data.index.min()
        data_end = data.index.max()
        
        logger.info(f"Running walk-forward analysis from {data_start} to {data_end}")
        
        # Generate windows
        self.windows = self.generate_windows(data_start, data_end)
        logger.info(f"Generated {len(self.windows)} walk-forward windows")
        
        if not self.windows:
            raise ValueError("No valid walk-forward windows could be generated")
        
        # Process each window
        for window in self.windows:
            logger.info(f"Processing window {window.window_id}: "
                       f"Training {window.training_start.date()} - {window.training_end.date()}, "
                       f"Testing {window.testing_start.date()} - {window.testing_end.date()}")
            
            # Optimize on training data
            optimized_params = self.optimize_parameters(data, window)
            
            # Run on both periods
            window = self.run_window(data, window, optimized_params)
            
            logger.info(f"Window {window.window_id}: "
                       f"Training trades={window.training_trades}, "
                       f"Testing trades={window.testing_trades}, "
                       f"OOS Sharpe={window.testing_metrics.get('sharpe_ratio', 'N/A')}")
        
        # Calculate combined metrics
        result = self._calculate_combined_results()
        
        return result
    
    def _calculate_combined_results(self) -> WalkForwardResult:
        """Calculate combined metrics across all windows."""
        # Aggregate OOS metrics
        oos_sharpes = []
        oos_returns = []
        is_returns = []
        profitable_windows = 0
        
        all_equity = []
        current_equity = self.config.initial_capital
        
        for window in self.windows:
            if window.testing_metrics:
                oos_sharpes.append(window.testing_metrics.get('sharpe_ratio', 0))
                oos_return = window.testing_metrics.get('total_return_percent', 0)
                oos_returns.append(oos_return)
                
                if oos_return > 0:
                    profitable_windows += 1
                
                # Track equity
                current_equity *= (1 + oos_return / 100)
                all_equity.append({
                    'window_id': window.window_id,
                    'date': window.testing_end,
                    'equity': current_equity,
                })
            
            if window.training_metrics:
                is_returns.append(window.training_metrics.get('total_return_percent', 0))
        
        # Calculate consistency
        consistency_score = (profitable_windows / len(self.windows)) * 100 if self.windows else 0
        
        # Calculate efficiency ratio (OOS / IS performance)
        avg_is = np.mean(is_returns) if is_returns else 0
        avg_oos = np.mean(oos_returns) if oos_returns else 0
        efficiency_ratio = avg_oos / avg_is if avg_is != 0 else 0
        
        # Calculate parameter stability
        param_stability = self._calculate_param_stability()
        
        # Combined metrics
        combined_metrics = {
            'total_windows': len(self.windows),
            'profitable_windows': profitable_windows,
            'consistency_score': round(consistency_score, 2),
            'efficiency_ratio': round(efficiency_ratio, 2),
            
            'avg_oos_sharpe': round(np.mean(oos_sharpes), 2) if oos_sharpes else 0,
            'std_oos_sharpe': round(np.std(oos_sharpes), 2) if oos_sharpes else 0,
            'avg_oos_return': round(avg_oos, 2),
            
            'total_oos_return': round(sum(oos_returns), 2),
            'final_equity': round(current_equity, 2),
            'total_trades': len(self.all_trades),
            
            'walk_forward_type': self.config.walk_type.value,
            'training_period_days': self.config.training_period_days,
            'testing_period_days': self.config.testing_period_days,
        }
        
        return WalkForwardResult(
            windows=self.windows,
            combined_metrics=combined_metrics,
            equity_curve=all_equity,
            all_trades=[self._trade_to_dict(t) for t in self.all_trades],
            consistency_score=consistency_score,
            efficiency_ratio=efficiency_ratio,
            parameter_stability=param_stability,
        )
    
    def _calculate_param_stability(self) -> Dict[str, float]:
        """Calculate stability of optimized parameters across windows."""
        param_values: Dict[str, List] = {}
        
        for window in self.windows:
            for param, value in window.optimized_params.items():
                if param not in param_values:
                    param_values[param] = []
                try:
                    param_values[param].append(float(value))
                except (ValueError, TypeError):
                    continue
        
        stability = {}
        for param, values in param_values.items():
            if len(values) > 1:
                stability[param] = round(np.std(values), 4)
            else:
                stability[param] = 0.0
        
        return stability
    
    def _trade_to_dict(self, trade: Trade) -> Dict[str, Any]:
        """Convert Trade to dictionary."""
        return {
            'entry_time': trade.entry_time.isoformat() if isinstance(trade.entry_time, datetime) else str(trade.entry_time),
            'exit_time': trade.exit_time.isoformat() if isinstance(trade.exit_time, datetime) else str(trade.exit_time),
            'symbol': trade.symbol,
            'side': trade.side.value if hasattr(trade.side, 'value') else str(trade.side),
            'entry_price': trade.entry_price,
            'exit_price': trade.exit_price,
            'quantity': trade.quantity,
            'pnl': trade.pnl,
            'pnl_percent': trade.pnl_percent,
            'commission': trade.commission,
            'slippage': trade.slippage,
        }


def create_walk_forward_engine(
    strategy_runner: Callable,
    training_period_days: int = 180,
    testing_period_days: int = 30,
    step_days: int = 30,
    walk_type: str = "rolling",
    optimize_metric: str = "sharpe_ratio",
    parameter_ranges: Optional[Dict[str, List]] = None,
    initial_capital: float = 100000.0,
) -> WalkForwardEngine:
    """
    Factory function to create a walk-forward engine.
    
    Args:
        strategy_runner: Function that takes (data, params, backtest_config) and returns (trades, metrics)
        training_period_days: Days for training (in-sample) period
        testing_period_days: Days for testing (out-of-sample) period
        step_days: Days to step forward between windows
        walk_type: "rolling", "anchored", or "expanding"
        optimize_metric: Metric to optimize ("sharpe_ratio", "total_return_percent", etc.)
        parameter_ranges: Dict of parameter names to list of values to test
        initial_capital: Starting capital
        
    Returns:
        Configured WalkForwardEngine
    """
    config = WalkForwardConfig(
        training_period_days=training_period_days,
        testing_period_days=testing_period_days,
        step_days=step_days,
        walk_type=WalkForwardType(walk_type),
        optimize_metric=optimize_metric,
        parameter_ranges=parameter_ranges or {},
        initial_capital=initial_capital,
    )
    
    return WalkForwardEngine(config, strategy_runner)
