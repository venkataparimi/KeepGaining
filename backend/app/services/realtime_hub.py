"""
Real-Time Data Hub
KeepGaining Trading Platform

Centralized real-time data aggregation and distribution service.
Features:
- Multiple data source integration (Upstox, Fyers)
- WebSocket streaming to frontend clients
- Option chain with Greeks
- Portfolio sync and streaming
- Market scanner with customizable filters
- Price alerts
- Event aggregation and deduplication
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from enum import Enum
import uuid

from loguru import logger
from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services.upstox_enhanced import (
    UpstoxEnhancedService,
    OptionGreeks,
    OptionChain,
    MarketQuote,
    create_upstox_enhanced_service,
)


class StreamType(str, Enum):
    """Types of data streams available."""
    MARKET_DATA = "market_data"
    OPTION_CHAIN = "option_chain"
    PORTFOLIO = "portfolio"
    TRADING = "trading"
    SCANNER = "scanner"
    ALERTS = "alerts"


class DataSourcePriority(str, Enum):
    """Data source priority for redundancy."""
    UPSTOX = "upstox"
    FYERS = "fyers"


@dataclass
class PriceAlert:
    """Price alert configuration."""
    id: str
    instrument_key: str
    condition: str  # "above", "below", "cross_above", "cross_below"
    price: float
    triggered: bool = False
    triggered_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ScannerFilter:
    """Market scanner filter configuration."""
    id: str
    name: str
    conditions: List[Dict[str, Any]]  # [{field: "change_percent", op: ">", value: 5}]
    instruments: List[str]  # Universe to scan
    active: bool = True


@dataclass
class ClientConnection:
    """WebSocket client connection info."""
    id: str
    websocket: WebSocket
    subscriptions: Set[str]  # Set of instrument keys
    stream_types: Set[StreamType]
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RealTimeDataHub:
    """
    Central hub for real-time data aggregation and distribution.
    
    Responsibilities:
    - Aggregate data from multiple sources (Upstox primary, Fyers backup)
    - Manage WebSocket connections to frontend clients
    - Distribute market data, option chains, portfolio updates
    - Run market scanners
    - Manage price alerts
    - Handle source failover
    
    Usage:
        hub = RealTimeDataHub()
        await hub.initialize()
        
        # Start market data streaming
        await hub.start_market_stream(["NSE_INDEX|Nifty 50"])
        
        # Add WebSocket client
        await hub.register_client(websocket)
        
        # Subscribe client to instruments
        await hub.subscribe_client(client_id, ["NSE_INDEX|Nifty 50"])
    """
    
    def __init__(
        self,
        upstox_token: Optional[str] = None,
        fyers_token: Optional[str] = None,
    ):
        """
        Initialize the data hub.
        
        Args:
            upstox_token: Upstox access token
            fyers_token: Fyers access token (backup)
        """
        self._upstox_token = upstox_token
        self._fyers_token = fyers_token
        
        # Data services
        self._upstox_service: Optional[UpstoxEnhancedService] = None
        
        # Client connections
        self._clients: Dict[str, ClientConnection] = {}
        self._client_lock = asyncio.Lock()
        
        # Subscriptions tracking
        self._instrument_subscribers: Dict[str, Set[str]] = {}  # instrument -> client_ids
        self._option_chain_cache: Dict[str, OptionChain] = {}
        self._quote_cache: Dict[str, MarketQuote] = {}
        
        # Alerts
        self._alerts: Dict[str, PriceAlert] = {}
        self._previous_prices: Dict[str, float] = {}
        
        # Scanners
        self._scanners: Dict[str, ScannerFilter] = {}
        self._scanner_results: Dict[str, List[str]] = {}  # scanner_id -> matching instruments
        
        # State
        self._initialized = False
        self._market_stream_active = False
        self._portfolio_stream_active = False
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._scanner_task: Optional[asyncio.Task] = None
        self._option_chain_task: Optional[asyncio.Task] = None
        
        # Stats
        self._messages_sent = 0
        self._messages_received = 0
    
    async def initialize(self) -> bool:
        """
        Initialize the data hub with configured services.
        
        Returns:
            True if initialization successful.
        """
        try:
            # Initialize Upstox service
            if self._upstox_token:
                self._upstox_service = await create_upstox_enhanced_service(
                    access_token=self._upstox_token
                )
                logger.info("✓ Upstox service initialized")
            else:
                logger.warning("No Upstox token provided")
            
            # Start background tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            self._initialized = True
            logger.info("✓ Real-Time Data Hub initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Data Hub: {e}")
            return False
    
    async def shutdown(self) -> None:
        """Shutdown the data hub and cleanup resources."""
        logger.info("Shutting down Data Hub...")
        
        # Cancel background tasks
        for task in [self._heartbeat_task, self._scanner_task, self._option_chain_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Stop streams
        if self._upstox_service:
            await self._upstox_service.stop_market_stream()
            await self._upstox_service.stop_portfolio_stream()
        
        # Close client connections
        async with self._client_lock:
            for client in list(self._clients.values()):
                try:
                    await client.websocket.close()
                except Exception:
                    pass
            self._clients.clear()
        
        self._initialized = False
        logger.info("Data Hub shutdown complete")
    
    # =========================================================================
    # WebSocket Client Management
    # =========================================================================
    
    async def register_client(self, websocket: WebSocket) -> str:
        """
        Register a new WebSocket client.
        
        Args:
            websocket: FastAPI WebSocket connection
            
        Returns:
            Client ID for future reference.
        """
        client_id = str(uuid.uuid4())[:8]
        
        client = ClientConnection(
            id=client_id,
            websocket=websocket,
            subscriptions=set(),
            stream_types={StreamType.MARKET_DATA},  # Default stream
        )
        
        async with self._client_lock:
            self._clients[client_id] = client
        
        logger.info(f"Client {client_id} connected")
        
        # Send welcome message
        await self._send_to_client(client_id, {
            "type": "connected",
            "client_id": client_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        return client_id
    
    async def unregister_client(self, client_id: str) -> None:
        """Unregister a WebSocket client."""
        async with self._client_lock:
            if client_id in self._clients:
                client = self._clients.pop(client_id)
                
                # Remove from all instrument subscriptions
                for instrument in client.subscriptions:
                    if instrument in self._instrument_subscribers:
                        self._instrument_subscribers[instrument].discard(client_id)
                
                logger.info(f"Client {client_id} disconnected")
    
    async def subscribe_client(
        self,
        client_id: str,
        instruments: List[str],
        stream_type: StreamType = StreamType.MARKET_DATA,
    ) -> bool:
        """
        Subscribe a client to instruments.
        
        Args:
            client_id: Client ID
            instruments: List of instrument keys
            stream_type: Type of stream to subscribe to
            
        Returns:
            True if successful.
        """
        async with self._client_lock:
            if client_id not in self._clients:
                return False
            
            client = self._clients[client_id]
            client.subscriptions.update(instruments)
            client.stream_types.add(stream_type)
            
            # Update instrument subscribers
            for instrument in instruments:
                if instrument not in self._instrument_subscribers:
                    self._instrument_subscribers[instrument] = set()
                self._instrument_subscribers[instrument].add(client_id)
        
        # Subscribe to data source if not already
        await self._ensure_instrument_subscription(instruments)
        
        # Send current cached data
        for instrument in instruments:
            if instrument in self._quote_cache:
                await self._send_to_client(client_id, {
                    "type": "quote",
                    "data": self._quote_cache[instrument].to_dict(),
                })
        
        logger.info(f"Client {client_id} subscribed to {len(instruments)} instruments")
        return True
    
    async def unsubscribe_client(
        self,
        client_id: str,
        instruments: List[str],
    ) -> bool:
        """Unsubscribe a client from instruments."""
        async with self._client_lock:
            if client_id not in self._clients:
                return False
            
            client = self._clients[client_id]
            client.subscriptions.difference_update(instruments)
            
            for instrument in instruments:
                if instrument in self._instrument_subscribers:
                    self._instrument_subscribers[instrument].discard(client_id)
        
        return True
    
    async def _send_to_client(self, client_id: str, message: Dict[str, Any]) -> bool:
        """Send a message to a specific client."""
        async with self._client_lock:
            if client_id not in self._clients:
                return False
            
            client = self._clients[client_id]
        
        try:
            await client.websocket.send_json(message)
            self._messages_sent += 1
            return True
        except Exception as e:
            logger.error(f"Error sending to client {client_id}: {e}")
            await self.unregister_client(client_id)
            return False
    
    async def _broadcast_to_subscribers(
        self,
        instrument: str,
        message: Dict[str, Any],
    ) -> int:
        """Broadcast a message to all subscribers of an instrument."""
        if instrument not in self._instrument_subscribers:
            return 0
        
        sent_count = 0
        for client_id in list(self._instrument_subscribers[instrument]):
            if await self._send_to_client(client_id, message):
                sent_count += 1
        
        return sent_count
    
    async def broadcast_all(self, message: Dict[str, Any]) -> int:
        """Broadcast a message to all connected clients."""
        sent_count = 0
        async with self._client_lock:
            client_ids = list(self._clients.keys())
        
        for client_id in client_ids:
            if await self._send_to_client(client_id, message):
                sent_count += 1
        
        return sent_count
    
    # =========================================================================
    # Market Data Streaming
    # =========================================================================
    
    async def start_market_stream(
        self,
        instruments: List[str],
        mode: str = "full",
    ) -> bool:
        """
        Start market data streaming for instruments.
        
        Args:
            instruments: List of instrument keys
            mode: Data mode (ltpc, full, option_greeks)
            
        Returns:
            True if stream started.
        """
        if not self._upstox_service:
            logger.error("Upstox service not available")
            return False
        
        success = await self._upstox_service.start_market_stream(
            instruments=instruments,
            mode=mode,
            on_tick=self._handle_market_tick,
        )
        
        if success:
            self._market_stream_active = True
            logger.info(f"Market stream started for {len(instruments)} instruments")
        
        return success
    
    async def stop_market_stream(self) -> None:
        """Stop market data streaming."""
        if self._upstox_service:
            await self._upstox_service.stop_market_stream()
        self._market_stream_active = False
    
    async def _handle_market_tick(self, tick_data: Dict[str, Any]) -> None:
        """Handle incoming market tick from data source."""
        self._messages_received += 1
        
        instrument_key = tick_data.get("instrument_key", "")
        
        # Parse tick data
        ltp = 0.0
        volume = 0
        oi = 0.0
        
        # Handle different feed formats
        if "ltpc" in tick_data:
            ltpc = tick_data["ltpc"]
            ltp = float(ltpc.get("ltp", 0))
        elif "fullFeed" in tick_data:
            full = tick_data["fullFeed"]
            if "marketFF" in full and "ltpc" in full["marketFF"]:
                ltp = float(full["marketFF"]["ltpc"].get("ltp", 0))
            if "marketFF" in full:
                volume = int(full["marketFF"].get("vtt", 0))
                oi = float(full["marketFF"].get("oi", 0))
        
        # Update cache
        if instrument_key in self._quote_cache:
            self._quote_cache[instrument_key].ltp = ltp
            self._quote_cache[instrument_key].volume = volume
            self._quote_cache[instrument_key].oi = oi
            self._quote_cache[instrument_key].timestamp = datetime.now(timezone.utc)
        else:
            self._quote_cache[instrument_key] = MarketQuote(
                instrument_key=instrument_key,
                symbol=instrument_key.split("|")[-1] if "|" in instrument_key else instrument_key,
                ltp=ltp,
                volume=volume,
                oi=oi,
            )
        
        # Check alerts
        await self._check_price_alerts(instrument_key, ltp)
        
        # Broadcast to subscribers
        message = {
            "type": "tick",
            "instrument_key": instrument_key,
            "ltp": ltp,
            "volume": volume,
            "oi": oi,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        await self._broadcast_to_subscribers(instrument_key, message)
    
    async def _ensure_instrument_subscription(self, instruments: List[str]) -> None:
        """Ensure instruments are subscribed at the data source."""
        if not self._upstox_service or not self._market_stream_active:
            return
        
        self._upstox_service.subscribe_instruments(instruments)
    
    # =========================================================================
    # Option Chain
    # =========================================================================
    
    async def get_option_chain(
        self,
        underlying_key: str,
        expiry_date: str,
    ) -> Optional[OptionChain]:
        """
        Get option chain for an underlying.
        
        Args:
            underlying_key: Underlying instrument key
            expiry_date: Expiry date (YYYY-MM-DD)
            
        Returns:
            OptionChain with all strikes and Greeks.
        """
        if not self._upstox_service:
            return None
        
        cache_key = f"{underlying_key}_{expiry_date}"
        
        # Check cache (valid for 30 seconds)
        if cache_key in self._option_chain_cache:
            cached = self._option_chain_cache[cache_key]
            age = (datetime.now(timezone.utc) - cached.timestamp).seconds
            if age < 30:
                return cached
        
        # Fetch fresh data
        chain = await self._upstox_service.get_option_chain(
            underlying_key=underlying_key,
            expiry_date=expiry_date,
        )
        
        if chain:
            self._option_chain_cache[cache_key] = chain
        
        return chain
    
    async def get_option_expiries(self, underlying_key: str) -> List[date]:
        """Get available expiry dates for an underlying."""
        if not self._upstox_service:
            return []
        
        return await self._upstox_service.get_option_expiries(underlying_key)
    
    async def subscribe_option_chain(
        self,
        client_id: str,
        underlying_key: str,
        expiry_date: str,
        refresh_interval: int = 5,
    ) -> bool:
        """
        Subscribe client to option chain updates.
        
        Args:
            client_id: Client ID
            underlying_key: Underlying instrument key
            expiry_date: Expiry date
            refresh_interval: Seconds between updates
            
        Returns:
            True if subscription successful.
        """
        async with self._client_lock:
            if client_id not in self._clients:
                return False
            
            client = self._clients[client_id]
            client.stream_types.add(StreamType.OPTION_CHAIN)
        
        # Start option chain refresh task if not running
        if not self._option_chain_task or self._option_chain_task.done():
            self._option_chain_task = asyncio.create_task(
                self._option_chain_refresh_loop()
            )
        
        # Send initial data
        chain = await self.get_option_chain(underlying_key, expiry_date)
        if chain:
            await self._send_to_client(client_id, {
                "type": "option_chain",
                "data": chain.to_dict(),
            })
        
        return True
    
    async def _option_chain_refresh_loop(self) -> None:
        """Background task to refresh option chains."""
        while True:
            try:
                await asyncio.sleep(5)  # Refresh every 5 seconds
                
                # Refresh cached option chains
                for cache_key in list(self._option_chain_cache.keys()):
                    parts = cache_key.rsplit("_", 1)
                    if len(parts) == 2:
                        underlying_key, expiry_date = parts
                        chain = await self.get_option_chain(underlying_key, expiry_date)
                        
                        if chain:
                            # Broadcast to clients subscribed to option chain
                            message = {
                                "type": "option_chain",
                                "data": chain.to_dict(),
                            }
                            
                            async with self._client_lock:
                                for client in self._clients.values():
                                    if StreamType.OPTION_CHAIN in client.stream_types:
                                        await self._send_to_client(client.id, message)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Option chain refresh error: {e}")
                await asyncio.sleep(5)
    
    # =========================================================================
    # Portfolio Streaming
    # =========================================================================
    
    async def start_portfolio_stream(
        self,
        on_update: Optional[Callable] = None,
    ) -> bool:
        """Start portfolio streaming (orders, positions)."""
        if not self._upstox_service:
            return False
        
        success = await self._upstox_service.start_portfolio_stream(
            order_update=True,
            position_update=True,
            on_update=self._handle_portfolio_update,
        )
        
        if success:
            self._portfolio_stream_active = True
            logger.info("Portfolio stream started")
        
        return success
    
    async def _handle_portfolio_update(self, update) -> None:
        """Handle portfolio update from data source."""
        message = {
            "type": "portfolio_update",
            "update_type": update.update_type,
            "data": update.data,
            "timestamp": update.timestamp.isoformat(),
        }
        
        # Broadcast to clients subscribed to portfolio stream
        async with self._client_lock:
            for client in self._clients.values():
                if StreamType.PORTFOLIO in client.stream_types:
                    await self._send_to_client(client.id, message)
    
    # =========================================================================
    # Price Alerts
    # =========================================================================
    
    async def add_alert(
        self,
        instrument_key: str,
        condition: str,
        price: float,
    ) -> str:
        """
        Add a price alert.
        
        Args:
            instrument_key: Instrument to watch
            condition: Alert condition (above, below, cross_above, cross_below)
            price: Target price
            
        Returns:
            Alert ID.
        """
        alert_id = str(uuid.uuid4())[:8]
        
        self._alerts[alert_id] = PriceAlert(
            id=alert_id,
            instrument_key=instrument_key,
            condition=condition,
            price=price,
        )
        
        # Ensure instrument is subscribed
        await self._ensure_instrument_subscription([instrument_key])
        
        logger.info(f"Alert {alert_id} created: {instrument_key} {condition} {price}")
        return alert_id
    
    async def remove_alert(self, alert_id: str) -> bool:
        """Remove a price alert."""
        if alert_id in self._alerts:
            del self._alerts[alert_id]
            return True
        return False
    
    async def get_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts."""
        return [
            {
                "id": a.id,
                "instrument_key": a.instrument_key,
                "condition": a.condition,
                "price": a.price,
                "triggered": a.triggered,
                "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in self._alerts.values()
        ]
    
    async def _check_price_alerts(self, instrument_key: str, current_price: float) -> None:
        """Check and trigger price alerts."""
        previous_price = self._previous_prices.get(instrument_key, current_price)
        self._previous_prices[instrument_key] = current_price
        
        for alert in list(self._alerts.values()):
            if alert.instrument_key != instrument_key or alert.triggered:
                continue
            
            triggered = False
            
            if alert.condition == "above" and current_price >= alert.price:
                triggered = True
            elif alert.condition == "below" and current_price <= alert.price:
                triggered = True
            elif alert.condition == "cross_above":
                if previous_price < alert.price <= current_price:
                    triggered = True
            elif alert.condition == "cross_below":
                if previous_price > alert.price >= current_price:
                    triggered = True
            
            if triggered:
                alert.triggered = True
                alert.triggered_at = datetime.now(timezone.utc)
                
                # Broadcast alert
                message = {
                    "type": "alert_triggered",
                    "alert_id": alert.id,
                    "instrument_key": instrument_key,
                    "condition": alert.condition,
                    "target_price": alert.price,
                    "current_price": current_price,
                    "timestamp": alert.triggered_at.isoformat(),
                }
                
                await self.broadcast_all(message)
                logger.info(f"Alert triggered: {alert.id} - {instrument_key} {alert.condition} {alert.price}")
    
    # =========================================================================
    # Market Scanner
    # =========================================================================
    
    async def create_scanner(
        self,
        name: str,
        conditions: List[Dict[str, Any]],
        instruments: List[str],
    ) -> str:
        """
        Create a market scanner.
        
        Args:
            name: Scanner name
            conditions: List of conditions
                [{"field": "change_percent", "op": ">", "value": 5}]
            instruments: Universe to scan
            
        Returns:
            Scanner ID.
        """
        scanner_id = str(uuid.uuid4())[:8]
        
        self._scanners[scanner_id] = ScannerFilter(
            id=scanner_id,
            name=name,
            conditions=conditions,
            instruments=instruments,
        )
        
        # Ensure instruments are subscribed
        await self._ensure_instrument_subscription(instruments)
        
        # Start scanner task if not running
        if not self._scanner_task or self._scanner_task.done():
            self._scanner_task = asyncio.create_task(self._scanner_loop())
        
        logger.info(f"Scanner {scanner_id} created: {name}")
        return scanner_id
    
    async def run_scanner(self, scanner_id: str) -> List[str]:
        """Run a scanner and return matching instruments."""
        if scanner_id not in self._scanners:
            return []
        
        scanner = self._scanners[scanner_id]
        matches: List[str] = []
        
        for instrument in scanner.instruments:
            quote = self._quote_cache.get(instrument)
            if not quote:
                continue
            
            # Check all conditions
            all_match = True
            for condition in scanner.conditions:
                field = condition.get("field")
                op = condition.get("op")
                value = condition.get("value")
                
                # Get field value from quote
                quote_value = getattr(quote, field, None)
                if quote_value is None:
                    all_match = False
                    break
                
                # Apply operator
                if op == ">" and not (quote_value > value):
                    all_match = False
                elif op == "<" and not (quote_value < value):
                    all_match = False
                elif op == ">=" and not (quote_value >= value):
                    all_match = False
                elif op == "<=" and not (quote_value <= value):
                    all_match = False
                elif op == "==" and not (quote_value == value):
                    all_match = False
            
            if all_match:
                matches.append(instrument)
        
        self._scanner_results[scanner_id] = matches
        return matches
    
    async def _scanner_loop(self) -> None:
        """Background task to run scanners periodically."""
        while True:
            try:
                await asyncio.sleep(60)  # Run scanners every minute
                
                for scanner_id, scanner in self._scanners.items():
                    if not scanner.active:
                        continue
                    
                    matches = await self.run_scanner(scanner_id)
                    
                    # Broadcast scanner results
                    message = {
                        "type": "scanner_results",
                        "scanner_id": scanner_id,
                        "scanner_name": scanner.name,
                        "matches": matches,
                        "count": len(matches),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    
                    async with self._client_lock:
                        for client in self._clients.values():
                            if StreamType.SCANNER in client.stream_types:
                                await self._send_to_client(client.id, message)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scanner loop error: {e}")
                await asyncio.sleep(10)
    
    # =========================================================================
    # Background Tasks
    # =========================================================================
    
    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to clients."""
        while True:
            try:
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
                
                message = {
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "stats": {
                        "clients": len(self._clients),
                        "instruments": len(self._quote_cache),
                        "messages_sent": self._messages_sent,
                        "messages_received": self._messages_received,
                    },
                }
                
                await self.broadcast_all(message)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    # =========================================================================
    # Status & Stats
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get hub status."""
        return {
            "initialized": self._initialized,
            "market_stream_active": self._market_stream_active,
            "portfolio_stream_active": self._portfolio_stream_active,
            "connected_clients": len(self._clients),
            "subscribed_instruments": len(self._instrument_subscribers),
            "cached_quotes": len(self._quote_cache),
            "cached_option_chains": len(self._option_chain_cache),
            "active_alerts": len([a for a in self._alerts.values() if not a.triggered]),
            "active_scanners": len([s for s in self._scanners.values() if s.active]),
            "messages_sent": self._messages_sent,
            "messages_received": self._messages_received,
            "upstox_status": self._upstox_service.get_status() if self._upstox_service else None,
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_data_hub: Optional[RealTimeDataHub] = None


async def get_data_hub() -> RealTimeDataHub:
    """Get the singleton data hub instance."""
    global _data_hub
    
    if _data_hub is None:
        _data_hub = RealTimeDataHub()
    
    return _data_hub


async def initialize_data_hub(
    upstox_token: Optional[str] = None,
    fyers_token: Optional[str] = None,
) -> RealTimeDataHub:
    """Initialize the data hub with tokens."""
    global _data_hub
    
    _data_hub = RealTimeDataHub(
        upstox_token=upstox_token,
        fyers_token=fyers_token,
    )
    
    await _data_hub.initialize()
    return _data_hub


__all__ = [
    "StreamType",
    "PriceAlert",
    "ScannerFilter",
    "ClientConnection",
    "RealTimeDataHub",
    "get_data_hub",
    "initialize_data_hub",
]
