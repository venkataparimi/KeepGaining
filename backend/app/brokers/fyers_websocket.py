"""
Fyers WebSocket Adapter
KeepGaining Trading Platform

Real-time market data streaming via Fyers WebSocket API.
Features:
- Auto-reconnection with exponential backoff
- Symbol subscription management
- Tick data normalization
- Event bus integration
"""

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
import threading

from loguru import logger
from fyers_apiv3.FyersWebsocket import data_ws

from app.core.config import settings
from app.core.events import EventBus, TickEvent, EventType, get_event_bus
from app.brokers.fyers_client import FyersClient


class ConnectionState(str, Enum):
    """WebSocket connection states."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


@dataclass
class TickData:
    """Normalized tick data structure."""
    symbol: str
    ltp: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    oi: int = 0  # Open interest
    bid: float = 0.0
    ask: float = 0.0
    bid_qty: int = 0
    ask_qty: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    exchange_timestamp: Optional[datetime] = None
    change: float = 0.0
    change_percent: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "ltp": self.ltp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "oi": self.oi,
            "bid": self.bid,
            "ask": self.ask,
            "bid_qty": self.bid_qty,
            "ask_qty": self.ask_qty,
            "timestamp": self.timestamp.isoformat(),
            "exchange_timestamp": self.exchange_timestamp.isoformat() if self.exchange_timestamp else None,
            "change": self.change,
            "change_percent": self.change_percent,
        }


class DataSourceBase(ABC):
    """
    Abstract base class for data sources.
    Defines the interface for all market data providers.
    """
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the data source."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the data source."""
        pass
    
    @abstractmethod
    async def subscribe(self, symbols: List[str]) -> bool:
        """Subscribe to symbols."""
        pass
    
    @abstractmethod
    async def unsubscribe(self, symbols: List[str]) -> bool:
        """Unsubscribe from symbols."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected."""
        pass
    
    @abstractmethod
    def get_subscribed_symbols(self) -> List[str]:
        """Get list of subscribed symbols."""
        pass


