"""
Position Sizing Module

Comprehensive position sizing strategies for risk management:
- Fixed Amount: Trade a fixed capital amount
- Fixed Quantity: Trade a fixed number of lots/shares
- Percent Risk: Risk a fixed percentage of capital per trade
- Kelly Criterion: Optimal position size based on win rate
- Volatility Based: Size based on ATR volatility

All strategies respect maximum position limits and available capital.

Usage:
    sizer = PositionSizer(capital=100000)
    size = sizer.calculate_size(
        method=SizingMethod.PERCENT_RISK,
        entry_price=100,
        stop_loss=95,
        risk_percent=2.0
    )
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Any, Dict, Optional
import logging


class SizingMethod(str, Enum):
    """Position sizing method."""
    FIXED_AMOUNT = "fixed_amount"  # Fixed capital per trade
    FIXED_QUANTITY = "fixed_quantity"  # Fixed lots/shares
    PERCENT_RISK = "percent_risk"  # Risk X% of capital
    PERCENT_EQUITY = "percent_equity"  # Use X% of equity
    KELLY = "kelly"  # Kelly criterion
    VOLATILITY = "volatility"  # ATR-based sizing


@dataclass
class PositionSizeResult:
    """Result of position sizing calculation."""
    quantity: int
    position_value: Decimal
    risk_amount: Decimal
    risk_percent: Decimal
    method: SizingMethod
    calculation_details: Dict[str, Any]


class PositionSizer:
    """
    Position sizing calculator with multiple strategies.
    
    Provides risk-based position sizing that integrates with:
    - Trading signals (from strategy engine)
    - Risk management (max loss limits)
    - Capital management (available capital)
    """
    
    def __init__(
        self,
        capital: Decimal = Decimal("100000"),
        max_position_pct: Decimal = Decimal("20"),  # Max 20% in single position
        min_quantity: int = 1,  # Minimum order quantity
        lot_size: int = 1,  # Lot size for F&O
    ):
        self.capital = capital
        self.max_position_pct = max_position_pct
        self.min_quantity = min_quantity
        self.lot_size = lot_size
        self.logger = logging.getLogger(__name__)
    
    def calculate_size(
        self,
        method: SizingMethod,
        entry_price: Decimal,
        stop_loss: Optional[Decimal] = None,
        risk_percent: Decimal = Decimal("2"),
        fixed_amount: Optional[Decimal] = None,
        fixed_quantity: Optional[int] = None,
        win_rate: Optional[Decimal] = None,
        avg_win_loss_ratio: Optional[Decimal] = None,
        atr: Optional[Decimal] = None,
        atr_multiplier: Decimal = Decimal("1"),
        available_capital: Optional[Decimal] = None,
    ) -> PositionSizeResult:
        """
        Calculate position size based on the specified method.
        
        Args:
            method: Sizing method to use
            entry_price: Entry price for the trade
            stop_loss: Stop loss price (required for risk-based methods)
            risk_percent: Percentage of capital to risk (for PERCENT_RISK)
            fixed_amount: Fixed capital amount (for FIXED_AMOUNT)
            fixed_quantity: Fixed quantity (for FIXED_QUANTITY)
            win_rate: Historical win rate (for KELLY)
            avg_win_loss_ratio: Average win/loss ratio (for KELLY)
            atr: Average True Range (for VOLATILITY)
            atr_multiplier: ATR multiplier for volatility sizing
            available_capital: Override for available capital
            
        Returns:
            PositionSizeResult with calculated quantity and details
        """
        capital = available_capital or self.capital
        
        if method == SizingMethod.FIXED_AMOUNT:
            return self._fixed_amount_sizing(
                entry_price, capital, fixed_amount or Decimal("10000")
            )
        
        elif method == SizingMethod.FIXED_QUANTITY:
            return self._fixed_quantity_sizing(
                entry_price, fixed_quantity or self.lot_size
            )
        
        elif method == SizingMethod.PERCENT_RISK:
            if not stop_loss:
                raise ValueError("Stop loss required for percent risk sizing")
            return self._percent_risk_sizing(
                entry_price, stop_loss, capital, risk_percent
            )
        
        elif method == SizingMethod.PERCENT_EQUITY:
            return self._percent_equity_sizing(
                entry_price, capital, risk_percent
            )
        
        elif method == SizingMethod.KELLY:
            if not all([win_rate, avg_win_loss_ratio]):
                raise ValueError("Win rate and win/loss ratio required for Kelly")
            return self._kelly_sizing(
                entry_price, capital, win_rate, avg_win_loss_ratio, stop_loss
            )
        
        elif method == SizingMethod.VOLATILITY:
            if not atr:
                raise ValueError("ATR required for volatility sizing")
            return self._volatility_sizing(
                entry_price, capital, atr, atr_multiplier, risk_percent
            )
        
        else:
            raise ValueError(f"Unknown sizing method: {method}")
    
    def _fixed_amount_sizing(
        self,
        entry_price: Decimal,
        capital: Decimal,
        amount: Decimal
    ) -> PositionSizeResult:
        """Fixed capital amount per trade."""
        # Cap at max position %
        max_amount = capital * (self.max_position_pct / 100)
        actual_amount = min(amount, max_amount)
        
        # Calculate quantity
        raw_qty = actual_amount / entry_price
        quantity = self._round_to_lot(raw_qty)
        
        position_value = entry_price * quantity
        
        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            risk_amount=Decimal("0"),  # No defined risk for fixed amount
            risk_percent=Decimal("0"),
            method=SizingMethod.FIXED_AMOUNT,
            calculation_details={
                "target_amount": float(amount),
                "max_allowed": float(max_amount),
                "actual_amount": float(actual_amount),
            }
        )
    
    def _fixed_quantity_sizing(
        self,
        entry_price: Decimal,
        quantity: int
    ) -> PositionSizeResult:
        """Fixed quantity per trade."""
        quantity = max(quantity, self.min_quantity)
        quantity = self._round_to_lot(quantity)
        
        position_value = entry_price * quantity
        
        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            risk_amount=Decimal("0"),
            risk_percent=Decimal("0"),
            method=SizingMethod.FIXED_QUANTITY,
            calculation_details={
                "requested_quantity": quantity,
            }
        )
    
    def _percent_risk_sizing(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        capital: Decimal,
        risk_percent: Decimal
    ) -> PositionSizeResult:
        """
        Position size based on risking X% of capital.
        
        Formula: Quantity = (Capital × Risk%) / (Entry - StopLoss)
        """
        # Calculate risk per share
        risk_per_share = abs(entry_price - stop_loss)
        
        if risk_per_share == 0:
            raise ValueError("Entry and stop loss cannot be the same")
        
        # Calculate max risk amount
        risk_amount = capital * (risk_percent / 100)
        
        # Calculate quantity
        raw_qty = risk_amount / risk_per_share
        quantity = self._round_to_lot(raw_qty)
        
        # Ensure quantity is at least minimum
        quantity = max(quantity, self.min_quantity)
        
        # Cap at max position %
        max_position_value = capital * (self.max_position_pct / 100)
        position_value = entry_price * quantity
        
        if position_value > max_position_value:
            quantity = self._round_to_lot(max_position_value / entry_price)
            position_value = entry_price * quantity
        
        # Recalculate actual risk
        actual_risk = risk_per_share * quantity
        actual_risk_pct = (actual_risk / capital) * 100
        
        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            risk_amount=actual_risk,
            risk_percent=actual_risk_pct,
            method=SizingMethod.PERCENT_RISK,
            calculation_details={
                "risk_per_share": float(risk_per_share),
                "target_risk_pct": float(risk_percent),
                "actual_risk_pct": float(actual_risk_pct),
                "target_risk_amount": float(risk_amount),
                "actual_risk_amount": float(actual_risk),
            }
        )
    
    def _percent_equity_sizing(
        self,
        entry_price: Decimal,
        capital: Decimal,
        equity_percent: Decimal
    ) -> PositionSizeResult:
        """Use X% of equity for position."""
        # Cap at max position %
        actual_pct = min(equity_percent, self.max_position_pct)
        
        position_amount = capital * (actual_pct / 100)
        raw_qty = position_amount / entry_price
        quantity = self._round_to_lot(raw_qty)
        
        quantity = max(quantity, self.min_quantity)
        position_value = entry_price * quantity
        
        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            risk_amount=Decimal("0"),
            risk_percent=Decimal("0"),
            method=SizingMethod.PERCENT_EQUITY,
            calculation_details={
                "requested_pct": float(equity_percent),
                "actual_pct": float(actual_pct),
                "position_amount": float(position_amount),
            }
        )
    
    def _kelly_sizing(
        self,
        entry_price: Decimal,
        capital: Decimal,
        win_rate: Decimal,
        avg_win_loss_ratio: Decimal,
        stop_loss: Optional[Decimal] = None
    ) -> PositionSizeResult:
        """
        Kelly Criterion position sizing.
        
        Kelly % = W - [(1-W) / R]
        Where:
            W = Win probability
            R = Win/Loss ratio
        
        We use half-Kelly for safety.
        """
        # Kelly formula
        w = win_rate / 100  # Convert to decimal
        r = avg_win_loss_ratio
        
        kelly_pct = w - ((1 - w) / r)
        
        # Use half-Kelly for safety
        half_kelly_pct = kelly_pct / 2
        
        # Cap at max position % and ensure positive
        actual_pct = max(Decimal("0"), min(half_kelly_pct * 100, self.max_position_pct))
        
        position_amount = capital * (actual_pct / 100)
        raw_qty = position_amount / entry_price
        quantity = self._round_to_lot(raw_qty)
        
        quantity = max(quantity, self.min_quantity)
        position_value = entry_price * quantity
        
        # Calculate risk if stop loss provided
        risk_amount = Decimal("0")
        if stop_loss:
            risk_amount = abs(entry_price - stop_loss) * quantity
        
        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            risk_amount=risk_amount,
            risk_percent=(risk_amount / capital) * 100 if capital > 0 else Decimal("0"),
            method=SizingMethod.KELLY,
            calculation_details={
                "win_rate": float(win_rate),
                "win_loss_ratio": float(r),
                "full_kelly_pct": float(kelly_pct * 100),
                "half_kelly_pct": float(half_kelly_pct * 100),
                "actual_pct": float(actual_pct),
            }
        )
    
    def _volatility_sizing(
        self,
        entry_price: Decimal,
        capital: Decimal,
        atr: Decimal,
        atr_multiplier: Decimal,
        risk_percent: Decimal
    ) -> PositionSizeResult:
        """
        Volatility-based sizing using ATR.
        
        Stop is placed at ATR × multiplier from entry.
        Position size is calculated to risk X% at that stop.
        """
        # Calculate implied stop distance
        stop_distance = atr * atr_multiplier
        
        if stop_distance == 0:
            raise ValueError("ATR cannot be zero")
        
        # Calculate risk amount
        risk_amount = capital * (risk_percent / 100)
        
        # Calculate quantity
        raw_qty = risk_amount / stop_distance
        quantity = self._round_to_lot(raw_qty)
        
        quantity = max(quantity, self.min_quantity)
        
        # Cap at max position %
        max_position_value = capital * (self.max_position_pct / 100)
        position_value = entry_price * quantity
        
        if position_value > max_position_value:
            quantity = self._round_to_lot(max_position_value / entry_price)
            position_value = entry_price * quantity
        
        # Recalculate actual risk
        actual_risk = stop_distance * quantity
        actual_risk_pct = (actual_risk / capital) * 100
        
        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            risk_amount=actual_risk,
            risk_percent=actual_risk_pct,
            method=SizingMethod.VOLATILITY,
            calculation_details={
                "atr": float(atr),
                "atr_multiplier": float(atr_multiplier),
                "stop_distance": float(stop_distance),
                "target_risk_pct": float(risk_percent),
                "actual_risk_pct": float(actual_risk_pct),
            }
        )
    
    def _round_to_lot(self, quantity: Decimal) -> int:
        """Round quantity to lot size."""
        if self.lot_size == 1:
            return max(int(quantity.to_integral_value(ROUND_DOWN)), self.min_quantity)
        
        lots = int(quantity / self.lot_size)
        return max(lots * self.lot_size, self.lot_size)
    
    def update_capital(self, new_capital: Decimal) -> None:
        """Update available capital."""
        self.capital = new_capital
    
    def set_lot_size(self, lot_size: int) -> None:
        """Set lot size for the current instrument."""
        self.lot_size = lot_size


class PositionSizingStrategy(ABC):
    """Base class for custom sizing strategies."""
    
    @abstractmethod
    def calculate(
        self,
        capital: Decimal,
        entry_price: Decimal,
        **kwargs
    ) -> int:
        """Calculate position size."""
        pass


class RiskParitySizing(PositionSizingStrategy):
    """
    Risk parity sizing: Equal risk across all positions.
    
    Each position contributes equally to total portfolio risk.
    """
    
    def __init__(
        self,
        total_risk_budget: Decimal = Decimal("10"),  # 10% total portfolio risk
        max_positions: int = 5
    ):
        self.total_risk_budget = total_risk_budget
        self.max_positions = max_positions
    
    def calculate(
        self,
        capital: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        current_positions: int = 0,
        **kwargs
    ) -> int:
        """Calculate position size for equal risk contribution."""
        # Risk budget per position
        available_slots = self.max_positions - current_positions
        if available_slots <= 0:
            return 0
        
        risk_per_position = self.total_risk_budget / self.max_positions
        risk_amount = capital * (risk_per_position / 100)
        
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0:
            return 0
        
        return int(risk_amount / risk_per_share)


class ScaledSizing(PositionSizingStrategy):
    """
    Scaled sizing: Adjust position size based on signal strength or confidence.
    """
    
    def __init__(
        self,
        base_risk_percent: Decimal = Decimal("2"),
        min_scale: Decimal = Decimal("0.5"),
        max_scale: Decimal = Decimal("1.5")
    ):
        self.base_risk_percent = base_risk_percent
        self.min_scale = min_scale
        self.max_scale = max_scale
    
    def calculate(
        self,
        capital: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        signal_strength: Decimal = Decimal("1.0"),  # 0-1 scale
        **kwargs
    ) -> int:
        """Calculate scaled position size based on signal strength."""
        # Scale factor based on signal strength
        scale_range = self.max_scale - self.min_scale
        scale = self.min_scale + (signal_strength * scale_range)
        
        # Calculate risk amount
        adjusted_risk_pct = self.base_risk_percent * scale
        risk_amount = capital * (adjusted_risk_pct / 100)
        
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0:
            return 0
        
        return int(risk_amount / risk_per_share)


# Factory function
def create_position_sizer(
    capital: Decimal = Decimal("100000"),
    lot_size: int = 1,
    max_position_pct: Decimal = Decimal("20")
) -> PositionSizer:
    """Create a position sizer with default configuration."""
    return PositionSizer(
        capital=capital,
        lot_size=lot_size,
        max_position_pct=max_position_pct
    )
