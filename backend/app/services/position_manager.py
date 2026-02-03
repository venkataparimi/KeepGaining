"""
Position Manager Service

Core position lifecycle management:
- Track all open positions with real-time P&L
- Monitor stop loss and target prices
- Implement trailing stop loss logic
- Auto-exit positions at market close
- Coordinate with Risk Manager and OMS

Position States:
- PENDING: Order placed, waiting for fill
- OPEN: Position is active
- PARTIAL_CLOSE: Part of position closed
- CLOSING: Exit order placed
- CLOSED: Position fully closed
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from zoneinfo import ZoneInfo

from app.core.events import EventBus


class PositionState(str, Enum):
    """Position lifecycle states."""
    PENDING = "pending"
    OPEN = "open"
    PARTIAL_CLOSE = "partial_close"
    CLOSING = "closing"
    CLOSED = "closed"


class PositionSide(str, Enum):
    """Position direction."""
    LONG = "long"
    SHORT = "short"


class ExitReason(str, Enum):
    """Reason for position exit."""
    STOP_LOSS = "stop_loss"
    TARGET = "target"
    TRAILING_STOP = "trailing_stop"
    MARKET_CLOSE = "market_close"
    MANUAL = "manual"
    SIGNAL_EXIT = "signal_exit"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class TrailingStopConfig:
    """Configuration for trailing stop loss."""
    enabled: bool = True
    activation_pct: Decimal = Decimal("1.0")  # Activate after 1% profit
    trail_pct: Decimal = Decimal("0.5")  # Trail by 0.5%
    step_size: Decimal = Decimal("0.25")  # Move SL in 0.25% steps
    min_profit_lock_pct: Decimal = Decimal("0.5")  # Lock at least 0.5% profit


@dataclass
class Position:
    """Represents a trading position."""
    position_id: str
    symbol: str
    exchange: str
    
    # Strategy info
    strategy_id: str
    strategy_name: str
    signal_id: str
    
    # Position details
    side: PositionSide
    quantity: int
    entry_price: Decimal
    current_price: Decimal
    
    # Risk management
    initial_stop_loss: Decimal
    current_stop_loss: Decimal
    target_price: Decimal
    
    # Trailing stop
    trailing_stop_config: TrailingStopConfig
    trailing_stop_active: bool = False
    highest_price: Decimal = Decimal("0")  # For long
    lowest_price: Decimal = Decimal("999999")  # For short
    
    # State
    state: PositionState = PositionState.PENDING
    
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Kolkata")))
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    
    # P&L
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    
    # Exit info
    exit_price: Optional[Decimal] = None
    exit_reason: Optional[ExitReason] = None
    
    # Order tracking
    entry_order_id: Optional[str] = None
    exit_order_id: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def calculate_unrealized_pnl(self) -> Decimal:
        """Calculate unrealized P&L based on current price."""
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (self.current_price - self.entry_price) * Decimal(str(self.quantity))
        else:
            self.unrealized_pnl = (self.entry_price - self.current_price) * Decimal(str(self.quantity))
        return self.unrealized_pnl
    
    def calculate_realized_pnl(self, exit_price: Decimal) -> Decimal:
        """Calculate realized P&L at exit."""
        if self.side == PositionSide.LONG:
            self.realized_pnl = (exit_price - self.entry_price) * Decimal(str(self.quantity))
        else:
            self.realized_pnl = (self.entry_price - exit_price) * Decimal(str(self.quantity))
        return self.realized_pnl
    
    def get_risk_amount(self) -> Decimal:
        """Calculate capital at risk."""
        risk_per_share = abs(self.entry_price - self.current_stop_loss)
        return risk_per_share * Decimal(str(self.quantity))
    
    def get_exposure(self) -> Decimal:
        """Calculate current exposure."""
        return self.current_price * Decimal(str(self.quantity))
    
    def get_pnl_percentage(self) -> Decimal:
        """Calculate P&L as percentage of entry."""
        if self.entry_price <= 0:
            return Decimal("0")
        return (self.unrealized_pnl / (self.entry_price * Decimal(str(self.quantity)))) * Decimal("100")


class PositionManager:
    """
    Manages position lifecycle and real-time monitoring.
    
    Responsibilities:
    - Create positions from signals
    - Track real-time P&L
    - Monitor stop loss and target levels
    - Implement trailing stop logic
    - Handle EOD auto-exit
    - Coordinate with OMS for order execution
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        default_trailing_config: Optional[TrailingStopConfig] = None
    ):
        self.event_bus = event_bus
        self.default_trailing_config = default_trailing_config or TrailingStopConfig()
        self.logger = logging.getLogger(__name__)
        self._running = False
        
        # Position storage
        self._positions: Dict[str, Position] = {}
        self._positions_by_symbol: Dict[str, List[str]] = {}  # symbol -> [position_ids]
        
        # Monitoring
        self._monitor_task: Optional[asyncio.Task] = None
        self._tick_lock = asyncio.Lock()
        
        # IST timezone
        self._tz = ZoneInfo("Asia/Kolkata")
        
        # Market close time
        self._market_close = time(15, 30)
        self._eod_exit_time = time(15, 25)  # Exit 5 mins before close
    
    async def start(self) -> None:
        """Start position manager service."""
        if self._running:
            return
        
        self._running = True
        self.logger.info("Starting position manager...")
        
        # Subscribe to events
        await self.event_bus.subscribe(
            "tick",
            self._on_tick,
            consumer_group="position_manager"
        )
        
        await self.event_bus.subscribe(
            "signal",
            self._on_signal,
            consumer_group="position_manager"
        )
        
        await self.event_bus.subscribe(
            "order_filled",
            self._on_order_filled,
            consumer_group="position_manager"
        )
        
        await self.event_bus.subscribe(
            "circuit_breaker",
            self._on_circuit_breaker,
            consumer_group="position_manager"
        )
        
        # Start EOD monitor
        self._monitor_task = asyncio.create_task(self._eod_monitor())
        
        self.logger.info("Position manager started")
    
    async def stop(self) -> None:
        """Stop position manager service."""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        await self.event_bus.unsubscribe("tick", "position_manager")
        await self.event_bus.unsubscribe("signal", "position_manager")
        await self.event_bus.unsubscribe("order_filled", "position_manager")
        await self.event_bus.unsubscribe("circuit_breaker", "position_manager")
        
        self.logger.info("Position manager stopped")
    
    async def create_position(
        self,
        signal: Dict[str, Any],
        quantity: int,
        trailing_config: Optional[TrailingStopConfig] = None
    ) -> Position:
        """
        Create a new position from a signal.
        
        Args:
            signal: Signal data from strategy engine
            quantity: Position quantity (from risk manager)
            trailing_config: Optional custom trailing stop config
            
        Returns:
            Created Position object
        """
        import uuid
        
        position_id = f"POS-{uuid.uuid4().hex[:8]}"
        symbol = signal.get("symbol", "")
        
        side = (
            PositionSide.LONG 
            if signal.get("signal_type") in ["long_entry", "LONG_ENTRY"]
            else PositionSide.SHORT
        )
        
        entry_price = Decimal(str(signal.get("entry_price", 0)))
        stop_loss = Decimal(str(signal.get("stop_loss", 0)))
        target = Decimal(str(signal.get("target_price", 0)))
        
        position = Position(
            position_id=position_id,
            symbol=symbol,
            exchange=signal.get("exchange", "NSE"),
            strategy_id=signal.get("strategy_id", ""),
            strategy_name=signal.get("strategy_name", ""),
            signal_id=signal.get("signal_id", ""),
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            initial_stop_loss=stop_loss,
            current_stop_loss=stop_loss,
            target_price=target,
            trailing_stop_config=trailing_config or self.default_trailing_config,
            highest_price=entry_price if side == PositionSide.LONG else Decimal("999999"),
            lowest_price=entry_price if side == PositionSide.SHORT else Decimal("999999"),
            metadata={
                "indicators": signal.get("indicators", {}),
                "reason": signal.get("reason", ""),
            }
        )
        
        self._positions[position_id] = position
        
        # Index by symbol
        if symbol not in self._positions_by_symbol:
            self._positions_by_symbol[symbol] = []
        self._positions_by_symbol[symbol].append(position_id)
        
        self.logger.info(
            f"Position created: {position_id} - {side.value} {quantity} {symbol} @ {entry_price}"
        )
        
        # Publish position update event
        await self._publish_position_update(position, "open")
        
        return position
    
    async def _on_tick(self, event: Dict[str, Any]) -> None:
        """Handle tick updates for position monitoring."""
        symbol = event.get("symbol")
        ltp = Decimal(str(event.get("ltp", 0)))
        
        if symbol not in self._positions_by_symbol:
            return
        
        async with self._tick_lock:
            for position_id in self._positions_by_symbol.get(symbol, []):
                position = self._positions.get(position_id)
                if not position or position.state != PositionState.OPEN:
                    continue
                
                # Update current price
                position.current_price = ltp
                position.calculate_unrealized_pnl()
                
                # Update high/low for trailing stop
                if position.side == PositionSide.LONG:
                    if ltp > position.highest_price:
                        position.highest_price = ltp
                else:
                    if ltp < position.lowest_price:
                        position.lowest_price = ltp
                
                # Check exit conditions
                await self._check_exit_conditions(position)
    
    async def _check_exit_conditions(self, position: Position) -> None:
        """Check if position should be exited."""
        
        # Check stop loss
        if self._is_stop_loss_hit(position):
            await self._request_exit(position, ExitReason.STOP_LOSS)
            return
        
        # Check target
        if self._is_target_hit(position):
            await self._request_exit(position, ExitReason.TARGET)
            return
        
        # Update trailing stop
        await self._update_trailing_stop(position)
    
    def _is_stop_loss_hit(self, position: Position) -> bool:
        """Check if stop loss is hit."""
        if position.side == PositionSide.LONG:
            return position.current_price <= position.current_stop_loss
        else:
            return position.current_price >= position.current_stop_loss
    
    def _is_target_hit(self, position: Position) -> bool:
        """Check if target is hit."""
        if position.side == PositionSide.LONG:
            return position.current_price >= position.target_price
        else:
            return position.current_price <= position.target_price
    
    async def _update_trailing_stop(self, position: Position) -> None:
        """Update trailing stop loss if conditions met."""
        config = position.trailing_stop_config
        
        if not config.enabled:
            return
        
        # Calculate profit percentage
        pnl_pct = position.get_pnl_percentage()
        
        # Activate trailing stop if profit threshold reached
        if pnl_pct >= config.activation_pct and not position.trailing_stop_active:
            position.trailing_stop_active = True
            self.logger.info(
                f"Trailing stop activated for {position.position_id} at {pnl_pct:.2f}% profit"
            )
        
        if not position.trailing_stop_active:
            return
        
        # Calculate new stop loss
        if position.side == PositionSide.LONG:
            # Trail below highest price
            trail_distance = position.highest_price * config.trail_pct / Decimal("100")
            new_stop = position.highest_price - trail_distance
            
            # Only move stop loss up, never down
            if new_stop > position.current_stop_loss:
                # Apply step size
                step = position.entry_price * config.step_size / Decimal("100")
                if new_stop - position.current_stop_loss >= step:
                    old_stop = position.current_stop_loss
                    position.current_stop_loss = new_stop.quantize(Decimal("0.05"))
                    
                    self.logger.info(
                        f"Trailing stop moved: {position.position_id} "
                        f"{old_stop} -> {position.current_stop_loss}"
                    )
                    
                    # Ensure minimum profit lock
                    min_profit_price = position.entry_price * (
                        Decimal("1") + config.min_profit_lock_pct / Decimal("100")
                    )
                    if position.current_stop_loss < min_profit_price and pnl_pct > config.min_profit_lock_pct:
                        position.current_stop_loss = min_profit_price.quantize(Decimal("0.05"))
        else:
            # Short position - trail above lowest price
            trail_distance = position.lowest_price * config.trail_pct / Decimal("100")
            new_stop = position.lowest_price + trail_distance
            
            if new_stop < position.current_stop_loss:
                step = position.entry_price * config.step_size / Decimal("100")
                if position.current_stop_loss - new_stop >= step:
                    old_stop = position.current_stop_loss
                    position.current_stop_loss = new_stop.quantize(Decimal("0.05"))
                    
                    self.logger.info(
                        f"Trailing stop moved: {position.position_id} "
                        f"{old_stop} -> {position.current_stop_loss}"
                    )
    
    async def _request_exit(
        self,
        position: Position,
        reason: ExitReason
    ) -> None:
        """Request position exit through OMS."""
        if position.state != PositionState.OPEN:
            return
        
        position.state = PositionState.CLOSING
        position.exit_reason = reason
        
        self.logger.info(
            f"Exit requested: {position.position_id} - Reason: {reason.value}"
        )
        
        # Publish exit request to OMS
        await self.event_bus.publish("exit_request", {
            "position_id": position.position_id,
            "symbol": position.symbol,
            "exchange": position.exchange,
            "side": "sell" if position.side == PositionSide.LONG else "buy",
            "quantity": position.quantity,
            "order_type": "market",
            "reason": reason.value,
            "current_price": float(position.current_price),
            "timestamp": datetime.now(self._tz).isoformat()
        })
    
    async def _on_signal(self, event: Dict[str, Any]) -> None:
        """Handle exit signals from strategy engine."""
        signal_type = event.get("signal_type", "")
        symbol = event.get("symbol", "")
        
        # Check for exit signals
        if signal_type in ["long_exit", "LONG_EXIT", "short_exit", "SHORT_EXIT"]:
            for position_id in self._positions_by_symbol.get(symbol, []):
                position = self._positions.get(position_id)
                if position and position.state == PositionState.OPEN:
                    # Match signal type with position side
                    if (signal_type in ["long_exit", "LONG_EXIT"] and 
                        position.side == PositionSide.LONG):
                        await self._request_exit(position, ExitReason.SIGNAL_EXIT)
                    elif (signal_type in ["short_exit", "SHORT_EXIT"] and 
                          position.side == PositionSide.SHORT):
                        await self._request_exit(position, ExitReason.SIGNAL_EXIT)
    
    async def _on_order_filled(self, event: Dict[str, Any]) -> None:
        """Handle order fill notifications."""
        position_id = event.get("position_id")
        order_type = event.get("order_type")  # "entry" or "exit"
        fill_price = Decimal(str(event.get("fill_price", 0)))
        
        position = self._positions.get(position_id)
        if not position:
            return
        
        if order_type == "entry":
            position.state = PositionState.OPEN
            position.opened_at = datetime.now(self._tz)
            position.entry_price = fill_price
            position.entry_order_id = event.get("order_id")
            self.logger.info(f"Position opened: {position_id} @ {fill_price}")
            
        elif order_type == "exit":
            position.state = PositionState.CLOSED
            position.closed_at = datetime.now(self._tz)
            position.exit_price = fill_price
            position.exit_order_id = event.get("order_id")
            position.calculate_realized_pnl(fill_price)
            
            self.logger.info(
                f"Position closed: {position_id} @ {fill_price}, "
                f"P&L: {position.realized_pnl}"
            )
            
            # Publish position close event
            await self._publish_position_update(position, "close")
            
            # Clean up
            await self._cleanup_position(position_id)
    
    async def _on_circuit_breaker(self, event: Dict[str, Any]) -> None:
        """Handle circuit breaker - exit all positions."""
        if event.get("active"):
            self.logger.warning("Circuit breaker triggered - exiting all positions")
            await self.close_all_positions(ExitReason.CIRCUIT_BREAKER)
    
    async def _eod_monitor(self) -> None:
        """Monitor for end of day auto-exit."""
        while self._running:
            try:
                now = datetime.now(self._tz).time()
                
                # Check if it's time for EOD exit
                if now >= self._eod_exit_time:
                    open_positions = [
                        p for p in self._positions.values()
                        if p.state == PositionState.OPEN
                    ]
                    
                    if open_positions:
                        self.logger.info(
                            f"EOD exit triggered - closing {len(open_positions)} positions"
                        )
                        await self.close_all_positions(ExitReason.MARKET_CLOSE)
                
                # Sleep until next check (every 30 seconds)
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in EOD monitor: {e}")
                await asyncio.sleep(30)
    
    async def close_all_positions(self, reason: ExitReason) -> None:
        """Close all open positions."""
        open_positions = [
            p for p in self._positions.values()
            if p.state == PositionState.OPEN
        ]
        
        for position in open_positions:
            await self._request_exit(position, reason)
    
    async def close_position(
        self,
        position_id: str,
        reason: ExitReason = ExitReason.MANUAL
    ) -> bool:
        """Manually close a specific position."""
        position = self._positions.get(position_id)
        if not position or position.state != PositionState.OPEN:
            return False
        
        await self._request_exit(position, reason)
        return True
    
    async def modify_stop_loss(
        self,
        position_id: str,
        new_stop_loss: Decimal
    ) -> bool:
        """Manually modify stop loss for a position."""
        position = self._positions.get(position_id)
        if not position or position.state != PositionState.OPEN:
            return False
        
        old_stop = position.current_stop_loss
        position.current_stop_loss = new_stop_loss
        
        self.logger.info(
            f"Stop loss modified: {position_id} {old_stop} -> {new_stop_loss}"
        )
        
        await self._publish_position_update(position, "update")
        return True
    
    async def modify_target(
        self,
        position_id: str,
        new_target: Decimal
    ) -> bool:
        """Manually modify target for a position."""
        position = self._positions.get(position_id)
        if not position or position.state != PositionState.OPEN:
            return False
        
        old_target = position.target_price
        position.target_price = new_target
        
        self.logger.info(
            f"Target modified: {position_id} {old_target} -> {new_target}"
        )
        
        await self._publish_position_update(position, "update")
        return True
    
    async def _publish_position_update(
        self,
        position: Position,
        action: str
    ) -> None:
        """Publish position update event."""
        await self.event_bus.publish("position_update", {
            "position_id": position.position_id,
            "action": action,
            "symbol": position.symbol,
            "exchange": position.exchange,
            "side": position.side.value,
            "quantity": position.quantity,
            "entry_price": float(position.entry_price),
            "current_price": float(position.current_price),
            "stop_loss": float(position.current_stop_loss),
            "target": float(position.target_price),
            "unrealized_pnl": float(position.unrealized_pnl),
            "realized_pnl": float(position.realized_pnl),
            "state": position.state.value,
            "strategy_id": position.strategy_id,
            "risk_amount": float(position.get_risk_amount()),
            "exposure": float(position.get_exposure()),
            "opened_at": position.opened_at.isoformat() if position.opened_at else None,
            "closed_at": position.closed_at.isoformat() if position.closed_at else None,
            "exit_reason": position.exit_reason.value if position.exit_reason else None,
            "timestamp": datetime.now(self._tz).isoformat()
        })
    
    async def _cleanup_position(self, position_id: str) -> None:
        """Clean up closed position from tracking."""
        position = self._positions.get(position_id)
        if not position:
            return
        
        # Remove from symbol index
        if position.symbol in self._positions_by_symbol:
            self._positions_by_symbol[position.symbol] = [
                pid for pid in self._positions_by_symbol[position.symbol]
                if pid != position_id
            ]
            if not self._positions_by_symbol[position.symbol]:
                del self._positions_by_symbol[position.symbol]
        
        # Keep in main dict for history (could move to archive)
        # For now, just mark as closed and keep for session
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get a position by ID."""
        return self._positions.get(position_id)
    
    def get_positions_by_symbol(self, symbol: str) -> List[Position]:
        """Get all positions for a symbol."""
        return [
            self._positions[pid]
            for pid in self._positions_by_symbol.get(symbol, [])
        ]
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return [
            p for p in self._positions.values()
            if p.state == PositionState.OPEN
        ]
    
    def get_all_positions(self) -> List[Position]:
        """Get all positions (including closed)."""
        return list(self._positions.values())
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary."""
        open_positions = self.get_open_positions()
        
        total_unrealized_pnl = sum(p.unrealized_pnl for p in open_positions)
        total_exposure = sum(p.get_exposure() for p in open_positions)
        total_risk = sum(p.get_risk_amount() for p in open_positions)
        
        return {
            "open_positions": len(open_positions),
            "total_unrealized_pnl": float(total_unrealized_pnl),
            "total_exposure": float(total_exposure),
            "total_risk_amount": float(total_risk),
            "positions": [
                {
                    "position_id": p.position_id,
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "quantity": p.quantity,
                    "entry_price": float(p.entry_price),
                    "current_price": float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pnl),
                    "pnl_pct": float(p.get_pnl_percentage()),
                    "stop_loss": float(p.current_stop_loss),
                    "target": float(p.target_price),
                }
                for p in open_positions
            ]
        }


# Factory function
def create_position_manager(event_bus: EventBus) -> PositionManager:
    """Create and configure position manager instance."""
    default_trailing = TrailingStopConfig(
        enabled=True,
        activation_pct=Decimal("1.0"),
        trail_pct=Decimal("0.5"),
        step_size=Decimal("0.25"),
        min_profit_lock_pct=Decimal("0.5")
    )
    return PositionManager(event_bus, default_trailing)
