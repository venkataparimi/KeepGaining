"""
Enhanced Backtest Engine with realistic modeling and comprehensive metrics
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

@dataclass
class Trade:
    """Individual trade record"""
    entry_time: datetime
    exit_time: datetime
    symbol: str
    side: OrderSide
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    pnl_percent: float
    commission: float
    slippage: float
    
@dataclass
class BacktestConfig:
    """Backtest configuration"""
    initial_capital: float = 100000.0
    commission_percent: float = 0.03  # 0.03% per trade
    slippage_percent: float = 0.05    # 0.05% slippage
    position_size_percent: float = 10.0  # 10% of capital per position
    max_positions: int = 5
    
class BacktestEngine:
    """Enhanced backtest engine with realistic modeling"""
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.current_capital = self.config.initial_capital
        self.peak_capital = self.config.initial_capital
        
    def calculate_slippage(self, price: float, side: OrderSide) -> float:
        """Calculate slippage based on order side"""
        slippage_amount = price * (self.config.slippage_percent / 100)
        if side == OrderSide.BUY:
            return price + slippage_amount
        else:
            return price - slippage_amount
    
    def calculate_commission(self, price: float, quantity: int) -> float:
        """Calculate commission for a trade"""
        trade_value = price * quantity
        return trade_value * (self.config.commission_percent / 100)
    
    def execute_trade(
        self,
        entry_time: datetime,
        exit_time: datetime,
        symbol: str,
        side: OrderSide,
        entry_price: float,
        exit_price: float
    ) -> Trade:
        """Execute a trade with slippage and commission"""
        # Apply slippage
        actual_entry = self.calculate_slippage(entry_price, side)
        actual_exit = self.calculate_slippage(exit_price, 
                                              OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY)
        
        # Calculate position size
        position_value = self.current_capital * (self.config.position_size_percent / 100)
        quantity = int(position_value / actual_entry)
        
        # Calculate commission
        entry_commission = self.calculate_commission(actual_entry, quantity)
        exit_commission = self.calculate_commission(actual_exit, quantity)
        total_commission = entry_commission + exit_commission
        
        # Calculate P&L
        if side == OrderSide.BUY:
            pnl = (actual_exit - actual_entry) * quantity - total_commission
        else:
            pnl = (actual_entry - actual_exit) * quantity - total_commission
        
        pnl_percent = (pnl / (actual_entry * quantity)) * 100
        
        # Update capital
        self.current_capital += pnl
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital
        
        # Record equity point
        self.equity_curve.append({
            'timestamp': exit_time,
            'equity': self.current_capital,
            'drawdown': ((self.peak_capital - self.current_capital) / self.peak_capital) * 100
        })
        
        trade = Trade(
            entry_time=entry_time,
            exit_time=exit_time,
            symbol=symbol,
            side=side,
            entry_price=actual_entry,
            exit_price=actual_exit,
            quantity=quantity,
            pnl=pnl,
            pnl_percent=pnl_percent,
            commission=total_commission,
            slippage=(actual_entry - entry_price) * quantity
        )
        
        self.trades.append(trade)
        return trade
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics"""
        if not self.trades:
            return {}
        
        # Basic metrics
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl <= 0]
        
        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
        
        total_pnl = sum(t.pnl for t in self.trades)
        total_return = ((self.current_capital - self.config.initial_capital) / self.config.initial_capital) * 100
        
        # Win/Loss metrics
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0
        
        # Profit factor
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Drawdown metrics
        equity_series = pd.Series([e['equity'] for e in self.equity_curve])
        running_max = equity_series.expanding().max()
        drawdown_series = ((equity_series - running_max) / running_max) * 100
        max_drawdown = abs(drawdown_series.min())
        
        # Sharpe Ratio (annualized)
        if len(self.trades) > 1:
            returns = pd.Series([t.pnl_percent for t in self.trades])
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Sortino Ratio (downside deviation)
        downside_returns = returns[returns < 0] if len(self.trades) > 1 else pd.Series([])
        downside_std = downside_returns.std() if len(downside_returns) > 0 else 0
        sortino_ratio = (returns.mean() / downside_std) * np.sqrt(252) if downside_std > 0 else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'total_return_percent': round(total_return, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'max_drawdown_percent': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'sortino_ratio': round(sortino_ratio, 2),
            'final_capital': round(self.current_capital, 2),
            'total_commission': round(sum(t.commission for t in self.trades), 2),
            'total_slippage': round(sum(t.slippage for t in self.trades), 2)
        }
    
    def get_equity_curve(self) -> pd.DataFrame:
        """Get equity curve as DataFrame"""
        return pd.DataFrame(self.equity_curve)
    
    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame"""
        return pd.DataFrame([{
            'entry_time': t.entry_time,
            'exit_time': t.exit_time,
            'symbol': t.symbol,
            'side': t.side.value,
            'entry_price': t.entry_price,
            'exit_price': t.exit_price,
            'quantity': t.quantity,
            'pnl': t.pnl,
            'pnl_percent': t.pnl_percent,
            'commission': t.commission,
            'slippage': t.slippage
        } for t in self.trades])
