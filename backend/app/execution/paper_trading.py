"""
Paper Trading Engine

A comprehensive paper trading system that simulates real trading without risking capital.
Supports:
- Realistic order execution with slippage and latency simulation
- Real-time position tracking with P&L
- Virtual portfolio management
- Integration with live market data for realistic fills
- Full trade history and analytics

Architecture:
    SignalEvent → PaperTradingEngine → VirtualPosition/VirtualOrder
                                     → TradeEvent (simulated fills)

Usage:
    engine = PaperTradingEngine(initial_capital=100000)
    await engine.start()
    await engine.execute_signal(signal)  # From strategy engine
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.core.events import EventBus, EventType, get_event_bus


class OrderSide(str, Enum):
    """Order side."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "SL"
    STOP_LOSS_MARKET = "SL-M"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ProductType(str, Enum):
    """Product type."""
    MIS = "MIS"  # Intraday
    CNC = "CNC"  # Delivery
    NRML = "NRML"  # Normal (F&O)


@dataclass
class VirtualOrder:
    """Virtual order in paper trading."""
    order_id: str
    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    product_type: ProductType
    quantity: int
    price: Optional[Decimal] = None  # For limit orders
    trigger_price: Optional[Decimal] = None  # For SL orders
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    average_fill_price: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    strategy_id: Optional[str] = None
    signal_id: Optional[str] = None
    parent_order_id: Optional[str] = None  # For bracket/cover orders
    created_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Kolkata")))
    updated_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Kolkata")))
    filled_at: Optional[datetime] = None
    reject_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VirtualPosition:
    """Virtual position in paper trading."""
    position_id: str
    symbol: str
    exchange: str
    side: OrderSide  # NET side (BUY = Long, SELL = Short)
    quantity: int
    average_price: Decimal
    current_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    stop_loss: Optional[Decimal] = None
    target: Optional[Decimal] = None
    trailing_sl: bool = False
    trailing_sl_points: Optional[Decimal] = None
    highest_price: Decimal = Decimal("0")  # For trailing SL
    lowest_price: Decimal = Decimal("0")
    product_type: ProductType = ProductType.MIS
    strategy_id: Optional[str] = None
    entry_order_id: Optional[str] = None
    entry_time: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Kolkata")))
    last_update: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Kolkata")))
    sl_order_id: Optional[str] = None
    target_order_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_price(self, price: Decimal) -> None:
        """Update current price and recalculate P&L."""
        self.current_price = price
        self.last_update = datetime.now(ZoneInfo("Asia/Kolkata"))
        
        # Track high/low for trailing SL
        if price > self.highest_price or self.highest_price == 0:
            self.highest_price = price
        if price < self.lowest_price or self.lowest_price == 0:
            self.lowest_price = price
        
        # Calculate unrealized P&L
        if self.side == OrderSide.BUY:
            self.unrealized_pnl = (price - self.average_price) * self.quantity
        else:  # Short position
            self.unrealized_pnl = (self.average_price - price) * self.quantity
    
    def should_trigger_sl(self, price: Decimal) -> bool:
        """Check if stop loss should be triggered."""
        if not self.stop_loss:
            return False
        
        if self.side == OrderSide.BUY:
            return price <= self.stop_loss
        else:
            return price >= self.stop_loss
    
    def should_trigger_target(self, price: Decimal) -> bool:
        """Check if target should be triggered."""
        if not self.target:
            return False
        
        if self.side == OrderSide.BUY:
            return price >= self.target
        else:
            return price <= self.target
    
    def update_trailing_sl(self, price: Decimal) -> bool:
        """Update trailing stop loss. Returns True if SL was modified."""
        if not self.trailing_sl or not self.trailing_sl_points:
            return False
        
        if self.side == OrderSide.BUY:
            new_sl = price - self.trailing_sl_points
            if new_sl > (self.stop_loss or Decimal("0")):
                self.stop_loss = new_sl
                return True
        else:
            new_sl = price + self.trailing_sl_points
            if self.stop_loss is None or new_sl < self.stop_loss:
                self.stop_loss = new_sl
                return True
        
        return False


