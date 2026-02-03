"""
Upstox WebSocket Adapter
KeepGaining Trading Platform

Real-time market data streaming via Upstox WebSocket API v3.
Features:
- Protobuf binary protocol for efficient data transfer
- Auto-reconnection with exponential backoff
- Support for 4000 instruments per connection
- Multiple data modes: LTPC, Full, Option Greeks
- Event bus integration
- Thread-safe async operations

API Documentation: https://upstox.com/developer/api-documentation/websocket-market-data-v3
"""

import asyncio
import json
import ssl
import sys
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Union
import threading
from pathlib import Path

import httpx
from loguru import logger

# Import websockets - async WebSocket client
try:
    import websockets
    from websockets.exceptions import ConnectionClosed
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    logger.warning("websockets not installed. Run: pip install websockets")

# Import protobuf for message decoding
try:
    from google.protobuf.json_format import MessageToDict
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False
    logger.warning("protobuf not installed. Run: pip install protobuf")

# Add path for local protobuf definitions
PROTO_PATH = Path(__file__).parent.parent / "upstox-python-master" / "examples" / "websocket" / "market_data" / "v3"
if PROTO_PATH.exists():
    sys.path.insert(0, str(PROTO_PATH))
    try:
        import MarketDataFeedV3_pb2 as pb
        UPSTOX_PROTO_AVAILABLE = True
    except ImportError:
        UPSTOX_PROTO_AVAILABLE = False
        pb = None
else:
    UPSTOX_PROTO_AVAILABLE = False
    pb = None

from app.core.config import settings
from app.core.events import EventBus, TickEvent, EventType, get_event_bus


