"""
Order Status Streaming Service
KeepGaining Trading Platform

Real-time order status streaming and tracking via WebSocket.
Features:
- Order lifecycle tracking (placed -> pending -> filled/rejected)
- Multi-broker support (Fyers, Upstox)
- WebSocket streaming to frontend
- Order event publishing
- Position auto-update on fills
"""

import asyncio
import json
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
import sys
from pathlib import Path

from loguru import logger

# WebSocket support
try:
    import websockets
    from websockets.exceptions import ConnectionClosed
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

from app.core.events import EventBus, EventType, get_event_bus_sync
from app.db.models import OrderStatus


class OrderStreamStatus(str, Enum):
    """Order stream connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class OrderUpdate:
    """Represents an order status update."""
    order_id: str
    status: str
    symbol: str
    side: str
    quantity: int
    price: float
    filled_quantity: int = 0
    average_price: float = 0.0
    pending_quantity: int = 0
    order_type: str = "MARKET"
    product_type: str = "MIS"
    exchange: str = "NSE"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message: str = ""
    rejection_reason: str = ""
    exchange_order_id: str = ""
    tag: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "status": self.status,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "filled_quantity": self.filled_quantity,
            "average_price": self.average_price,
            "pending_quantity": self.pending_quantity,
            "order_type": self.order_type,
            "product_type": self.product_type,
            "exchange": self.exchange,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "rejection_reason": self.rejection_reason,
            "exchange_order_id": self.exchange_order_id,
            "tag": self.tag,
        }


class OrderStreamCallback:
    """Callback handler for order updates."""
    
    async def on_order_placed(self, update: OrderUpdate) -> None:
        """Called when order is placed."""
        pass
    
    async def on_order_pending(self, update: OrderUpdate) -> None:
        """Called when order is pending at exchange."""
        pass
    
    async def on_order_filled(self, update: OrderUpdate) -> None:
        """Called when order is fully filled."""
        pass
    
    async def on_order_partially_filled(self, update: OrderUpdate) -> None:
        """Called when order is partially filled."""
        pass
    
    async def on_order_cancelled(self, update: OrderUpdate) -> None:
        """Called when order is cancelled."""
        pass
    
    async def on_order_rejected(self, update: OrderUpdate) -> None:
        """Called when order is rejected."""
        pass
    
    async def on_order_modified(self, update: OrderUpdate) -> None:
        """Called when order is modified."""
        pass


class FyersOrderStream:
    """
    Fyers WebSocket Order Stream.
    
    Connects to Fyers order update WebSocket and streams real-time
    order status updates.
    """
    
    WEBSOCKET_URL = "wss://api-t1.fyers.in/socket/v2/orderStatus"
    
    def __init__(
        self,
        access_token: str,
        client_id: str,
        on_update: Optional[Callable[[OrderUpdate], Coroutine[Any, Any, None]]] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self._access_token = access_token
        self._client_id = client_id
        self._on_update = on_update
        self._event_bus = event_bus or get_event_bus_sync()
        
        self._status = OrderStreamStatus.DISCONNECTED
        self._ws = None
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        
        # Order tracking
        self._orders: Dict[str, OrderUpdate] = {}
        self._callbacks: List[OrderStreamCallback] = []
    
    async def connect(self) -> bool:
        """Connect to Fyers order stream."""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not available")
            return False
        
        try:
            self._status = OrderStreamStatus.CONNECTING
            
            # Create SSL context
            ssl_context = ssl.create_default_context()
            
            # Build auth header
            auth_token = f"{self._client_id}:{self._access_token}"
            headers = {
                "Authorization": f"Bearer {auth_token}",
            }
            
            # Connect
            self._ws = await websockets.connect(
                self.WEBSOCKET_URL,
                extra_headers=headers,
                ssl=ssl_context,
            )
            
            self._status = OrderStreamStatus.CONNECTED
            self._running = True
            self._reconnect_attempts = 0
            
            logger.info("Connected to Fyers order stream")
            
            # Start listening
            asyncio.create_task(self._listen_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Fyers order stream: {e}")
            self._status = OrderStreamStatus.ERROR
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from order stream."""
        self._running = False
        
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            self._ws = None
        
        self._status = OrderStreamStatus.DISCONNECTED
        logger.info("Disconnected from Fyers order stream")
    
    async def _listen_loop(self) -> None:
        """Listen for order updates."""
        while self._running:
            try:
                if not self._ws:
                    break
                
                message = await self._ws.recv()
                await self._process_message(message)
                
            except ConnectionClosed:
                logger.warning("Fyers order stream connection closed")
                await self._handle_reconnect()
                break
            except Exception as e:
                logger.error(f"Order stream error: {e}")
                await asyncio.sleep(1)
    
    async def _process_message(self, message: str) -> None:
        """Process incoming order update message."""
        try:
            data = json.loads(message)
            
            # Fyers order update format
            if data.get("s") == "ok" and "d" in data:
                order_data = data["d"]
                
                update = OrderUpdate(
                    order_id=order_data.get("id", ""),
                    status=self._map_fyers_status(order_data.get("status", 0)),
                    symbol=order_data.get("symbol", ""),
                    side="BUY" if order_data.get("side") == 1 else "SELL",
                    quantity=order_data.get("qty", 0),
                    price=order_data.get("limitPrice", 0),
                    filled_quantity=order_data.get("filledQty", 0),
                    average_price=order_data.get("tradedPrice", 0),
                    pending_quantity=order_data.get("remainingQuantity", 0),
                    order_type=order_data.get("type", "MARKET"),
                    product_type=order_data.get("productType", ""),
                    exchange=order_data.get("exchange", "NSE"),
                    exchange_order_id=order_data.get("exchOrdId", ""),
                    message=order_data.get("message", ""),
                    rejection_reason=order_data.get("rejectionReason", ""),
                )
                
                await self._handle_update(update)
                
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in order stream: {message[:100]}")
        except Exception as e:
            logger.error(f"Error processing order update: {e}")
    
    def _map_fyers_status(self, status_code: int) -> str:
        """Map Fyers status code to standard status string."""
        mapping = {
            1: "CANCELLED",
            2: "FILLED",
            3: "REJECTED",
            4: "PENDING",
            5: "REJECTED",
            6: "PENDING",
        }
        return mapping.get(status_code, "UNKNOWN")
    
    async def _handle_update(self, update: OrderUpdate) -> None:
        """Handle processed order update."""
        # Store update
        self._orders[update.order_id] = update
        
        # Call custom callback
        if self._on_update:
            await self._on_update(update)
        
        # Publish to event bus
        event_type = f"order.{update.status.lower()}"
        try:
            await self._event_bus.publish(event_type, update.to_dict())
        except Exception as e:
            logger.warning(f"Failed to publish order event: {e}")
        
        # Call registered callbacks
        for callback in self._callbacks:
            try:
                if update.status == "FILLED":
                    await callback.on_order_filled(update)
                elif update.status == "PENDING":
                    await callback.on_order_pending(update)
                elif update.status == "CANCELLED":
                    await callback.on_order_cancelled(update)
                elif update.status == "REJECTED":
                    await callback.on_order_rejected(update)
                elif update.filled_quantity > 0 and update.pending_quantity > 0:
                    await callback.on_order_partially_filled(update)
            except Exception as e:
                logger.error(f"Callback error: {e}")
        
        logger.info(f"Order update: {update.order_id} -> {update.status}")
    
    async def _handle_reconnect(self) -> None:
        """Handle reconnection logic."""
        if not self._running:
            return
        
        self._reconnect_attempts += 1
        
        if self._reconnect_attempts > self._max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            self._status = OrderStreamStatus.ERROR
            return
        
        self._status = OrderStreamStatus.RECONNECTING
        wait_time = min(30, 2 ** self._reconnect_attempts)
        
        logger.info(f"Reconnecting in {wait_time}s (attempt {self._reconnect_attempts})")
        await asyncio.sleep(wait_time)
        
        await self.connect()
    
    def register_callback(self, callback: OrderStreamCallback) -> None:
        """Register a callback handler."""
        self._callbacks.append(callback)
    
    def get_order(self, order_id: str) -> Optional[OrderUpdate]:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    def get_status(self) -> OrderStreamStatus:
        """Get connection status."""
        return self._status


