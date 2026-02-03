"""
Unified Order Manager

Central order management system that:
- Routes orders to appropriate broker
- Manages positions across multiple brokers
- Provides unified view of portfolio
- Handles broker failover
- Tracks order lifecycle
- Aggregates P&L across brokers

Supported brokers:
- Fyers
- Upstox
- Zerodha
- Angel One
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Tuple
from collections import defaultdict

from app.brokers.base import BaseBroker
from app.schemas.broker import (
    OrderRequest, OrderResponse, Position, Quote,
    OrderType, OrderSide, ProductType
)
from app.db.models import OrderStatus

logger = logging.getLogger(__name__)


class BrokerType(str, Enum):
    """Supported broker types."""
    FYERS = "fyers"
    UPSTOX = "upstox"
    ZERODHA = "zerodha"
    ANGELONE = "angelone"
    PAPER = "paper"


class OrderRoutingStrategy(str, Enum):
    """Order routing strategies."""
    PRIMARY = "primary"           # Always use primary broker
    ROUND_ROBIN = "round_robin"   # Distribute orders
    BEST_PRICE = "best_price"     # Route to broker with best quote
    LOWEST_COST = "lowest_cost"   # Route to broker with lowest fees
    LOAD_BALANCE = "load_balance" # Balance by open order count


@dataclass
class BrokerConfig:
    """Configuration for a broker instance."""
    broker_type: BrokerType
    priority: int  # Lower = higher priority
    enabled: bool = True
    max_orders_per_day: int = 100
    max_order_value: float = 1000000
    allowed_exchanges: List[str] = field(default_factory=lambda: ["NSE", "BSE", "NFO"])
    allowed_products: List[str] = field(default_factory=lambda: ["MIS", "CNC", "NRML"])


@dataclass
class UnifiedPosition:
    """Unified position across brokers."""
    symbol: str
    exchange: str
    broker: BrokerType
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    unrealized_pnl: float
    realized_pnl: float
    product: str
    value: float
    
    @property
    def is_long(self) -> bool:
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        return self.quantity < 0


@dataclass
class UnifiedOrder:
    """Unified order across brokers."""
    unified_id: str  # Internal tracking ID
    broker: BrokerType
    broker_order_id: str
    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float
    trigger_price: float
    product: ProductType
    status: OrderStatus
    filled_quantity: int
    average_price: float
    placed_at: datetime
    updated_at: datetime
    message: str = ""
    tag: str = ""


@dataclass 
class BrokerStats:
    """Statistics for a broker."""
    broker: BrokerType
    orders_placed: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    orders_cancelled: int = 0
    total_turnover: float = 0
    total_pnl: float = 0
    avg_fill_time_ms: float = 0
    success_rate: float = 0


class UnifiedOrderManager:
    """
    Unified Order Management System.
    
    Provides a single interface to manage orders across multiple brokers.
    """
    
    def __init__(
        self,
        routing_strategy: OrderRoutingStrategy = OrderRoutingStrategy.PRIMARY,
        enable_failover: bool = True,
        max_retry_attempts: int = 3
    ):
        self.routing_strategy = routing_strategy
        self.enable_failover = enable_failover
        self.max_retry_attempts = max_retry_attempts
        
        # Broker instances
        self._brokers: Dict[BrokerType, BaseBroker] = {}
        self._broker_configs: Dict[BrokerType, BrokerConfig] = {}
        
        # Order tracking
        self._orders: Dict[str, UnifiedOrder] = {}
        self._order_counter = 0
        
        # Statistics
        self._broker_stats: Dict[BrokerType, BrokerStats] = {}
        
        # Callbacks
        self._order_callbacks: List[Callable] = []
        self._position_callbacks: List[Callable] = []
        
        # Cache
        self._quote_cache: Dict[str, Tuple[Quote, datetime]] = {}
        self._cache_ttl = timedelta(seconds=5)
    
    def register_broker(
        self,
        broker_type: BrokerType,
        broker: BaseBroker,
        config: Optional[BrokerConfig] = None
    ) -> None:
        """
        Register a broker instance.
        
        Args:
            broker_type: Type of broker
            broker: Broker instance
            config: Broker configuration (optional)
        """
        self._brokers[broker_type] = broker
        self._broker_configs[broker_type] = config or BrokerConfig(
            broker_type=broker_type,
            priority=len(self._brokers)
        )
        self._broker_stats[broker_type] = BrokerStats(broker=broker_type)
        
        logger.info(f"Registered broker: {broker_type.value}")
    
    def unregister_broker(self, broker_type: BrokerType) -> None:
        """Unregister a broker."""
        if broker_type in self._brokers:
            del self._brokers[broker_type]
            del self._broker_configs[broker_type]
            logger.info(f"Unregistered broker: {broker_type.value}")
    
    def get_active_brokers(self) -> List[BrokerType]:
        """Get list of active (enabled) brokers."""
        return [
            bt for bt, config in self._broker_configs.items()
            if config.enabled and bt in self._brokers
        ]
    
    def get_primary_broker(self) -> Optional[BrokerType]:
        """Get the primary (highest priority) broker."""
        active = self.get_active_brokers()
        if not active:
            return None
        
        # Sort by priority
        sorted_brokers = sorted(
            active,
            key=lambda bt: self._broker_configs[bt].priority
        )
        return sorted_brokers[0]
    
    async def place_order(
        self,
        order: OrderRequest,
        broker: Optional[BrokerType] = None,
        tag: str = ""
    ) -> UnifiedOrder:
        """
        Place an order through the unified manager.
        
        Args:
            order: Order request
            broker: Specific broker to use (optional)
            tag: Custom tag for tracking
            
        Returns:
            UnifiedOrder with status
        """
        # Select broker
        target_broker = broker or self._select_broker(order)
        
        if not target_broker:
            raise ValueError("No active broker available")
        
        # Generate unified ID
        self._order_counter += 1
        unified_id = f"UOM-{datetime.now().strftime('%Y%m%d')}-{self._order_counter:06d}"
        
        # Place order with retry and failover
        attempts = 0
        last_error = None
        brokers_tried = []
        
        while attempts < self.max_retry_attempts:
            attempts += 1
            
            if target_broker in brokers_tried:
                # Try next broker on failover
                if self.enable_failover:
                    target_broker = self._get_next_broker(brokers_tried)
                    if not target_broker:
                        break
                else:
                    break
            
            brokers_tried.append(target_broker)
            
            try:
                broker_instance = self._brokers[target_broker]
                response = await broker_instance.place_order(order)
                
                # Create unified order
                unified_order = UnifiedOrder(
                    unified_id=unified_id,
                    broker=target_broker,
                    broker_order_id=response.order_id,
                    symbol=order.symbol,
                    exchange=order.exchange,
                    side=order.side,
                    order_type=order.order_type,
                    quantity=order.quantity,
                    price=order.price or 0,
                    trigger_price=order.trigger_price or 0,
                    product=order.product,
                    status=response.status,
                    filled_quantity=response.filled_quantity or 0,
                    average_price=response.average_price or 0,
                    placed_at=datetime.now(),
                    updated_at=datetime.now(),
                    message=response.message,
                    tag=tag,
                )
                
                # Track order
                self._orders[unified_id] = unified_order
                
                # Update stats
                stats = self._broker_stats[target_broker]
                stats.orders_placed += 1
                if response.status == OrderStatus.FILLED:
                    stats.orders_filled += 1
                elif response.status == OrderStatus.REJECTED:
                    stats.orders_rejected += 1
                
                # Notify callbacks
                await self._notify_order_update(unified_order)
                
                logger.info(f"Order placed: {unified_id} via {target_broker.value}")
                return unified_order
                
            except Exception as e:
                last_error = e
                logger.error(f"Order placement failed on {target_broker.value}: {e}")
                
                # Try failover
                if self.enable_failover:
                    target_broker = self._get_next_broker(brokers_tried)
                    if target_broker:
                        logger.info(f"Failing over to {target_broker.value}")
                        continue
                break
        
        # All attempts failed
        raise Exception(f"Order placement failed after {attempts} attempts: {last_error}")
    
    async def modify_order(
        self,
        unified_id: str,
        price: Optional[float] = None,
        quantity: Optional[int] = None,
        trigger_price: Optional[float] = None
    ) -> UnifiedOrder:
        """
        Modify an existing order.
        
        Args:
            unified_id: Unified order ID
            price: New price (optional)
            quantity: New quantity (optional)
            trigger_price: New trigger price (optional)
            
        Returns:
            Updated UnifiedOrder
        """
        if unified_id not in self._orders:
            raise ValueError(f"Order not found: {unified_id}")
        
        order = self._orders[unified_id]
        broker_instance = self._brokers[order.broker]
        
        response = await broker_instance.modify_order(
            order_id=order.broker_order_id,
            price=price,
            quantity=quantity,
            trigger_price=trigger_price
        )
        
        # Update tracked order
        if price is not None:
            order.price = price
        if quantity is not None:
            order.quantity = quantity
        if trigger_price is not None:
            order.trigger_price = trigger_price
        
        order.status = response.status
        order.message = response.message
        order.updated_at = datetime.now()
        
        await self._notify_order_update(order)
        
        logger.info(f"Order modified: {unified_id}")
        return order
    
    async def cancel_order(self, unified_id: str) -> UnifiedOrder:
        """
        Cancel an order.
        
        Args:
            unified_id: Unified order ID
            
        Returns:
            Updated UnifiedOrder
        """
        if unified_id not in self._orders:
            raise ValueError(f"Order not found: {unified_id}")
        
        order = self._orders[unified_id]
        broker_instance = self._brokers[order.broker]
        
        response = await broker_instance.cancel_order(order.broker_order_id)
        
        order.status = response.status
        order.message = response.message
        order.updated_at = datetime.now()
        
        # Update stats
        if response.status == OrderStatus.CANCELLED:
            self._broker_stats[order.broker].orders_cancelled += 1
        
        await self._notify_order_update(order)
        
        logger.info(f"Order cancelled: {unified_id}")
        return order
    
    async def get_order_status(self, unified_id: str) -> UnifiedOrder:
        """
        Get current status of an order.
        
        Args:
            unified_id: Unified order ID
            
        Returns:
            Updated UnifiedOrder
        """
        if unified_id not in self._orders:
            raise ValueError(f"Order not found: {unified_id}")
        
        order = self._orders[unified_id]
        broker_instance = self._brokers[order.broker]
        
        response = await broker_instance.get_order_status(order.broker_order_id)
        
        order.status = response.status
        order.filled_quantity = response.filled_quantity or order.filled_quantity
        order.average_price = response.average_price or order.average_price
        order.message = response.message
        order.updated_at = datetime.now()
        
        return order
    
    async def get_all_orders(
        self,
        broker: Optional[BrokerType] = None,
        status: Optional[OrderStatus] = None
    ) -> List[UnifiedOrder]:
        """
        Get all tracked orders.
        
        Args:
            broker: Filter by broker (optional)
            status: Filter by status (optional)
            
        Returns:
            List of UnifiedOrder
        """
        orders = list(self._orders.values())
        
        if broker:
            orders = [o for o in orders if o.broker == broker]
        
        if status:
            orders = [o for o in orders if o.status == status]
        
        return sorted(orders, key=lambda o: o.placed_at, reverse=True)
    
    async def get_all_positions(
        self,
        broker: Optional[BrokerType] = None
    ) -> List[UnifiedPosition]:
        """
        Get all positions across brokers.
        
        Args:
            broker: Filter by broker (optional)
            
        Returns:
            List of UnifiedPosition
        """
        all_positions = []
        
        brokers_to_check = [broker] if broker else self.get_active_brokers()
        
        for bt in brokers_to_check:
            if bt not in self._brokers:
                continue
            
            try:
                broker_instance = self._brokers[bt]
                positions = await broker_instance.get_positions()
                
                for pos in positions:
                    all_positions.append(UnifiedPosition(
                        symbol=pos.symbol,
                        exchange=pos.exchange,
                        broker=bt,
                        quantity=pos.quantity,
                        average_price=pos.average_price,
                        last_price=pos.last_price,
                        pnl=pos.pnl,
                        unrealized_pnl=pos.unrealized_pnl,
                        realized_pnl=pos.realized_pnl,
                        product=pos.product,
                        value=pos.value,
                    ))
                    
            except Exception as e:
                logger.error(f"Failed to get positions from {bt.value}: {e}")
        
        return all_positions
    
    async def get_aggregated_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get positions aggregated by symbol across brokers.
        
        Returns:
            Dict mapping symbol to aggregated position data
        """
        positions = await self.get_all_positions()
        
        aggregated = defaultdict(lambda: {
            "symbol": "",
            "exchange": "",
            "total_quantity": 0,
            "weighted_avg_price": 0,
            "total_value": 0,
            "total_pnl": 0,
            "brokers": [],
            "positions": [],
        })
        
        for pos in positions:
            key = f"{pos.exchange}:{pos.symbol}"
            agg = aggregated[key]
            
            agg["symbol"] = pos.symbol
            agg["exchange"] = pos.exchange
            agg["total_quantity"] += pos.quantity
            agg["total_value"] += pos.value
            agg["total_pnl"] += pos.pnl
            
            if pos.broker.value not in agg["brokers"]:
                agg["brokers"].append(pos.broker.value)
            
            agg["positions"].append({
                "broker": pos.broker.value,
                "quantity": pos.quantity,
                "average_price": pos.average_price,
                "pnl": pos.pnl,
            })
        
        # Calculate weighted average price
        for key, agg in aggregated.items():
            if agg["total_quantity"] != 0:
                total_cost = sum(
                    p["quantity"] * p["average_price"]
                    for p in agg["positions"]
                )
                agg["weighted_avg_price"] = total_cost / agg["total_quantity"]
        
        return dict(aggregated)
    
    async def get_quote(
        self,
        symbol: str,
        exchange: str = "NSE",
        broker: Optional[BrokerType] = None
    ) -> Quote:
        """
        Get quote from broker(s).
        
        Args:
            symbol: Trading symbol
            exchange: Exchange
            broker: Specific broker (optional, uses primary if not specified)
            
        Returns:
            Quote object
        """
        cache_key = f"{exchange}:{symbol}"
        
        # Check cache
        if cache_key in self._quote_cache:
            cached_quote, cached_time = self._quote_cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                return cached_quote
        
        target_broker = broker or self.get_primary_broker()
        
        if not target_broker:
            raise ValueError("No active broker available")
        
        broker_instance = self._brokers[target_broker]
        quote = await broker_instance.get_quote(symbol, exchange)
        
        # Update cache
        self._quote_cache[cache_key] = (quote, datetime.now())
        
        return quote
    
    async def get_best_quote(
        self,
        symbol: str,
        exchange: str = "NSE"
    ) -> Tuple[Quote, BrokerType]:
        """
        Get best quote across all brokers.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange
            
        Returns:
            Tuple of (best Quote, broker type)
        """
        quotes = []
        
        for bt in self.get_active_brokers():
            try:
                broker_instance = self._brokers[bt]
                quote = await broker_instance.get_quote(symbol, exchange)
                if quote.last_price > 0:
                    quotes.append((quote, bt))
            except Exception as e:
                logger.warning(f"Failed to get quote from {bt.value}: {e}")
        
        if not quotes:
            raise ValueError(f"No quotes available for {symbol}")
        
        # Return best bid (highest) for selling, best ask (lowest) for buying
        # For simplicity, return quote with highest last_price
        best = max(quotes, key=lambda x: x[0].last_price)
        return best
    
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get unified portfolio summary.
        
        Returns:
            Dict with portfolio metrics
        """
        positions = await self.get_all_positions()
        
        total_value = sum(p.value for p in positions)
        total_pnl = sum(p.pnl for p in positions)
        total_unrealized = sum(p.unrealized_pnl for p in positions)
        total_realized = sum(p.realized_pnl for p in positions)
        
        by_broker = defaultdict(lambda: {"value": 0, "pnl": 0, "positions": 0})
        by_exchange = defaultdict(lambda: {"value": 0, "pnl": 0, "positions": 0})
        
        for pos in positions:
            by_broker[pos.broker.value]["value"] += pos.value
            by_broker[pos.broker.value]["pnl"] += pos.pnl
            by_broker[pos.broker.value]["positions"] += 1
            
            by_exchange[pos.exchange]["value"] += pos.value
            by_exchange[pos.exchange]["pnl"] += pos.pnl
            by_exchange[pos.exchange]["positions"] += 1
        
        return {
            "total_positions": len(positions),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_unrealized_pnl": round(total_unrealized, 2),
            "total_realized_pnl": round(total_realized, 2),
            "pnl_pct": round(total_pnl / total_value * 100, 2) if total_value > 0 else 0,
            "by_broker": dict(by_broker),
            "by_exchange": dict(by_exchange),
            "active_brokers": [b.value for b in self.get_active_brokers()],
        }
    
    async def get_broker_stats(self) -> Dict[str, BrokerStats]:
        """Get statistics for all brokers."""
        # Update success rates
        for bt, stats in self._broker_stats.items():
            total = stats.orders_placed
            if total > 0:
                stats.success_rate = stats.orders_filled / total
        
        return {bt.value: stats for bt, stats in self._broker_stats.items()}
    
    def _select_broker(self, order: OrderRequest) -> Optional[BrokerType]:
        """
        Select broker based on routing strategy.
        
        Args:
            order: Order request
            
        Returns:
            Selected broker type
        """
        active_brokers = self.get_active_brokers()
        
        if not active_brokers:
            return None
        
        # Filter by exchange support
        valid_brokers = [
            bt for bt in active_brokers
            if order.exchange in self._broker_configs[bt].allowed_exchanges
        ]
        
        if not valid_brokers:
            return None
        
        if self.routing_strategy == OrderRoutingStrategy.PRIMARY:
            # Return highest priority
            return min(valid_brokers, key=lambda bt: self._broker_configs[bt].priority)
        
        elif self.routing_strategy == OrderRoutingStrategy.ROUND_ROBIN:
            # Distribute based on order count
            broker_counts = {
                bt: self._broker_stats[bt].orders_placed
                for bt in valid_brokers
            }
            return min(broker_counts, key=broker_counts.get)
        
        elif self.routing_strategy == OrderRoutingStrategy.LOAD_BALANCE:
            # Balance by pending orders
            pending_counts = defaultdict(int)
            for order in self._orders.values():
                if order.status in [OrderStatus.PENDING, OrderStatus.OPEN]:
                    pending_counts[order.broker] += 1
            
            return min(valid_brokers, key=lambda bt: pending_counts[bt])
        
        else:
            return valid_brokers[0]
    
    def _get_next_broker(self, tried: List[BrokerType]) -> Optional[BrokerType]:
        """Get next broker for failover."""
        active = self.get_active_brokers()
        available = [bt for bt in active if bt not in tried]
        
        if not available:
            return None
        
        # Return next highest priority
        return min(available, key=lambda bt: self._broker_configs[bt].priority)
    
    async def _notify_order_update(self, order: UnifiedOrder) -> None:
        """Notify callbacks of order update."""
        for callback in self._order_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(order)
                else:
                    callback(order)
            except Exception as e:
                logger.error(f"Order callback error: {e}")
    
    def add_order_callback(self, callback: Callable) -> None:
        """Add callback for order updates."""
        self._order_callbacks.append(callback)
    
    def add_position_callback(self, callback: Callable) -> None:
        """Add callback for position updates."""
        self._position_callbacks.append(callback)
    
    def get_status(self) -> Dict[str, Any]:
        """Get unified order manager status."""
        return {
            "active_brokers": [b.value for b in self.get_active_brokers()],
            "primary_broker": self.get_primary_broker().value if self.get_primary_broker() else None,
            "routing_strategy": self.routing_strategy.value,
            "failover_enabled": self.enable_failover,
            "total_tracked_orders": len(self._orders),
            "pending_orders": len([o for o in self._orders.values() if o.status in [OrderStatus.PENDING, OrderStatus.OPEN]]),
        }


# Singleton instance
_unified_manager: Optional[UnifiedOrderManager] = None


def get_unified_order_manager() -> UnifiedOrderManager:
    """Get or create unified order manager singleton."""
    global _unified_manager
    if _unified_manager is None:
        _unified_manager = UnifiedOrderManager()
    return _unified_manager
