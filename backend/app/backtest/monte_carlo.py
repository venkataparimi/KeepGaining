"""
Monte Carlo Simulator for Strategy Robustness Testing
KeepGaining Trading Platform

Provides statistical robustness testing for trading strategies by:
- Shuffling trade order to test path-dependency
- Bootstrap resampling to assess variance
- Calculating probability of ruin and confidence intervals
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np
import pandas as pd
from enum import Enum
from loguru import logger


class SimulationType(str, Enum):
    """Types of Monte Carlo simulation."""
    SHUFFLE = "shuffle"          # Random order shuffling
    BOOTSTRAP = "bootstrap"      # Bootstrap with replacement
    PARAMETRIC = "parametric"    # Parametric (normal) simulation


@dataclass
class MonteCarloResult:
    """Results from Monte Carlo simulation."""
    
    # Return statistics
    median_return: float
    mean_return: float
    std_return: float
    percentile_5: float       # 5th percentile (worst case)
    percentile_25: float      # 25th percentile
    percentile_75: float      # 75th percentile
    percentile_95: float      # 95th percentile (best case)
    
    # Risk metrics
    probability_of_profit: float      # P(return > 0)
    probability_of_ruin: float        # P(drawdown > ruin_threshold)
    expected_max_drawdown: float
    max_drawdown_95: float            # 95th percentile of max drawdowns
    
    # Confidence intervals
    return_ci_95: Tuple[float, float]  # 95% CI for returns
    sharpe_ci_95: Tuple[float, float]  # 95% CI for Sharpe ratio
    
    # Simulation details
    num_simulations: int
    simulation_type: SimulationType
    original_trades: int
    
    # Distribution of outcomes
    return_distribution: List[float] = field(default_factory=list)
    drawdown_distribution: List[float] = field(default_factory=list)
    sharpe_distribution: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "median_return": round(self.median_return, 4),
            "mean_return": round(self.mean_return, 4),
            "std_return": round(self.std_return, 4),
            "percentile_5": round(self.percentile_5, 4),
            "percentile_25": round(self.percentile_25, 4),
            "percentile_75": round(self.percentile_75, 4),
            "percentile_95": round(self.percentile_95, 4),
            "probability_of_profit": round(self.probability_of_profit, 4),
            "probability_of_ruin": round(self.probability_of_ruin, 4),
            "expected_max_drawdown": round(self.expected_max_drawdown, 4),
            "max_drawdown_95": round(self.max_drawdown_95, 4),
            "return_ci_95": (round(self.return_ci_95[0], 4), round(self.return_ci_95[1], 4)),
            "sharpe_ci_95": (round(self.sharpe_ci_95[0], 4), round(self.sharpe_ci_95[1], 4)),
            "num_simulations": self.num_simulations,
            "simulation_type": self.simulation_type.value,
            "original_trades": self.original_trades,
        }


@dataclass
class TradeRecord:
    """Simplified trade record for Monte Carlo."""
    pnl: float
    pnl_percent: float
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    symbol: str = ""


class MonteCarloSimulator:
    """
    Monte Carlo simulator for strategy robustness testing.
    
    Performs multiple simulations by:
    1. SHUFFLE: Randomly reorder trades to test path-dependency
    2. BOOTSTRAP: Sample trades with replacement to test variance
    3. PARAMETRIC: Generate synthetic trades from fitted distribution
    
    Usage:
        simulator = MonteCarloSimulator(initial_capital=100000)
        result = simulator.run(trades, simulations=1000, sim_type=SimulationType.SHUFFLE)
        
        print(f"Probability of Profit: {result.probability_of_profit:.1%}")
        print(f"Expected Max Drawdown: {result.expected_max_drawdown:.1%}")
        print(f"95% CI for Returns: {result.return_ci_95}")
    """
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        ruin_threshold: float = 0.5,  # 50% drawdown = ruin
        seed: Optional[int] = None,
    ):
        """
        Initialize Monte Carlo simulator.
        
        Args:
            initial_capital: Starting capital
            ruin_threshold: Drawdown percentage that constitutes ruin (0.5 = 50%)
            seed: Random seed for reproducibility
        """
        self.initial_capital = initial_capital
        self.ruin_threshold = ruin_threshold
        
        if seed is not None:
            np.random.seed(seed)
    
    def run(
        self,
        trades: List[TradeRecord],
        simulations: int = 1000,
        sim_type: SimulationType = SimulationType.SHUFFLE,
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation.
        
        Args:
            trades: List of trade records with PnL
            simulations: Number of simulation runs
            sim_type: Type of simulation (shuffle, bootstrap, parametric)
            
        Returns:
            MonteCarloResult with comprehensive statistics
        """
        if len(trades) < 5:
            logger.warning(f"Only {len(trades)} trades - results may not be statistically significant")
        
        # Extract PnL values
        pnls = np.array([t.pnl for t in trades])
        pnl_percents = np.array([t.pnl_percent for t in trades])
        
        logger.info(f"Running {simulations} Monte Carlo simulations ({sim_type.value}) on {len(trades)} trades")
        
        # Run simulations
        if sim_type == SimulationType.SHUFFLE:
            results = self._run_shuffle_simulation(pnls, simulations)
        elif sim_type == SimulationType.BOOTSTRAP:
            results = self._run_bootstrap_simulation(pnls, simulations)
        elif sim_type == SimulationType.PARAMETRIC:
            results = self._run_parametric_simulation(pnls, pnl_percents, simulations)
        else:
            raise ValueError(f"Unknown simulation type: {sim_type}")
        
        # Calculate statistics
        return self._calculate_statistics(results, trades, simulations, sim_type)
    
    def _run_shuffle_simulation(
        self,
        pnls: np.ndarray,
        simulations: int,
    ) -> Dict[str, List[float]]:
        """
        Run shuffle simulation - randomly reorder trades.
        Tests if strategy results are path-dependent.
        """
        returns = []
        max_drawdowns = []
        sharpe_ratios = []
        
        for _ in range(simulations):
            # Shuffle trade order
            shuffled = np.random.permutation(pnls)
            
            # Calculate equity curve
            equity_curve = self.initial_capital + np.cumsum(shuffled)
            
            # Calculate final return
            final_return = (equity_curve[-1] - self.initial_capital) / self.initial_capital
            returns.append(final_return)
            
            # Calculate max drawdown
            running_max = np.maximum.accumulate(equity_curve)
            drawdowns = (running_max - equity_curve) / running_max
            max_drawdowns.append(np.max(drawdowns))
            
            # Calculate Sharpe (annualized, assuming daily)
            daily_returns = shuffled / self.initial_capital
            if np.std(daily_returns) > 0:
                sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252)
            else:
                sharpe = 0
            sharpe_ratios.append(sharpe)
        
        return {
            "returns": returns,
            "max_drawdowns": max_drawdowns,
            "sharpe_ratios": sharpe_ratios,
        }
    
    def _run_bootstrap_simulation(
        self,
        pnls: np.ndarray,
        simulations: int,
    ) -> Dict[str, List[float]]:
        """
        Run bootstrap simulation - sample with replacement.
        Tests variance of results and builds confidence intervals.
        """
        n_trades = len(pnls)
        returns = []
        max_drawdowns = []
        sharpe_ratios = []
        
        for _ in range(simulations):
            # Sample with replacement
            indices = np.random.choice(n_trades, size=n_trades, replace=True)
            sampled = pnls[indices]
            
            # Calculate equity curve
            equity_curve = self.initial_capital + np.cumsum(sampled)
            
            # Calculate final return
            final_return = (equity_curve[-1] - self.initial_capital) / self.initial_capital
            returns.append(final_return)
            
            # Calculate max drawdown
            running_max = np.maximum.accumulate(equity_curve)
            drawdowns = (running_max - equity_curve) / running_max
            max_drawdowns.append(np.max(drawdowns))
            
            # Calculate Sharpe
            daily_returns = sampled / self.initial_capital
            if np.std(daily_returns) > 0:
                sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252)
            else:
                sharpe = 0
            sharpe_ratios.append(sharpe)
        
        return {
            "returns": returns,
            "max_drawdowns": max_drawdowns,
            "sharpe_ratios": sharpe_ratios,
        }
    
    def _run_parametric_simulation(
        self,
        pnls: np.ndarray,
        pnl_percents: np.ndarray,
        simulations: int,
    ) -> Dict[str, List[float]]:
        """
        Run parametric simulation - generate synthetic trades from fitted distribution.
        Uses empirical distribution (more realistic than normal).
        """
        n_trades = len(pnls)
        returns = []
        max_drawdowns = []
        sharpe_ratios = []
        
        # Fit distribution parameters
        mean_pnl = np.mean(pnls)
        std_pnl = np.std(pnls)
        
        # Use skew-normal if scipy available, otherwise normal
        try:
            from scipy import stats
            # Fit to actual distribution
            params = stats.norm.fit(pnls)
        except ImportError:
            params = (mean_pnl, std_pnl)
        
        for _ in range(simulations):
            # Generate synthetic trades
            synthetic_pnls = np.random.normal(mean_pnl, std_pnl, n_trades)
            
            # Calculate equity curve
            equity_curve = self.initial_capital + np.cumsum(synthetic_pnls)
            
            # Ensure equity doesn't go negative
            equity_curve = np.maximum(equity_curve, 1)
            
            # Calculate final return
            final_return = (equity_curve[-1] - self.initial_capital) / self.initial_capital
            returns.append(final_return)
            
            # Calculate max drawdown
            running_max = np.maximum.accumulate(equity_curve)
            drawdowns = (running_max - equity_curve) / running_max
            max_drawdowns.append(np.max(drawdowns))
            
            # Calculate Sharpe
            daily_returns = synthetic_pnls / self.initial_capital
            if np.std(daily_returns) > 0:
                sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252)
            else:
                sharpe = 0
            sharpe_ratios.append(sharpe)
        
        return {
            "returns": returns,
            "max_drawdowns": max_drawdowns,
            "sharpe_ratios": sharpe_ratios,
        }
    
    def _calculate_statistics(
        self,
        results: Dict[str, List[float]],
        trades: List[TradeRecord],
        simulations: int,
        sim_type: SimulationType,
    ) -> MonteCarloResult:
        """Calculate comprehensive statistics from simulation results."""
        
        returns = np.array(results["returns"])
        drawdowns = np.array(results["max_drawdowns"])
        sharpes = np.array(results["sharpe_ratios"])
        
        # Return statistics
        median_return = np.median(returns)
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        # Percentiles
        percentile_5 = np.percentile(returns, 5)
        percentile_25 = np.percentile(returns, 25)
        percentile_75 = np.percentile(returns, 75)
        percentile_95 = np.percentile(returns, 95)
        
        # Risk metrics
        probability_of_profit = np.mean(returns > 0)
        probability_of_ruin = np.mean(drawdowns > self.ruin_threshold)
        expected_max_drawdown = np.mean(drawdowns)
        max_drawdown_95 = np.percentile(drawdowns, 95)
        
        # Confidence intervals (95%)
        return_ci_95 = (np.percentile(returns, 2.5), np.percentile(returns, 97.5))
        sharpe_ci_95 = (np.percentile(sharpes, 2.5), np.percentile(sharpes, 97.5))
        
        return MonteCarloResult(
            median_return=median_return,
            mean_return=mean_return,
            std_return=std_return,
            percentile_5=percentile_5,
            percentile_25=percentile_25,
            percentile_75=percentile_75,
            percentile_95=percentile_95,
            probability_of_profit=probability_of_profit,
            probability_of_ruin=probability_of_ruin,
            expected_max_drawdown=expected_max_drawdown,
            max_drawdown_95=max_drawdown_95,
            return_ci_95=return_ci_95,
            sharpe_ci_95=sharpe_ci_95,
            num_simulations=simulations,
            simulation_type=sim_type,
            original_trades=len(trades),
            return_distribution=returns.tolist(),
            drawdown_distribution=drawdowns.tolist(),
            sharpe_distribution=sharpes.tolist(),
        )
    
    def analyze_path_dependency(
        self,
        trades: List[TradeRecord],
        simulations: int = 1000,
    ) -> Dict[str, Any]:
        """
        Analyze if strategy results are path-dependent.
        
        Compares actual sequence return to shuffled distribution.
        High path-dependency means results depend heavily on trade order.
        
        Returns:
            Dict with dependency metrics and percentile rank
        """
        # Calculate actual return
        pnls = np.array([t.pnl for t in trades])
        actual_return = np.sum(pnls) / self.initial_capital
        
        # Run shuffle simulation
        shuffle_result = self.run(trades, simulations, SimulationType.SHUFFLE)
        
        # Calculate percentile rank of actual return
        percentile_rank = np.mean(
            np.array(shuffle_result.return_distribution) <= actual_return
        ) * 100
        
        # Path dependency score (0 = no dependency, 1 = high dependency)
        # If actual return is at extreme percentiles, high path dependency
        if percentile_rank < 50:
            path_score = (50 - percentile_rank) / 50
        else:
            path_score = (percentile_rank - 50) / 50
        
        return {
            "actual_return": actual_return,
            "median_shuffled_return": shuffle_result.median_return,
            "percentile_rank": percentile_rank,
            "path_dependency_score": path_score,
            "is_path_dependent": path_score > 0.3,  # >30% deviation from median
            "interpretation": self._interpret_path_dependency(path_score, percentile_rank),
        }
    
    def _interpret_path_dependency(self, score: float, percentile: float) -> str:
        """Generate human-readable interpretation of path dependency."""
        if score < 0.1:
            return "Low path dependency - results are robust to trade ordering"
        elif score < 0.3:
            return "Moderate path dependency - some sensitivity to trade ordering"
        else:
            if percentile < 50:
                return f"High path dependency - actual sequence underperformed ({percentile:.0f}th percentile)"
            else:
                return f"High path dependency - actual sequence outperformed ({percentile:.0f}th percentile), be cautious of luck"


def create_monte_carlo_simulator(
    initial_capital: float = 100000.0,
    ruin_threshold: float = 0.5,
    seed: Optional[int] = None,
) -> MonteCarloSimulator:
    """Factory function to create Monte Carlo simulator."""
    return MonteCarloSimulator(
        initial_capital=initial_capital,
        ruin_threshold=ruin_threshold,
        seed=seed,
    )
