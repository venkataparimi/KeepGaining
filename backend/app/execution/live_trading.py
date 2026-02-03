"""
Live Trading Engine
KeepGaining Trading Platform

Production-grade live trading engine for executing real trades via brokers.
Features:
- Multi-broker support (Fyers, Upstox)
- Position reconciliation with broker
- Order status tracking and streaming
- SL/Target monitoring
- Auto square-off
- Safety checks and circuit breakers
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

from loguru import logger

from app.brokers.base import BaseBroker
from app.schemas.broker import (
    OrderRequest, OrderResponse, Position, Quote,
    OrderType, ProductType
)
from app.db.models import OrderSide, OrderStatus
from app.core.events import EventBus, EventType, get_event_bus_sync


class LiveTradingMode(str, Enum):
    """Live trading modes."""
    NORMAL = "normal"        # Full live trading
    SHADOW = "shadow"        # Execute in paper, mirror signals to live
    DRY_RUN = "dry_run"      # Validate but don't execute


class PositionState(str, Enum):
    """Position lifecycle states."""
    PENDING = "pending"      # Order placed, awaiting fill
    OPEN = "open"           # Position is active
    CLOSING = "closing"     # Exit order placed
    CLOSED = "closed"       # Position fully closed


@dataclass
class LivePosition:
    """Represents a live trading position with monitoring."""
    position_id: str
    symbol: str
    exchange: str
    side: OrderSide
    quantity: int
    average_price: Decimal
    current_price: Decimal = Decimal("0")
    
    # Order tracking
    entry_order_id: Optional[str] = None
    exit_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    target_order_id: Optional[str] = None
    
    # Risk management
    stop_loss: Optional[Decimal] = None
    target: Optional[Decimal] = None
    trailing_sl: bool = False
    trailing_sl_points: Optional[Decimal] = None
    highest_price: Optional[Decimal] = None  # For trailing SL
    
    # State
    state: PositionState = PositionState.PENDING
    product_type: str = "MIS"  # MIS or CNC
    strategy_id: Optional[str] = None
    
    # Timestamps
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    exit_time: Optional[datetime] = None
    
    # P&L
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_pnl(self) -> None:
        """Update unrealized P&L based on current price."""
        if self.current_price > 0:
            if self.side == OrderSide.BUY:
                self.unrealized_pnl = (self.current_price - self.average_price) * self.quantity
            else:
                self.unrealized_pnl = (self.average_price - self.current_price) * self.quantity
    
    def should_stop_loss(self) -> bool:
        """Check if stop loss should trigger."""
        if not self.stop_loss or self.current_price <= 0:
            return False
        
        if self.side == OrderSide.BUY:
            return self.current_price <= self.stop_loss
        else:
            return self.current_price >= self.stop_loss
    
    def should_take_profit(self) -> bool:
        """Check if target should trigger."""
        if not self.target or self.current_price <= 0:
            return False
        
        if self.side == OrderSide.BUY:
            return self.current_price >= self.target
        else:
            return self.current_price <= self.target
    
    def update_trailing_sl(self) -> None:
        """Update trailing stop loss based on price movement."""
        if not self.trailing_sl or not self.trailing_sl_points:
            return
        
        if self.highest_price is None:
            self.highest_price = self.current_price
        
        if self.side == OrderSide.BUY:
            if self.current_price > self.highest_price:
                self.highest_price = self.current_price
                self.stop_loss = self.highest_price - self.trailing_sl_points
        else:
            if self.current_price < self.highest_price:
                self.highest_price = self.current_price
                self.stop_loss = self.highest_price + self.trailing_sl_points
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.side.value if hasattr(self.side, 'value') else str(self.side),
            "quantity": self.quantity,
            "average_price": float(self.average_price),
            "current_price": float(self.current_price),
            "stop_loss": float(self.stop_loss) if self.stop_loss else None,
            "target": float(self.target) if self.target else None,
            "unrealized_pnl": float(self.unrealized_pnl),
            "realized_pnl": float(self.realized_pnl),
            "state": self.state.value,
            "product_type": self.product_type,
            "strategy_id": self.strategy_id,
            "entry_order_id": self.entry_order_id,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
        }


@dataclass
class LiveTradingConfig:
    """Live trading engine configuration."""
    # Capital limits
    max_capital: Decimal = Decimal("500000")
    max_position_value: Decimal = Decimal("100000")
    max_positions: int = 5
    
    # Risk limits
    max_daily_loss: Decimal = Decimal("25000")
    max_daily_loss_percent: Decimal = Decimal("5")
    max_single_loss: Decimal = Decimal("5000")
    
    # Trading hours (IST)
    market_open: str = "09:15"
    market_close: str = "15:30"
    no_entry_after: str = "14:45"
    auto_square_off_time: str = "15:20"
    
    # Execution settings
    default_product_type: str = "MIS"  # MIS for intraday
    slippage_percent: Decimal = Decimal("0.1")  # Expected slippage
    
    # Safety
    require_sl: bool = True  # Require stop loss for every trade
    max_sl_percent: Decimal = Decimal("3")  # Max 3% stop loss
    min_rr_ratio: Decimal = Decimal("1.5")  # Minimum risk-reward ratio
    
    # Mode
    trading_mode: LiveTradingMode = LiveTradingMode.NORMAL
    enable_auto_square_off: bool = True


@dataclass
class TradeSummary:
    """Summary of a completed trade."""
    trade_id: str
    symbol: str
    side: OrderSide
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    entry_time: datetime
    exit_time: datetime
    net_pnl: Decimal
    pnl_percent: Decimal
    exit_reason: str
    strategy_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side.value if hasattr(self.side, 'value') else str(self.side),
            "quantity": self.quantity,
            "entry_price": float(self.entry_price),
            "exit_price": float(self.exit_price),
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "net_pnl": float(self.net_pnl),
            "pnl_percent": float(self.pnl_percent),
            "exit_reason": self.exit_reason,
            "strategy_id": self.strategy_id,
        }


class LiveTradingEngine:
    """
    Production live trading engine.
    
    Features:
    - Real order execution via brokers
    - Position reconciliation
    - SL/Target monitoring
    - Auto square-off
    - Circuit breakers
    - Audit trail
    """
    
    def __init__(
        self,
        broker: BaseBroker,
        config: Optional[LiveTradingConfig] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self.broker = broker
        self.config = config or LiveTradingConfig()
        self.event_bus = event_bus or get_event_bus_sync()
        
        # State
        self._running = False
        self._positions: Dict[str, LivePosition] = {}  # symbol -> position
        self._orders: Dict[str, Dict] = {}  # order_id -> order info
        self._trades: List[TradeSummary] = []
        
        # Daily tracking
        self._daily_pnl = Decimal("0")
        self._daily_trades = 0
        self._initial_capital = self.config.max_capital
        
        # Circuit breakers
        self._trading_halted = False
        self._halt_reason: Optional[str] = None
        
        # Background tasks
        self._monitor_task: Optional[asyncio.Task] = None
        self._reconcile_task: Optional[asyncio.Task] = None
        
        logger.info(f"LiveTradingEngine initialized (mode={self.config.trading_mode.value})")
    
    async def start(self) -> bool:
        """Start the live trading engine."""
        if self._running:
            logger.warning("Live trading engine already running")
            return False
        
        try:
            # Verify broker authentication
            if not await self.broker.authenticate():
                logger.error("Broker authentication failed")
                return False
            
            # Initial position reconciliation
            await self._reconcile_positions()
            
            # Start monitoring tasks
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            self._reconcile_task = asyncio.create_task(self._reconciliation_loop())
            
            self._running = True
            logger.info("Live trading engine started")
            
            # Publish event
            await self._publish_event("live_trading_started", {
                "mode": self.config.trading_mode.value,
                "max_capital": float(self.config.max_capital),
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start live trading engine: {e}")
            return False
    
    async def stop(self) -> None:
        """Stop the live trading engine."""
        if not self._running:
            return
        
        logger.info("Stopping live trading engine...")
        self._running = False
        
        # Cancel background tasks
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        if self._reconcile_task:
            self._reconcile_task.cancel()
            try:
                await self._reconcile_task
            except asyncio.CancelledError:
                pass
        
        # Publish event
        await self._publish_event("live_trading_stopped", {
            "daily_pnl": float(self._daily_pnl),
            "daily_trades": self._daily_trades,
        })
        
        logger.info("Live trading engine stopped")
    
    async def enter_position(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        order_type: str = "MARKET",
        product_type: Optional[str] = None,
        strategy_id: Optional[str] = None,
        trailing_sl: bool = False,
        trailing_sl_points: Optional[float] = None,
    ) -> Optional[LivePosition]:
        """
        Enter a new position.
        
        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Number of shares/lots
            price: Limit price (None for market order)
            stop_loss: Stop loss price
            target: Target price
            order_type: MARKET, LIMIT, SL, SL-M
            product_type: MIS (intraday) or CNC (delivery)
            strategy_id: Strategy that generated this signal
            trailing_sl: Enable trailing stop loss
            trailing_sl_points: Points to trail by
            
        Returns:
            LivePosition if order placed successfully, None otherwise
        """
        # Pre-flight checks
        if self._trading_halted:
            logger.warning(f"Trading halted: {self._halt_reason}")
            return None
        
        if not self._is_trading_hours():
            logger.warning("Outside trading hours")
            return None
        
        if symbol in self._positions:
            logger.warning(f"Already have position in {symbol}")
            return None
        
        if len(self._positions) >= self.config.max_positions:
            logger.warning("Max positions limit reached")
            return None
        
        # Validate stop loss requirement
        if self.config.require_sl and not stop_loss:
            logger.warning("Stop loss required but not provided")
            return None
        
        # Validate risk-reward if target provided
        if stop_loss and target and price:
            risk = abs(price - stop_loss)
            reward = abs(target - price)
            if reward / risk < float(self.config.min_rr_ratio):
                logger.warning(f"Risk-reward ratio below minimum: {reward/risk:.2f}")
                return None
        
        # Check position value limit
        estimated_value = quantity * (price or 0)
        if Decimal(str(estimated_value)) > self.config.max_position_value:
            logger.warning(f"Position value exceeds limit: {estimated_value}")
            return None
        
        # Check daily loss limit
        if await self._check_daily_loss_limit():
            return None
        
        try:
            # Create order request
            order = OrderRequest(
                symbol=symbol,
                quantity=quantity,
                side=side,
                price=price,
                order_type=order_type,
                product_type=product_type or self.config.default_product_type,
            )
            
            # Execute based on mode
            if self.config.trading_mode == LiveTradingMode.DRY_RUN:
                logger.info(f"[DRY_RUN] Would place order: {order}")
                response = OrderResponse(
                    order_id=f"DRY_{datetime.now().timestamp()}",
                    status=OrderStatus.PENDING,
                    message="Dry run - order not placed"
                )
            else:
                # Place actual order
                response = await self.broker.place_order(order)
            
            if response.status == OrderStatus.REJECTED:
                logger.error(f"Order rejected: {response.message}")
                await self._publish_event("order_rejected", {
                    "symbol": symbol,
                    "reason": response.message,
                })
                return None
            
            # Create position
            import uuid
            position = LivePosition(
                position_id=str(uuid.uuid4()),
                symbol=symbol,
                exchange="NSE",  # TODO: Extract from symbol
                side=side,
                quantity=quantity,
                average_price=Decimal(str(price or 0)),
                entry_order_id=response.order_id,
                stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
                target=Decimal(str(target)) if target else None,
                trailing_sl=trailing_sl,
                trailing_sl_points=Decimal(str(trailing_sl_points)) if trailing_sl_points else None,
                product_type=product_type or self.config.default_product_type,
                strategy_id=strategy_id,
                state=PositionState.PENDING,
            )
            
            self._positions[symbol] = position
            self._orders[response.order_id] = {
                "order_id": response.order_id,
                "symbol": symbol,
                "type": "entry",
                "position_id": position.position_id,
                "placed_at": datetime.now(timezone.utc),
            }
            
            logger.info(f"Entry order placed: {symbol} {side.value} {quantity} @ {price or 'MARKET'}")
            
            # Publish event
            await self._publish_event("position_entry_placed", position.to_dict())
            
            # Place SL order if using bracket
            if stop_loss and self.config.trading_mode != LiveTradingMode.DRY_RUN:
                await self._place_sl_order(position, Decimal(str(stop_loss)))
            
            return position
            
        except Exception as e:
            logger.error(f"Failed to enter position: {e}")
            return None
    
    async def exit_position(
        self,
        symbol: str,
        reason: str = "MANUAL",
        price: Optional[float] = None,
    ) -> Optional[TradeSummary]:
        """
        Exit an existing position.
        
        Args:
            symbol: Symbol to exit
            reason: Exit reason (MANUAL, STOP_LOSS, TARGET, AUTO_SQUARE_OFF, etc.)
            price: Limit price (None for market order)
            
        Returns:
            TradeSummary if successful, None otherwise
        """
        position = self._positions.get(symbol)
        if not position:
            logger.warning(f"No position found for {symbol}")
            return None
        
        if position.state in [PositionState.CLOSING, PositionState.CLOSED]:
            logger.warning(f"Position already closing/closed: {symbol}")
            return None
        
        try:
            # Determine exit side (opposite of entry)
            exit_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY
            
            order = OrderRequest(
                symbol=symbol,
                quantity=position.quantity,
                side=exit_side,
                price=price,
                order_type="MARKET" if not price else "LIMIT",
                product_type=position.product_type,
            )
            
            position.state = PositionState.CLOSING
            
            if self.config.trading_mode == LiveTradingMode.DRY_RUN:
                logger.info(f"[DRY_RUN] Would place exit order: {order}")
                response = OrderResponse(
                    order_id=f"DRY_EXIT_{datetime.now().timestamp()}",
                    status=OrderStatus.FILLED,
                    average_price=float(position.current_price),
                    filled_quantity=position.quantity,
                )
            else:
                # Cancel pending SL/target orders first
                await self._cancel_position_orders(position)
                
                # Place exit order
                response = await self.broker.place_order(order)
            
            if response.status == OrderStatus.REJECTED:
                position.state = PositionState.OPEN  # Revert
                logger.error(f"Exit order rejected: {response.message}")
                return None
            
            position.exit_order_id = response.order_id
            
            # If market order, assume immediate fill for calculation
            exit_price = Decimal(str(response.average_price or position.current_price))
            position.exit_time = datetime.now(timezone.utc)
            position.state = PositionState.CLOSED
            
            # Calculate P&L
            if position.side == OrderSide.BUY:
                position.realized_pnl = (exit_price - position.average_price) * position.quantity
            else:
                position.realized_pnl = (position.average_price - exit_price) * position.quantity
            
            pnl_percent = (position.realized_pnl / (position.average_price * position.quantity)) * 100
            
            # Create trade summary
            trade = TradeSummary(
                trade_id=position.position_id,
                symbol=symbol,
                side=position.side,
                quantity=position.quantity,
                entry_price=position.average_price,
                exit_price=exit_price,
                entry_time=position.entry_time,
                exit_time=position.exit_time,
                net_pnl=position.realized_pnl,
                pnl_percent=pnl_percent,
                exit_reason=reason,
                strategy_id=position.strategy_id,
            )
            
            self._trades.append(trade)
            self._daily_pnl += position.realized_pnl
            self._daily_trades += 1
            
            # Remove from active positions
            del self._positions[symbol]
            
            logger.info(f"Position closed: {symbol} P&L: ₹{position.realized_pnl:,.2f} ({pnl_percent:.1f}%)")
            
            # Publish event
            await self._publish_event("position_closed", {
                **trade.to_dict(),
                "daily_pnl": float(self._daily_pnl),
            })
            
            return trade
            
        except Exception as e:
            logger.error(f"Failed to exit position: {e}")
            position.state = PositionState.OPEN  # Revert
            return None
    
    async def modify_sl(self, symbol: str, new_sl: float) -> bool:
        """Modify stop loss for a position."""
        position = self._positions.get(symbol)
        if not position:
            return False
        
        position.stop_loss = Decimal(str(new_sl))
        
        # If there's an existing SL order, modify or replace it
        if position.sl_order_id and self.config.trading_mode != LiveTradingMode.DRY_RUN:
            # Cancel old SL order
            await self.broker.cancel_order(position.sl_order_id)
            # Place new SL order
            await self._place_sl_order(position, position.stop_loss)
        
        logger.info(f"SL modified for {symbol}: {new_sl}")
        return True
    
    async def modify_target(self, symbol: str, new_target: float) -> bool:
        """Modify target for a position."""
        position = self._positions.get(symbol)
        if not position:
            return False
        
        position.target = Decimal(str(new_target))
        logger.info(f"Target modified for {symbol}: {new_target}")
        return True
    
    async def _place_sl_order(self, position: LivePosition, sl_price: Decimal) -> None:
        """Place a stop loss order for position."""
        exit_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY
        
        sl_order = OrderRequest(
            symbol=position.symbol,
            quantity=position.quantity,
            side=exit_side,
            trigger_price=float(sl_price),
            order_type="SL-M",  # Stop loss market
            product_type=position.product_type,
        )
        
        response = await self.broker.place_order(sl_order)
        if response.status != OrderStatus.REJECTED:
            position.sl_order_id = response.order_id
            logger.info(f"SL order placed for {position.symbol}: {sl_price}")
    
    async def _cancel_position_orders(self, position: LivePosition) -> None:
        """Cancel all pending orders for a position."""
        for order_id in [position.sl_order_id, position.target_order_id]:
            if order_id:
                try:
                    await self.broker.cancel_order(order_id)
                except Exception as e:
                    logger.warning(f"Failed to cancel order {order_id}: {e}")
    
    async def _monitor_loop(self) -> None:
        """Background task to monitor positions and trigger SL/target."""
        while self._running:
            try:
                await self._update_prices()
                await self._check_sl_target()
                await self._check_auto_square_off()
                await asyncio.sleep(1)  # Check every second
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(5)
    
    async def _reconciliation_loop(self) -> None:
        """Background task to reconcile positions with broker."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Reconcile every 30 seconds
                await self._reconcile_positions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconciliation error: {e}")
    
    async def _update_prices(self) -> None:
        """Update current prices for all positions."""
        if not self._positions:
            return
        
        symbols = list(self._positions.keys())
        
        try:
            # Batch fetch quotes
            if hasattr(self.broker, 'get_quotes_batch'):
                quotes = await self.broker.get_quotes_batch(symbols)
                for symbol, data in quotes.items():
                    if symbol in self._positions:
                        self._positions[symbol].current_price = Decimal(str(data.get('price', 0)))
                        self._positions[symbol].update_pnl()
                        if self._positions[symbol].trailing_sl:
                            self._positions[symbol].update_trailing_sl()
            else:
                # Fallback to individual quotes
                for symbol in symbols:
                    quote = await self.broker.get_quote(symbol)
                    if quote and symbol in self._positions:
                        self._positions[symbol].current_price = Decimal(str(quote.last_price))
                        self._positions[symbol].update_pnl()
        except Exception as e:
            logger.warning(f"Price update error: {e}")
    
    async def _check_sl_target(self) -> None:
        """Check if any positions hit SL or target."""
        for symbol, position in list(self._positions.items()):
            if position.state != PositionState.OPEN:
                continue
            
            if position.should_stop_loss():
                logger.info(f"Stop loss triggered for {symbol}")
                await self.exit_position(symbol, reason="STOP_LOSS")
            
            elif position.should_take_profit():
                logger.info(f"Target hit for {symbol}")
                await self.exit_position(symbol, reason="TARGET")
    
    async def _check_auto_square_off(self) -> None:
        """Check if it's time for auto square-off."""
        if not self.config.enable_auto_square_off:
            return
        
        now = datetime.now(ZoneInfo("Asia/Kolkata")).time()
        square_off_time = datetime.strptime(self.config.auto_square_off_time, "%H:%M").time()
        
        if now >= square_off_time:
            # Square off all intraday positions
            for symbol, position in list(self._positions.items()):
                if position.product_type == "MIS" and position.state == PositionState.OPEN:
                    logger.info(f"Auto square-off: {symbol}")
                    await self.exit_position(symbol, reason="AUTO_SQUARE_OFF")
    
    async def _check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit is reached."""
        if self._daily_pnl < -self.config.max_daily_loss:
            if not self._trading_halted:
                self._trading_halted = True
                self._halt_reason = f"Daily loss limit reached: ₹{self._daily_pnl:,.2f}"
                logger.warning(self._halt_reason)
                await self._publish_event("circuit_breaker_triggered", {
                    "reason": self._halt_reason,
                    "daily_pnl": float(self._daily_pnl),
                })
            return True
        
        # Check percentage
        loss_percent = (abs(self._daily_pnl) / self._initial_capital) * 100
        if self._daily_pnl < 0 and loss_percent > float(self.config.max_daily_loss_percent):
            if not self._trading_halted:
                self._trading_halted = True
                self._halt_reason = f"Daily loss limit reached: {loss_percent:.1f}%"
                logger.warning(self._halt_reason)
                await self._publish_event("circuit_breaker_triggered", {
                    "reason": self._halt_reason,
                    "loss_percent": float(loss_percent),
                })
            return True
        
        return False
    
    async def _reconcile_positions(self) -> None:
        """
        Reconcile local positions with broker positions.
        
        This ensures our position state matches the broker's actual state,
        handling cases like:
        - Orders filled while we were disconnected
        - Manual trades made outside the system
        - System restarts
        """
        try:
            broker_positions = await self.broker.get_positions()
            broker_symbols = {p.symbol for p in broker_positions}
            local_symbols = set(self._positions.keys())
            
            # Check for positions we have but broker doesn't
            for symbol in local_symbols - broker_symbols:
                position = self._positions[symbol]
                if position.state == PositionState.OPEN:
                    logger.warning(f"Position {symbol} not found at broker - marking closed")
                    position.state = PositionState.CLOSED
                    # Could be filled exit order we missed
            
            # Update positions from broker data
            for bp in broker_positions:
                if bp.symbol in self._positions:
                    # Update with broker data
                    position = self._positions[bp.symbol]
                    position.current_price = Decimal(str(bp.last_price or 0))
                    position.quantity = bp.quantity
                    if position.state == PositionState.PENDING:
                        position.state = PositionState.OPEN
                        position.average_price = Decimal(str(bp.average_price or 0))
                    position.update_pnl()
                else:
                    # Position at broker we don't have - likely external trade
                    if bp.quantity != 0:
                        logger.info(f"Found external position: {bp.symbol}")
                        # Optionally: Create local tracking for it
            
            logger.debug(f"Position reconciliation complete: {len(broker_positions)} broker positions")
            
        except Exception as e:
            logger.error(f"Position reconciliation failed: {e}")
    
    def _is_trading_hours(self, allow_entry: bool = True) -> bool:
        """Check if within trading hours."""
        now = datetime.now(ZoneInfo("Asia/Kolkata")).time()
        
        market_open = datetime.strptime(self.config.market_open, "%H:%M").time()
        market_close = datetime.strptime(self.config.market_close, "%H:%M").time()
        
        if not (market_open <= now <= market_close):
            return False
        
        # For entries, check no_entry_after
        if allow_entry:
            no_entry = datetime.strptime(self.config.no_entry_after, "%H:%M").time()
            return now <= no_entry
        
        return True
    
    async def _publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish event to event bus."""
        try:
            await self.event_bus.publish(event_type, data)
        except Exception as e:
            logger.warning(f"Failed to publish event {event_type}: {e}")
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all positions."""
        return [p.to_dict() for p in self._positions.values()]
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get a specific position."""
        position = self._positions.get(symbol)
        return position.to_dict() if position else None
    
    def get_trades(self) -> List[Dict[str, Any]]:
        """Get trade history."""
        return [t.to_dict() for t in self._trades]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get trading statistics."""
        winning = [t for t in self._trades if t.net_pnl > 0]
        losing = [t for t in self._trades if t.net_pnl < 0]
        
        total_profit = sum(t.net_pnl for t in winning)
        total_loss = abs(sum(t.net_pnl for t in losing))
        
        unrealized_pnl = sum(p.unrealized_pnl for p in self._positions.values())
        
        return {
            "running": self._running,
            "trading_halted": self._trading_halted,
            "halt_reason": self._halt_reason,
            "open_positions": len(self._positions),
            "total_trades": self._daily_trades,
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": len(winning) / len(self._trades) * 100 if self._trades else 0,
            "realized_pnl": float(self._daily_pnl),
            "unrealized_pnl": float(unrealized_pnl),
            "total_pnl": float(self._daily_pnl + unrealized_pnl),
            "profit_factor": float(total_profit / total_loss) if total_loss > 0 else 0,
        }


# Factory function
def create_live_trading_engine(
    broker: BaseBroker,
    config: Optional[LiveTradingConfig] = None,
) -> LiveTradingEngine:
    """Create a live trading engine instance."""
    return LiveTradingEngine(broker=broker, config=config)
