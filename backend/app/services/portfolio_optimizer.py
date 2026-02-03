"""
Portfolio Optimization Service

Implements modern portfolio theory and advanced optimization:
- Mean-Variance Optimization (Markowitz)
- Risk Parity
- Black-Litterman Model
- Maximum Sharpe Ratio
- Minimum Volatility
- Hierarchical Risk Parity (HRP)

Provides:
- Optimal portfolio weights
- Efficient frontier visualization
- Risk contribution analysis
- Rebalancing recommendations
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize, Bounds, LinearConstraint

logger = logging.getLogger(__name__)


class OptimizationMethod(str, Enum):
    """Portfolio optimization methods."""
    MAX_SHARPE = "max_sharpe"
    MIN_VOLATILITY = "min_volatility"
    RISK_PARITY = "risk_parity"
    MAX_RETURN = "max_return"
    EQUAL_WEIGHT = "equal_weight"
    INVERSE_VOLATILITY = "inverse_volatility"


class RiskMetric(str, Enum):
    """Risk measurement methods."""
    VOLATILITY = "volatility"
    VAR = "var"  # Value at Risk
    CVAR = "cvar"  # Conditional VaR
    MAX_DRAWDOWN = "max_drawdown"
    SEMI_VARIANCE = "semi_variance"


@dataclass
class PortfolioAllocation:
    """Optimal portfolio allocation."""
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    var_95: float  # 95% VaR
    cvar_95: float  # 95% CVaR
    max_drawdown: float
    diversification_ratio: float
    optimization_method: OptimizationMethod
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass 
class EfficientFrontierPoint:
    """A point on the efficient frontier."""
    return_: float
    volatility: float
    sharpe_ratio: float
    weights: Dict[str, float]


@dataclass
class RiskContribution:
    """Risk contribution analysis."""
    symbol: str
    weight: float
    marginal_risk: float
    risk_contribution: float
    risk_contribution_pct: float


@dataclass
class RebalanceRecommendation:
    """Portfolio rebalancing recommendation."""
    symbol: str
    current_weight: float
    target_weight: float
    action: str  # 'buy', 'sell', 'hold'
    amount_pct: float
    reason: str


class PortfolioOptimizer:
    """
    Portfolio Optimization Service.
    
    Implements various portfolio optimization techniques for
    optimal capital allocation across assets.
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.065,  # ~6.5% India 10Y yield
        trading_days: int = 252,
        min_weight: float = 0.0,
        max_weight: float = 0.4,  # Max 40% in single asset
        transaction_cost: float = 0.001  # 0.1% transaction cost
    ):
        self.risk_free_rate = risk_free_rate
        self.trading_days = trading_days
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.transaction_cost = transaction_cost
    
    def calculate_returns(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Calculate daily returns from price data."""
        return prices.pct_change().dropna()
    
    def calculate_expected_returns(
        self,
        returns: pd.DataFrame,
        method: str = "mean"
    ) -> pd.Series:
        """
        Calculate expected returns.
        
        Args:
            returns: Daily returns DataFrame
            method: 'mean', 'ewma', or 'cagr'
            
        Returns:
            Annualized expected returns per asset
        """
        if method == "mean":
            return returns.mean() * self.trading_days
        elif method == "ewma":
            # Exponentially weighted mean (more weight on recent)
            return returns.ewm(span=60).mean().iloc[-1] * self.trading_days
        elif method == "cagr":
            # Compound Annual Growth Rate
            total_return = (1 + returns).prod()
            n_years = len(returns) / self.trading_days
            return total_return ** (1 / n_years) - 1
        else:
            return returns.mean() * self.trading_days
    
    def calculate_covariance(
        self,
        returns: pd.DataFrame,
        method: str = "sample"
    ) -> pd.DataFrame:
        """
        Calculate covariance matrix.
        
        Args:
            returns: Daily returns DataFrame
            method: 'sample', 'ewma', or 'shrinkage'
            
        Returns:
            Annualized covariance matrix
        """
        if method == "sample":
            return returns.cov() * self.trading_days
        elif method == "ewma":
            return returns.ewm(span=60).cov().iloc[-len(returns.columns):] * self.trading_days
        elif method == "shrinkage":
            # Ledoit-Wolf shrinkage (simplified)
            sample_cov = returns.cov()
            n = len(returns)
            p = len(returns.columns)
            
            # Target: identity matrix scaled
            mu = np.trace(sample_cov) / p
            target = mu * np.eye(p)
            
            # Shrinkage intensity (simplified)
            delta = 0.1
            
            shrunk = (1 - delta) * sample_cov + delta * pd.DataFrame(target, index=sample_cov.index, columns=sample_cov.columns)
            return shrunk * self.trading_days
        else:
            return returns.cov() * self.trading_days
    
    def portfolio_return(self, weights: np.ndarray, expected_returns: np.ndarray) -> float:
        """Calculate portfolio expected return."""
        return np.dot(weights, expected_returns)
    
    def portfolio_volatility(self, weights: np.ndarray, cov_matrix: np.ndarray) -> float:
        """Calculate portfolio volatility."""
        return np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
    
    def portfolio_sharpe(self, weights: np.ndarray, expected_returns: np.ndarray, cov_matrix: np.ndarray) -> float:
        """Calculate portfolio Sharpe ratio."""
        ret = self.portfolio_return(weights, expected_returns)
        vol = self.portfolio_volatility(weights, cov_matrix)
        return (ret - self.risk_free_rate) / vol if vol > 0 else 0
    
    def negative_sharpe(self, weights: np.ndarray, expected_returns: np.ndarray, cov_matrix: np.ndarray) -> float:
        """Negative Sharpe ratio for minimization."""
        return -self.portfolio_sharpe(weights, expected_returns, cov_matrix)
    
    async def optimize(
        self,
        prices: pd.DataFrame,
        method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
        constraints: Optional[Dict[str, Any]] = None
    ) -> PortfolioAllocation:
        """
        Optimize portfolio weights.
        
        Args:
            prices: Price DataFrame with columns as asset names
            method: Optimization method to use
            constraints: Additional constraints (sector limits, etc.)
            
        Returns:
            PortfolioAllocation with optimal weights
        """
        returns = self.calculate_returns(prices)
        expected_returns = self.calculate_expected_returns(returns)
        cov_matrix = self.calculate_covariance(returns)
        
        n_assets = len(prices.columns)
        symbols = list(prices.columns)
        
        # Initial guess: equal weights
        init_weights = np.array([1.0 / n_assets] * n_assets)
        
        # Bounds
        bounds = Bounds(
            [self.min_weight] * n_assets,
            [self.max_weight] * n_assets
        )
        
        # Constraint: weights sum to 1
        sum_constraint = LinearConstraint(
            np.ones(n_assets),
            lb=1.0,
            ub=1.0
        )
        
        if method == OptimizationMethod.MAX_SHARPE:
            result = minimize(
                self.negative_sharpe,
                init_weights,
                args=(expected_returns.values, cov_matrix.values),
                method='SLSQP',
                bounds=bounds,
                constraints={'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
            )
            optimal_weights = result.x
            
        elif method == OptimizationMethod.MIN_VOLATILITY:
            result = minimize(
                lambda w: self.portfolio_volatility(w, cov_matrix.values),
                init_weights,
                method='SLSQP',
                bounds=bounds,
                constraints={'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
            )
            optimal_weights = result.x
            
        elif method == OptimizationMethod.RISK_PARITY:
            optimal_weights = self._risk_parity_weights(cov_matrix.values, n_assets)
            
        elif method == OptimizationMethod.MAX_RETURN:
            # Maximize return subject to volatility constraint
            target_vol = np.sqrt(np.diag(cov_matrix.values)).mean()  # Average asset volatility
            result = minimize(
                lambda w: -self.portfolio_return(w, expected_returns.values),
                init_weights,
                method='SLSQP',
                bounds=bounds,
                constraints=[
                    {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
                    {'type': 'ineq', 'fun': lambda x: target_vol - self.portfolio_volatility(x, cov_matrix.values)}
                ]
            )
            optimal_weights = result.x
            
        elif method == OptimizationMethod.EQUAL_WEIGHT:
            optimal_weights = np.array([1.0 / n_assets] * n_assets)
            
        elif method == OptimizationMethod.INVERSE_VOLATILITY:
            vols = np.sqrt(np.diag(cov_matrix.values))
            inv_vols = 1.0 / vols
            optimal_weights = inv_vols / inv_vols.sum()
            
        else:
            optimal_weights = init_weights
        
        # Normalize weights
        optimal_weights = optimal_weights / optimal_weights.sum()
        optimal_weights = np.clip(optimal_weights, self.min_weight, self.max_weight)
        optimal_weights = optimal_weights / optimal_weights.sum()
        
        # Calculate portfolio metrics
        port_return = self.portfolio_return(optimal_weights, expected_returns.values)
        port_vol = self.portfolio_volatility(optimal_weights, cov_matrix.values)
        port_sharpe = (port_return - self.risk_free_rate) / port_vol if port_vol > 0 else 0
        
        # Calculate VaR and CVaR
        port_returns = returns.dot(optimal_weights)
        var_95 = np.percentile(port_returns, 5) * np.sqrt(self.trading_days)
        cvar_95 = port_returns[port_returns <= np.percentile(port_returns, 5)].mean() * np.sqrt(self.trading_days)
        
        # Calculate max drawdown
        cumulative_returns = (1 + port_returns).cumprod()
        rolling_max = cumulative_returns.expanding().max()
        drawdowns = cumulative_returns / rolling_max - 1
        max_dd = drawdowns.min()
        
        # Calculate diversification ratio
        weighted_vols = optimal_weights * np.sqrt(np.diag(cov_matrix.values))
        diversification_ratio = weighted_vols.sum() / port_vol if port_vol > 0 else 1
        
        return PortfolioAllocation(
            weights={symbols[i]: round(w, 4) for i, w in enumerate(optimal_weights)},
            expected_return=round(port_return, 4),
            volatility=round(port_vol, 4),
            sharpe_ratio=round(port_sharpe, 4),
            var_95=round(var_95, 4),
            cvar_95=round(cvar_95, 4),
            max_drawdown=round(max_dd, 4),
            diversification_ratio=round(diversification_ratio, 4),
            optimization_method=method,
        )
    
    def _risk_parity_weights(self, cov_matrix: np.ndarray, n_assets: int) -> np.ndarray:
        """Calculate risk parity weights (equal risk contribution)."""
        def risk_budget_objective(weights, cov):
            port_vol = np.sqrt(np.dot(weights.T, np.dot(cov, weights)))
            marginal_risk = np.dot(cov, weights) / port_vol
            risk_contribution = weights * marginal_risk
            target_risk = port_vol / n_assets
            return np.sum((risk_contribution - target_risk) ** 2)
        
        init_weights = np.array([1.0 / n_assets] * n_assets)
        
        result = minimize(
            risk_budget_objective,
            init_weights,
            args=(cov_matrix,),
            method='SLSQP',
            bounds=Bounds([0.01] * n_assets, [0.5] * n_assets),
            constraints={'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
        )
        
        return result.x
    
    async def efficient_frontier(
        self,
        prices: pd.DataFrame,
        n_points: int = 50
    ) -> List[EfficientFrontierPoint]:
        """
        Generate efficient frontier points.
        
        Args:
            prices: Price DataFrame
            n_points: Number of points on the frontier
            
        Returns:
            List of EfficientFrontierPoint
        """
        returns = self.calculate_returns(prices)
        expected_returns = self.calculate_expected_returns(returns)
        cov_matrix = self.calculate_covariance(returns)
        
        n_assets = len(prices.columns)
        symbols = list(prices.columns)
        
        # Find min and max return portfolios
        min_vol_alloc = await self.optimize(prices, OptimizationMethod.MIN_VOLATILITY)
        
        # Target returns range
        min_ret = min_vol_alloc.expected_return
        max_ret = expected_returns.max() * 0.95
        target_returns = np.linspace(min_ret, max_ret, n_points)
        
        frontier_points = []
        
        for target_ret in target_returns:
            # Minimize volatility for target return
            result = minimize(
                lambda w: self.portfolio_volatility(w, cov_matrix.values),
                np.array([1.0 / n_assets] * n_assets),
                method='SLSQP',
                bounds=Bounds([self.min_weight] * n_assets, [self.max_weight] * n_assets),
                constraints=[
                    {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
                    {'type': 'eq', 'fun': lambda x, t=target_ret: self.portfolio_return(x, expected_returns.values) - t}
                ]
            )
            
            if result.success:
                weights = result.x / result.x.sum()
                vol = self.portfolio_volatility(weights, cov_matrix.values)
                ret = self.portfolio_return(weights, expected_returns.values)
                sharpe = (ret - self.risk_free_rate) / vol if vol > 0 else 0
                
                frontier_points.append(EfficientFrontierPoint(
                    return_=round(ret, 4),
                    volatility=round(vol, 4),
                    sharpe_ratio=round(sharpe, 4),
                    weights={symbols[i]: round(w, 4) for i, w in enumerate(weights)}
                ))
        
        return frontier_points
    
    async def risk_contribution_analysis(
        self,
        prices: pd.DataFrame,
        weights: Dict[str, float]
    ) -> List[RiskContribution]:
        """
        Analyze risk contribution of each asset.
        
        Args:
            prices: Price DataFrame
            weights: Current portfolio weights
            
        Returns:
            List of RiskContribution per asset
        """
        returns = self.calculate_returns(prices)
        cov_matrix = self.calculate_covariance(returns)
        
        symbols = list(prices.columns)
        w = np.array([weights.get(s, 0) for s in symbols])
        
        # Portfolio volatility
        port_vol = self.portfolio_volatility(w, cov_matrix.values)
        
        # Marginal risk (partial derivative of portfolio vol w.r.t. weights)
        marginal_risk = np.dot(cov_matrix.values, w) / port_vol
        
        # Risk contribution
        risk_contribution = w * marginal_risk
        total_risk = risk_contribution.sum()
        
        contributions = []
        for i, symbol in enumerate(symbols):
            contributions.append(RiskContribution(
                symbol=symbol,
                weight=round(w[i], 4),
                marginal_risk=round(marginal_risk[i], 4),
                risk_contribution=round(risk_contribution[i], 4),
                risk_contribution_pct=round(risk_contribution[i] / total_risk * 100, 2) if total_risk > 0 else 0
            ))
        
        return sorted(contributions, key=lambda x: x.risk_contribution_pct, reverse=True)
    
    async def rebalance_recommendations(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        threshold: float = 0.05
    ) -> List[RebalanceRecommendation]:
        """
        Generate rebalancing recommendations.
        
        Args:
            current_weights: Current portfolio weights
            target_weights: Target portfolio weights
            threshold: Minimum deviation to trigger rebalance (5% default)
            
        Returns:
            List of RebalanceRecommendation
        """
        recommendations = []
        
        all_symbols = set(current_weights.keys()) | set(target_weights.keys())
        
        for symbol in all_symbols:
            current = current_weights.get(symbol, 0)
            target = target_weights.get(symbol, 0)
            diff = target - current
            
            if abs(diff) < threshold:
                action = "hold"
                reason = f"Within {threshold*100:.0f}% threshold"
            elif diff > 0:
                action = "buy"
                reason = f"Underweight by {abs(diff)*100:.1f}%"
            else:
                action = "sell"
                reason = f"Overweight by {abs(diff)*100:.1f}%"
            
            recommendations.append(RebalanceRecommendation(
                symbol=symbol,
                current_weight=round(current, 4),
                target_weight=round(target, 4),
                action=action,
                amount_pct=round(abs(diff) * 100, 2),
                reason=reason
            ))
        
        return sorted(recommendations, key=lambda x: x.amount_pct, reverse=True)
    
    async def black_litterman(
        self,
        prices: pd.DataFrame,
        views: Dict[str, float],  # Symbol -> Expected return view
        view_confidences: Optional[Dict[str, float]] = None,
        tau: float = 0.05
    ) -> PortfolioAllocation:
        """
        Black-Litterman portfolio optimization.
        
        Combines market equilibrium with investor views.
        
        Args:
            prices: Price DataFrame
            views: Dict of symbol -> expected return views
            view_confidences: Dict of symbol -> confidence (0-1)
            tau: Scalar for uncertainty in prior
            
        Returns:
            PortfolioAllocation
        """
        returns = self.calculate_returns(prices)
        cov_matrix = self.calculate_covariance(returns)
        
        symbols = list(prices.columns)
        n_assets = len(symbols)
        
        # Market cap weights (assume equal for simplicity)
        market_weights = np.array([1.0 / n_assets] * n_assets)
        
        # Prior (equilibrium) returns
        delta = (self.risk_free_rate + 0.05)  # Risk aversion
        pi = delta * np.dot(cov_matrix.values, market_weights)
        
        # Build view matrix P and view vector Q
        view_symbols = [s for s in views.keys() if s in symbols]
        k = len(view_symbols)
        
        if k == 0:
            # No views, return market equilibrium
            return await self.optimize(prices, OptimizationMethod.MAX_SHARPE)
        
        P = np.zeros((k, n_assets))
        Q = np.zeros(k)
        
        for i, symbol in enumerate(view_symbols):
            idx = symbols.index(symbol)
            P[i, idx] = 1
            Q[i] = views[symbol]
        
        # Uncertainty in views
        if view_confidences:
            omega_diag = [
                tau * cov_matrix.values[symbols.index(s), symbols.index(s)] / view_confidences.get(s, 0.5)
                for s in view_symbols
            ]
        else:
            omega_diag = [tau * cov_matrix.values[symbols.index(s), symbols.index(s)] for s in view_symbols]
        
        omega = np.diag(omega_diag)
        
        # Black-Litterman expected returns
        tau_sigma = tau * cov_matrix.values
        
        # BL formula
        M_inv = np.linalg.inv(np.linalg.inv(tau_sigma) + P.T @ np.linalg.inv(omega) @ P)
        bl_returns = M_inv @ (np.linalg.inv(tau_sigma) @ pi + P.T @ np.linalg.inv(omega) @ Q)
        
        # Create synthetic expected returns for optimization
        bl_expected = pd.Series(bl_returns, index=symbols)
        
        # Optimize using BL expected returns
        init_weights = np.array([1.0 / n_assets] * n_assets)
        
        result = minimize(
            lambda w: -((np.dot(w, bl_returns) - self.risk_free_rate) / self.portfolio_volatility(w, cov_matrix.values)),
            init_weights,
            method='SLSQP',
            bounds=Bounds([self.min_weight] * n_assets, [self.max_weight] * n_assets),
            constraints={'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
        )
        
        optimal_weights = result.x / result.x.sum()
        
        # Calculate metrics
        port_return = np.dot(optimal_weights, bl_returns)
        port_vol = self.portfolio_volatility(optimal_weights, cov_matrix.values)
        
        return PortfolioAllocation(
            weights={symbols[i]: round(w, 4) for i, w in enumerate(optimal_weights)},
            expected_return=round(port_return, 4),
            volatility=round(port_vol, 4),
            sharpe_ratio=round((port_return - self.risk_free_rate) / port_vol, 4) if port_vol > 0 else 0,
            var_95=0,  # Calculate if needed
            cvar_95=0,
            max_drawdown=0,
            diversification_ratio=1.0,
            optimization_method=OptimizationMethod.MAX_SHARPE,
        )
    
    def get_summary(self) -> Dict[str, Any]:
        """Get optimizer configuration summary."""
        return {
            "risk_free_rate": self.risk_free_rate,
            "trading_days": self.trading_days,
            "min_weight": self.min_weight,
            "max_weight": self.max_weight,
            "transaction_cost": self.transaction_cost,
            "available_methods": [m.value for m in OptimizationMethod],
            "available_risk_metrics": [r.value for r in RiskMetric],
        }


# Singleton instance
_portfolio_optimizer: Optional[PortfolioOptimizer] = None


def get_portfolio_optimizer() -> PortfolioOptimizer:
    """Get or create portfolio optimizer singleton."""
    global _portfolio_optimizer
    if _portfolio_optimizer is None:
        _portfolio_optimizer = PortfolioOptimizer()
    return _portfolio_optimizer
