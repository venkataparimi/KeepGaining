"""
Data Feed Orchestrator

Coordinates multiple data sources for comprehensive market coverage:
- Fyers WebSocket for real-time streaming (subscribed symbols)
- Upstox batch API for universe scanning (minute-by-minute)
- Symbol subscription management
- Data source failover
- Gap detection and backfill

Data Flow:
    Fyers WebSocket (50-200 symbols) → TickEvent → CandleBuilder
                        ↓
    Upstox Batch (1000+ symbols) → CandleEvent (direct 1m candles)
                        ↓
              IndicatorService → StrategyEngine
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

from app.core.events import EventBus


class DataSourceType(str, Enum):
    """Data source types."""
    WEBSOCKET = "websocket"
    BATCH = "batch"
    HISTORICAL = "historical"


class SubscriptionPriority(str, Enum):
    """Subscription priority levels."""
    HIGH = "high"      # Active positions, triggered signals
    MEDIUM = "medium"  # Watchlist, strategy universe
    LOW = "low"        # Universe scan only


@dataclass
class SymbolSubscription:
    """Subscription details for a symbol."""
    symbol: str
    exchange: str
    priority: SubscriptionPriority
    data_source: DataSourceType
    subscribed_at: datetime
    last_update: Optional[datetime] = None
    update_count: int = 0
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataSourceStatus:
    """Status of a data source."""
    source_type: DataSourceType
    connected: bool
    last_heartbeat: Optional[datetime] = None
    symbols_count: int = 0
    updates_per_minute: int = 0
    error_count: int = 0
    last_error: Optional[str] = None


class DataFeedOrchestrator:
    """
    Orchestrates data feeds from multiple sources.
    
    Responsibilities:
    - Manage symbol subscriptions across data sources
    - Route symbols to appropriate data source based on priority
    - Monitor data source health and handle failover
    - Coordinate batch scans for universe coverage
    - Detect gaps and trigger backfill
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        websocket_max_symbols: int = 200,
        batch_scan_interval_seconds: int = 60
    ):
        self.event_bus = event_bus
        self.websocket_max_symbols = websocket_max_symbols
        self.batch_scan_interval = batch_scan_interval_seconds
        self.logger = logging.getLogger(__name__)
        self._running = False
        
        # Subscriptions
        self._subscriptions: Dict[str, SymbolSubscription] = {}
        self._websocket_symbols: Set[str] = set()
        self._batch_symbols: Set[str] = set()
        
        # Data source references (injected)
        self._websocket_adapter = None
        self._batch_service = None
        
        # Data source status
        self._source_status: Dict[DataSourceType, DataSourceStatus] = {
            DataSourceType.WEBSOCKET: DataSourceStatus(
                source_type=DataSourceType.WEBSOCKET,
                connected=False
            ),
            DataSourceType.BATCH: DataSourceStatus(
                source_type=DataSourceType.BATCH,
                connected=False
            )
        }
        
        # Background tasks
        self._batch_scan_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._rebalance_task: Optional[asyncio.Task] = None
        
        # IST timezone
        self._tz = ZoneInfo("Asia/Kolkata")
        
        # Market hours
        self._market_open = time(9, 15)
        self._market_close = time(15, 30)
        self._pre_market_start = time(9, 0)
        
        # Universe management
        self._universe: Set[str] = set()
        self._position_symbols: Set[str] = set()
        self._watchlist: Set[str] = set()
    
    def set_websocket_adapter(self, adapter) -> None:
        """Set the WebSocket adapter reference."""
        self._websocket_adapter = adapter
        self.logger.info("WebSocket adapter configured")
    
    def set_batch_service(self, service) -> None:
        """Set the batch data service reference."""
        self._batch_service = service
        self.logger.info("Batch data service configured")
    
    async def start(self) -> None:
        """Start the data feed orchestrator."""
        if self._running:
            return
        
        self._running = True
        self.logger.info("Starting data feed orchestrator...")
        
        # Subscribe to relevant events
        await self.event_bus.subscribe(
            "position_update",
            self._on_position_update,
            consumer_group="data_orchestrator"
        )
        
        await self.event_bus.subscribe(
            "websocket_status",
            self._on_websocket_status,
            consumer_group="data_orchestrator"
        )
        
        # Start background tasks
        self._batch_scan_task = asyncio.create_task(self._batch_scan_loop())
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self._rebalance_task = asyncio.create_task(self._subscription_rebalance_loop())
        
        self.logger.info("Data feed orchestrator started")
    
    async def stop(self) -> None:
        """Stop the data feed orchestrator."""
        self._running = False
        
        # Cancel background tasks
        for task in [self._batch_scan_task, self._health_check_task, self._rebalance_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Unsubscribe from WebSocket
        if self._websocket_adapter:
            await self._websocket_adapter.unsubscribe_all()
        
        await self.event_bus.unsubscribe("position_update", "data_orchestrator")
        await self.event_bus.unsubscribe("websocket_status", "data_orchestrator")
        
        self.logger.info("Data feed orchestrator stopped")
    
    async def set_universe(self, symbols: List[str]) -> None:
        """
        Set the trading universe.
        
        Args:
            symbols: List of symbols to track
        """
        self._universe = set(symbols)
        self.logger.info(f"Universe set with {len(symbols)} symbols")
        
        # Trigger subscription rebalance
        await self._rebalance_subscriptions()
    
    async def add_to_watchlist(self, symbol: str) -> None:
        """Add symbol to watchlist (gets WebSocket priority)."""
        self._watchlist.add(symbol)
        
        # Subscribe via WebSocket if available
        await self._subscribe_symbol(symbol, SubscriptionPriority.MEDIUM)
    
    async def remove_from_watchlist(self, symbol: str) -> None:
        """Remove symbol from watchlist."""
        self._watchlist.discard(symbol)
        
        # Rebalance to potentially downgrade to batch
        if symbol not in self._position_symbols:
            await self._rebalance_subscriptions()
    
    async def _subscribe_symbol(
        self,
        symbol: str,
        priority: SubscriptionPriority
    ) -> bool:
        """
        Subscribe to a symbol with given priority.
        
        High priority → WebSocket
        Medium priority → WebSocket if space, else batch
        Low priority → Batch
        """
        # Determine data source based on priority and capacity
        if priority == SubscriptionPriority.HIGH:
            data_source = DataSourceType.WEBSOCKET
        elif priority == SubscriptionPriority.MEDIUM:
            if len(self._websocket_symbols) < self.websocket_max_symbols:
                data_source = DataSourceType.WEBSOCKET
            else:
                data_source = DataSourceType.BATCH
        else:
            data_source = DataSourceType.BATCH
        
        # Create subscription record
        subscription = SymbolSubscription(
            symbol=symbol,
            exchange=symbol.split(":")[0] if ":" in symbol else "NSE",
            priority=priority,
            data_source=data_source,
            subscribed_at=datetime.now(self._tz)
        )
        
        self._subscriptions[symbol] = subscription
        
        # Subscribe to appropriate source
        if data_source == DataSourceType.WEBSOCKET:
            await self._subscribe_websocket(symbol)
        else:
            self._batch_symbols.add(symbol)
        
        self.logger.debug(f"Subscribed {symbol} via {data_source.value} ({priority.value})")
        return True
    
    async def _subscribe_websocket(self, symbol: str) -> bool:
        """Subscribe symbol to WebSocket."""
        if not self._websocket_adapter:
            self.logger.warning("WebSocket adapter not configured")
            return False
        
        if symbol in self._websocket_symbols:
            return True
        
        if len(self._websocket_symbols) >= self.websocket_max_symbols:
            self.logger.warning("WebSocket subscription limit reached")
            return False
        
        try:
            success = await self._websocket_adapter.subscribe([symbol])
            if success:
                self._websocket_symbols.add(symbol)
                return True
        except Exception as e:
            self.logger.error(f"Failed to subscribe {symbol} to WebSocket: {e}")
        
        return False
    
    async def _unsubscribe_websocket(self, symbol: str) -> bool:
        """Unsubscribe symbol from WebSocket."""
        if not self._websocket_adapter:
            return False
        
        if symbol not in self._websocket_symbols:
            return True
        
        try:
            success = await self._websocket_adapter.unsubscribe([symbol])
            if success:
                self._websocket_symbols.discard(symbol)
                return True
        except Exception as e:
            self.logger.error(f"Failed to unsubscribe {symbol} from WebSocket: {e}")
        
        return False
    
    async def _rebalance_subscriptions(self) -> None:
        """
        Rebalance subscriptions based on current priorities.
        
        Priority order:
        1. Position symbols → Always WebSocket
        2. Watchlist symbols → WebSocket if space
        3. Universe symbols → Batch
        """
        # Get all high priority symbols
        high_priority = self._position_symbols.copy()
        
        # Medium priority = watchlist - positions
        medium_priority = self._watchlist - self._position_symbols
        
        # Low priority = universe - positions - watchlist
        low_priority = self._universe - self._position_symbols - self._watchlist
        
        # Calculate WebSocket allocation
        websocket_capacity = self.websocket_max_symbols - len(high_priority)
        
        # Allocate medium priority to WebSocket
        websocket_medium = set()
        if websocket_capacity > 0:
            websocket_medium = set(list(medium_priority)[:websocket_capacity])
        
        # Build target WebSocket set
        target_websocket = high_priority | websocket_medium
        
        # Symbols to add to WebSocket
        to_add = target_websocket - self._websocket_symbols
        
        # Symbols to remove from WebSocket
        to_remove = self._websocket_symbols - target_websocket
        
        # Perform changes
        for symbol in to_remove:
            await self._unsubscribe_websocket(symbol)
            self._batch_symbols.add(symbol)
        
        for symbol in to_add:
            await self._subscribe_websocket(symbol)
            self._batch_symbols.discard(symbol)
        
        # All non-WebSocket symbols go to batch
        self._batch_symbols = (
            (medium_priority - websocket_medium) | 
            low_priority | 
            (self._websocket_symbols - target_websocket)
        )
        
        self.logger.info(
            f"Rebalanced subscriptions: WebSocket={len(self._websocket_symbols)}, "
            f"Batch={len(self._batch_symbols)}"
        )
    
    async def _on_position_update(self, event: Dict[str, Any]) -> None:
        """Handle position updates to adjust subscriptions."""
        action = event.get("action")
        symbol = event.get("symbol")
        
        if action == "open":
            # Upgrade to high priority
            self._position_symbols.add(symbol)
            await self._subscribe_symbol(symbol, SubscriptionPriority.HIGH)
            
        elif action == "close":
            # Downgrade priority
            self._position_symbols.discard(symbol)
            
            if symbol in self._watchlist:
                # Downgrade to medium
                await self._subscribe_symbol(symbol, SubscriptionPriority.MEDIUM)
            else:
                # Downgrade to low (batch only)
                await self._unsubscribe_websocket(symbol)
                self._batch_symbols.add(symbol)
    
    async def _on_websocket_status(self, event: Dict[str, Any]) -> None:
        """Handle WebSocket status updates."""
        status = self._source_status[DataSourceType.WEBSOCKET]
        status.connected = event.get("connected", False)
        status.last_heartbeat = datetime.now(self._tz)
        
        if event.get("error"):
            status.error_count += 1
            status.last_error = event.get("error")
    
    async def _batch_scan_loop(self) -> None:
        """Periodically fetch batch data for non-WebSocket symbols."""
        while self._running:
            try:
                # Only during market hours
                if not self._is_market_hours():
                    await asyncio.sleep(60)
                    continue
                
                if not self._batch_service or not self._batch_symbols:
                    await asyncio.sleep(self.batch_scan_interval)
                    continue
                
                # Fetch batch quotes
                symbols = list(self._batch_symbols)
                self.logger.debug(f"Batch scan: {len(symbols)} symbols")
                
                try:
                    quotes = await self._batch_service.get_batch_quotes(symbols)
                    
                    if quotes:
                        # Update source status
                        status = self._source_status[DataSourceType.BATCH]
                        status.connected = True
                        status.last_heartbeat = datetime.now(self._tz)
                        status.symbols_count = len(symbols)
                        
                        # Publish as candle events (1-minute candles from quotes)
                        for quote in quotes:
                            await self._publish_batch_candle(quote)
                        
                except Exception as e:
                    self.logger.error(f"Batch scan failed: {e}")
                    status = self._source_status[DataSourceType.BATCH]
                    status.error_count += 1
                    status.last_error = str(e)
                
                await asyncio.sleep(self.batch_scan_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in batch scan loop: {e}")
                await asyncio.sleep(self.batch_scan_interval)
    
    async def _publish_batch_candle(self, quote: Dict[str, Any]) -> None:
        """Convert batch quote to candle event and publish."""
        symbol = quote.get("symbol", "")
        
        # Update subscription record
        if symbol in self._subscriptions:
            sub = self._subscriptions[symbol]
            sub.last_update = datetime.now(self._tz)
            sub.update_count += 1
        
        # Create 1-minute candle from quote
        candle_data = {
            "symbol": symbol,
            "exchange": quote.get("exchange", "NSE"),
            "timeframe": "1m",
            "open": quote.get("open", quote.get("ltp")),
            "high": quote.get("high", quote.get("ltp")),
            "low": quote.get("low", quote.get("ltp")),
            "close": quote.get("ltp"),
            "volume": quote.get("volume", 0),
            "timestamp": datetime.now(self._tz).isoformat(),
            "source": "batch"
        }
        
        await self.event_bus.publish("candle", candle_data)
    
    async def _health_check_loop(self) -> None:
        """Monitor data source health."""
        while self._running:
            try:
                now = datetime.now(self._tz)
                
                # Check WebSocket health
                ws_status = self._source_status[DataSourceType.WEBSOCKET]
                if ws_status.connected and ws_status.last_heartbeat:
                    time_since_heartbeat = (now - ws_status.last_heartbeat).total_seconds()
                    if time_since_heartbeat > 30:  # No heartbeat for 30s
                        self.logger.warning("WebSocket heartbeat timeout")
                        ws_status.connected = False
                        
                        # Trigger reconnection
                        if self._websocket_adapter:
                            await self._websocket_adapter.reconnect()
                
                # Check batch service health
                batch_status = self._source_status[DataSourceType.BATCH]
                if batch_status.error_count > 5:
                    self.logger.warning(
                        f"Batch service has {batch_status.error_count} errors"
                    )
                
                # Publish health status
                await self._publish_health_status()
                
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(10)
    
    async def _subscription_rebalance_loop(self) -> None:
        """Periodically rebalance subscriptions."""
        while self._running:
            try:
                # Rebalance every 5 minutes
                await asyncio.sleep(300)
                
                if self._is_market_hours():
                    await self._rebalance_subscriptions()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in rebalance loop: {e}")
                await asyncio.sleep(300)
    
    async def _publish_health_status(self) -> None:
        """Publish data feed health status."""
        await self.event_bus.publish("data_feed_status", {
            "timestamp": datetime.now(self._tz).isoformat(),
            "websocket": {
                "connected": self._source_status[DataSourceType.WEBSOCKET].connected,
                "symbols": len(self._websocket_symbols),
                "last_heartbeat": (
                    self._source_status[DataSourceType.WEBSOCKET].last_heartbeat.isoformat()
                    if self._source_status[DataSourceType.WEBSOCKET].last_heartbeat
                    else None
                ),
                "error_count": self._source_status[DataSourceType.WEBSOCKET].error_count
            },
            "batch": {
                "connected": self._source_status[DataSourceType.BATCH].connected,
                "symbols": len(self._batch_symbols),
                "last_heartbeat": (
                    self._source_status[DataSourceType.BATCH].last_heartbeat.isoformat()
                    if self._source_status[DataSourceType.BATCH].last_heartbeat
                    else None
                ),
                "error_count": self._source_status[DataSourceType.BATCH].error_count
            },
            "total_subscriptions": len(self._subscriptions),
            "position_symbols": len(self._position_symbols),
            "watchlist_symbols": len(self._watchlist),
            "universe_symbols": len(self._universe)
        })
    
    def _is_market_hours(self) -> bool:
        """Check if within market hours."""
        now = datetime.now(self._tz).time()
        return self._market_open <= now <= self._market_close
    
    def get_subscription(self, symbol: str) -> Optional[SymbolSubscription]:
        """Get subscription details for a symbol."""
        return self._subscriptions.get(symbol)
    
    def get_data_source_status(self) -> Dict[str, Any]:
        """Get status of all data sources."""
        return {
            source.value: {
                "connected": status.connected,
                "symbols_count": status.symbols_count,
                "error_count": status.error_count,
                "last_error": status.last_error,
                "last_heartbeat": (
                    status.last_heartbeat.isoformat()
                    if status.last_heartbeat else None
                )
            }
            for source, status in self._source_status.items()
        }
    
    def get_subscription_summary(self) -> Dict[str, Any]:
        """Get subscription summary."""
        return {
            "total": len(self._subscriptions),
            "websocket": len(self._websocket_symbols),
            "batch": len(self._batch_symbols),
            "by_priority": {
                "high": len([s for s in self._subscriptions.values() 
                            if s.priority == SubscriptionPriority.HIGH]),
                "medium": len([s for s in self._subscriptions.values() 
                              if s.priority == SubscriptionPriority.MEDIUM]),
                "low": len([s for s in self._subscriptions.values() 
                           if s.priority == SubscriptionPriority.LOW])
            },
            "position_symbols": list(self._position_symbols),
            "watchlist": list(self._watchlist)
        }
    
    async def backfill_history(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1m"
    ) -> List[Dict[str, Any]]:
        """
        Backfill historical data for a symbol.
        
        Uses batch service for historical data download.
        """
        if not self._batch_service:
            self.logger.error("Batch service not configured for backfill")
            return []
        
        try:
            candles = await self._batch_service.get_historical_candles(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe
            )
            
            self.logger.info(
                f"Backfilled {len(candles)} candles for {symbol} "
                f"({start_date} to {end_date})"
            )
            
            return candles
            
        except Exception as e:
            self.logger.error(f"Backfill failed for {symbol}: {e}")
            return []


# Factory function
def create_data_orchestrator(
    event_bus: EventBus,
    websocket_max_symbols: int = 200,
    batch_scan_interval: int = 60
) -> DataFeedOrchestrator:
    """Create and configure data feed orchestrator."""
    return DataFeedOrchestrator(
        event_bus=event_bus,
        websocket_max_symbols=websocket_max_symbols,
        batch_scan_interval_seconds=batch_scan_interval
    )
