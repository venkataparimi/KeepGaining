"""
Audit Trail & Logging System
KeepGaining Trading Platform

Production-grade audit trail for:
- Trade execution logging
- Order lifecycle tracking
- Position changes
- Risk events
- System events
- Compliance reporting
"""

import asyncio
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional, Union
from enum import Enum
from pathlib import Path
import gzip
import shutil

from loguru import logger

from app.core.events import EventBus, get_event_bus_sync


class AuditEventType(str, Enum):
    """Types of audit events."""
    # Order Events
    ORDER_PLACED = "order_placed"
    ORDER_MODIFIED = "order_modified"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    ORDER_EXPIRED = "order_expired"
    
    # Position Events
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_MODIFIED = "position_modified"
    POSITION_SQUARED_OFF = "position_squared_off"
    
    # Risk Events
    STOP_LOSS_TRIGGERED = "stop_loss_triggered"
    TARGET_HIT = "target_hit"
    TRAILING_SL_UPDATED = "trailing_sl_updated"
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker_triggered"
    RISK_LIMIT_BREACHED = "risk_limit_breached"
    
    # System Events
    TRADING_STARTED = "trading_started"
    TRADING_STOPPED = "trading_stopped"
    TRADING_PAUSED = "trading_paused"
    TRADING_RESUMED = "trading_resumed"
    MODE_CHANGED = "mode_changed"
    
    # Broker Events
    BROKER_CONNECTED = "broker_connected"
    BROKER_DISCONNECTED = "broker_disconnected"
    BROKER_RECONNECTED = "broker_reconnected"
    
    # Strategy Events
    STRATEGY_STARTED = "strategy_started"
    STRATEGY_STOPPED = "strategy_stopped"
    STRATEGY_SIGNAL = "strategy_signal"
    
    # Alert Events
    ALERT_TRIGGERED = "alert_triggered"
    ALERT_ACKNOWLEDGED = "alert_acknowledged"
    ALERT_RESOLVED = "alert_resolved"
    
    # User Actions
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    SETTINGS_CHANGED = "settings_changed"
    MANUAL_INTERVENTION = "manual_intervention"


@dataclass
class AuditEvent:
    """
    Represents an auditable event in the system.
    
    All significant actions are captured for compliance and debugging.
    """
    event_id: str
    event_type: AuditEventType
    timestamp: datetime
    
    # Actor information
    user_id: Optional[str] = None
    strategy_id: Optional[str] = None
    broker_id: Optional[str] = None
    
    # Event details
    symbol: Optional[str] = None
    order_id: Optional[str] = None
    position_id: Optional[str] = None
    
    # Action details
    action: str = ""
    description: str = ""
    
    # Before/After state for tracking changes
    before_state: Dict[str, Any] = field(default_factory=dict)
    after_state: Dict[str, Any] = field(default_factory=dict)
    
    # Additional context
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Financial impact
    quantity: Optional[int] = None
    price: Optional[float] = None
    value: Optional[float] = None
    pnl: Optional[float] = None
    
    # Source information
    source: str = "system"
    ip_address: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "strategy_id": self.strategy_id,
            "broker_id": self.broker_id,
            "symbol": self.symbol,
            "order_id": self.order_id,
            "position_id": self.position_id,
            "action": self.action,
            "description": self.description,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "metadata": self.metadata,
            "quantity": self.quantity,
            "price": self.price,
            "value": self.value,
            "pnl": self.pnl,
            "source": self.source,
            "ip_address": self.ip_address,
        }
    
    def to_log_line(self) -> str:
        """Convert to log line format."""
        parts = [
            self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            f"[{self.event_type.value}]",
        ]
        
        if self.symbol:
            parts.append(f"symbol={self.symbol}")
        if self.order_id:
            parts.append(f"order={self.order_id[:8]}")
        if self.action:
            parts.append(f"action={self.action}")
        if self.quantity:
            parts.append(f"qty={self.quantity}")
        if self.price:
            parts.append(f"price={self.price}")
        if self.pnl is not None:
            parts.append(f"pnl={self.pnl:+.2f}")
        if self.description:
            parts.append(f"| {self.description}")
        
        return " ".join(parts)