class ConnectionState(str, Enum):
    """WebSocket connection states."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


class DataMode(str, Enum):
    """Upstox WebSocket data modes."""
    LTPC = "ltpc"          # Last Traded Price & Change (lightest)
    FULL_D5 = "full"       # Full market depth (5 levels)
    FULL_D30 = "full_d30"  # Full market depth (30 levels)
    OPTION_GREEKS = "option_greeks"  # Option Greeks with LTPC


@dataclass
class UpstoxTickData:
    """Normalized tick data from Upstox WebSocket."""
    symbol: str
    instrument_key: str
    ltp: float
    ltt: int = 0  # Last traded timestamp (epoch ms)
    ltq: int = 0  # Last traded quantity
    cp: float = 0.0  # Close price (previous day)
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    oi: float = 0.0  # Open interest
    atp: float = 0.0  # Average traded price
    bid: float = 0.0
    ask: float = 0.0
    bid_qty: int = 0
    ask_qty: int = 0
    total_buy_qty: float = 0.0
    total_sell_qty: float = 0.0
    iv: float = 0.0  # Implied volatility
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Option Greeks (if mode=option_greeks)
    delta: Optional[float] = None
    theta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "instrument_key": self.instrument_key,
            "ltp": self.ltp,
            "ltt": self.ltt,
            "ltq": self.ltq,
            "cp": self.cp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "oi": self.oi,
            "atp": self.atp,
            "bid": self.bid,
            "ask": self.ask,
            "bid_qty": self.bid_qty,
            "ask_qty": self.ask_qty,
            "total_buy_qty": self.total_buy_qty,
            "total_sell_qty": self.total_sell_qty,
            "iv": self.iv,
            "timestamp": self.timestamp.isoformat(),
            "delta": self.delta,
            "theta": self.theta,
            "gamma": self.gamma,
            "vega": self.vega,
            "rho": self.rho,
        }


class UpstoxWebSocketAdapter:
    """
    Upstox WebSocket adapter for real-time market data.
    
    Features:
    - Supports up to 4000 instruments per connection (vs Fyers 200)
    - Protobuf binary encoding for efficiency
    - Multiple data modes (LTPC, Full, Option Greeks)
    - Automatic reconnection with exponential backoff
    - Integration with event bus for publishing ticks
    - Thread-safe operations
    
    Usage:
        adapter = UpstoxWebSocketAdapter(access_token="...")
        await adapter.connect()
        await adapter.subscribe(["NSE_EQ|INE002A01018", "NSE_INDEX|Nifty 50"])
        
        # Later
        await adapter.disconnect()
    """
    
    AUTH_URL = "https://api.upstox.com/v3/feed/market-data-feed/authorize"
    MAX_INSTRUMENTS = 4000  # Upstox limit per WebSocket
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        data_mode: DataMode = DataMode.FULL_D5,
        on_tick: Optional[Callable[[UpstoxTickData], Coroutine[Any, Any, None]]] = None,
        publish_to_event_bus: bool = True,
    ):
        """
        Initialize Upstox WebSocket adapter.
        
        Args:
            access_token: Upstox API access token (required)
            data_mode: Type of data to receive (ltpc, full, option_greeks)
            on_tick: Optional callback for tick data
            publish_to_event_bus: Whether to publish ticks to event bus
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets library required. Install: pip install websockets")
        if not PROTOBUF_AVAILABLE:
            raise ImportError("protobuf library required. Install: pip install protobuf")
        if not UPSTOX_PROTO_AVAILABLE:
            logger.warning("Upstox protobuf definitions not found. JSON mode will be used.")
        
        self._access_token = access_token
        self._data_mode = data_mode
        self._on_tick = on_tick
        self._publish_to_event_bus = publish_to_event_bus
        
        self._ws = None
        self._state = ConnectionState.DISCONNECTED
        self._subscribed_instruments: Set[str] = set()
        self._pending_subscriptions: Set[str] = set()
        
        # Reconnection settings
        self._reconnect_delay = 1.0
        self._max_reconnect_attempts = 10
        self._reconnect_attempts = 0
        
        # Thread safety
        self._lock = threading.Lock()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._consumer_task: Optional[asyncio.Task] = None
        
        # Event bus
        self._event_bus: Optional[EventBus] = None
        
        # Stats
        self._tick_count = 0
        self._last_tick_time: Optional[datetime] = None
        self._error_count = 0
        self._connected_at: Optional[datetime] = None
    
    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._state == ConnectionState.CONNECTED
    
    def get_subscribed_instruments(self) -> List[str]:
        """Get list of currently subscribed instruments."""
        with self._lock:
            return list(self._subscribed_instruments)
    
    async def _get_websocket_url(self) -> Optional[str]:
        """Get authorized WebSocket URL from Upstox."""
        if not self._access_token:
            logger.error("Access token not set")
            return None
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.AUTH_URL,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {self._access_token}",
                    },
                )
                
                if response.status_code != 200:
                    logger.error(f"Auth failed: {response.status_code} - {response.text}")
                    return None
                
                data = response.json()
                if data.get("status") != "success":
                    logger.error(f"Auth failed: {data}")
                    return None
                
                return data.get("data", {}).get("authorized_redirect_uri")
                
            except Exception as e:
                logger.error(f"Auth request error: {e}")
                return None
    
    async def connect(self) -> bool:
        """
        Connect to Upstox WebSocket.
        
        Returns:
            True if connection successful, False otherwise.
        """
        if self._state == ConnectionState.CONNECTED:
            logger.warning("WebSocket already connected")
            return True
        
        self._state = ConnectionState.CONNECTING
        self._event_loop = asyncio.get_event_loop()
        
        try:
            # Get authorized WebSocket URL
            ws_url = await self._get_websocket_url()
            if not ws_url:
                self._state = ConnectionState.ERROR
                return False
            
            logger.info(f"Connecting to Upstox WebSocket...")
            
            # Get event bus for publishing
            if self._publish_to_event_bus:
                self._event_bus = await get_event_bus()
            
            # Create SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Connect to WebSocket
            self._ws = await websockets.connect(
                ws_url,
                ssl=ssl_context,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
            )
            
            self._state = ConnectionState.CONNECTED
            self._connected_at = datetime.now(timezone.utc)
            self._reconnect_attempts = 0
            
            logger.info("✓ Upstox WebSocket connected successfully")
            
            # Start message consumer
            self._consumer_task = asyncio.create_task(self._consume_messages())
            
            # Subscribe pending instruments
            if self._pending_subscriptions:
                instruments = list(self._pending_subscriptions)
                self._pending_subscriptions.clear()
                await self.subscribe(instruments)
            
            return True
            
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            self._state = ConnectionState.ERROR
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self._state = ConnectionState.DISCONNECTED
        
        # Cancel consumer task
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None
        
        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
            self._ws = None
        
        self._subscribed_instruments.clear()
        logger.info("Upstox WebSocket disconnected")
    
    async def subscribe(
        self,
        instrument_keys: List[str],
        mode: Optional[DataMode] = None,
    ) -> bool:
        """
        Subscribe to instruments for real-time data.
        
        Args:
            instrument_keys: List of Upstox instrument keys
                (e.g., "NSE_EQ|INE002A01018", "NSE_INDEX|Nifty 50")
            mode: Optional override for data mode
            
        Returns:
            True if subscription successful, False otherwise.
        """
        if not instrument_keys:
            return True
        
        with self._lock:
            # Check instrument limit
            total_instruments = len(self._subscribed_instruments) + len(instrument_keys)
            if total_instruments > self.MAX_INSTRUMENTS:
                logger.error(
                    f"Cannot subscribe: would exceed {self.MAX_INSTRUMENTS} instrument limit "
                    f"(current: {len(self._subscribed_instruments)}, requested: {len(instrument_keys)})"
                )
                return False
            
            # Filter out already subscribed
            new_instruments = [k for k in instrument_keys if k not in self._subscribed_instruments]
            
            if not new_instruments:
                logger.debug("All instruments already subscribed")
                return True
        
        if not self.is_connected():
            # Store for later subscription after connect
            with self._lock:
                self._pending_subscriptions.update(new_instruments)
            logger.warning(f"WebSocket not connected. {len(new_instruments)} instruments queued")
            return False
        
        try:
            # Prepare subscription message
            data_mode = mode or self._data_mode
            subscribe_msg = {
                "guid": f"sub_{datetime.now().timestamp()}",
                "method": "sub",
                "data": {
                    "mode": data_mode.value,
                    "instrumentKeys": new_instruments,
                },
            }
            
            # Send subscription
            await self._ws.send(json.dumps(subscribe_msg).encode("utf-8"))
            
            with self._lock:
                self._subscribed_instruments.update(new_instruments)
            
            logger.info(
                f"✓ Subscribed to {len(new_instruments)} instruments "
                f"(total: {len(self._subscribed_instruments)}, mode: {data_mode.value})"
            )
            return True
            
        except Exception as e:
            logger.error(f"Subscription error: {e}")
            return False
    
    async def unsubscribe(self, instrument_keys: List[str]) -> bool:
        """
        Unsubscribe from instruments.
        
        Args:
            instrument_keys: List of instrument keys to unsubscribe.
            
        Returns:
            True if successful, False otherwise.
        """
        if not instrument_keys:
            return True
        
        with self._lock:
            instruments_to_unsub = [k for k in instrument_keys if k in self._subscribed_instruments]
            
            if not instruments_to_unsub:
                return True
        
        if not self.is_connected():
            with self._lock:
                self._subscribed_instruments.difference_update(instruments_to_unsub)
            return True
        
        try:
            # Prepare unsubscription message
            unsub_msg = {
                "guid": f"unsub_{datetime.now().timestamp()}",
                "method": "unsub",
                "data": {
                    "mode": self._data_mode.value,
                    "instrumentKeys": instruments_to_unsub,
                },
            }
            
            await self._ws.send(json.dumps(unsub_msg).encode("utf-8"))
            
            with self._lock:
                self._subscribed_instruments.difference_update(instruments_to_unsub)
            
            logger.info(f"Unsubscribed from {len(instruments_to_unsub)} instruments")
            return True
            
        except Exception as e:
            logger.error(f"Unsubscription error: {e}")
            return False
    
    async def change_mode(
        self,
        instrument_keys: List[str],
        new_mode: DataMode,
    ) -> bool:
        """
        Change data mode for specific instruments.
        
        Args:
            instrument_keys: Instruments to change mode for
            new_mode: New data mode
            
        Returns:
            True if successful.
        """
        if not self.is_connected():
            return False
        
        try:
            change_msg = {
                "guid": f"change_{datetime.now().timestamp()}",
                "method": "change_mode",
                "data": {
                    "mode": new_mode.value,
                    "instrumentKeys": instrument_keys,
                },
            }
            
            await self._ws.send(json.dumps(change_msg).encode("utf-8"))
            logger.info(f"Changed mode to {new_mode.value} for {len(instrument_keys)} instruments")
            return True
            
        except Exception as e:
            logger.error(f"Mode change error: {e}")
            return False
    
    async def _consume_messages(self) -> None:
        """Consume messages from WebSocket."""
        logger.info("Starting Upstox message consumer")
        
        while self._state == ConnectionState.CONNECTED:
            try:
                message = await self._ws.recv()
                await self._process_message(message)
                
            except ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
                self._state = ConnectionState.RECONNECTING
                await self._handle_reconnect()
                break
                
            except asyncio.CancelledError:
                break
                
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                self._error_count += 1
    
    async def _process_message(self, message: bytes) -> None:
        """Process incoming WebSocket message."""
        try:
            # Decode protobuf if available
            if UPSTOX_PROTO_AVAILABLE and pb:
                feed_response = pb.FeedResponse()
                feed_response.ParseFromString(message)
                data = MessageToDict(feed_response)
            else:
                # Fallback to JSON (less efficient)
                data = json.loads(message.decode("utf-8"))
            
            # Process feeds
            feeds = data.get("feeds", {})
            for instrument_key, feed_data in feeds.items():
                await self._process_feed(instrument_key, feed_data)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self._error_count += 1
    
    async def _process_feed(self, instrument_key: str, feed_data: Dict[str, Any]) -> None:
        """Process a single instrument feed."""
        try:
            # Extract data based on feed type
            tick = UpstoxTickData(
                symbol=instrument_key.split("|")[-1] if "|" in instrument_key else instrument_key,
                instrument_key=instrument_key,
                ltp=0.0,
                timestamp=datetime.now(timezone.utc),
            )
            
            # LTPC mode data
            if "ltpc" in feed_data:
                ltpc = feed_data["ltpc"]
                tick.ltp = float(ltpc.get("ltp", 0))
                tick.ltt = int(ltpc.get("ltt", 0))
                tick.ltq = int(ltpc.get("ltq", 0))
                tick.cp = float(ltpc.get("cp", 0))
            
            # Full feed data
            if "fullFeed" in feed_data:
                full = feed_data["fullFeed"]
                
                # Market full feed
                if "marketFF" in full:
                    market = full["marketFF"]
                    
                    # LTPC from full feed
                    if "ltpc" in market:
                        ltpc = market["ltpc"]
                        tick.ltp = float(ltpc.get("ltp", tick.ltp))
                        tick.ltt = int(ltpc.get("ltt", tick.ltt))
                        tick.ltq = int(ltpc.get("ltq", tick.ltq))
                        tick.cp = float(ltpc.get("cp", tick.cp))
                    
                    # Market depth
                    if "marketLevel" in market:
                        depth = market["marketLevel"].get("bidAskQuote", [])
                        if depth:
                            tick.bid = float(depth[0].get("bidP", 0))
                            tick.bid_qty = int(depth[0].get("bidQ", 0))
                            tick.ask = float(depth[0].get("askP", 0))
                            tick.ask_qty = int(depth[0].get("askQ", 0))
                    
                    # OHLC
                    if "marketOHLC" in market:
                        ohlc_list = market["marketOHLC"].get("ohlc", [])
                        # Get 1D (daily) OHLC if available
                        for ohlc in ohlc_list:
                            if ohlc.get("interval") == "1d":
                                tick.open = float(ohlc.get("open", 0))
                                tick.high = float(ohlc.get("high", 0))
                                tick.low = float(ohlc.get("low", 0))
                                tick.close = float(ohlc.get("close", 0))
                                tick.volume = int(ohlc.get("vol", 0))
                                break
                    
                    # Additional fields
                    tick.atp = float(market.get("atp", 0))
                    tick.oi = float(market.get("oi", 0))
                    tick.iv = float(market.get("iv", 0))
                    tick.total_buy_qty = float(market.get("tbq", 0))
                    tick.total_sell_qty = float(market.get("tsq", 0))
                    tick.volume = int(market.get("vtt", tick.volume))
                    
                    # Option Greeks
                    if "optionGreeks" in market:
                        greeks = market["optionGreeks"]
                        tick.delta = float(greeks.get("delta", 0))
                        tick.theta = float(greeks.get("theta", 0))
                        tick.gamma = float(greeks.get("gamma", 0))
                        tick.vega = float(greeks.get("vega", 0))
                        tick.rho = float(greeks.get("rho", 0))
                
                # Index full feed
                elif "indexFF" in full:
                    index = full["indexFF"]
                    
                    if "ltpc" in index:
                        ltpc = index["ltpc"]
                        tick.ltp = float(ltpc.get("ltp", tick.ltp))
                        tick.ltt = int(ltpc.get("ltt", tick.ltt))
                        tick.cp = float(ltpc.get("cp", tick.cp))
                    
                    if "marketOHLC" in index:
                        ohlc_list = index["marketOHLC"].get("ohlc", [])
                        for ohlc in ohlc_list:
                            if ohlc.get("interval") == "1d":
                                tick.open = float(ohlc.get("open", 0))
                                tick.high = float(ohlc.get("high", 0))
                                tick.low = float(ohlc.get("low", 0))
                                tick.close = float(ohlc.get("close", 0))
                                break
            
            # First level with Greeks
            if "firstLevelWithGreeks" in feed_data:
                fl = feed_data["firstLevelWithGreeks"]
                
                if "ltpc" in fl:
                    ltpc = fl["ltpc"]
                    tick.ltp = float(ltpc.get("ltp", tick.ltp))
                    tick.ltt = int(ltpc.get("ltt", tick.ltt))
                    tick.ltq = int(ltpc.get("ltq", tick.ltq))
                    tick.cp = float(ltpc.get("cp", tick.cp))
                
                if "firstDepth" in fl:
                    depth = fl["firstDepth"]
                    tick.bid = float(depth.get("bidP", 0))
                    tick.bid_qty = int(depth.get("bidQ", 0))
                    tick.ask = float(depth.get("askP", 0))
                    tick.ask_qty = int(depth.get("askQ", 0))
                
                if "optionGreeks" in fl:
                    greeks = fl["optionGreeks"]
                    tick.delta = float(greeks.get("delta", 0))
                    tick.theta = float(greeks.get("theta", 0))
                    tick.gamma = float(greeks.get("gamma", 0))
                    tick.vega = float(greeks.get("vega", 0))
                    tick.rho = float(greeks.get("rho", 0))
                
                tick.volume = int(fl.get("vtt", tick.volume))
                tick.oi = float(fl.get("oi", tick.oi))
                tick.iv = float(fl.get("iv", tick.iv))
            
            # Update stats
            self._tick_count += 1
            self._last_tick_time = tick.timestamp
            
            # Call user callback
            if self._on_tick:
                await self._on_tick(tick)
            
            # Publish to event bus
            if self._event_bus:
                event = TickEvent(
                    event_type=EventType.TICK_RECEIVED,
                    instrument_id=instrument_key,
                    symbol=tick.symbol,
                    ltp=tick.ltp,
                    bid=tick.bid,
                    ask=tick.ask,
                    volume=tick.volume,
                    oi=int(tick.oi),
                    source="upstox_ws",
                )
                await self._event_bus.publish(event)
                
        except Exception as e:
            logger.error(f"Error processing feed for {instrument_key}: {e}")
    
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
            self._pending_subscriptions = self._subscribed_instruments.copy()
            self._subscribed_instruments.clear()
        
        # Attempt reconnection
        success = await self.connect()
        
        if not success:
            self._state = ConnectionState.RECONNECTING
            await self._handle_reconnect()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket statistics."""
        return {
            "state": self._state.value,
            "data_mode": self._data_mode.value,
            "subscribed_instruments": len(self._subscribed_instruments),
            "tick_count": self._tick_count,
            "last_tick_time": self._last_tick_time.isoformat() if self._last_tick_time else None,
            "error_count": self._error_count,
            "reconnect_attempts": self._reconnect_attempts,
            "connected_at": self._connected_at.isoformat() if self._connected_at else None,
            "max_instruments": self.MAX_INSTRUMENTS,
        }


# =============================================================================
# Factory Function
# =============================================================================

async def create_upstox_websocket(
    access_token: str,
    instruments: Optional[List[str]] = None,
    data_mode: DataMode = DataMode.FULL_D5,
    on_tick: Optional[Callable[[UpstoxTickData], Coroutine[Any, Any, None]]] = None,
) -> UpstoxWebSocketAdapter:
    """
    Factory function to create and connect an Upstox WebSocket adapter.
    
    Args:
        access_token: Upstox API access token (required)
        instruments: Optional list of instruments to subscribe on connect
        data_mode: Type of data to receive
        on_tick: Optional callback for tick data
        
    Returns:
        Connected UpstoxWebSocketAdapter instance
        
    Example:
        # Get token first
        from app.brokers.upstox_data import get_upstox_auth
        auth = get_upstox_auth()
        token = await auth.authenticate()
        
        # Create WebSocket
        ws = await create_upstox_websocket(
            access_token=token,
            instruments=["NSE_EQ|INE002A01018", "NSE_INDEX|Nifty 50"],
        )
    """
    adapter = UpstoxWebSocketAdapter(
        access_token=access_token,
        data_mode=data_mode,
        on_tick=on_tick,
    )
    
    success = await adapter.connect()
    if not success:
        raise ConnectionError("Failed to connect to Upstox WebSocket")
    
    if instruments:
        await adapter.subscribe(instruments)
    
    return adapter


__all__ = [
    "ConnectionState",
    "DataMode",
    "UpstoxTickData",
    "UpstoxWebSocketAdapter",
    "create_upstox_websocket",
]
