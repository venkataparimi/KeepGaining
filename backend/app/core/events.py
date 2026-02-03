"""
Event Bus - Redis Streams Implementation
KeepGaining Trading Platform

Provides event-driven architecture with:
- Pub/Sub messaging via Redis Streams
- Consumer groups for reliable delivery
- Event replay and dead-letter handling
- Type-safe event definitions
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any, Callable, Coroutine, Dict, Generic, List, 
    Optional, Type, TypeVar, Union
)
import asyncio
import json
import uuid

from loguru import logger
import redis.asyncio as redis
from pydantic import BaseModel, Field

from app.core.config import settings


# =============================================================================
# Event Types & Definitions
# =============================================================================

class EventType(str, Enum):
    """All event types in the system."""
    
    # Market Data Events
    TICK_RECEIVED = "tick.received"
    CANDLE_FORMED = "candle.formed"
    INDICATOR_UPDATED = "indicator.updated"
    OPTION_CHAIN_UPDATED = "option_chain.updated"
    
    # Trading Events
    SIGNAL_GENERATED = "signal.generated"
    ORDER_PLACED = "order.placed"
    ORDER_UPDATED = "order.updated"
    ORDER_FILLED = "order.filled"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REJECTED = "order.rejected"
    TRADE_EXECUTED = "trade.executed"
    
    # Position Events
    POSITION_OPENED = "position.opened"
    POSITION_UPDATED = "position.updated"
    POSITION_CLOSED = "position.closed"
    
    # Risk Events
    RISK_LIMIT_BREACHED = "risk.limit_breached"
    STOP_LOSS_TRIGGERED = "risk.sl_triggered"
    TARGET_HIT = "risk.target_hit"
    TRAILING_SL_UPDATED = "risk.trailing_updated"
    
    # System Events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    BROKER_CONNECTED = "broker.connected"
    BROKER_DISCONNECTED = "broker.disconnected"
    WEBSOCKET_CONNECTED = "websocket.connected"
    WEBSOCKET_DISCONNECTED = "websocket.disconnected"
    
    # Strategy Events
    STRATEGY_STARTED = "strategy.started"
    STRATEGY_STOPPED = "strategy.stopped"
    STRATEGY_ERROR = "strategy.error"


class EventPriority(int, Enum):
    """Event priority levels for processing order."""
    CRITICAL = 0   # Process immediately (risk alerts, emergency exits)
    HIGH = 1       # Trading signals, order updates
    NORMAL = 2     # Standard events
    LOW = 3        # Logging, analytics


# =============================================================================
# Base Event Models
# =============================================================================

class BaseEvent(BaseModel):
    """Base event model with common fields."""
    
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    priority: EventPriority = EventPriority.NORMAL
    source: str = "unknown"
    correlation_id: Optional[str] = None  # For tracking related events
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


# Market Data Events
class TickEvent(BaseEvent):
    """Real-time tick data event."""
    event_type: EventType = EventType.TICK_RECEIVED
    
    instrument_id: str
    symbol: str
    ltp: float  # Last traded price
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    oi: Optional[int] = None  # Open interest


class CandleEvent(BaseEvent):
    """Candle formation event."""
    event_type: EventType = EventType.CANDLE_FORMED
    
    instrument_id: str
    symbol: str
    timeframe: str  # 1m, 5m, 15m, etc.
    open: float
    high: float
    low: float
    close: float
    volume: int
    is_complete: bool = True


class IndicatorEvent(BaseEvent):
    """Indicator calculation event."""
    event_type: EventType = EventType.INDICATOR_UPDATED
    
    instrument_id: str
    symbol: str
    timeframe: str
    indicators: Dict[str, float]  # e.g., {"rsi_14": 65.5, "ema_21": 1250.0}


# Trading Events
class SignalEvent(BaseEvent):
    """Trading signal event."""
    event_type: EventType = EventType.SIGNAL_GENERATED
    priority: EventPriority = EventPriority.HIGH
    
    strategy_id: str
    instrument_id: str
    symbol: str
    signal_type: str  # ENTRY_LONG, ENTRY_SHORT, EXIT
    strength: float = 100.0  # Signal strength 0-100
    price: float
    conditions_met: Dict[str, Any] = Field(default_factory=dict)
    suggested_sl: Optional[float] = None
    suggested_target: Optional[float] = None


class OrderEvent(BaseEvent):
    """Order lifecycle event."""
    event_type: EventType = EventType.ORDER_PLACED
    priority: EventPriority = EventPriority.HIGH
    
    order_id: str
    strategy_id: Optional[str] = None
    instrument_id: str
    symbol: str
    side: str  # BUY, SELL
    order_type: str  # MARKET, LIMIT, SL, SL-M
    quantity: int
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    status: str
    broker_order_id: Optional[str] = None
    rejection_reason: Optional[str] = None


class TradeEvent(BaseEvent):
    """Trade execution event."""
    event_type: EventType = EventType.TRADE_EXECUTED
    priority: EventPriority = EventPriority.HIGH
    
    trade_id: str
    order_id: str
    instrument_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    broker_trade_id: Optional[str] = None


class PositionEvent(BaseEvent):
    """Position update event."""
    event_type: EventType = EventType.POSITION_UPDATED
    
    position_id: str
    strategy_id: Optional[str] = None
    instrument_id: str
    symbol: str
    side: str  # LONG, SHORT
    quantity: int
    average_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    stop_loss: Optional[float] = None
    target: Optional[float] = None


# Risk Events
class RiskEvent(BaseEvent):
    """Risk management event."""
    event_type: EventType = EventType.RISK_LIMIT_BREACHED
    priority: EventPriority = EventPriority.CRITICAL
    
    risk_type: str  # DAILY_LOSS, MAX_POSITION, DRAWDOWN
    current_value: float
    limit_value: float
    action_taken: str  # ALERT, BLOCK_ENTRY, FORCE_EXIT
    affected_strategies: List[str] = Field(default_factory=list)


# System Events
class SystemEvent(BaseEvent):
    """System lifecycle event."""
    event_type: EventType = EventType.SYSTEM_STARTUP
    
    component: str
    status: str  # STARTED, STOPPED, ERROR
    details: Dict[str, Any] = Field(default_factory=dict)


class BrokerEvent(BaseEvent):
    """Broker connection event."""
    event_type: EventType = EventType.BROKER_CONNECTED
    
    broker_name: str
    status: str  # CONNECTED, DISCONNECTED, ERROR
    error_message: Optional[str] = None


# =============================================================================
# Event Bus Implementation
# =============================================================================

EventT = TypeVar("EventT", bound=BaseEvent)
EventHandler = Callable[[BaseEvent], Coroutine[Any, Any, None]]


@dataclass
class Subscription:
    """Event subscription details."""
    event_type: EventType
    handler: EventHandler
    consumer_group: Optional[str] = None
    priority_filter: Optional[EventPriority] = None


class EventBus:
    """
    Redis Streams based event bus for async event-driven architecture.
    
    Features:
    - Pub/Sub messaging with Redis Streams
    - Consumer groups for reliable delivery
    - Event replay support
    - Dead-letter queue handling
    - Type-safe event definitions
    """
    
    @staticmethod
    def _get_enum_value(val: Union[EventType, EventPriority, str, int]) -> str:
        """Safely get the string value from an enum or string."""
        if hasattr(val, 'value'):
            return str(val.value)
        return str(val)
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        stream_prefix: str = "kg:events:",
        max_stream_length: int = 10000,
        consumer_group: str = "keepgaining",
    ):
        self.redis_url = redis_url or settings.REDIS_URL
        self.stream_prefix = stream_prefix
        self.max_stream_length = max_stream_length
        self.consumer_group = consumer_group
        self.consumer_name = f"consumer-{uuid.uuid4().hex[:8]}"
        
        self._redis: Optional[redis.Redis] = None
        self._subscriptions: Dict[EventType, List[Subscription]] = {}
        self._running = False
        self._consumer_tasks: List[asyncio.Task] = []
    
    async def connect(self) -> None:
        """Connect to Redis."""
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info(f"Event bus connected to Redis: {self.redis_url}")
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        self._running = False
        
        # Cancel consumer tasks
        for task in self._consumer_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("Event bus disconnected from Redis")
    
    def _get_stream_name(self, event_type: Union[EventType, str]) -> str:
        """Get Redis stream name for event type."""
        # Handle both EventType enum and string (from use_enum_values=True)
        type_value = self._get_enum_value(event_type)
        return f"{self.stream_prefix}{type_value}"
    
    async def publish(
        self, 
        event: Union[BaseEvent, str],
        data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Publish an event to the event bus.
        
        Args:
            event: Either a BaseEvent object, or a string event type
            data: Optional data dict when event is a string type
            
        Returns:
            The Redis stream message ID
        """
        if not self._redis:
            await self.connect()
        
        # Handle legacy (event_type_str, data_dict) pattern
        if isinstance(event, str):
            # Resolve event type alias
            event_type = self.EVENT_TYPE_ALIASES.get(event)
            if not event_type:
                # Try to find matching EventType
                for et in EventType:
                    if et.value == event or et.name.lower() == event.lower():
                        event_type = et
                        break
                else:
                    logger.warning(f"Unknown event type for publish: {event}")
                    return ""
            
            # Create a BaseEvent with the data in metadata
            event = BaseEvent(
                event_type=event_type,
                metadata=data or {},
            )
        
        stream_name = self._get_stream_name(event.event_type)
        
        # Handle both enum and string values (use_enum_values=True)
        event_type_value = self._get_enum_value(event.event_type)
        priority_value = self._get_enum_value(event.priority)
        
        # Serialize event to dict
        event_data = {
            "data": event.model_dump_json(),
            "event_type": event_type_value,
            "timestamp": event.timestamp.isoformat(),
            "priority": str(priority_value),
        }
        
        # Add to stream with max length
        message_id = await self._redis.xadd(
            stream_name,
            event_data,
            maxlen=self.max_stream_length,
            approximate=True,
        )
        
        logger.debug(f"Published event {event.event_type}: {event.event_id} -> {message_id}")
        return message_id
    
    async def publish_many(self, events: List[BaseEvent]) -> List[str]:
        """Publish multiple events."""
        return [await self.publish(event) for event in events]
    
    # Mapping of short aliases to EventType values
    EVENT_TYPE_ALIASES = {
        "tick": EventType.TICK_RECEIVED,
        "candle": EventType.CANDLE_FORMED,
        "indicator": EventType.INDICATOR_UPDATED,
        "signal": EventType.SIGNAL_GENERATED,
        "order_filled": EventType.ORDER_FILLED,
        "order_placed": EventType.ORDER_PLACED,
        "order_updated": EventType.ORDER_UPDATED,
        "order_update": EventType.ORDER_UPDATED,  # Alias
        "order_cancelled": EventType.ORDER_CANCELLED,
        "order_rejected": EventType.ORDER_REJECTED,
        "trade_executed": EventType.TRADE_EXECUTED,
        "position_opened": EventType.POSITION_OPENED,
        "position_update": EventType.POSITION_UPDATED,
        "position_updated": EventType.POSITION_UPDATED,
        "position_closed": EventType.POSITION_CLOSED,
        "risk_limit_breached": EventType.RISK_LIMIT_BREACHED,
        "sl_triggered": EventType.STOP_LOSS_TRIGGERED,
        "target_hit": EventType.TARGET_HIT,
        "broker_connected": EventType.BROKER_CONNECTED,
        "broker_disconnected": EventType.BROKER_DISCONNECTED,
        "websocket_connected": EventType.WEBSOCKET_CONNECTED,
        "websocket_disconnected": EventType.WEBSOCKET_DISCONNECTED,
        "websocket_status": EventType.WEBSOCKET_CONNECTED,  # Alias
        "circuit_breaker": EventType.RISK_LIMIT_BREACHED,   # Map to risk event
        "exit_request": EventType.ORDER_PLACED,              # Map to order event
        "signal_approved": EventType.SIGNAL_GENERATED,       # Map to signal event
        "data_feed_status": EventType.WEBSOCKET_CONNECTED,   # Alias
    }
    
    async def subscribe(
        self,
        event_type: Union[EventType, str],
        handler: EventHandler,
        consumer_group: Optional[str] = None,
        priority_filter: Optional[EventPriority] = None,
    ) -> None:
        """
        Subscribe to an event type.
        
        Args:
            event_type: The event type to subscribe to (EventType enum or string)
            handler: Async handler function
            consumer_group: Optional consumer group name
            priority_filter: Only process events with this priority or higher
        """
        # Convert string to EventType if needed
        if isinstance(event_type, str):
            # First check aliases
            if event_type in self.EVENT_TYPE_ALIASES:
                event_type = self.EVENT_TYPE_ALIASES[event_type]
            else:
                # Try to find matching EventType by value or name
                for et in EventType:
                    if et.value == event_type or et.name.lower() == event_type.lower():
                        event_type = et
                        break
                else:
                    # Unknown event type - skip
                    logger.warning(f"Unknown event type: {event_type}, skipping subscription")
                    return
        
        subscription = Subscription(
            event_type=event_type,
            handler=handler,
            consumer_group=consumer_group or self.consumer_group,
            priority_filter=priority_filter,
        )
        
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
        
        self._subscriptions[event_type].append(subscription)
        logger.info(f"Subscribed to {self._get_enum_value(event_type)}: {handler.__name__}")
    
    async def unsubscribe(
        self,
        event_type: Union[EventType, str],
        consumer_group: Optional[str] = None,
    ) -> None:
        """
        Unsubscribe from an event type.
        
        Args:
            event_type: The event type to unsubscribe from
            consumer_group: If specified, only remove subscriptions for this group
        """
        # Convert string to EventType if needed
        if isinstance(event_type, str):
            # First check aliases
            if event_type in self.EVENT_TYPE_ALIASES:
                event_type = self.EVENT_TYPE_ALIASES[event_type]
            else:
                for et in EventType:
                    if et.value == event_type or et.name.lower() == event_type.lower():
                        event_type = et
                        break
                else:
                    return  # Unknown event type, nothing to unsubscribe
        
        if event_type not in self._subscriptions:
            return
        
        if consumer_group:
            # Remove only subscriptions for this consumer group
            self._subscriptions[event_type] = [
                sub for sub in self._subscriptions[event_type]
                if sub.consumer_group != consumer_group
            ]
        else:
            # Remove all subscriptions
            del self._subscriptions[event_type]
        
        logger.info(f"Unsubscribed from {self._get_enum_value(event_type)}")
    
    async def subscribe_all(
        self,
        handler: EventHandler,
        event_types: Optional[List[EventType]] = None,
    ) -> None:
        """Subscribe to multiple event types with the same handler."""
        types_to_subscribe = event_types or list(EventType)
        for event_type in types_to_subscribe:
            await self.subscribe(event_type, handler)
    
    async def _ensure_consumer_group(self, stream_name: str, group_name: str) -> None:
        """Ensure consumer group exists for a stream."""
        try:
            await self._redis.xgroup_create(
                stream_name,
                group_name,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
    
    async def _process_message(
        self,
        stream_name: str,
        message_id: str,
        message_data: Dict[str, str],
        subscriptions: List[Subscription],
    ) -> None:
        """Process a single message from a stream."""
        try:
            # Deserialize event
            event_json = message_data.get("data")
            event_type_str = message_data.get("event_type")
            
            if not event_json or not event_type_str:
                logger.warning(f"Invalid message format: {message_id}")
                return
            
            # Parse event
            event_data = json.loads(event_json)
            event = BaseEvent.model_validate(event_data)
            
            # Call handlers
            for sub in subscriptions:
                # Check priority filter
                if sub.priority_filter and event.priority > sub.priority_filter:
                    continue
                
                try:
                    await sub.handler(event)
                except Exception as e:
                    logger.error(f"Handler error for {event.event_type}: {e}")
            
            # Acknowledge message
            await self._redis.xack(stream_name, self.consumer_group, message_id)
            
        except Exception as e:
            logger.error(f"Error processing message {message_id}: {e}")
    
    async def _consume_stream(self, event_type: EventType) -> None:
        """Consume events from a specific stream."""
        stream_name = self._get_stream_name(event_type)
        subscriptions = self._subscriptions.get(event_type, [])
        
        if not subscriptions:
            return
        
        # Ensure consumer group exists
        await self._ensure_consumer_group(stream_name, self.consumer_group)
        
        logger.info(f"Starting consumer for {self._get_enum_value(event_type)}")
        
        while self._running:
            try:
                # Read from consumer group
                messages = await self._redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={stream_name: ">"},
                    count=10,
                    block=1000,  # Block for 1 second
                )
                
                if messages:
                    for stream, stream_messages in messages:
                        for message_id, message_data in stream_messages:
                            await self._process_message(
                                stream_name,
                                message_id,
                                message_data,
                                subscriptions,
                            )
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consumer error for {self._get_enum_value(event_type)}: {e}")
                await asyncio.sleep(1)
    
    async def start_consuming(self) -> None:
        """Start consuming events from all subscribed streams."""
        if not self._redis:
            await self.connect()
        
        self._running = True
        
        # Create consumer task for each subscribed event type
        for event_type in self._subscriptions.keys():
            task = asyncio.create_task(self._consume_stream(event_type))
            self._consumer_tasks.append(task)
        
        logger.info(f"Event bus started with {len(self._consumer_tasks)} consumers")
    
    async def stop_consuming(self) -> None:
        """Stop consuming events."""
        await self.disconnect()
    
    async def replay_events(
        self,
        event_type: EventType,
        start_id: str = "0",
        end_id: str = "+",
        count: int = 100,
    ) -> List[BaseEvent]:
        """
        Replay events from a stream.
        
        Useful for rebuilding state after restart.
        """
        if not self._redis:
            await self.connect()
        
        stream_name = self._get_stream_name(event_type)
        messages = await self._redis.xrange(stream_name, start_id, end_id, count=count)
        
        events = []
        for message_id, message_data in messages:
            try:
                event_json = message_data.get("data")
                if event_json:
                    event_data = json.loads(event_json)
                    events.append(BaseEvent.model_validate(event_data))
            except Exception as e:
                logger.warning(f"Failed to replay event {message_id}: {e}")
        
        return events
    
    async def get_stream_info(self, event_type: EventType) -> Dict[str, Any]:
        """Get information about a stream."""
        if not self._redis:
            await self.connect()
        
        stream_name = self._get_stream_name(event_type)
        
        try:
            info = await self._redis.xinfo_stream(stream_name)
            return {
                "length": info.get("length", 0),
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry"),
                "groups": info.get("groups", 0),
            }
        except redis.ResponseError:
            return {"length": 0, "exists": False}


