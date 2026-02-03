"""
Risk Management Service

Pre-trade and real-time risk management:
- Capital allocation and position sizing
- Daily loss limits and circuit breakers
- Maximum position limits per symbol/strategy
- Exposure monitoring
- Margin requirement calculation for options

Risk Rules:
- Max 2% capital risk per trade
- Max 5% daily loss limit (circuit breaker)
- Max 10 concurrent positions
- No new trades in last 15 mins before market close
- Max 50% capital exposure at any time
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, time
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

from app.core.events import EventBus


class RiskCheckResult(str, Enum):
    """Result of risk check."""
    APPROVED = "approved"
    REJECTED = "rejected"
    WARNING = "warning"


class RiskViolationType(str, Enum):
    """Types of risk violations."""
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_POSITIONS = "max_positions"
    POSITION_SIZE_EXCEEDED = "position_size_exceeded"
    CAPITAL_EXPOSURE = "capital_exposure"
    TRADING_HOURS = "trading_hours"
    SYMBOL_EXPOSURE = "symbol_exposure"
    STRATEGY_EXPOSURE = "strategy_exposure"
    INSUFFICIENT_MARGIN = "insufficient_margin"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class RiskConfig:
    """Risk management configuration."""
    # Capital limits
    total_capital: Decimal = Decimal("1000000")  # 10L default
    max_risk_per_trade_pct: Decimal = Decimal("2.0")  # 2% max risk per trade
    max_capital_exposure_pct: Decimal = Decimal("50.0")  # 50% max exposure
    
    # Loss limits
    daily_loss_limit_pct: Decimal = Decimal("5.0")  # 5% daily loss limit
    trailing_stop_loss_pct: Decimal = Decimal("3.0")  # 3% trailing SL on profits
    
    # Position limits
    max_positions: int = 10  # Max concurrent positions
    max_positions_per_symbol: int = 2  # Max positions in same underlying
    max_positions_per_strategy: int = 5  # Max positions per strategy
    
    # Options specific
    max_options_lots: int = 50  # Max lot size for options
    min_option_premium: Decimal = Decimal("5.0")  # Min premium to buy
    max_option_premium_pct: Decimal = Decimal("3.0")  # Max % of underlying
    
    # Trading hours (IST)
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    no_new_entry_after: time = time(15, 15)  # No new trades in last 15 mins
    
    # Circuit breakers
    circuit_breaker_loss_pct: Decimal = Decimal("5.0")  # Stop all trading
    consecutive_loss_limit: int = 3  # Max consecutive losses


@dataclass
class PositionRisk:
    """Risk metrics for a single position."""
    position_id: str
    symbol: str
    strategy_id: str
    entry_price: Decimal
    current_price: Decimal
    quantity: int
    direction: str  # "long" or "short"
    stop_loss: Decimal
    unrealized_pnl: Decimal
    risk_amount: Decimal  # Capital at risk
    exposure: Decimal  # Current exposure value
    opened_at: datetime


@dataclass
class DailyRiskMetrics:
    """Daily risk tracking metrics."""
    trade_date: date
    starting_capital: Decimal
    current_capital: Decimal
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    peak_capital: Decimal = Decimal("0")
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    consecutive_losses: int = 0
    circuit_breaker_triggered: bool = False
    positions_opened: int = 0
    positions_closed: int = 0


@dataclass
class RiskCheckResponse:
    """Response from risk check."""
    result: RiskCheckResult
    violations: List[RiskViolationType] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    adjusted_quantity: Optional[int] = None
    max_allowed_quantity: Optional[int] = None
    risk_metrics: Dict[str, Any] = field(default_factory=dict)


class RiskManager:
    """
    Core risk management service.
    
    Responsibilities:
    - Pre-trade risk validation
    - Position sizing based on risk limits
    - Real-time exposure monitoring
    - Daily P&L tracking and circuit breakers
    - Margin requirement estimation
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        config: Optional[RiskConfig] = None
    ):
        self.event_bus = event_bus
        self.config = config or RiskConfig()
        self.logger = logging.getLogger(__name__)
        self._running = False
        
        # Active positions tracking
        self._positions: Dict[str, PositionRisk] = {}
        
        # Daily metrics
        self._daily_metrics = DailyRiskMetrics(
            trade_date=date.today(),
            starting_capital=self.config.total_capital,
            current_capital=self.config.total_capital,
            peak_capital=self.config.total_capital
        )
        
        # Circuit breaker state
        self._circuit_breaker_active = False
        self._circuit_breaker_reason: Optional[str] = None
        
        # IST timezone
        self._tz = ZoneInfo("Asia/Kolkata")
    
    async def start(self) -> None:
        """Start risk manager service."""
        if self._running:
            return
        
        self._running = True
        self.logger.info("Starting risk manager...")
        
        # Subscribe to relevant events
        await self.event_bus.subscribe(
            "position_update",
            self._on_position_update,
            consumer_group="risk_manager"
        )
        
        await self.event_bus.subscribe(
            "trade_executed",
            self._on_trade_executed,
            consumer_group="risk_manager"
        )
        
        # Reset daily metrics if new day
        self._check_new_day()
        
        self.logger.info("Risk manager started")
    
    async def stop(self) -> None:
        """Stop risk manager service."""
        self._running = False
        await self.event_bus.unsubscribe("position_update", "risk_manager")
        await self.event_bus.unsubscribe("trade_executed", "risk_manager")
        self.logger.info("Risk manager stopped")
    
    def _check_new_day(self) -> None:
        """Reset metrics if it's a new trading day."""
        today = date.today()
        if self._daily_metrics.trade_date != today:
            self._daily_metrics = DailyRiskMetrics(
                trade_date=today,
                starting_capital=self.config.total_capital,
                current_capital=self.config.total_capital,
                peak_capital=self.config.total_capital
            )
            self._circuit_breaker_active = False
            self._circuit_breaker_reason = None
            self.logger.info(f"New trading day: {today}, metrics reset")
    
    async def validate_signal(
        self,
        signal: Dict[str, Any]
    ) -> RiskCheckResponse:
        """
        Validate a trading signal against risk rules.
        
        Args:
            signal: Signal data from strategy engine
            
        Returns:
            RiskCheckResponse with approval/rejection and details
        """
        violations = []
        messages = []
        
        symbol = signal.get("symbol", "")
        strategy_id = signal.get("strategy_id", "")
        entry_price = Decimal(str(signal.get("entry_price", 0)))
        stop_loss = Decimal(str(signal.get("stop_loss", 0)))
        quantity_pct = Decimal(str(signal.get("quantity_pct", 0)))
        signal_type = signal.get("signal_type", "")
        
        # Check 1: Circuit breaker
        if self._circuit_breaker_active:
            violations.append(RiskViolationType.CIRCUIT_BREAKER)
            messages.append(f"Circuit breaker active: {self._circuit_breaker_reason}")
            return RiskCheckResponse(
                result=RiskCheckResult.REJECTED,
                violations=violations,
                messages=messages
            )
        
        # Check 2: Trading hours
        if not self._is_trading_hours():
            violations.append(RiskViolationType.TRADING_HOURS)
            messages.append("Outside trading hours")
        
        # Check 3: No new trades near market close
        if not self._can_enter_new_position():
            violations.append(RiskViolationType.TRADING_HOURS)
            messages.append(f"No new entries after {self.config.no_new_entry_after}")
        
        # Check 4: Daily loss limit
        if self._check_daily_loss_limit():
            violations.append(RiskViolationType.DAILY_LOSS_LIMIT)
            messages.append(
                f"Daily loss limit ({self.config.daily_loss_limit_pct}%) reached"
            )
        
        # Check 5: Maximum positions
        if len(self._positions) >= self.config.max_positions:
            violations.append(RiskViolationType.MAX_POSITIONS)
            messages.append(
                f"Maximum positions ({self.config.max_positions}) reached"
            )
        
        # Check 6: Symbol exposure
        symbol_positions = self._count_positions_for_symbol(symbol)
        if symbol_positions >= self.config.max_positions_per_symbol:
            violations.append(RiskViolationType.SYMBOL_EXPOSURE)
            messages.append(
                f"Maximum positions for {symbol} "
                f"({self.config.max_positions_per_symbol}) reached"
            )
        
        # Check 7: Strategy exposure
        strategy_positions = self._count_positions_for_strategy(strategy_id)
        if strategy_positions >= self.config.max_positions_per_strategy:
            violations.append(RiskViolationType.STRATEGY_EXPOSURE)
            messages.append(
                f"Maximum positions for strategy {strategy_id} "
                f"({self.config.max_positions_per_strategy}) reached"
            )
        
        # Check 8: Capital exposure
        current_exposure = self._calculate_total_exposure()
        max_exposure = (
            self.config.total_capital * 
            self.config.max_capital_exposure_pct / Decimal("100")
        )
        if current_exposure >= max_exposure:
            violations.append(RiskViolationType.CAPITAL_EXPOSURE)
            messages.append(
                f"Capital exposure limit ({self.config.max_capital_exposure_pct}%) reached"
            )
        
        # Check 9: Consecutive losses
        if self._daily_metrics.consecutive_losses >= self.config.consecutive_loss_limit:
            violations.append(RiskViolationType.CIRCUIT_BREAKER)
            messages.append(
                f"Consecutive loss limit ({self.config.consecutive_loss_limit}) reached"
            )
        
        # If any hard violations, reject
        hard_violations = {
            RiskViolationType.CIRCUIT_BREAKER,
            RiskViolationType.DAILY_LOSS_LIMIT,
            RiskViolationType.MAX_POSITIONS,
        }
        if violations and any(v in hard_violations for v in violations):
            return RiskCheckResponse(
                result=RiskCheckResult.REJECTED,
                violations=violations,
                messages=messages,
                risk_metrics=self._get_current_metrics()
            )
        
        # Calculate position size
        position_size = self._calculate_position_size(
            entry_price=entry_price,
            stop_loss=stop_loss,
            quantity_pct=quantity_pct
        )
        
        # Check if position size is valid
        if position_size <= 0:
            violations.append(RiskViolationType.POSITION_SIZE_EXCEEDED)
            messages.append("Calculated position size is zero or negative")
            return RiskCheckResponse(
                result=RiskCheckResult.REJECTED,
                violations=violations,
                messages=messages
            )
        
        # Return approved with calculated quantity
        result = (
            RiskCheckResult.WARNING if violations 
            else RiskCheckResult.APPROVED
        )
        
        return RiskCheckResponse(
            result=result,
            violations=violations,
            messages=messages,
            adjusted_quantity=position_size,
            max_allowed_quantity=position_size,
            risk_metrics=self._get_current_metrics()
        )
    
    def _calculate_position_size(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        quantity_pct: Decimal
    ) -> int:
        """
        Calculate position size based on risk parameters.
        
        Uses fixed fractional position sizing:
        Position Size = (Capital * Risk%) / (Entry - StopLoss)
        """
        if entry_price <= 0 or stop_loss <= 0:
            return 0
        
        # Risk per share
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return 0
        
        # Maximum capital to risk on this trade
        max_risk_capital = (
            self.config.total_capital * 
            self.config.max_risk_per_trade_pct / Decimal("100")
        )
        
        # Also consider the quantity percentage from signal
        signal_capital = (
            self.config.total_capital * 
            quantity_pct / Decimal("100")
        )
        
        # Use the smaller of the two
        capital_to_use = min(max_risk_capital, signal_capital)
        
        # Calculate quantity
        quantity = int(capital_to_use / risk_per_share)
        
        return max(1, quantity)  # At least 1 share
    
    def calculate_options_lot_size(
        self,
        underlying_symbol: str,
        premium: Decimal,
        lot_size: int = 50  # NIFTY default
    ) -> int:
        """
        Calculate number of lots for options trade.
        
        Args:
            underlying_symbol: The underlying index/stock
            premium: Option premium price
            lot_size: Exchange lot size
            
        Returns:
            Number of lots to trade
        """
        # Maximum capital for options = 2% risk
        max_risk_capital = (
            self.config.total_capital * 
            self.config.max_risk_per_trade_pct / Decimal("100")
        )
        
        # Premium per lot
        premium_per_lot = premium * Decimal(str(lot_size))
        
        if premium_per_lot <= 0:
            return 0
        
        # Calculate lots
        lots = int(max_risk_capital / premium_per_lot)
        
        # Apply maximum lot limit
        lots = min(lots, self.config.max_options_lots)
        
        return max(1, lots)
    
    def _is_trading_hours(self) -> bool:
        """Check if within trading hours."""
        now = datetime.now(self._tz).time()
        return self.config.market_open <= now <= self.config.market_close
    
    def _can_enter_new_position(self) -> bool:
        """Check if new entries are allowed."""
        now = datetime.now(self._tz).time()
        return self.config.market_open <= now <= self.config.no_new_entry_after
    
    def _check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit is breached."""
        loss_pct = (
            (self._daily_metrics.starting_capital - self._daily_metrics.current_capital)
            / self._daily_metrics.starting_capital * Decimal("100")
        )
        return loss_pct >= self.config.daily_loss_limit_pct
    
    def _calculate_total_exposure(self) -> Decimal:
        """Calculate total current exposure."""
        return sum(p.exposure for p in self._positions.values())
    
    def _count_positions_for_symbol(self, symbol: str) -> int:
        """Count positions for a symbol."""
        # Extract underlying from symbol (e.g., "NSE:NIFTY24JUN22000CE" -> "NIFTY")
        underlying = symbol.split(":")[1][:5] if ":" in symbol else symbol[:5]
        return sum(
            1 for p in self._positions.values()
            if p.symbol.startswith(underlying) or underlying in p.symbol
        )
    
    def _count_positions_for_strategy(self, strategy_id: str) -> int:
        """Count positions for a strategy."""
        return sum(
            1 for p in self._positions.values()
            if p.strategy_id == strategy_id
        )
    
    def _get_current_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics snapshot."""
        return {
            "total_capital": float(self.config.total_capital),
            "current_capital": float(self._daily_metrics.current_capital),
            "realized_pnl": float(self._daily_metrics.realized_pnl),
            "unrealized_pnl": float(self._daily_metrics.unrealized_pnl),
            "total_pnl": float(self._daily_metrics.total_pnl),
            "max_drawdown": float(self._daily_metrics.max_drawdown),
            "open_positions": len(self._positions),
            "total_exposure": float(self._calculate_total_exposure()),
            "daily_loss_pct": float(
                (self._daily_metrics.starting_capital - self._daily_metrics.current_capital)
                / self._daily_metrics.starting_capital * Decimal("100")
            ),
            "circuit_breaker_active": self._circuit_breaker_active,
            "consecutive_losses": self._daily_metrics.consecutive_losses,
        }
    
    async def _on_position_update(self, event: Dict[str, Any]) -> None:
        """Handle position update events."""
        try:
            position_id = event.get("position_id")
            action = event.get("action")  # "open", "update", "close"
            
            if action == "open":
                self._positions[position_id] = PositionRisk(
                    position_id=position_id,
                    symbol=event.get("symbol", ""),
                    strategy_id=event.get("strategy_id", ""),
                    entry_price=Decimal(str(event.get("entry_price", 0))),
                    current_price=Decimal(str(event.get("current_price", 0))),
                    quantity=event.get("quantity", 0),
                    direction=event.get("direction", "long"),
                    stop_loss=Decimal(str(event.get("stop_loss", 0))),
                    unrealized_pnl=Decimal("0"),
                    risk_amount=Decimal(str(event.get("risk_amount", 0))),
                    exposure=Decimal(str(event.get("exposure", 0))),
                    opened_at=datetime.fromisoformat(event.get("opened_at", datetime.now().isoformat()))
                )
                self._daily_metrics.positions_opened += 1
                
            elif action == "update" and position_id in self._positions:
                pos = self._positions[position_id]
                pos.current_price = Decimal(str(event.get("current_price", pos.current_price)))
                pos.unrealized_pnl = Decimal(str(event.get("unrealized_pnl", pos.unrealized_pnl)))
                pos.exposure = Decimal(str(event.get("exposure", pos.exposure)))
                
            elif action == "close" and position_id in self._positions:
                pos = self._positions.pop(position_id)
                realized_pnl = Decimal(str(event.get("realized_pnl", 0)))
                self._daily_metrics.realized_pnl += realized_pnl
                self._daily_metrics.positions_closed += 1
                self._daily_metrics.total_trades += 1
                
                if realized_pnl > 0:
                    self._daily_metrics.winning_trades += 1
                    self._daily_metrics.consecutive_losses = 0
                else:
                    self._daily_metrics.losing_trades += 1
                    self._daily_metrics.consecutive_losses += 1
                
                # Check circuit breaker after loss
                await self._check_circuit_breaker()
            
            # Update unrealized P&L
            self._update_unrealized_pnl()
            
        except Exception as e:
            self.logger.error(f"Error handling position update: {e}")
    
    async def _on_trade_executed(self, event: Dict[str, Any]) -> None:
        """Handle trade execution events for tracking."""
        try:
            trade_type = event.get("trade_type")  # "entry" or "exit"
            pnl = Decimal(str(event.get("pnl", 0)))
            
            if trade_type == "exit":
                self._daily_metrics.realized_pnl += pnl
                self._daily_metrics.current_capital += pnl
                
                # Update peak capital
                if self._daily_metrics.current_capital > self._daily_metrics.peak_capital:
                    self._daily_metrics.peak_capital = self._daily_metrics.current_capital
                
                # Update max drawdown
                drawdown = (
                    self._daily_metrics.peak_capital - self._daily_metrics.current_capital
                )
                if drawdown > self._daily_metrics.max_drawdown:
                    self._daily_metrics.max_drawdown = drawdown
                
                await self._check_circuit_breaker()
                
        except Exception as e:
            self.logger.error(f"Error handling trade executed: {e}")
    
    def _update_unrealized_pnl(self) -> None:
        """Update total unrealized P&L from all positions."""
        self._daily_metrics.unrealized_pnl = sum(
            p.unrealized_pnl for p in self._positions.values()
        )
        self._daily_metrics.total_pnl = (
            self._daily_metrics.realized_pnl + 
            self._daily_metrics.unrealized_pnl
        )
    
    async def _check_circuit_breaker(self) -> None:
        """Check and trigger circuit breaker if needed."""
        if self._circuit_breaker_active:
            return
        
        # Check daily loss limit
        if self._check_daily_loss_limit():
            self._circuit_breaker_active = True
            self._circuit_breaker_reason = (
                f"Daily loss limit of {self.config.daily_loss_limit_pct}% breached"
            )
            await self._publish_circuit_breaker_event()
            return
        
        # Check consecutive losses
        if self._daily_metrics.consecutive_losses >= self.config.consecutive_loss_limit:
            self._circuit_breaker_active = True
            self._circuit_breaker_reason = (
                f"Consecutive loss limit of {self.config.consecutive_loss_limit} reached"
            )
            await self._publish_circuit_breaker_event()
            return
    
    async def _publish_circuit_breaker_event(self) -> None:
        """Publish circuit breaker event to bus."""
        await self.event_bus.publish("circuit_breaker", {
            "active": self._circuit_breaker_active,
            "reason": self._circuit_breaker_reason,
            "timestamp": datetime.now(self._tz).isoformat(),
            "metrics": self._get_current_metrics()
        })
        self.logger.critical(
            f"CIRCUIT BREAKER TRIGGERED: {self._circuit_breaker_reason}"
        )
    
    def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker (admin action)."""
        self._circuit_breaker_active = False
        self._circuit_breaker_reason = None
        self.logger.warning("Circuit breaker manually reset")
    
    def update_capital(self, new_capital: Decimal) -> None:
        """Update total capital (e.g., after deposit/withdrawal)."""
        self.config.total_capital = new_capital
        self.logger.info(f"Total capital updated to {new_capital}")
    
    def get_daily_report(self) -> Dict[str, Any]:
        """Get comprehensive daily risk report."""
        return {
            "date": self._daily_metrics.trade_date.isoformat(),
            "capital": {
                "starting": float(self._daily_metrics.starting_capital),
                "current": float(self._daily_metrics.current_capital),
                "peak": float(self._daily_metrics.peak_capital),
            },
            "pnl": {
                "realized": float(self._daily_metrics.realized_pnl),
                "unrealized": float(self._daily_metrics.unrealized_pnl),
                "total": float(self._daily_metrics.total_pnl),
            },
            "drawdown": {
                "max": float(self._daily_metrics.max_drawdown),
                "current": float(
                    self._daily_metrics.peak_capital - self._daily_metrics.current_capital
                ),
            },
            "trades": {
                "total": self._daily_metrics.total_trades,
                "winning": self._daily_metrics.winning_trades,
                "losing": self._daily_metrics.losing_trades,
                "win_rate": (
                    self._daily_metrics.winning_trades / self._daily_metrics.total_trades
                    if self._daily_metrics.total_trades > 0 else 0
                ),
            },
            "positions": {
                "opened": self._daily_metrics.positions_opened,
                "closed": self._daily_metrics.positions_closed,
                "current": len(self._positions),
            },
            "risk": {
                "exposure": float(self._calculate_total_exposure()),
                "exposure_pct": float(
                    self._calculate_total_exposure() / self.config.total_capital * Decimal("100")
                ),
                "consecutive_losses": self._daily_metrics.consecutive_losses,
                "circuit_breaker_active": self._circuit_breaker_active,
                "circuit_breaker_reason": self._circuit_breaker_reason,
            }
        }


# Factory function
def create_risk_manager(
    event_bus: EventBus,
    total_capital: Decimal = Decimal("1000000")
) -> RiskManager:
    """Create and configure risk manager instance."""
    config = RiskConfig(total_capital=total_capital)
    return RiskManager(event_bus, config)
