"""
Order Management System (OMS)

Complete order lifecycle management:
- Order creation and validation
- Order routing to brokers
- Order status tracking
- Fill management
- Order modification and cancellation
- Paper trading mode support

Order Flow:
Signal → Risk Check → Create Order → Route to Broker → Track Status → Handle Fill
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol
from zoneinfo import ZoneInfo

from app.core.events import EventBus


class OrderType(str, Enum):
    """Order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LOSS_MARKET = "stop_loss_market"


class OrderSide(str, Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Order lifecycle status."""
    PENDING = "pending"          # Created, not yet sent
    SUBMITTED = "submitted"      # Sent to broker
    OPEN = "open"               # Active in market
    PARTIAL_FILL = "partial"    # Partially filled
    FILLED = "filled"           # Completely filled
    CANCELLED = "cancelled"     # Cancelled by user
    REJECTED = "rejected"       # Rejected by broker
    EXPIRED = "expired"         # Expired (day order)


class ProductType(str, Enum):
    """Product type for Indian markets."""
    INTRADAY = "intraday"       # MIS - Margin Intraday Square-off
    DELIVERY = "delivery"       # CNC - Cash and Carry
    NORMAL = "normal"           # NRML - Normal (F&O)


@dataclass
class Order:
    """Represents a trading order."""
    order_id: str
    
    # Instrument details
    symbol: str
    exchange: str
    
    # Order details
    order_type: OrderType
    side: OrderSide
    quantity: int
    
    # Pricing
    price: Optional[Decimal] = None              # For limit orders
    trigger_price: Optional[Decimal] = None      # For stop orders
    
    # Product
    product_type: ProductType = ProductType.INTRADAY
    
    # Status
    status: OrderStatus = OrderStatus.PENDING
    
    # Fill info
    filled_quantity: int = 0
    average_fill_price: Decimal = Decimal("0")
    
    # Broker info
    broker_order_id: Optional[str] = None
    broker_name: Optional[str] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Kolkata")))
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    
    # Linking
    position_id: Optional[str] = None
    signal_id: Optional[str] = None
    parent_order_id: Optional[str] = None  # For bracket/cover orders
    
    # Error info
    rejection_reason: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_complete(self) -> bool:
        """Check if order is in terminal state."""
        return self.status in [
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED
        ]
    
    def get_pending_quantity(self) -> int:
        """Get remaining quantity to fill."""
        return self.quantity - self.filled_quantity


class BrokerAdapter(Protocol):
    """Protocol for broker adapters."""
    
    async def place_order(self, order: Order) -> str:
        """Place order with broker, return broker order ID."""
        ...
    
    async def modify_order(
        self,
        broker_order_id: str,
        quantity: Optional[int] = None,
        price: Optional[Decimal] = None,
        trigger_price: Optional[Decimal] = None
    ) -> bool:
        """Modify existing order."""
        ...
    
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel order."""
        ...
    
    async def get_order_status(self, broker_order_id: str) -> Dict[str, Any]:
        """Get order status from broker."""
        ...


class PaperBrokerAdapter:
    """
    Paper trading broker adapter for simulation.
    
    Simulates order fills with realistic slippage and delays.
    """
    
    def __init__(self, slippage_pct: float = 0.01, fill_delay_ms: int = 100):
        self.slippage_pct = slippage_pct
        self.fill_delay_ms = fill_delay_ms
        self.logger = logging.getLogger(__name__)
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._order_counter = 0
    
    async def place_order(self, order: Order) -> str:
        """Simulate order placement."""
        self._order_counter += 1
        broker_order_id = f"PAPER-{self._order_counter:06d}"
        
        # Store order for tracking
        self._orders[broker_order_id] = {
            "order": order,
            "status": "submitted",
            "submitted_at": datetime.now(ZoneInfo("Asia/Kolkata"))
        }
        
        self.logger.info(f"Paper order placed: {broker_order_id} - {order.side.value} {order.quantity} {order.symbol}")
        
        return broker_order_id
    
    async def simulate_fill(
        self,
        broker_order_id: str,
        market_price: Decimal
    ) -> Dict[str, Any]:
        """Simulate order fill with slippage."""
        if broker_order_id not in self._orders:
            return {"status": "error", "message": "Order not found"}
        
        order_data = self._orders[broker_order_id]
        order = order_data["order"]
        
        # Add simulated delay
        await asyncio.sleep(self.fill_delay_ms / 1000)
        
        # Calculate fill price with slippage
        slippage = market_price * Decimal(str(self.slippage_pct)) / Decimal("100")
        
        if order.side == OrderSide.BUY:
            fill_price = market_price + slippage  # Pay more
        else:
            fill_price = market_price - slippage  # Receive less
        
        fill_price = fill_price.quantize(Decimal("0.05"))
        
        order_data["status"] = "filled"
        order_data["fill_price"] = fill_price
        order_data["filled_at"] = datetime.now(ZoneInfo("Asia/Kolkata"))
        
        self.logger.info(f"Paper order filled: {broker_order_id} @ {fill_price}")
        
        return {
            "status": "filled",
            "fill_price": float(fill_price),
            "filled_quantity": order.quantity,
            "filled_at": order_data["filled_at"].isoformat()
        }
    
    async def modify_order(
        self,
        broker_order_id: str,
        quantity: Optional[int] = None,
        price: Optional[Decimal] = None,
        trigger_price: Optional[Decimal] = None
    ) -> bool:
        """Simulate order modification."""
        if broker_order_id not in self._orders:
            return False
        
        order_data = self._orders[broker_order_id]
        if order_data["status"] != "submitted":
            return False
        
        self.logger.info(f"Paper order modified: {broker_order_id}")
        return True
    
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Simulate order cancellation."""
        if broker_order_id not in self._orders:
            return False
        
        order_data = self._orders[broker_order_id]
        if order_data["status"] in ["filled", "cancelled"]:
            return False
        
        order_data["status"] = "cancelled"
        self.logger.info(f"Paper order cancelled: {broker_order_id}")
        return True
    
    async def get_order_status(self, broker_order_id: str) -> Dict[str, Any]:
        """Get simulated order status."""
        if broker_order_id not in self._orders:
            return {"status": "error", "message": "Order not found"}
        
        order_data = self._orders[broker_order_id]
        return {
            "broker_order_id": broker_order_id,
            "status": order_data["status"],
            "fill_price": order_data.get("fill_price"),
            "filled_at": order_data.get("filled_at")
        }


class OrderValidationError(Exception):
    """Raised when order validation fails."""
    pass


class OrderManager:
    """
    Order Management System.
    
    Responsibilities:
    - Order creation with validation
    - Order routing to appropriate broker
    - Order status tracking and updates
    - Fill management and position linking
    - Support for paper trading mode
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        broker_adapter: Optional[BrokerAdapter] = None,
        paper_trading: bool = True
    ):
        self.event_bus = event_bus
        self.paper_trading = paper_trading
        self.logger = logging.getLogger(__name__)
        self._running = False
        
        # Broker adapter
        if paper_trading:
            self._paper_adapter = PaperBrokerAdapter()
            self.broker_adapter = self._paper_adapter
        else:
            self.broker_adapter = broker_adapter
            self._paper_adapter = None
        
        # Order storage
        self._orders: Dict[str, Order] = {}
        self._broker_order_map: Dict[str, str] = {}  # broker_order_id -> order_id
        self._position_orders: Dict[str, List[str]] = {}  # position_id -> [order_ids]
        
        # Order counter
        self._order_counter = 0
        
        # IST timezone
        self._tz = ZoneInfo("Asia/Kolkata")
        
        # Status polling task
        self._status_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the order manager."""
        if self._running:
            return
        
        self._running = True
        self.logger.info(f"Starting order manager (paper_trading={self.paper_trading})...")
        
        # Subscribe to events
        await self.event_bus.subscribe(
            "exit_request",
            self._on_exit_request,
            consumer_group="order_manager"
        )
        
        await self.event_bus.subscribe(
            "signal_approved",
            self._on_signal_approved,
            consumer_group="order_manager"
        )
        
        # Start status polling (for real broker)
        if not self.paper_trading:
            self._status_task = asyncio.create_task(self._poll_order_status())
        
        self.logger.info("Order manager started")
    
    async def stop(self) -> None:
        """Stop the order manager."""
        self._running = False
        
        if self._status_task:
            self._status_task.cancel()
            try:
                await self._status_task
            except asyncio.CancelledError:
                pass
        
        await self.event_bus.unsubscribe("exit_request", "order_manager")
        await self.event_bus.unsubscribe("signal_approved", "order_manager")
        
        self.logger.info("Order manager stopped")
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        self._order_counter += 1
        timestamp = datetime.now(self._tz).strftime("%Y%m%d")
        return f"ORD-{timestamp}-{self._order_counter:06d}"
    
    async def create_order(
        self,
        symbol: str,
        exchange: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[Decimal] = None,
        trigger_price: Optional[Decimal] = None,
        product_type: ProductType = ProductType.INTRADAY,
        position_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Order:
        """
        Create and validate a new order.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange (NSE, NFO, etc.)
            side: Buy or Sell
            quantity: Order quantity
            order_type: Market, Limit, Stop Loss
            price: Limit price (for limit orders)
            trigger_price: Trigger price (for stop orders)
            product_type: Intraday or Delivery
            position_id: Linked position ID
            signal_id: Originating signal ID
            metadata: Additional metadata
            
        Returns:
            Created Order object
        """
        # Validate order
        self._validate_order(
            symbol=symbol,
            quantity=quantity,
            order_type=order_type,
            price=price,
            trigger_price=trigger_price
        )
        
        order_id = self._generate_order_id()
        
        order = Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            product_type=product_type,
            position_id=position_id,
            signal_id=signal_id,
            metadata=metadata or {}
        )
        
        self._orders[order_id] = order
        
        # Index by position
        if position_id:
            if position_id not in self._position_orders:
                self._position_orders[position_id] = []
            self._position_orders[position_id].append(order_id)
        
        self.logger.info(
            f"Order created: {order_id} - {side.value} {quantity} {symbol} "
            f"({order_type.value})"
        )
        
        return order
    
    def _validate_order(
        self,
        symbol: str,
        quantity: int,
        order_type: OrderType,
        price: Optional[Decimal],
        trigger_price: Optional[Decimal]
    ) -> None:
        """Validate order parameters."""
        if not symbol:
            raise OrderValidationError("Symbol is required")
        
        if quantity <= 0:
            raise OrderValidationError("Quantity must be positive")
        
        if order_type == OrderType.LIMIT and price is None:
            raise OrderValidationError("Price required for limit orders")
        
        if order_type in [OrderType.STOP_LOSS, OrderType.STOP_LOSS_MARKET]:
            if trigger_price is None:
                raise OrderValidationError("Trigger price required for stop orders")
    
    async def submit_order(self, order_id: str) -> bool:
        """
        Submit order to broker.
        
        Args:
            order_id: Order ID to submit
            
        Returns:
            True if submission successful
        """
        order = self._orders.get(order_id)
        if not order:
            self.logger.error(f"Order not found: {order_id}")
            return False
        
        if order.status != OrderStatus.PENDING:
            self.logger.error(f"Order not in pending state: {order_id}")
            return False
        
        try:
            # Send to broker
            broker_order_id = await self.broker_adapter.place_order(order)
            
            order.broker_order_id = broker_order_id
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now(self._tz)
            order.broker_name = "paper" if self.paper_trading else "fyers"
            
            self._broker_order_map[broker_order_id] = order_id
            
            self.logger.info(f"Order submitted: {order_id} -> {broker_order_id}")
            
            # Publish order submitted event
            await self._publish_order_event(order, "submitted")
            
            # For paper trading, simulate immediate fill for market orders
            if self.paper_trading and order.order_type == OrderType.MARKET:
                await self._simulate_paper_fill(order)
            
            return True
            
        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = str(e)
            self.logger.error(f"Order submission failed: {order_id} - {e}")
            await self._publish_order_event(order, "rejected")
            return False
    
    async def _simulate_paper_fill(self, order: Order) -> None:
        """Simulate fill for paper trading."""
        if not self._paper_adapter:
            return
        
        # Get current market price (use order price or a default)
        market_price = order.price or Decimal("100")  # Would normally fetch from market
        
        # Simulate fill
        fill_result = await self._paper_adapter.simulate_fill(
            order.broker_order_id,
            market_price
        )
        
        if fill_result.get("status") == "filled":
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.average_fill_price = Decimal(str(fill_result["fill_price"]))
            order.filled_at = datetime.now(self._tz)
            
            await self._publish_order_event(order, "filled")
            await self._publish_fill_event(order)
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[Decimal] = None,
        trigger_price: Optional[Decimal] = None
    ) -> bool:
        """
        Modify an existing order.
        
        Args:
            order_id: Order to modify
            quantity: New quantity (optional)
            price: New price (optional)
            trigger_price: New trigger price (optional)
            
        Returns:
            True if modification successful
        """
        order = self._orders.get(order_id)
        if not order or not order.broker_order_id:
            return False
        
        if order.is_complete():
            self.logger.error(f"Cannot modify completed order: {order_id}")
            return False
        
        try:
            success = await self.broker_adapter.modify_order(
                order.broker_order_id,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price
            )
            
            if success:
                if quantity:
                    order.quantity = quantity
                if price:
                    order.price = price
                if trigger_price:
                    order.trigger_price = trigger_price
                
                self.logger.info(f"Order modified: {order_id}")
                await self._publish_order_event(order, "modified")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Order modification failed: {order_id} - {e}")
            return False
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order to cancel
            
        Returns:
            True if cancellation successful
        """
        order = self._orders.get(order_id)
        if not order or not order.broker_order_id:
            return False
        
        if order.is_complete():
            self.logger.error(f"Cannot cancel completed order: {order_id}")
            return False
        
        try:
            success = await self.broker_adapter.cancel_order(order.broker_order_id)
            
            if success:
                order.status = OrderStatus.CANCELLED
                self.logger.info(f"Order cancelled: {order_id}")
                await self._publish_order_event(order, "cancelled")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Order cancellation failed: {order_id} - {e}")
            return False
    
    async def _on_signal_approved(self, event: Dict[str, Any]) -> None:
        """Handle approved signal - create entry order."""
        try:
            signal = event.get("signal", {})
            quantity = event.get("approved_quantity", 0)
            position_id = event.get("position_id")
            
            if quantity <= 0:
                return
            
            symbol = signal.get("symbol", "")
            exchange = signal.get("exchange", "NSE")
            signal_type = signal.get("signal_type", "")
            
            # Determine order side
            side = (
                OrderSide.BUY 
                if signal_type in ["long_entry", "LONG_ENTRY"]
                else OrderSide.SELL
            )
            
            # Create entry order
            order = await self.create_order(
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                order_type=OrderType.MARKET,
                product_type=ProductType.INTRADAY,
                position_id=position_id,
                signal_id=signal.get("signal_id"),
                metadata={
                    "entry_type": "strategy_signal",
                    "strategy_id": signal.get("strategy_id"),
                    "indicators": signal.get("indicators", {})
                }
            )
            
            # Submit order
            await self.submit_order(order.order_id)
            
        except Exception as e:
            self.logger.error(f"Error processing approved signal: {e}")
    
    async def _on_exit_request(self, event: Dict[str, Any]) -> None:
        """Handle exit request from position manager."""
        try:
            position_id = event.get("position_id")
            symbol = event.get("symbol", "")
            exchange = event.get("exchange", "NSE")
            side_str = event.get("side", "sell")
            quantity = event.get("quantity", 0)
            reason = event.get("reason", "")
            
            if quantity <= 0:
                return
            
            side = OrderSide.SELL if side_str == "sell" else OrderSide.BUY
            
            # Create exit order
            order = await self.create_order(
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                order_type=OrderType.MARKET,
                product_type=ProductType.INTRADAY,
                position_id=position_id,
                metadata={
                    "exit_type": "position_exit",
                    "exit_reason": reason
                }
            )
            
            # Submit order
            await self.submit_order(order.order_id)
            
        except Exception as e:
            self.logger.error(f"Error processing exit request: {e}")
    
    async def _poll_order_status(self) -> None:
        """Poll broker for order status updates."""
        while self._running:
            try:
                # Get open orders
                open_orders = [
                    o for o in self._orders.values()
                    if o.status in [OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIAL_FILL]
                    and o.broker_order_id
                ]
                
                for order in open_orders:
                    try:
                        status = await self.broker_adapter.get_order_status(
                            order.broker_order_id
                        )
                        await self._process_status_update(order, status)
                    except Exception as e:
                        self.logger.error(
                            f"Error polling status for {order.order_id}: {e}"
                        )
                
                # Poll every 2 seconds
                await asyncio.sleep(2)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in status polling: {e}")
                await asyncio.sleep(5)
    
    async def _process_status_update(
        self,
        order: Order,
        status: Dict[str, Any]
    ) -> None:
        """Process status update from broker."""
        broker_status = status.get("status", "").lower()
        
        if broker_status == "filled" and order.status != OrderStatus.FILLED:
            order.status = OrderStatus.FILLED
            order.filled_quantity = status.get("filled_quantity", order.quantity)
            order.average_fill_price = Decimal(str(status.get("fill_price", 0)))
            order.filled_at = datetime.now(self._tz)
            
            await self._publish_order_event(order, "filled")
            await self._publish_fill_event(order)
            
        elif broker_status == "rejected" and order.status != OrderStatus.REJECTED:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = status.get("message", "Unknown")
            await self._publish_order_event(order, "rejected")
            
        elif broker_status == "cancelled" and order.status != OrderStatus.CANCELLED:
            order.status = OrderStatus.CANCELLED
            await self._publish_order_event(order, "cancelled")
    
    async def _publish_order_event(self, order: Order, event_type: str) -> None:
        """Publish order status event."""
        await self.event_bus.publish("order_update", {
            "order_id": order.order_id,
            "broker_order_id": order.broker_order_id,
            "event_type": event_type,
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": order.quantity,
            "order_type": order.order_type.value,
            "status": order.status.value,
            "position_id": order.position_id,
            "timestamp": datetime.now(self._tz).isoformat()
        })
    
    async def _publish_fill_event(self, order: Order) -> None:
        """Publish order fill event for position manager."""
        # Determine if entry or exit based on metadata
        order_type = "entry"
        if order.metadata.get("exit_type"):
            order_type = "exit"
        
        await self.event_bus.publish("order_filled", {
            "order_id": order.order_id,
            "position_id": order.position_id,
            "order_type": order_type,
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": order.filled_quantity,
            "fill_price": float(order.average_fill_price),
            "timestamp": order.filled_at.isoformat() if order.filled_at else None
        })
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    def get_orders_by_position(self, position_id: str) -> List[Order]:
        """Get all orders for a position."""
        order_ids = self._position_orders.get(position_id, [])
        return [self._orders[oid] for oid in order_ids if oid in self._orders]
    
    def get_open_orders(self) -> List[Order]:
        """Get all open/pending orders."""
        return [
            o for o in self._orders.values()
            if o.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.OPEN]
        ]
    
    def get_all_orders(self) -> List[Order]:
        """Get all orders."""
        return list(self._orders.values())
    
    def get_order_summary(self) -> Dict[str, Any]:
        """Get order summary statistics."""
        all_orders = list(self._orders.values())
        
        return {
            "total_orders": len(all_orders),
            "pending": len([o for o in all_orders if o.status == OrderStatus.PENDING]),
            "submitted": len([o for o in all_orders if o.status == OrderStatus.SUBMITTED]),
            "filled": len([o for o in all_orders if o.status == OrderStatus.FILLED]),
            "cancelled": len([o for o in all_orders if o.status == OrderStatus.CANCELLED]),
            "rejected": len([o for o in all_orders if o.status == OrderStatus.REJECTED]),
            "paper_trading": self.paper_trading
        }


# Factory function
def create_order_manager(
    event_bus: EventBus,
    paper_trading: bool = True,
    broker_adapter: Optional[BrokerAdapter] = None
) -> OrderManager:
    """Create and configure order manager instance."""
    return OrderManager(
        event_bus=event_bus,
        broker_adapter=broker_adapter,
        paper_trading=paper_trading
    )
