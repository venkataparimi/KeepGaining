"""
Event Publisher Service
KeepGaining Trading Platform

Central service for publishing events to the event bus.
Provides type-safe event creation and publishing.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID

from loguru import logger

from app.core.events import (
    EventBus,
    EventType,
    EventPriority,
    get_event_bus,
    # Event types
    TickEvent,
    CandleEvent,
    IndicatorEvent,
    SignalEvent,
    OrderEvent,
    TradeEvent,
    PositionEvent,
    RiskEvent,
    SystemEvent,
    BrokerEvent,
)


class EventPublisher:
    """
    Service for publishing events to the event bus.
    
    Provides convenient methods for creating and publishing
    different types of events.
    """
    
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._source = "trading_engine"
    
    async def _get_bus(self) -> EventBus:
        """Get event bus instance."""
        if self._event_bus is None:
            self._event_bus = await get_event_bus()
        return self._event_bus
    
    # =========================================================================
    # Market Data Events
    # =========================================================================
    
    async def publish_tick(
        self,
        instrument_id: str,
        symbol: str,
        ltp: float,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        volume: Optional[int] = None,
        oi: Optional[int] = None,
    ) -> str:
        """Publish tick data event."""
        bus = await self._get_bus()
        event = TickEvent(
            instrument_id=instrument_id,
            symbol=symbol,
            ltp=ltp,
            bid=bid,
            ask=ask,
            volume=volume,
            oi=oi,
            source=self._source,
        )
        return await bus.publish(event)
    
    async def publish_candle(
        self,
        instrument_id: str,
        symbol: str,
        timeframe: str,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: int,
        is_complete: bool = True,
    ) -> str:
        """Publish candle formation event."""
        bus = await self._get_bus()
        event = CandleEvent(
            instrument_id=instrument_id,
            symbol=symbol,
            timeframe=timeframe,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
            is_complete=is_complete,
            source=self._source,
        )
        return await bus.publish(event)
    
    async def publish_indicators(
        self,
        instrument_id: str,
        symbol: str,
        timeframe: str,
        indicators: Dict[str, float],
    ) -> str:
        """Publish indicator update event."""
        bus = await self._get_bus()
        event = IndicatorEvent(
            instrument_id=instrument_id,
            symbol=symbol,
            timeframe=timeframe,
            indicators=indicators,
            source=self._source,
        )
        return await bus.publish(event)
    
    # =========================================================================
    # Trading Events
    # =========================================================================
    
    async def publish_signal(
        self,
        strategy_id: str,
        instrument_id: str,
        symbol: str,
        signal_type: str,  # ENTRY_LONG, ENTRY_SHORT, EXIT
        price: float,
        strength: float = 100.0,
        conditions_met: Optional[Dict[str, Any]] = None,
        suggested_sl: Optional[float] = None,
        suggested_target: Optional[float] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Publish trading signal event."""
        bus = await self._get_bus()
        event = SignalEvent(
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            strength=strength,
            conditions_met=conditions_met or {},
            suggested_sl=suggested_sl,
            suggested_target=suggested_target,
            correlation_id=correlation_id,
            source=self._source,
        )
        logger.info(f"Signal generated: {signal_type} for {symbol} @ {price}")
        return await bus.publish(event)
    
    async def publish_order_placed(
        self,
        order_id: str,
        instrument_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: int,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        strategy_id: Optional[str] = None,
        broker_order_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Publish order placed event."""
        bus = await self._get_bus()
        event = OrderEvent(
            event_type=EventType.ORDER_PLACED,
            order_id=order_id,
            instrument_id=instrument_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            status="PLACED",
            strategy_id=strategy_id,
            broker_order_id=broker_order_id,
            correlation_id=correlation_id,
            source=self._source,
        )
        logger.info(f"Order placed: {side} {quantity} {symbol} @ {price or 'MARKET'}")
        return await bus.publish(event)
    
    async def publish_order_update(
        self,
        order_id: str,
        instrument_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: int,
        status: str,
        broker_order_id: Optional[str] = None,
        filled_quantity: int = 0,
        average_price: Optional[float] = None,
        rejection_reason: Optional[str] = None,
        strategy_id: Optional[str] = None,
    ) -> str:
        """Publish order update event."""
        bus = await self._get_bus()
        
        # Determine event type based on status
        event_type_map = {
            "FILLED": EventType.ORDER_FILLED,
            "CANCELLED": EventType.ORDER_CANCELLED,
            "REJECTED": EventType.ORDER_REJECTED,
        }
        event_type = event_type_map.get(status, EventType.ORDER_UPDATED)
        
        event = OrderEvent(
            event_type=event_type,
            order_id=order_id,
            instrument_id=instrument_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            status=status,
            broker_order_id=broker_order_id,
            strategy_id=strategy_id,
            rejection_reason=rejection_reason,
            source=self._source,
        )
        
        if status == "FILLED":
            logger.info(f"Order filled: {order_id} @ {average_price}")
        elif status == "REJECTED":
            logger.warning(f"Order rejected: {order_id} - {rejection_reason}")
        
        return await bus.publish(event)
    
    async def publish_trade(
        self,
        trade_id: str,
        order_id: str,
        instrument_id: str,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        broker_trade_id: Optional[str] = None,
    ) -> str:
        """Publish trade execution event."""
        bus = await self._get_bus()
        event = TradeEvent(
            trade_id=trade_id,
            order_id=order_id,
            instrument_id=instrument_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            broker_trade_id=broker_trade_id,
            source=self._source,
        )
        logger.info(f"Trade executed: {side} {quantity} {symbol} @ {price}")
        return await bus.publish(event)
    
    async def publish_position_update(
        self,
        position_id: str,
        instrument_id: str,
        symbol: str,
        side: str,
        quantity: int,
        average_price: float,
        current_price: float,
        unrealized_pnl: float,
        realized_pnl: float = 0.0,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        strategy_id: Optional[str] = None,
        event_type: EventType = EventType.POSITION_UPDATED,
    ) -> str:
        """Publish position update event."""
        bus = await self._get_bus()
        event = PositionEvent(
            event_type=event_type,
            position_id=position_id,
            instrument_id=instrument_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            average_price=average_price,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            stop_loss=stop_loss,
            target=target,
            strategy_id=strategy_id,
            source=self._source,
        )
        return await bus.publish(event)
    
    async def publish_position_opened(
        self,
        position_id: str,
        instrument_id: str,
        symbol: str,
        side: str,
        quantity: int,
        entry_price: float,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        strategy_id: Optional[str] = None,
    ) -> str:
        """Publish position opened event."""
        return await self.publish_position_update(
            position_id=position_id,
            instrument_id=instrument_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            average_price=entry_price,
            current_price=entry_price,
            unrealized_pnl=0.0,
            stop_loss=stop_loss,
            target=target,
            strategy_id=strategy_id,
            event_type=EventType.POSITION_OPENED,
        )
    
    async def publish_position_closed(
        self,
        position_id: str,
        instrument_id: str,
        symbol: str,
        side: str,
        quantity: int,
        average_price: float,
        exit_price: float,
        realized_pnl: float,
        strategy_id: Optional[str] = None,
    ) -> str:
        """Publish position closed event."""
        return await self.publish_position_update(
            position_id=position_id,
            instrument_id=instrument_id,
            symbol=symbol,
            side=side,
            quantity=0,  # Position closed
            average_price=average_price,
            current_price=exit_price,
            unrealized_pnl=0.0,
            realized_pnl=realized_pnl,
            strategy_id=strategy_id,
            event_type=EventType.POSITION_CLOSED,
        )
    
    # =========================================================================
    # Risk Events
    # =========================================================================
    
    async def publish_risk_alert(
        self,
        risk_type: str,  # DAILY_LOSS, MAX_POSITION, DRAWDOWN
        current_value: float,
        limit_value: float,
        action_taken: str,  # ALERT, BLOCK_ENTRY, FORCE_EXIT
        affected_strategies: Optional[List[str]] = None,
    ) -> str:
        """Publish risk limit breach event."""
        bus = await self._get_bus()
        event = RiskEvent(
            risk_type=risk_type,
            current_value=current_value,
            limit_value=limit_value,
            action_taken=action_taken,
            affected_strategies=affected_strategies or [],
            source=self._source,
        )
        logger.warning(
            f"Risk alert: {risk_type} - Current: {current_value}, Limit: {limit_value}, Action: {action_taken}"
        )
        return await bus.publish(event)
    
    async def publish_sl_triggered(
        self,
        position_id: str,
        symbol: str,
        sl_price: float,
        triggered_price: float,
    ) -> str:
        """Publish stop loss triggered event."""
        bus = await self._get_bus()
        event = RiskEvent(
            event_type=EventType.STOP_LOSS_TRIGGERED,
            risk_type="STOP_LOSS",
            current_value=triggered_price,
            limit_value=sl_price,
            action_taken="EXIT_POSITION",
            metadata={"position_id": position_id, "symbol": symbol},
            source=self._source,
        )
        logger.info(f"Stop loss triggered: {symbol} @ {triggered_price}")
        return await bus.publish(event)
    
    async def publish_target_hit(
        self,
        position_id: str,
        symbol: str,
        target_price: float,
        hit_price: float,
    ) -> str:
        """Publish target hit event."""
        bus = await self._get_bus()
        event = RiskEvent(
            event_type=EventType.TARGET_HIT,
            risk_type="TARGET",
            current_value=hit_price,
            limit_value=target_price,
            action_taken="EXIT_POSITION",
            metadata={"position_id": position_id, "symbol": symbol},
            source=self._source,
        )
        logger.info(f"Target hit: {symbol} @ {hit_price}")
        return await bus.publish(event)
    
    # =========================================================================
    # System Events
    # =========================================================================
    
    async def publish_system_event(
        self,
        component: str,
        status: str,
        event_type: EventType = EventType.SYSTEM_STARTUP,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Publish system lifecycle event."""
        bus = await self._get_bus()
        event = SystemEvent(
            event_type=event_type,
            component=component,
            status=status,
            details=details or {},
            source=self._source,
        )
        logger.info(f"System event: {component} - {status}")
        return await bus.publish(event)
    
    async def publish_broker_connected(
        self,
        broker_name: str,
    ) -> str:
        """Publish broker connected event."""
        bus = await self._get_bus()
        event = BrokerEvent(
            event_type=EventType.BROKER_CONNECTED,
            broker_name=broker_name,
            status="CONNECTED",
            source=self._source,
        )
        logger.info(f"Broker connected: {broker_name}")
        return await bus.publish(event)
    
    async def publish_broker_disconnected(
        self,
        broker_name: str,
        error_message: Optional[str] = None,
    ) -> str:
        """Publish broker disconnected event."""
        bus = await self._get_bus()
        event = BrokerEvent(
            event_type=EventType.BROKER_DISCONNECTED,
            broker_name=broker_name,
            status="DISCONNECTED",
            error_message=error_message,
            source=self._source,
        )
        logger.warning(f"Broker disconnected: {broker_name} - {error_message or 'No error'}")
        return await bus.publish(event)


# Global publisher instance
_publisher: Optional[EventPublisher] = None


async def get_event_publisher() -> EventPublisher:
    """Get or create the global event publisher."""
    global _publisher
    if _publisher is None:
        _publisher = EventPublisher()
    return _publisher


__all__ = [
    "EventPublisher",
    "get_event_publisher",
]