@dataclass
class VirtualTrade:
    """Completed trade record."""
    trade_id: str
    order_id: str
    position_id: str
    symbol: str
    exchange: str
    side: OrderSide
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    entry_time: datetime
    exit_time: datetime
    gross_pnl: Decimal
    commission: Decimal
    slippage: Decimal
    net_pnl: Decimal
    pnl_percent: Decimal
    strategy_id: Optional[str] = None
    exit_reason: str = "MANUAL"  # SL_HIT, TARGET_HIT, MANUAL, TRAILING_SL, TIME_EXIT
    holding_period_minutes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperTradingConfig:
    """Paper trading configuration."""
    initial_capital: Decimal = Decimal("100000")
    slippage_percent: Decimal = Decimal("0.05")  # 0.05% slippage
    commission_percent: Decimal = Decimal("0.03")  # 0.03% per trade
    latency_ms: int = 100  # Simulated latency
    partial_fill_probability: float = 0.0  # Probability of partial fills
    rejection_probability: float = 0.0  # Probability of order rejection
    max_positions: int = 10
    max_order_value: Decimal = Decimal("200000")
    auto_square_off_time: Optional[str] = "15:20"  # For MIS orders
    enable_trailing_sl: bool = True


class PaperTradingEngine:
    """
    Paper Trading Engine for simulated trading.
    
    Features:
    - Virtual order execution with realistic simulation
    - Position tracking with real-time P&L
    - Portfolio management
    - Integration with live data feed for price updates
    - Full trade history
    """
    
    def __init__(
        self,
        config: Optional[PaperTradingConfig] = None,
        event_bus: Optional[EventBus] = None
    ):
        self.config = config or PaperTradingConfig()
        self.event_bus = event_bus
        self.logger = logging.getLogger(__name__)
        
        # Virtual portfolio state
        self.capital = self.config.initial_capital
        self.available_capital = self.config.initial_capital
        self.used_margin = Decimal("0")
        
        # Orders and positions
        self.orders: Dict[str, VirtualOrder] = {}
        self.positions: Dict[str, VirtualPosition] = {}  # Key: symbol
        self.trades: List[VirtualTrade] = []
        
        # Pending orders waiting for execution
        self.pending_orders: Dict[str, VirtualOrder] = {}
        
        # Price cache (symbol -> last price)
        self._price_cache: Dict[str, Decimal] = {}
        
        # Statistics
        self._stats = {
            "orders_placed": 0,
            "orders_filled": 0,
            "orders_rejected": 0,
            "orders_cancelled": 0,
            "trades_completed": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": Decimal("0"),
            "total_commission": Decimal("0"),
            "total_slippage": Decimal("0"),
        }
        
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the paper trading engine."""
        if self._running:
            return
        
        self._running = True
        self.logger.info(
            f"Paper trading engine started with capital: ₹{self.capital:,.2f}"
        )
        
        # Subscribe to price updates if event bus available
        if self.event_bus:
            await self.event_bus.subscribe(
                EventType.TICK,
                self._on_tick
            )
            await self.event_bus.subscribe(
                EventType.CANDLE,
                self._on_candle
            )
        
        # Start position monitor
        self._monitor_task = asyncio.create_task(self._position_monitor())
    
    async def stop(self) -> None:
        """Stop the paper trading engine."""
        self._running = False
        
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Paper trading engine stopped")
    
    async def _on_tick(self, tick_data: Dict[str, Any]) -> None:
        """Handle incoming tick data."""
        symbol = tick_data.get("symbol")
        price = Decimal(str(tick_data.get("last_price", 0)))
        
        if symbol and price > 0:
            self._price_cache[symbol] = price
            
            # Update position if exists
            if symbol in self.positions:
                await self._update_position_price(symbol, price)
    
    async def _on_candle(self, candle_data: Dict[str, Any]) -> None:
        """Handle incoming candle data."""
        symbol = candle_data.get("symbol")
        close = Decimal(str(candle_data.get("close", 0)))
        
        if symbol and close > 0:
            self._price_cache[symbol] = close
            
            if symbol in self.positions:
                await self._update_position_price(symbol, close)
    
    async def _update_position_price(
        self,
        symbol: str,
        price: Decimal
    ) -> None:
        """Update position price and check SL/Target."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        old_pnl = position.unrealized_pnl
        
        position.update_price(price)
        
        # Check trailing SL update
        if position.trailing_sl:
            if position.update_trailing_sl(price):
                self.logger.info(
                    f"Trailing SL updated for {symbol}: {position.stop_loss}"
                )
        
        # Check stop loss
        if position.should_trigger_sl(price):
            self.logger.info(f"SL triggered for {symbol} at {price}")
            await self._exit_position(
                symbol,
                "SL_HIT",
                exit_price=price
            )
            return
        
        # Check target
        if position.should_trigger_target(price):
            self.logger.info(f"Target hit for {symbol} at {price}")
            await self._exit_position(
                symbol,
                "TARGET_HIT",
                exit_price=price
            )
            return
    
    async def _position_monitor(self) -> None:
        """Background task to monitor positions."""
        while self._running:
            try:
                now = datetime.now(ZoneInfo("Asia/Kolkata"))
                
                # Check auto square-off time for MIS
                if self.config.auto_square_off_time:
                    sq_time = datetime.strptime(
                        self.config.auto_square_off_time,
                        "%H:%M"
                    ).time()
                    
                    if now.time() >= sq_time:
                        mis_positions = [
                            p for p in self.positions.values()
                            if p.product_type == ProductType.MIS
                        ]
                        for pos in mis_positions:
                            self.logger.info(
                                f"Auto square-off for MIS position: {pos.symbol}"
                            )
                            await self._exit_position(
                                pos.symbol,
                                "TIME_EXIT"
                            )
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in position monitor: {e}")
                await asyncio.sleep(1)
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        return f"PAPER-{uuid.uuid4().hex[:12].upper()}"
    
    def _generate_position_id(self) -> str:
        """Generate unique position ID."""
        return f"POS-{uuid.uuid4().hex[:10].upper()}"
    
    def _generate_trade_id(self) -> str:
        """Generate unique trade ID."""
        return f"TRD-{uuid.uuid4().hex[:10].upper()}"
    
    def _calculate_slippage(
        self,
        price: Decimal,
        side: OrderSide
    ) -> Decimal:
        """Calculate slippage for an order."""
        slippage_amount = price * (self.config.slippage_percent / 100)
        
        # Slippage is adverse - buy higher, sell lower
        if side == OrderSide.BUY:
            return slippage_amount
        else:
            return -slippage_amount
    
    def _calculate_commission(
        self,
        price: Decimal,
        quantity: int
    ) -> Decimal:
        """Calculate commission for a trade."""
        trade_value = price * quantity
        commission = trade_value * (self.config.commission_percent / 100)
        return commission.quantize(Decimal("0.01"))
    
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[Decimal] = None,
        trigger_price: Optional[Decimal] = None,
        product_type: ProductType = ProductType.MIS,
        strategy_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        stop_loss: Optional[Decimal] = None,
        target: Optional[Decimal] = None,
        trailing_sl_points: Optional[Decimal] = None,
        exchange: str = "NSE",
        metadata: Optional[Dict[str, Any]] = None
    ) -> VirtualOrder:
        """
        Place a virtual order.
        
        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Order quantity
            order_type: MARKET, LIMIT, SL, SL-M
            price: Limit price (for limit orders)
            trigger_price: Trigger price (for SL orders)
            product_type: MIS, CNC, NRML
            strategy_id: Strategy that generated this order
            signal_id: Signal ID from strategy
            stop_loss: Stop loss price for the position
            target: Target price for the position
            trailing_sl_points: Points for trailing SL
            exchange: Exchange (NSE, BSE)
            metadata: Additional metadata
            
        Returns:
            VirtualOrder with execution status
        """
        order = VirtualOrder(
            order_id=self._generate_order_id(),
            symbol=symbol,
            exchange=exchange,
            side=side,
            order_type=order_type,
            product_type=product_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            strategy_id=strategy_id,
            signal_id=signal_id,
            metadata=metadata or {}
        )
        
        self.orders[order.order_id] = order
        self._stats["orders_placed"] += 1
        
        # Validate order
        validation_result = await self._validate_order(order)
        if not validation_result["valid"]:
            order.status = OrderStatus.REJECTED
            order.reject_reason = validation_result["reason"]
            self._stats["orders_rejected"] += 1
            self.logger.warning(
                f"Order rejected: {order.order_id} - {order.reject_reason}"
            )
            return order
        
        # Simulate latency
        await asyncio.sleep(self.config.latency_ms / 1000.0)
        
        # Execute based on order type
        if order_type == OrderType.MARKET:
            await self._execute_market_order(
                order,
                stop_loss=stop_loss,
                target=target,
                trailing_sl_points=trailing_sl_points
            )
        elif order_type == OrderType.LIMIT:
            # Add to pending orders
            order.status = OrderStatus.OPEN
            self.pending_orders[order.order_id] = order
            self.logger.info(f"Limit order placed: {order.order_id} @ {price}")
        elif order_type in [OrderType.STOP_LOSS, OrderType.STOP_LOSS_MARKET]:
            order.status = OrderStatus.OPEN
            self.pending_orders[order.order_id] = order
            self.logger.info(
                f"SL order placed: {order.order_id} trigger @ {trigger_price}"
            )
        
        return order
    
    async def _validate_order(
        self,
        order: VirtualOrder
    ) -> Dict[str, Any]:
        """Validate order against risk rules."""
        # Check if we have a price
        if order.order_type == OrderType.MARKET:
            price = self._price_cache.get(order.symbol)
            if not price:
                return {
                    "valid": False,
                    "reason": f"No price available for {order.symbol}"
                }
        else:
            price = order.price or order.trigger_price
        
        if not price:
            return {"valid": False, "reason": "Price not specified"}
        
        # Check order value
        order_value = price * order.quantity
        if order_value > self.config.max_order_value:
            return {
                "valid": False,
                "reason": f"Order value {order_value} exceeds max {self.config.max_order_value}"
            }
        
        # Check position limit
        if len(self.positions) >= self.config.max_positions:
            if order.symbol not in self.positions or \
               order.side != self.positions[order.symbol].side:
                return {
                    "valid": False,
                    "reason": f"Max positions ({self.config.max_positions}) reached"
                }
        
        # Check available capital
        if order.side == OrderSide.BUY:
            if order_value > self.available_capital:
                return {
                    "valid": False,
                    "reason": f"Insufficient capital. Required: {order_value}, Available: {self.available_capital}"
                }
        
        return {"valid": True, "reason": ""}
    
    async def _execute_market_order(
        self,
        order: VirtualOrder,
        stop_loss: Optional[Decimal] = None,
        target: Optional[Decimal] = None,
        trailing_sl_points: Optional[Decimal] = None
    ) -> None:
        """Execute a market order immediately."""
        # Get current price
        base_price = self._price_cache.get(order.symbol)
        if not base_price:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "No market price available"
            self._stats["orders_rejected"] += 1
            return
        
        # Apply slippage
        slippage = self._calculate_slippage(base_price, order.side)
        executed_price = base_price + slippage
        
        # Calculate commission
        commission = self._calculate_commission(executed_price, order.quantity)
        
        # Update order
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.average_fill_price = executed_price
        order.slippage = slippage
        order.commission = commission
        order.filled_at = datetime.now(ZoneInfo("Asia/Kolkata"))
        order.updated_at = order.filled_at
        
        self._stats["orders_filled"] += 1
        self._stats["total_commission"] += commission
        self._stats["total_slippage"] += abs(slippage * order.quantity)
        
        self.logger.info(
            f"Order filled: {order.order_id} {order.side.value} "
            f"{order.quantity} {order.symbol} @ {executed_price:.2f} "
            f"(slippage: {slippage:.2f})"
        )
        
        # Update position
        await self._update_position_from_order(
            order,
            stop_loss=stop_loss,
            target=target,
            trailing_sl_points=trailing_sl_points
        )
    
    async def _update_position_from_order(
        self,
        order: VirtualOrder,
        stop_loss: Optional[Decimal] = None,
        target: Optional[Decimal] = None,
        trailing_sl_points: Optional[Decimal] = None
    ) -> None:
        """Update or create position based on filled order."""
        symbol = order.symbol
        
        if symbol in self.positions:
            position = self.positions[symbol]
            
            if order.side == position.side:
                # Adding to existing position - average price
                total_qty = position.quantity + order.filled_quantity
                total_value = (
                    position.average_price * position.quantity +
                    order.average_fill_price * order.filled_quantity
                )
                position.quantity = total_qty
                position.average_price = total_value / total_qty
            else:
                # Reducing or closing position
                if order.filled_quantity >= position.quantity:
                    # Close position
                    await self._close_position(
                        position,
                        order,
                        "MANUAL"
                    )
                    return
                else:
                    # Partial close
                    position.quantity -= order.filled_quantity
                    # Record partial trade
                    # TODO: Implement partial close logic
        else:
            # New position
            position = VirtualPosition(
                position_id=self._generate_position_id(),
                symbol=symbol,
                exchange=order.exchange,
                side=order.side,
                quantity=order.filled_quantity,
                average_price=order.average_fill_price,
                current_price=order.average_fill_price,
                stop_loss=stop_loss,
                target=target,
                trailing_sl=trailing_sl_points is not None,
                trailing_sl_points=trailing_sl_points,
                highest_price=order.average_fill_price,
                lowest_price=order.average_fill_price,
                product_type=order.product_type,
                strategy_id=order.strategy_id,
                entry_order_id=order.order_id
            )
            self.positions[symbol] = position
            
            # Update available capital
            margin_used = order.average_fill_price * order.filled_quantity
            self.available_capital -= margin_used
            self.used_margin += margin_used
            
            self.logger.info(
                f"New position opened: {symbol} {order.side.value} "
                f"{order.filled_quantity} @ {order.average_fill_price:.2f} "
                f"SL: {stop_loss} Target: {target}"
            )
    
    async def _exit_position(
        self,
        symbol: str,
        reason: str,
        exit_price: Optional[Decimal] = None
    ) -> Optional[VirtualTrade]:
        """Exit an existing position."""
        if symbol not in self.positions:
            self.logger.warning(f"No position to exit for {symbol}")
            return None
        
        position = self.positions[symbol]
        
        # Get exit price
        if exit_price is None:
            exit_price = self._price_cache.get(symbol, position.current_price)
        
        # Place exit order
        exit_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY
        
        exit_order = await self.place_order(
            symbol=symbol,
            side=exit_side,
            quantity=position.quantity,
            order_type=OrderType.MARKET,
            product_type=position.product_type,
            strategy_id=position.strategy_id,
            exchange=position.exchange,
            metadata={"exit_reason": reason}
        )
        
        if exit_order.status == OrderStatus.FILLED:
            return await self._close_position(position, exit_order, reason)
        
        return None
    
    async def _close_position(
        self,
        position: VirtualPosition,
        exit_order: VirtualOrder,
        reason: str
    ) -> VirtualTrade:
        """Close position and record trade."""
        # Calculate P&L
        if position.side == OrderSide.BUY:
            gross_pnl = (exit_order.average_fill_price - position.average_price) * position.quantity
        else:
            gross_pnl = (position.average_price - exit_order.average_fill_price) * position.quantity
        
        # Get entry order commission
        entry_order = self.orders.get(position.entry_order_id)
        entry_commission = entry_order.commission if entry_order else Decimal("0")
        
        total_commission = entry_commission + exit_order.commission
        total_slippage = abs(exit_order.slippage * position.quantity)
        
        net_pnl = gross_pnl - total_commission
        pnl_percent = (net_pnl / (position.average_price * position.quantity)) * 100
        
        # Calculate holding period
        holding_minutes = int(
            (exit_order.filled_at - position.entry_time).total_seconds() / 60
        )
        
        # Create trade record
        trade = VirtualTrade(
            trade_id=self._generate_trade_id(),
            order_id=exit_order.order_id,
            position_id=position.position_id,
            symbol=position.symbol,
            exchange=position.exchange,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.average_price,
            exit_price=exit_order.average_fill_price,
            entry_time=position.entry_time,
            exit_time=exit_order.filled_at,
            gross_pnl=gross_pnl,
            commission=total_commission,
            slippage=total_slippage,
            net_pnl=net_pnl,
            pnl_percent=pnl_percent,
            strategy_id=position.strategy_id,
            exit_reason=reason,
            holding_period_minutes=holding_minutes,
            metadata={
                "stop_loss": float(position.stop_loss) if position.stop_loss else None,
                "target": float(position.target) if position.target else None,
                "trailing_sl": position.trailing_sl
            }
        )
        
        self.trades.append(trade)
        self._stats["trades_completed"] += 1
        self._stats["total_pnl"] += net_pnl
        
        if net_pnl > 0:
            self._stats["winning_trades"] += 1
        else:
            self._stats["losing_trades"] += 1
        
        # Update capital
        margin_released = position.average_price * position.quantity
        self.available_capital += margin_released + net_pnl
        self.used_margin -= margin_released
        self.capital += net_pnl
        
        # Remove position
        del self.positions[position.symbol]
        
        self.logger.info(
            f"Position closed: {position.symbol} "
            f"P&L: ₹{net_pnl:,.2f} ({pnl_percent:.2f}%) "
            f"Reason: {reason}"
        )
        
        # Publish trade event
        if self.event_bus:
            await self._publish_trade_event(trade)
        
        return trade
    
    async def _publish_trade_event(self, trade: VirtualTrade) -> None:
        """Publish trade event to event bus."""
        if not self.event_bus:
            return
        
        trade_data = {
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "side": trade.side.value,
            "quantity": trade.quantity,
            "entry_price": float(trade.entry_price),
            "exit_price": float(trade.exit_price),
            "net_pnl": float(trade.net_pnl),
            "pnl_percent": float(trade.pnl_percent),
            "exit_reason": trade.exit_reason,
            "strategy_id": trade.strategy_id,
            "timestamp": trade.exit_time.isoformat()
        }
        
        await self.event_bus.publish("paper_trade", trade_data)
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if order_id in self.pending_orders:
            order = self.pending_orders[order_id]
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now(ZoneInfo("Asia/Kolkata"))
            del self.pending_orders[order_id]
            self._stats["orders_cancelled"] += 1
            self.logger.info(f"Order cancelled: {order_id}")
            return True
        return False
    
    async def modify_order(
        self,
        order_id: str,
        price: Optional[Decimal] = None,
        trigger_price: Optional[Decimal] = None,
        quantity: Optional[int] = None
    ) -> Optional[VirtualOrder]:
        """Modify a pending order."""
        if order_id not in self.pending_orders:
            return None
        
        order = self.pending_orders[order_id]
        
        if price is not None:
            order.price = price
        if trigger_price is not None:
            order.trigger_price = trigger_price
        if quantity is not None:
            order.quantity = quantity
        
        order.updated_at = datetime.now(ZoneInfo("Asia/Kolkata"))
        self.logger.info(f"Order modified: {order_id}")
        
        return order
    
    async def modify_position_sl(
        self,
        symbol: str,
        new_sl: Decimal
    ) -> bool:
        """Modify stop loss for a position."""
        if symbol not in self.positions:
            return False
        
        self.positions[symbol].stop_loss = new_sl
        self.logger.info(f"SL modified for {symbol}: {new_sl}")
        return True
    
    async def modify_position_target(
        self,
        symbol: str,
        new_target: Decimal
    ) -> bool:
        """Modify target for a position."""
        if symbol not in self.positions:
            return False
        
        self.positions[symbol].target = new_target
        self.logger.info(f"Target modified for {symbol}: {new_target}")
        return True
    
    def update_price(self, symbol: str, price: Decimal) -> None:
        """Manually update price for a symbol."""
        self._price_cache[symbol] = price
        if symbol in self.positions:
            self.positions[symbol].update_price(price)
    
    def get_position(self, symbol: str) -> Optional[VirtualPosition]:
        """Get position for a symbol."""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> List[VirtualPosition]:
        """Get all open positions."""
        return list(self.positions.values())
    
    def get_order(self, order_id: str) -> Optional[VirtualOrder]:
        """Get order by ID."""
        return self.orders.get(order_id)
    
    def get_all_orders(self) -> List[VirtualOrder]:
        """Get all orders."""
        return list(self.orders.values())
    
    def get_pending_orders(self) -> List[VirtualOrder]:
        """Get all pending orders."""
        return list(self.pending_orders.values())
    
    def get_trades(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        strategy_id: Optional[str] = None
    ) -> List[VirtualTrade]:
        """Get trades with optional filters."""
        trades = self.trades
        
        if start_date:
            trades = [t for t in trades if t.entry_time >= start_date]
        if end_date:
            trades = [t for t in trades if t.exit_time <= end_date]
        if strategy_id:
            trades = [t for t in trades if t.strategy_id == strategy_id]
        
        return trades
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary."""
        total_unrealized = sum(
            p.unrealized_pnl for p in self.positions.values()
        )
        total_realized = self._stats["total_pnl"]
        
        return {
            "initial_capital": float(self.config.initial_capital),
            "current_capital": float(self.capital),
            "available_capital": float(self.available_capital),
            "used_margin": float(self.used_margin),
            "unrealized_pnl": float(total_unrealized),
            "realized_pnl": float(total_realized),
            "total_pnl": float(total_realized + total_unrealized),
            "total_return_percent": float(
                ((self.capital - self.config.initial_capital) / 
                 self.config.initial_capital) * 100
            ),
            "open_positions": len(self.positions),
            "total_trades": len(self.trades),
            "positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "quantity": p.quantity,
                    "avg_price": float(p.average_price),
                    "current_price": float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pnl),
                    "stop_loss": float(p.stop_loss) if p.stop_loss else None,
                    "target": float(p.target) if p.target else None
                }
                for p in self.positions.values()
            ]
        }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics."""
        if not self.trades:
            return {
                "total_trades": 0,
                "message": "No trades completed yet"
            }
        
        winning_trades = [t for t in self.trades if t.net_pnl > 0]
        losing_trades = [t for t in self.trades if t.net_pnl <= 0]
        
        total_pnl = sum(t.net_pnl for t in self.trades)
        gross_profit = sum(t.net_pnl for t in winning_trades)
        gross_loss = abs(sum(t.net_pnl for t in losing_trades))
        
        avg_win = (
            sum(t.net_pnl for t in winning_trades) / len(winning_trades)
            if winning_trades else Decimal("0")
        )
        avg_loss = (
            abs(sum(t.net_pnl for t in losing_trades)) / len(losing_trades)
            if losing_trades else Decimal("0")
        )
        
        profit_factor = (
            float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        )
        
        # Calculate Sharpe Ratio (simplified)
        if len(self.trades) > 1:
            import statistics
            returns = [float(t.pnl_percent) for t in self.trades]
            avg_return = statistics.mean(returns)
            std_return = statistics.stdev(returns)
            sharpe = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0
        else:
            sharpe = 0
        
        # Calculate max drawdown
        equity_curve = [float(self.config.initial_capital)]
        for trade in self.trades:
            equity_curve.append(equity_curve[-1] + float(trade.net_pnl))
        
        peak = equity_curve[0]
        max_drawdown = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak * 100
            max_drawdown = max(max_drawdown, drawdown)
        
        return {
            "total_trades": len(self.trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(len(winning_trades) / len(self.trades) * 100, 2),
            "total_pnl": float(total_pnl),
            "total_return_percent": float(
                (total_pnl / self.config.initial_capital) * 100
            ),
            "gross_profit": float(gross_profit),
            "gross_loss": float(gross_loss),
            "profit_factor": round(profit_factor, 2),
            "avg_win": float(avg_win),
            "avg_loss": float(avg_loss),
            "avg_win_loss_ratio": round(
                float(avg_win / avg_loss) if avg_loss > 0 else 0, 2
            ),
            "max_drawdown_percent": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "total_commission": float(self._stats["total_commission"]),
            "total_slippage": float(self._stats["total_slippage"]),
            "avg_holding_minutes": round(
                sum(t.holding_period_minutes for t in self.trades) / len(self.trades), 1
            ),
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            "running": self._running,
            "orders_placed": self._stats["orders_placed"],
            "orders_filled": self._stats["orders_filled"],
            "orders_rejected": self._stats["orders_rejected"],
            "orders_cancelled": self._stats["orders_cancelled"],
            "trades_completed": self._stats["trades_completed"],
            "winning_trades": self._stats["winning_trades"],
            "losing_trades": self._stats["losing_trades"],
            "total_pnl": float(self._stats["total_pnl"]),
            "total_commission": float(self._stats["total_commission"]),
            "total_slippage": float(self._stats["total_slippage"]),
        }
    
    async def execute_signal(self, signal: 'Signal') -> Optional[VirtualOrder]:
        """
        Execute a trading signal from the strategy engine.
        
        This is the main integration point with the strategy engine.
        Converts signals to orders and executes them.
        """
        from app.services.strategy_engine import SignalType
        
        # Determine order side from signal type
        if signal.signal_type in [SignalType.LONG_ENTRY]:
            side = OrderSide.BUY
        elif signal.signal_type in [SignalType.SHORT_ENTRY]:
            side = OrderSide.SELL
        elif signal.signal_type in [SignalType.LONG_EXIT, SignalType.SHORT_EXIT]:
            # Handle exit signals
            if signal.symbol in self.positions:
                await self._exit_position(
                    signal.symbol,
                    "SIGNAL_EXIT",
                    exit_price=signal.entry_price
                )
            return None
        else:
            self.logger.warning(f"Unknown signal type: {signal.signal_type}")
            return None
        
        # Calculate quantity based on capital allocation
        allocation = self.available_capital * Decimal(str(signal.quantity_pct / 100))
        quantity = int(allocation / signal.entry_price)
        
        if quantity <= 0:
            self.logger.warning(
                f"Insufficient allocation for {signal.symbol}: {allocation}"
            )
            return None
        
        # Calculate trailing SL points if applicable
        trailing_points = None
        if signal.stop_loss and signal.entry_price:
            trailing_points = abs(signal.entry_price - signal.stop_loss)
        
        # Place the order
        order = await self.place_order(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            product_type=ProductType.MIS,  # Default to intraday
            strategy_id=signal.strategy_id,
            signal_id=signal.signal_id,
            stop_loss=signal.stop_loss,
            target=signal.target_price,
            trailing_sl_points=trailing_points if self.config.enable_trailing_sl else None,
            exchange=signal.exchange,
            metadata={
                "signal_strength": signal.strength.value if hasattr(signal.strength, 'value') else str(signal.strength),
                "reason": signal.reason,
                "indicators": signal.indicators
            }
        )
        
        return order


# Factory function
def create_paper_trading_engine(
    initial_capital: Decimal = Decimal("100000"),
    event_bus: Optional[EventBus] = None
) -> PaperTradingEngine:
    """Create and configure paper trading engine."""
    config = PaperTradingConfig(initial_capital=initial_capital)
    engine = PaperTradingEngine(config=config, event_bus=event_bus)
    return engine
