"""
Event Subscriber Manager
KeepGaining Trading Platform

Manages event subscriptions and handler registration.
Provides decorator-based subscription pattern.
"""

import asyncio
from functools import wraps
from typing import Callable, Coroutine, Any, Dict, List, Optional, Type

from loguru import logger

from app.core.events import (
    EventBus,
    EventType,
    EventPriority,
    get_event_bus,
    BaseEvent,
    TickEvent,
    CandleEvent,
    SignalEvent,
    OrderEvent,
    TradeEvent,
    PositionEvent,
    RiskEvent,
)


# Type alias for event handlers
EventHandler = Callable[[BaseEvent], Coroutine[Any, Any, None]]


class EventSubscriberManager:
    """
    Manages event subscriptions across the application.
    
    Features:
    - Decorator-based handler registration
    - Automatic event bus connection
    - Handler grouping by component
    - Graceful startup/shutdown
    """
    
    def __init__(self):
        self._handlers: Dict[EventType, List[EventHandler]] = {}
        self._event_bus: Optional[EventBus] = None
        self._running = False
    
    def subscribe(
        self,
        event_type: EventType,
        priority_filter: Optional[EventPriority] = None,
    ):
        """
        Decorator to register an event handler.
        
        Usage:
            @subscriber.subscribe(EventType.SIGNAL_GENERATED)
            async def handle_signal(event: SignalEvent):
                ...
        """
        def decorator(handler: EventHandler) -> EventHandler:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            
            # Store handler with metadata
            handler._event_type = event_type
            handler._priority_filter = priority_filter
            self._handlers[event_type].append(handler)
            
            logger.debug(f"Registered handler {handler.__name__} for {event_type.value}")
            return handler
        
        return decorator
    
    def subscribe_many(self, event_types: List[EventType]):
        """
        Decorator to register handler for multiple event types.
        
        Usage:
            @subscriber.subscribe_many([EventType.ORDER_PLACED, EventType.ORDER_FILLED])
            async def handle_order(event: OrderEvent):
                ...
        """
        def decorator(handler: EventHandler) -> EventHandler:
            for event_type in event_types:
                if event_type not in self._handlers:
                    self._handlers[event_type] = []
                self._handlers[event_type].append(handler)
            return handler
        
        return decorator
    
    async def start(self) -> None:
        """Start the event subscriber manager."""
        if self._running:
            return
        
        self._event_bus = await get_event_bus()
        
        # Register all handlers with the event bus
        for event_type, handlers in self._handlers.items():
            for handler in handlers:
                priority_filter = getattr(handler, '_priority_filter', None)
                await self._event_bus.subscribe(
                    event_type=event_type,
                    handler=handler,
                    priority_filter=priority_filter,
                )
        
        # Start consuming events
        await self._event_bus.start_consuming()
        self._running = True
        
        logger.info(
            f"Event subscriber started with {sum(len(h) for h in self._handlers.values())} handlers"
        )
    
    async def stop(self) -> None:
        """Stop the event subscriber manager."""
        if self._event_bus:
            await self._event_bus.stop_consuming()
        self._running = False
        logger.info("Event subscriber stopped")
    
    @property
    def registered_handlers(self) -> Dict[str, int]:
        """Get count of registered handlers by event type."""
        return {
            event_type.value: len(handlers)
            for event_type, handlers in self._handlers.items()
        }


# Global subscriber instance
subscriber = EventSubscriberManager()


# =============================================================================
# Example Built-in Handlers
# =============================================================================

@subscriber.subscribe(EventType.SIGNAL_GENERATED, priority_filter=EventPriority.HIGH)
async def log_signal(event: SignalEvent) -> None:
    """Log all generated signals."""
    logger.info(
        f"[SIGNAL] {event.signal_type} | {event.symbol} | "
        f"Price: {event.price} | Strength: {event.strength}%"
    )


@subscriber.subscribe(EventType.ORDER_FILLED)
async def log_order_filled(event: OrderEvent) -> None:
    """Log filled orders."""
    logger.info(
        f"[ORDER FILLED] {event.side} {event.quantity} {event.symbol} | "
        f"Order ID: {event.order_id}"
    )


@subscriber.subscribe(EventType.POSITION_OPENED)
async def log_position_opened(event: PositionEvent) -> None:
    """Log new positions."""
    logger.info(
        f"[POSITION OPENED] {event.side} {event.quantity} {event.symbol} | "
        f"Entry: {event.average_price} | SL: {event.stop_loss} | Target: {event.target}"
    )


@subscriber.subscribe(EventType.POSITION_CLOSED)
async def log_position_closed(event: PositionEvent) -> None:
    """Log closed positions."""
    logger.info(
        f"[POSITION CLOSED] {event.symbol} | P&L: {event.realized_pnl}"
    )


@subscriber.subscribe(EventType.RISK_LIMIT_BREACHED)
async def handle_risk_breach(event: RiskEvent) -> None:
    """Handle risk limit breaches."""
    logger.warning(
        f"[RISK ALERT] {event.risk_type} | "
        f"Current: {event.current_value} | Limit: {event.limit_value} | "
        f"Action: {event.action_taken}"
    )


@subscriber.subscribe(EventType.STOP_LOSS_TRIGGERED)
async def handle_sl_trigger(event: RiskEvent) -> None:
    """Handle stop loss triggers."""
    position_id = event.metadata.get("position_id", "unknown")
    symbol = event.metadata.get("symbol", "unknown")
    logger.warning(
        f"[STOP LOSS] {symbol} | Position: {position_id} | "
        f"Price: {event.current_value}"
    )


@subscriber.subscribe(EventType.TARGET_HIT)
async def handle_target_hit(event: RiskEvent) -> None:
    """Handle target hits."""
    position_id = event.metadata.get("position_id", "unknown")
    symbol = event.metadata.get("symbol", "unknown")
    logger.info(
        f"[TARGET HIT] {symbol} | Position: {position_id} | "
        f"Price: {event.current_value}"
    )


@subscriber.subscribe(EventType.BROKER_DISCONNECTED)
async def handle_broker_disconnect(event) -> None:
    """Handle broker disconnection."""
    logger.error(
        f"[BROKER DISCONNECT] {event.broker_name} | "
        f"Error: {event.error_message or 'No error message'}"
    )
    # TODO: Trigger reconnection logic


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "EventSubscriberManager",
    "subscriber",
]