class AuditStorage:
    """
    Base class for audit event storage.
    
    Supports multiple storage backends.
    """
    
    async def store(self, event: AuditEvent) -> None:
        """Store an audit event."""
        raise NotImplementedError
    
    async def query(
        self,
        event_types: Optional[List[AuditEventType]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Query audit events."""
        raise NotImplementedError
    
    async def close(self) -> None:
        """Close storage connection."""
        pass


class FileAuditStorage(AuditStorage):
    """
    File-based audit storage.
    
    Stores events in daily JSON files with optional compression.
    """
    
    def __init__(
        self,
        base_dir: str = "logs/audit",
        compress_old: bool = True,
        retention_days: int = 90,
    ):
        self.base_dir = Path(base_dir)
        self.compress_old = compress_old
        self.retention_days = retention_days
        
        # Ensure directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Current day's file
        self._current_file: Optional[Path] = None
        self._current_date: Optional[date] = None
        self._buffer: List[Dict] = []
        self._buffer_size = 100
        
        logger.info(f"FileAuditStorage initialized at {self.base_dir}")
    
    def _get_file_path(self, event_date: date) -> Path:
        """Get file path for a specific date."""
        return self.base_dir / f"audit_{event_date.strftime('%Y%m%d')}.jsonl"
    
    async def store(self, event: AuditEvent) -> None:
        """Store an audit event."""
        event_date = event.timestamp.date()
        
        # Check if we need to rotate files
        if self._current_date != event_date:
            await self._flush_buffer()
            await self._rotate_file(event_date)
        
        # Add to buffer
        self._buffer.append(event.to_dict())
        
        # Flush if buffer is full
        if len(self._buffer) >= self._buffer_size:
            await self._flush_buffer()
    
    async def _flush_buffer(self) -> None:
        """Flush buffer to file."""
        if not self._buffer or not self._current_file:
            return
        
        try:
            with open(self._current_file, "a", encoding="utf-8") as f:
                for event_dict in self._buffer:
                    f.write(json.dumps(event_dict) + "\n")
            self._buffer = []
        except Exception as e:
            logger.error(f"Failed to flush audit buffer: {e}")
    
    async def _rotate_file(self, new_date: date) -> None:
        """Rotate to a new file for a new date."""
        # Compress old file if configured
        if self.compress_old and self._current_file and self._current_file.exists():
            await self._compress_file(self._current_file)
        
        # Set new file
        self._current_date = new_date
        self._current_file = self._get_file_path(new_date)
        
        # Clean up old files
        await self._cleanup_old_files()
    
    async def _compress_file(self, file_path: Path) -> None:
        """Compress a file using gzip."""
        try:
            with open(file_path, "rb") as f_in:
                with gzip.open(str(file_path) + ".gz", "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            file_path.unlink()  # Remove original
            logger.debug(f"Compressed audit file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to compress file: {e}")
    
    async def _cleanup_old_files(self) -> None:
        """Remove files older than retention period."""
        cutoff = datetime.now().date()
        cutoff = date(
            cutoff.year,
            cutoff.month,
            cutoff.day
        ) - __import__('datetime').timedelta(days=self.retention_days)
        
        for file_path in self.base_dir.glob("audit_*.jsonl*"):
            try:
                # Extract date from filename
                date_str = file_path.stem.replace("audit_", "").split(".")[0]
                file_date = datetime.strptime(date_str, "%Y%m%d").date()
                
                if file_date < cutoff:
                    file_path.unlink()
                    logger.debug(f"Removed old audit file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to process file {file_path}: {e}")
    
    async def query(
        self,
        event_types: Optional[List[AuditEventType]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Query audit events from files."""
        # Flush current buffer first
        await self._flush_buffer()
        
        results = []
        
        # Determine which files to read
        if start_time:
            start_date = start_time.date()
        else:
            start_date = datetime.now().date() - __import__('datetime').timedelta(days=7)
        
        if end_time:
            end_date = end_time.date()
        else:
            end_date = datetime.now().date()
        
        # Iterate through files
        current = start_date
        while current <= end_date and len(results) < limit:
            file_path = self._get_file_path(current)
            
            # Check for uncompressed or compressed file
            if file_path.exists():
                results.extend(await self._read_file(file_path, event_types, start_time, end_time, symbol))
            elif (file_path.parent / (file_path.name + ".gz")).exists():
                gz_path = file_path.parent / (file_path.name + ".gz")
                results.extend(await self._read_gzip_file(gz_path, event_types, start_time, end_time, symbol))
            
            current = current + __import__('datetime').timedelta(days=1)
        
        return results[-limit:]
    
    async def _read_file(
        self,
        file_path: Path,
        event_types: Optional[List[AuditEventType]],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        symbol: Optional[str],
    ) -> List[AuditEvent]:
        """Read and filter events from a file."""
        results = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        event = self._dict_to_event(data)
                        
                        if self._matches_filter(event, event_types, start_time, end_time, symbol):
                            results.append(event)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Failed to read audit file {file_path}: {e}")
        
        return results
    
    async def _read_gzip_file(
        self,
        file_path: Path,
        event_types: Optional[List[AuditEventType]],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        symbol: Optional[str],
    ) -> List[AuditEvent]:
        """Read and filter events from a gzipped file."""
        results = []
        
        try:
            with gzip.open(file_path, "rt", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        event = self._dict_to_event(data)
                        
                        if self._matches_filter(event, event_types, start_time, end_time, symbol):
                            results.append(event)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Failed to read gzip file {file_path}: {e}")
        
        return results
    
    def _dict_to_event(self, data: Dict[str, Any]) -> AuditEvent:
        """Convert dictionary to AuditEvent."""
        return AuditEvent(
            event_id=data.get("event_id", ""),
            event_type=AuditEventType(data.get("event_type", "manual_intervention")),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            user_id=data.get("user_id"),
            strategy_id=data.get("strategy_id"),
            broker_id=data.get("broker_id"),
            symbol=data.get("symbol"),
            order_id=data.get("order_id"),
            position_id=data.get("position_id"),
            action=data.get("action", ""),
            description=data.get("description", ""),
            before_state=data.get("before_state", {}),
            after_state=data.get("after_state", {}),
            metadata=data.get("metadata", {}),
            quantity=data.get("quantity"),
            price=data.get("price"),
            value=data.get("value"),
            pnl=data.get("pnl"),
            source=data.get("source", "system"),
            ip_address=data.get("ip_address"),
        )
    
    def _matches_filter(
        self,
        event: AuditEvent,
        event_types: Optional[List[AuditEventType]],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        symbol: Optional[str],
    ) -> bool:
        """Check if event matches filter criteria."""
        if event_types and event.event_type not in event_types:
            return False
        if start_time and event.timestamp < start_time:
            return False
        if end_time and event.timestamp > end_time:
            return False
        if symbol and event.symbol != symbol:
            return False
        return True
    
    async def close(self) -> None:
        """Close storage and flush remaining buffer."""
        await self._flush_buffer()


class AuditTrail:
    """
    Central audit trail manager.
    
    Captures and stores all auditable events in the trading system.
    """
    
    def __init__(
        self,
        storage: Optional[AuditStorage] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self.storage = storage or FileAuditStorage()
        self.event_bus = event_bus or get_event_bus_sync()
        
        # In-memory recent events for quick access
        self._recent_events: List[AuditEvent] = []
        self._max_recent = 500
        
        # Running state
        self._running = False
        
        logger.info("AuditTrail initialized")
    
    async def start(self) -> None:
        """Start the audit trail system."""
        if self._running:
            return
        
        self._running = True
        
        # Subscribe to events
        await self._subscribe_to_events()
        
        # Log startup
        await self.log_event(
            event_type=AuditEventType.TRADING_STARTED,
            action="system_startup",
            description="Audit trail system started",
        )
        
        logger.info("AuditTrail started")
    
    async def stop(self) -> None:
        """Stop the audit trail system."""
        # Log shutdown
        await self.log_event(
            event_type=AuditEventType.TRADING_STOPPED,
            action="system_shutdown",
            description="Audit trail system stopped",
        )
        
        # Close storage
        await self.storage.close()
        
        self._running = False
        logger.info("AuditTrail stopped")
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to system events for automatic logging."""
        try:
            # Order events
            await self.event_bus.subscribe("order.placed", self._on_order_placed)
            await self.event_bus.subscribe("order.filled", self._on_order_filled)
            await self.event_bus.subscribe("order.cancelled", self._on_order_cancelled)
            await self.event_bus.subscribe("order.rejected", self._on_order_rejected)
            
            # Position events
            await self.event_bus.subscribe("position_opened", self._on_position_opened)
            await self.event_bus.subscribe("position_closed", self._on_position_closed)
            
            # Risk events
            await self.event_bus.subscribe("circuit_breaker_triggered", self._on_circuit_breaker)
            await self.event_bus.subscribe("stop_loss_triggered", self._on_stop_loss)
            
            # Broker events
            await self.event_bus.subscribe("broker_connected", self._on_broker_connected)
            await self.event_bus.subscribe("broker_disconnected", self._on_broker_disconnected)
        except Exception as e:
            logger.warning(f"Failed to subscribe to events: {e}")
    
    async def log_event(
        self,
        event_type: AuditEventType,
        action: str = "",
        description: str = "",
        symbol: Optional[str] = None,
        order_id: Optional[str] = None,
        position_id: Optional[str] = None,
        user_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        broker_id: Optional[str] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        value: Optional[float] = None,
        pnl: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "system",
    ) -> AuditEvent:
        """
        Log an audit event.
        
        Args:
            event_type: Type of event
            action: Action performed
            description: Human-readable description
            symbol: Trading symbol
            order_id: Associated order ID
            position_id: Associated position ID
            user_id: User who triggered the event
            strategy_id: Strategy that triggered the event
            broker_id: Broker associated with the event
            before_state: State before the action
            after_state: State after the action
            quantity: Quantity involved
            price: Price involved
            value: Value involved
            pnl: P&L impact
            metadata: Additional metadata
            source: Source of the event
            
        Returns:
            The created AuditEvent
        """
        import uuid
        
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            strategy_id=strategy_id,
            broker_id=broker_id,
            symbol=symbol,
            order_id=order_id,
            position_id=position_id,
            action=action,
            description=description,
            before_state=before_state or {},
            after_state=after_state or {},
            metadata=metadata or {},
            quantity=quantity,
            price=price,
            value=value,
            pnl=pnl,
            source=source,
        )
        
        # Store event
        await self.storage.store(event)
        
        # Add to recent events
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_recent:
            self._recent_events = self._recent_events[-self._max_recent:]
        
        # Log to loguru as well
        logger.info(event.to_log_line())
        
        return event
    
    # Event handlers
    async def _on_order_placed(self, event: Any) -> None:
        """Handle order placed event."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        await self.log_event(
            event_type=AuditEventType.ORDER_PLACED,
            action="order_placed",
            symbol=data.get("symbol"),
            order_id=data.get("order_id"),
            quantity=data.get("quantity"),
            price=data.get("price"),
            metadata=data,
        )
    
    async def _on_order_filled(self, event: Any) -> None:
        """Handle order filled event."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        await self.log_event(
            event_type=AuditEventType.ORDER_FILLED,
            action="order_filled",
            symbol=data.get("symbol"),
            order_id=data.get("order_id"),
            quantity=data.get("filled_quantity"),
            price=data.get("average_price"),
            metadata=data,
        )
    
    async def _on_order_cancelled(self, event: Any) -> None:
        """Handle order cancelled event."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        await self.log_event(
            event_type=AuditEventType.ORDER_CANCELLED,
            action="order_cancelled",
            symbol=data.get("symbol"),
            order_id=data.get("order_id"),
            metadata=data,
        )
    
    async def _on_order_rejected(self, event: Any) -> None:
        """Handle order rejected event."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        await self.log_event(
            event_type=AuditEventType.ORDER_REJECTED,
            action="order_rejected",
            description=data.get("reason", ""),
            symbol=data.get("symbol"),
            order_id=data.get("order_id"),
            metadata=data,
        )
    
    async def _on_position_opened(self, event: Any) -> None:
        """Handle position opened event."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        await self.log_event(
            event_type=AuditEventType.POSITION_OPENED,
            action="position_opened",
            symbol=data.get("symbol"),
            position_id=data.get("position_id"),
            quantity=data.get("quantity"),
            price=data.get("average_price"),
            metadata=data,
        )
    
    async def _on_position_closed(self, event: Any) -> None:
        """Handle position closed event."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        await self.log_event(
            event_type=AuditEventType.POSITION_CLOSED,
            action="position_closed",
            symbol=data.get("symbol"),
            position_id=data.get("position_id"),
            quantity=data.get("quantity"),
            price=data.get("exit_price"),
            pnl=data.get("net_pnl"),
            metadata=data,
        )
    
    async def _on_circuit_breaker(self, event: Any) -> None:
        """Handle circuit breaker event."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        await self.log_event(
            event_type=AuditEventType.CIRCUIT_BREAKER_TRIGGERED,
            action="circuit_breaker",
            description=data.get("reason", "Circuit breaker triggered"),
            metadata=data,
        )
    
    async def _on_stop_loss(self, event: Any) -> None:
        """Handle stop loss event."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        await self.log_event(
            event_type=AuditEventType.STOP_LOSS_TRIGGERED,
            action="stop_loss",
            symbol=data.get("symbol"),
            position_id=data.get("position_id"),
            pnl=data.get("pnl"),
            metadata=data,
        )
    
    async def _on_broker_connected(self, event: Any) -> None:
        """Handle broker connected event."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        await self.log_event(
            event_type=AuditEventType.BROKER_CONNECTED,
            action="broker_connected",
            broker_id=data.get("broker_name"),
            metadata=data,
        )
    
    async def _on_broker_disconnected(self, event: Any) -> None:
        """Handle broker disconnected event."""
        data = event if isinstance(event, dict) else getattr(event, 'data', {})
        await self.log_event(
            event_type=AuditEventType.BROKER_DISCONNECTED,
            action="broker_disconnected",
            broker_id=data.get("broker_name"),
            metadata=data,
        )
    
    # Query methods
    def get_recent_events(self, limit: int = 100) -> List[AuditEvent]:
        """Get recent events from memory."""
        return self._recent_events[-limit:]
    
    async def query_events(
        self,
        event_types: Optional[List[AuditEventType]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Query events from storage."""
        return await self.storage.query(
            event_types=event_types,
            start_time=start_time,
            end_time=end_time,
            symbol=symbol,
            limit=limit,
        )
    
    async def get_trade_history(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Get trade-related events."""
        trade_types = [
            AuditEventType.ORDER_PLACED,
            AuditEventType.ORDER_FILLED,
            AuditEventType.POSITION_OPENED,
            AuditEventType.POSITION_CLOSED,
        ]
        return await self.query_events(
            event_types=trade_types,
            start_time=start_time,
            end_time=end_time,
            symbol=symbol,
            limit=limit,
        )
    
    async def get_risk_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Get risk-related events."""
        risk_types = [
            AuditEventType.STOP_LOSS_TRIGGERED,
            AuditEventType.TARGET_HIT,
            AuditEventType.CIRCUIT_BREAKER_TRIGGERED,
            AuditEventType.RISK_LIMIT_BREACHED,
        ]
        return await self.query_events(
            event_types=risk_types,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get audit trail statistics."""
        type_counts: Dict[str, int] = {}
        for event in self._recent_events:
            type_counts[event.event_type.value] = type_counts.get(event.event_type.value, 0) + 1
        
        return {
            "recent_count": len(self._recent_events),
            "by_type": type_counts,
        }


# Singleton instance
_audit_trail: Optional[AuditTrail] = None


def get_audit_trail() -> AuditTrail:
    """Get or create the global AuditTrail instance."""
    global _audit_trail
    if _audit_trail is None:
        _audit_trail = AuditTrail()
    return _audit_trail