class UpstoxOrderStream:
    """
    Upstox WebSocket Order/Portfolio Stream.
    
    Streams real-time order and portfolio updates via Upstox WebSocket API.
    """
    
    AUTH_URL = "https://api.upstox.com/v2/feed/portfolio-stream-feed/authorize"
    
    def __init__(
        self,
        access_token: str,
        on_update: Optional[Callable[[OrderUpdate], Coroutine[Any, Any, None]]] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self._access_token = access_token
        self._on_update = on_update
        self._event_bus = event_bus or get_event_bus_sync()
        
        self._status = OrderStreamStatus.DISCONNECTED
        self._ws = None
        self._running = False
        self._reconnect_attempts = 0
        
        # Order tracking
        self._orders: Dict[str, OrderUpdate] = {}
        self._callbacks: List[OrderStreamCallback] = []
    
    async def connect(self) -> bool:
        """Connect to Upstox portfolio stream."""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not available")
            return False
        
        try:
            self._status = OrderStreamStatus.CONNECTING
            
            # Get WebSocket URL via auth endpoint
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.AUTH_URL,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get WebSocket URL: {response.text}")
                    return False
                
                data = response.json()
                ws_url = data.get("data", {}).get("authorized_redirect_uri")
            
            if not ws_url:
                logger.error("No WebSocket URL returned")
                return False
            
            # Connect to WebSocket
            ssl_context = ssl.create_default_context()
            self._ws = await websockets.connect(ws_url, ssl=ssl_context)
            
            self._status = OrderStreamStatus.CONNECTED
            self._running = True
            self._reconnect_attempts = 0
            
            logger.info("Connected to Upstox portfolio stream")
            
            # Start listening
            asyncio.create_task(self._listen_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Upstox portfolio stream: {e}")
            self._status = OrderStreamStatus.ERROR
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from portfolio stream."""
        self._running = False
        
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            self._ws = None
        
        self._status = OrderStreamStatus.DISCONNECTED
        logger.info("Disconnected from Upstox portfolio stream")
    
    async def _listen_loop(self) -> None:
        """Listen for portfolio updates."""
        while self._running:
            try:
                if not self._ws:
                    break
                
                message = await self._ws.recv()
                
                # Upstox sends binary protobuf or JSON
                if isinstance(message, bytes):
                    await self._process_binary_message(message)
                else:
                    await self._process_json_message(message)
                
            except ConnectionClosed:
                logger.warning("Upstox portfolio stream connection closed")
                await self._handle_reconnect()
                break
            except Exception as e:
                logger.error(f"Portfolio stream error: {e}")
                await asyncio.sleep(1)
    
    async def _process_binary_message(self, message: bytes) -> None:
        """Process binary protobuf message."""
        # Upstox portfolio stream uses protobuf
        # For simplicity, we'll try to decode as JSON if protobuf fails
        try:
            data = json.loads(message.decode('utf-8'))
            await self._process_order_data(data)
        except Exception:
            logger.debug("Binary message processing skipped (likely protobuf)")
    
    async def _process_json_message(self, message: str) -> None:
        """Process JSON message."""
        try:
            data = json.loads(message)
            
            # Handle different message types
            msg_type = data.get("type", "")
            
            if msg_type == "order":
                await self._process_order_data(data.get("data", {}))
            elif msg_type == "position":
                # Position updates can also be processed here
                pass
            elif msg_type == "heartbeat":
                pass  # Ignore heartbeats
            
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON: {message[:100]}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _process_order_data(self, order_data: Dict[str, Any]) -> None:
        """Process order data from stream."""
        update = OrderUpdate(
            order_id=order_data.get("order_id", ""),
            status=self._map_upstox_status(order_data.get("status", "")),
            symbol=order_data.get("tradingsymbol", ""),
            side=order_data.get("transaction_type", "BUY"),
            quantity=order_data.get("quantity", 0),
            price=order_data.get("price", 0),
            filled_quantity=order_data.get("filled_quantity", 0),
            average_price=order_data.get("average_price", 0),
            pending_quantity=order_data.get("pending_quantity", 0),
            order_type=order_data.get("order_type", "MARKET"),
            product_type=order_data.get("product", ""),
            exchange=order_data.get("exchange", ""),
            exchange_order_id=order_data.get("exchange_order_id", ""),
            message=order_data.get("status_message", ""),
            tag=order_data.get("tag", ""),
        )
        
        await self._handle_update(update)
    
    def _map_upstox_status(self, status: str) -> str:
        """Map Upstox status to standard status."""
        status_lower = status.lower()
        mapping = {
            "open": "PENDING",
            "pending": "PENDING",
            "trigger pending": "PENDING",
            "complete": "FILLED",
            "traded": "FILLED",
            "cancelled": "CANCELLED",
            "rejected": "REJECTED",
            "modified": "MODIFIED",
        }
        return mapping.get(status_lower, status.upper())
    
    async def _handle_update(self, update: OrderUpdate) -> None:
        """Handle processed order update."""
        self._orders[update.order_id] = update
        
        if self._on_update:
            await self._on_update(update)
        
        # Publish to event bus
        try:
            await self._event_bus.publish(f"order.{update.status.lower()}", update.to_dict())
        except Exception as e:
            logger.warning(f"Failed to publish event: {e}")
        
        # Call registered callbacks
        for callback in self._callbacks:
            try:
                if update.status == "FILLED":
                    await callback.on_order_filled(update)
                elif update.status == "PENDING":
                    await callback.on_order_pending(update)
                elif update.status == "CANCELLED":
                    await callback.on_order_cancelled(update)
                elif update.status == "REJECTED":
                    await callback.on_order_rejected(update)
            except Exception as e:
                logger.error(f"Callback error: {e}")
        
        logger.info(f"Order update: {update.order_id} -> {update.status}")
    
    async def _handle_reconnect(self) -> None:
        """Handle reconnection."""
        if not self._running:
            return
        
        self._reconnect_attempts += 1
        
        if self._reconnect_attempts > 10:
            logger.error("Max reconnection attempts reached")
            self._status = OrderStreamStatus.ERROR
            return
        
        self._status = OrderStreamStatus.RECONNECTING
        wait_time = min(30, 2 ** self._reconnect_attempts)
        
        logger.info(f"Reconnecting in {wait_time}s")
        await asyncio.sleep(wait_time)
        
        await self.connect()
    
    def register_callback(self, callback: OrderStreamCallback) -> None:
        """Register a callback handler."""
        self._callbacks.append(callback)
    
    def get_order(self, order_id: str) -> Optional[OrderUpdate]:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    def get_status(self) -> OrderStreamStatus:
        """Get connection status."""
        return self._status


class UnifiedOrderStream:
    """
    Unified order stream manager for multiple brokers.
    
    Provides a single interface for order streaming regardless of
    the underlying broker connection.
    """
    
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus or get_event_bus_sync()
        self._fyers_stream: Optional[FyersOrderStream] = None
        self._upstox_stream: Optional[UpstoxOrderStream] = None
        self._callbacks: List[OrderStreamCallback] = []
        self._update_handlers: List[Callable[[OrderUpdate], Coroutine[Any, Any, None]]] = []
    
    async def connect_fyers(self, access_token: str, client_id: str) -> bool:
        """Connect to Fyers order stream."""
        self._fyers_stream = FyersOrderStream(
            access_token=access_token,
            client_id=client_id,
            on_update=self._on_order_update,
            event_bus=self._event_bus,
        )
        
        for cb in self._callbacks:
            self._fyers_stream.register_callback(cb)
        
        return await self._fyers_stream.connect()
    
    async def connect_upstox(self, access_token: str) -> bool:
        """Connect to Upstox order stream."""
        self._upstox_stream = UpstoxOrderStream(
            access_token=access_token,
            on_update=self._on_order_update,
            event_bus=self._event_bus,
        )
        
        for cb in self._callbacks:
            self._upstox_stream.register_callback(cb)
        
        return await self._upstox_stream.connect()
    
    async def disconnect_all(self) -> None:
        """Disconnect all streams."""
        if self._fyers_stream:
            await self._fyers_stream.disconnect()
            self._fyers_stream = None
        
        if self._upstox_stream:
            await self._upstox_stream.disconnect()
            self._upstox_stream = None
    
    async def _on_order_update(self, update: OrderUpdate) -> None:
        """Handle order update from any stream."""
        for handler in self._update_handlers:
            try:
                await handler(update)
            except Exception as e:
                logger.error(f"Update handler error: {e}")
    
    def on_update(self, handler: Callable[[OrderUpdate], Coroutine[Any, Any, None]]) -> None:
        """Register an update handler."""
        self._update_handlers.append(handler)
    
    def register_callback(self, callback: OrderStreamCallback) -> None:
        """Register a callback for all streams."""
        self._callbacks.append(callback)
        
        if self._fyers_stream:
            self._fyers_stream.register_callback(callback)
        if self._upstox_stream:
            self._upstox_stream.register_callback(callback)
    
    def get_order(self, order_id: str) -> Optional[OrderUpdate]:
        """Get order from any stream."""
        if self._fyers_stream:
            order = self._fyers_stream.get_order(order_id)
            if order:
                return order
        
        if self._upstox_stream:
            return self._upstox_stream.get_order(order_id)
        
        return None
    
    def get_status(self) -> Dict[str, str]:
        """Get status of all streams."""
        return {
            "fyers": self._fyers_stream.get_status().value if self._fyers_stream else "not_initialized",
            "upstox": self._upstox_stream.get_status().value if self._upstox_stream else "not_initialized",
        }


# Singleton instance
_order_stream: Optional[UnifiedOrderStream] = None


def get_order_stream() -> UnifiedOrderStream:
    """Get or create the global order stream instance."""
    global _order_stream
    if _order_stream is None:
        _order_stream = UnifiedOrderStream()
    return _order_stream