class FyersWebSocketAdapter(DataSourceBase):
    """
    Fyers WebSocket adapter for real-time market data.
    
    Features:
    - Automatic reconnection with exponential backoff
    - Symbol subscription management (max 200 symbols)
    - Tick data normalization to internal format
    - Integration with event bus for publishing ticks
    - Thread-safe operations
    """
    
    MAX_SYMBOLS = 200  # Fyers limit per WebSocket
    
    def __init__(
        self,
        client: Optional[FyersClient] = None,
        on_tick: Optional[Callable[[TickData], Coroutine[Any, Any, None]]] = None,
        publish_to_event_bus: bool = True,
    ):
        """
        Initialize Fyers WebSocket adapter.
        
        Args:
            client: FyersClient instance (creates new if not provided)
            on_tick: Callback function for tick data
            publish_to_event_bus: Whether to publish ticks to event bus
        """
        self._client = client
        self._on_tick = on_tick
        self._publish_to_event_bus = publish_to_event_bus
        
        self._ws: Optional[data_ws.FyersDataSocket] = None
        self._state = ConnectionState.DISCONNECTED
        self._subscribed_symbols: Set[str] = set()
        self._pending_subscriptions: Set[str] = set()
        
        # Reconnection settings
        self._reconnect_delay = settings.fyers.ws_reconnect_delay
        self._max_reconnect_attempts = 10
        self._reconnect_attempts = 0
        
        # Thread safety
        self._lock = threading.Lock()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Event bus
        self._event_bus: Optional[EventBus] = None
        
        # Stats
        self._tick_count = 0
        self._last_tick_time: Optional[datetime] = None
        self._error_count = 0
    
    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._state == ConnectionState.CONNECTED
    
    def get_subscribed_symbols(self) -> List[str]:
        """Get list of currently subscribed symbols."""
        with self._lock:
            return list(self._subscribed_symbols)
    
    async def connect(self) -> bool:
        """
        Connect to Fyers WebSocket.
        
        Returns:
            True if connection successful, False otherwise.
        """
        if self._state == ConnectionState.CONNECTED:
            logger.warning("WebSocket already connected")
            return True
        
        self._state = ConnectionState.CONNECTING
        self._event_loop = asyncio.get_event_loop()
        
        try:
            # Initialize client if not provided
            if not self._client:
                self._client = FyersClient(
                    client_id=settings.FYERS_CLIENT_ID,
                    secret_key=settings.FYERS_SECRET_KEY,
                    redirect_uri=settings.FYERS_REDIRECT_URI,
                    username=settings.FYERS_USER_ID,
                    pin=settings.FYERS_PIN,
                    totp_key=settings.FYERS_TOTP_KEY,
                )
            
            # Get event bus for publishing
            if self._publish_to_event_bus:
                self._event_bus = await get_event_bus()
            
            # Create WebSocket connection
            access_token = f"{settings.FYERS_CLIENT_ID}:{self._client.access_token}"
            
            self._ws = data_ws.FyersDataSocket(
                access_token=access_token,
                log_path="",
                litemode=False,
                write_to_file=False,
                reconnect=True,
                on_connect=self._on_connect,
                on_close=self._on_close,
                on_error=self._on_error,
                on_message=self._on_message,
            )
            
            # Connect in background thread
            self._ws.connect()
            
            # Wait for connection
            for _ in range(50):  # 5 second timeout
                await asyncio.sleep(0.1)
                if self._state == ConnectionState.CONNECTED:
                    logger.info("✓ Fyers WebSocket connected successfully")
                    self._reconnect_attempts = 0
                    return True
            
            logger.error("WebSocket connection timeout")
            self._state = ConnectionState.ERROR
            return False
            
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            self._state = ConnectionState.ERROR
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        if self._ws:
            try:
                self._ws.close_connection()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
        
        self._state = ConnectionState.DISCONNECTED
        self._subscribed_symbols.clear()
        logger.info("Fyers WebSocket disconnected")
    
    async def subscribe(self, symbols: List[str]) -> bool:
        """
        Subscribe to symbols for real-time data.
        
        Args:
            symbols: List of symbols in Fyers format (e.g., "NSE:RELIANCE-EQ")
            
        Returns:
            True if subscription successful, False otherwise.
        """
        if not symbols:
            return True
        
        with self._lock:
            # Check symbol limit
            total_symbols = len(self._subscribed_symbols) + len(symbols)
            if total_symbols > self.MAX_SYMBOLS:
                logger.error(
                    f"Cannot subscribe: would exceed {self.MAX_SYMBOLS} symbol limit "
                    f"(current: {len(self._subscribed_symbols)}, requested: {len(symbols)})"
                )
                return False
            
            # Filter out already subscribed
            new_symbols = [s for s in symbols if s not in self._subscribed_symbols]
            
            if not new_symbols:
                logger.debug("All symbols already subscribed")
                return True
        
        if not self.is_connected():
            # Store for later subscription after connect
            with self._lock:
                self._pending_subscriptions.update(new_symbols)
            logger.warning(f"WebSocket not connected. {len(new_symbols)} symbols queued for subscription")
            return False
        
        try:
            # Subscribe via WebSocket
            self._ws.subscribe(symbols=new_symbols, data_type="SymbolUpdate")
            
            with self._lock:
                self._subscribed_symbols.update(new_symbols)
            
            logger.info(f"✓ Subscribed to {len(new_symbols)} symbols (total: {len(self._subscribed_symbols)})")
            return True
            
        except Exception as e:
            logger.error(f"Subscription error: {e}")
            return False
    
    async def unsubscribe(self, symbols: List[str]) -> bool:
        """
        Unsubscribe from symbols.
        
        Args:
            symbols: List of symbols to unsubscribe.
            
        Returns:
            True if successful, False otherwise.
        """
        if not symbols:
            return True
        
        with self._lock:
            symbols_to_unsub = [s for s in symbols if s in self._subscribed_symbols]
            
            if not symbols_to_unsub:
                return True
        
        if not self.is_connected():
            # Just remove from local tracking
            with self._lock:
                self._subscribed_symbols.difference_update(symbols_to_unsub)
            return True
        
        try:
            self._ws.unsubscribe(symbols=symbols_to_unsub, data_type="SymbolUpdate")
            
            with self._lock:
                self._subscribed_symbols.difference_update(symbols_to_unsub)
            
            logger.info(f"Unsubscribed from {len(symbols_to_unsub)} symbols")
            return True
            
        except Exception as e:
            logger.error(f"Unsubscription error: {e}")
            return False
    
    def _on_connect(self) -> None:
        """WebSocket connect callback."""
        logger.info("Fyers WebSocket connected")
        self._state = ConnectionState.CONNECTED
        self._reconnect_attempts = 0
        
        # Subscribe pending symbols
        if self._pending_subscriptions:
            symbols = list(self._pending_subscriptions)
            self._pending_subscriptions.clear()
            
            # Use asyncio.run_coroutine_threadsafe since this is called from WS thread
            if self._event_loop:
                asyncio.run_coroutine_threadsafe(
                    self.subscribe(symbols),
                    self._event_loop
                )
    
    def _on_close(self) -> None:
        """WebSocket close callback."""
        logger.warning("Fyers WebSocket connection closed")
        
        if self._state != ConnectionState.DISCONNECTED:
            self._state = ConnectionState.RECONNECTING
            
            # Attempt reconnection
            if self._event_loop:
                asyncio.run_coroutine_threadsafe(
                    self._handle_reconnect(),
                    self._event_loop
                )
    
    def _on_error(self, error: Any) -> None:
        """WebSocket error callback."""
        logger.error(f"Fyers WebSocket error: {error}")
        self._error_count += 1
        self._state = ConnectionState.ERROR
    
    def _on_message(self, message: Any) -> None:
        """
        WebSocket message callback.
        
        Processes incoming tick data and publishes to event bus.
        """
        try:
            # Parse tick data from Fyers format
            if isinstance(message, list):
                for item in message:
                    self._process_tick(item)
            elif isinstance(message, dict):
                self._process_tick(message)
            else:
                logger.warning(f"Unknown message format: {type(message)}")
                
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
    
    def _process_tick(self, data: Dict[str, Any]) -> None:
        """Process a single tick from Fyers."""
        try:
            # Normalize Fyers tick data
            # Fyers fields: symbol, ltp, open_price, high_price, low_price, prev_close_price, 
            #               ch (change), chp (change %), vol_traded_today, oi, bid_price, 
            #               ask_price, bid_size, ask_size, exch_feed_time
            
            symbol = data.get("symbol", "")
            if not symbol:
                return
            
            # Create normalized tick
            tick = TickData(
                symbol=symbol,
                ltp=float(data.get("ltp", 0)),
                open=float(data.get("open_price", 0)),
                high=float(data.get("high_price", 0)),
                low=float(data.get("low_price", 0)),
                close=float(data.get("prev_close_price", 0)),
                volume=int(data.get("vol_traded_today", 0)),
                oi=int(data.get("oi", 0)),
                bid=float(data.get("bid_price", 0)),
                ask=float(data.get("ask_price", 0)),
                bid_qty=int(data.get("bid_size", 0)),
                ask_qty=int(data.get("ask_size", 0)),
                change=float(data.get("ch", 0)),
                change_percent=float(data.get("chp", 0)),
                timestamp=datetime.now(timezone.utc),
            )
            
            # Parse exchange timestamp if available
            exch_time = data.get("exch_feed_time")
            if exch_time:
                try:
                    tick.exchange_timestamp = datetime.fromtimestamp(
                        exch_time, tz=timezone.utc
                    )
                except Exception:
                    pass
            
            # Update stats
            self._tick_count += 1
            self._last_tick_time = tick.timestamp
            
            # Call user callback
            if self._on_tick and self._event_loop:
                asyncio.run_coroutine_threadsafe(
                    self._on_tick(tick),
                    self._event_loop
                )
            
            # Publish to event bus
            if self._event_bus and self._event_loop:
                event = TickEvent(
                    event_type=EventType.TICK_RECEIVED,
                    instrument_id=symbol,  # TODO: Map to internal ID
                    symbol=symbol,
                    ltp=tick.ltp,
                    bid=tick.bid,
                    ask=tick.ask,
                    volume=tick.volume,
                    oi=tick.oi,
                    source="fyers_ws",
                )
                
                asyncio.run_coroutine_threadsafe(
                    self._event_bus.publish(event),
                    self._event_loop
                )
                
        except Exception as e:
            logger.error(f"Error processing tick for {data.get('symbol', 'unknown')}: {e}")
    
    async def _handle_reconnect(self) -> None:
        """Handle WebSocket reconnection with exponential backoff."""
        self._reconnect_attempts += 1
        
        if self._reconnect_attempts > self._max_reconnect_attempts:
            logger.error(f"Max reconnection attempts ({self._max_reconnect_attempts}) exceeded")
            self._state = ConnectionState.ERROR
            return
        
        # Exponential backoff
        delay = min(self._reconnect_delay * (2 ** (self._reconnect_attempts - 1)), 60)
        logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})")
        
        await asyncio.sleep(delay)
        
        # Store current subscriptions for resubscription
        with self._lock:
            self._pending_subscriptions = self._subscribed_symbols.copy()
            self._subscribed_symbols.clear()
        
        # Attempt reconnection
        success = await self.connect()
        
        if success and self._pending_subscriptions:
            symbols = list(self._pending_subscriptions)
            self._pending_subscriptions.clear()
            await self.subscribe(symbols)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket statistics."""
        return {
            "state": self._state.value,
            "subscribed_symbols": len(self._subscribed_symbols),
            "tick_count": self._tick_count,
            "last_tick_time": self._last_tick_time.isoformat() if self._last_tick_time else None,
            "error_count": self._error_count,
            "reconnect_attempts": self._reconnect_attempts,
        }


# =============================================================================
# Factory Function
# =============================================================================

async def create_fyers_websocket(
    symbols: Optional[List[str]] = None,
    on_tick: Optional[Callable[[TickData], Coroutine[Any, Any, None]]] = None,
) -> FyersWebSocketAdapter:
    """
    Factory function to create and connect a Fyers WebSocket adapter.
    
    Args:
        symbols: Optional list of symbols to subscribe on connect
        on_tick: Optional callback for tick data
        
    Returns:
        Connected FyersWebSocketAdapter instance
    """
    adapter = FyersWebSocketAdapter(on_tick=on_tick)
    
    success = await adapter.connect()
    if not success:
        raise ConnectionError("Failed to connect to Fyers WebSocket")
    
    if symbols:
        await adapter.subscribe(symbols)
    
    return adapter


__all__ = [
    "ConnectionState",
    "TickData",
    "DataSourceBase",
    "FyersWebSocketAdapter",
    "create_fyers_websocket",
]