# =============================================================================
# Global Event Bus Instance
# =============================================================================

_event_bus: Optional[EventBus] = None


def get_event_bus_sync() -> EventBus:
    """
    Get or create the global event bus instance synchronously.
    
    Use this for __init__ methods where async isn't available.
    Note: This does NOT connect to Redis. Call connect() later in an async context.
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


async def get_event_bus() -> EventBus:
    """Get or create the global event bus instance with connection."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
        await _event_bus.connect()
    elif _event_bus._redis is None:
        await _event_bus.connect()
    return _event_bus


async def shutdown_event_bus() -> None:
    """Shutdown the global event bus."""
    global _event_bus
    if _event_bus:
        await _event_bus.disconnect()
        _event_bus = None


# =============================================================================
# Decorator for Event Handlers
# =============================================================================

def event_handler(
    event_type: EventType,
    priority_filter: Optional[EventPriority] = None,
):
    """
    Decorator to register an event handler.
    
    Usage:
        @event_handler(EventType.SIGNAL_GENERATED)
        async def handle_signal(event: SignalEvent):
            ...
    """
    def decorator(func: EventHandler) -> EventHandler:
        # Store handler info for later registration
        func._event_type = event_type
        func._priority_filter = priority_filter
        return func
    return decorator


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Event Types
    "EventType",
    "EventPriority",
    
    # Base Event
    "BaseEvent",
    
    # Specific Events
    "TickEvent",
    "CandleEvent",
    "IndicatorEvent",
    "SignalEvent",
    "OrderEvent",
    "TradeEvent",
    "PositionEvent",
    "RiskEvent",
    "SystemEvent",
    "BrokerEvent",
    
    # Event Bus
    "EventBus",
    "get_event_bus",
    "get_event_bus_sync",
    "shutdown_event_bus",
    
    # Decorator
    "event_handler",
]
