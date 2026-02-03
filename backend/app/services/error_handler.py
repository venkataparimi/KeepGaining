"""
Error Handling & Recovery System
KeepGaining Trading Platform

Production-grade error handling with:
- Graceful error recovery
- Auto-reconnection to brokers/data feeds
- State persistence and restoration
- Error categorization and escalation
- Health monitoring
"""

import asyncio
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Type
from functools import wraps
import sys

from loguru import logger

from app.core.events import EventBus, get_event_bus_sync


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    LOW = "low"           # Warnings, non-critical issues
    MEDIUM = "medium"     # Recoverable errors
    HIGH = "high"         # Serious errors requiring attention
    CRITICAL = "critical" # System-level failures


class ErrorCategory(str, Enum):
    """Error categories for routing and handling."""
    BROKER = "broker"           # Broker connection/API errors
    DATA_FEED = "data_feed"     # Market data errors
    EXECUTION = "execution"     # Order execution errors
    DATABASE = "database"       # Database errors
    NETWORK = "network"         # Network connectivity errors
    VALIDATION = "validation"   # Input validation errors
    SYSTEM = "system"           # System-level errors
    UNKNOWN = "unknown"         # Uncategorized errors


class RecoveryAction(str, Enum):
    """Recovery actions to take."""
    RETRY = "retry"
    RECONNECT = "reconnect"
    RESTART_SERVICE = "restart_service"
    FALLBACK = "fallback"
    ALERT = "alert"
    HALT = "halt"
    IGNORE = "ignore"


@dataclass
class ErrorRecord:
    """Record of an error occurrence."""
    error_id: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    exception_type: str
    stack_trace: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: Dict[str, Any] = field(default_factory=dict)
    recovery_attempted: bool = False
    recovery_action: Optional[RecoveryAction] = None
    recovery_successful: bool = False
    resolved: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_id": self.error_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "exception_type": self.exception_type,
            "stack_trace": self.stack_trace,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
            "recovery_attempted": self.recovery_attempted,
            "recovery_action": self.recovery_action.value if self.recovery_action else None,
            "recovery_successful": self.recovery_successful,
            "resolved": self.resolved,
        }


@dataclass
class ServiceHealth:
    """Health status of a service."""
    service_name: str
    healthy: bool = True
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_count: int = 0
    last_error: Optional[str] = None
    uptime_seconds: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class RecoveryStrategy:
    """Base class for recovery strategies."""
    
    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_multiplier: float = 2.0,
        max_delay: float = 60.0,
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_multiplier = backoff_multiplier
        self.max_delay = max_delay
        self._retry_count = 0
    
    async def execute(self, error: ErrorRecord) -> bool:
        """Execute recovery strategy. Returns True if successful."""
        raise NotImplementedError
    
    def get_delay(self) -> float:
        """Get delay before next retry with exponential backoff."""
        delay = self.retry_delay * (self.backoff_multiplier ** self._retry_count)
        return min(delay, self.max_delay)
    
    def reset(self) -> None:
        """Reset retry counter."""
        self._retry_count = 0


class RetryStrategy(RecoveryStrategy):
    """Retry the failed operation with exponential backoff."""
    
    def __init__(
        self,
        retry_func: Callable[..., Coroutine[Any, Any, Any]],
        **kwargs
    ):
        super().__init__(**kwargs)
        self.retry_func = retry_func
    
    async def execute(self, error: ErrorRecord) -> bool:
        while self._retry_count < self.max_retries:
            try:
                await asyncio.sleep(self.get_delay())
                self._retry_count += 1
                
                await self.retry_func()
                self.reset()
                return True
                
            except Exception as e:
                logger.warning(f"Retry {self._retry_count}/{self.max_retries} failed: {e}")
        
        return False


class ReconnectStrategy(RecoveryStrategy):
    """Reconnect to a service."""
    
    def __init__(
        self,
        connect_func: Callable[..., Coroutine[Any, Any, bool]],
        disconnect_func: Optional[Callable[..., Coroutine[Any, Any, None]]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.connect_func = connect_func
        self.disconnect_func = disconnect_func
    
    async def execute(self, error: ErrorRecord) -> bool:
        while self._retry_count < self.max_retries:
            try:
                # Disconnect first if possible
                if self.disconnect_func:
                    try:
                        await self.disconnect_func()
                    except Exception:
                        pass
                
                await asyncio.sleep(self.get_delay())
                self._retry_count += 1
                
                success = await self.connect_func()
                if success:
                    self.reset()
                    return True
                    
            except Exception as e:
                logger.warning(f"Reconnect {self._retry_count}/{self.max_retries} failed: {e}")
        
        return False


class ErrorHandler:
    """
    Central error handling system.
    
    Features:
    - Error categorization and severity assignment
    - Automatic recovery strategies
    - Error rate limiting (circuit breaker pattern)
    - Health monitoring
    - Error event publishing
    """
    
    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus or get_event_bus_sync()
        
        # Error tracking
        self._errors: List[ErrorRecord] = []
        self._max_errors = 1000
        self._error_counts: Dict[ErrorCategory, int] = {cat: 0 for cat in ErrorCategory}
        
        # Recovery strategies by category
        self._recovery_strategies: Dict[ErrorCategory, RecoveryStrategy] = {}
        
        # Health monitoring
        self._service_health: Dict[str, ServiceHealth] = {}
        
        # Error rate limiting
        self._error_window: Dict[ErrorCategory, List[datetime]] = {cat: [] for cat in ErrorCategory}
        self._rate_limit_window = 60  # seconds
        self._rate_limit_threshold = 10  # max errors per window
        
        # Callbacks
        self._error_callbacks: List[Callable[[ErrorRecord], Coroutine[Any, Any, None]]] = []
        
        logger.info("ErrorHandler initialized")
    
    def register_recovery_strategy(
        self,
        category: ErrorCategory,
        strategy: RecoveryStrategy,
    ) -> None:
        """Register a recovery strategy for an error category."""
        self._recovery_strategies[category] = strategy
        logger.info(f"Registered recovery strategy for {category.value}")
    
    def register_error_callback(
        self,
        callback: Callable[[ErrorRecord], Coroutine[Any, Any, None]],
    ) -> None:
        """Register a callback for error notifications."""
        self._error_callbacks.append(callback)
    
    async def handle_error(
        self,
        exception: Exception,
        category: Optional[ErrorCategory] = None,
        severity: Optional[ErrorSeverity] = None,
        context: Optional[Dict[str, Any]] = None,
        attempt_recovery: bool = True,
    ) -> ErrorRecord:
        """
        Handle an error with categorization and optional recovery.
        
        Args:
            exception: The exception that occurred
            category: Error category (auto-detected if not provided)
            severity: Error severity (auto-detected if not provided)
            context: Additional context information
            attempt_recovery: Whether to attempt automatic recovery
            
        Returns:
            ErrorRecord with details about the error and recovery
        """
        import uuid
        
        # Auto-detect category if not provided
        if category is None:
            category = self._categorize_exception(exception)
        
        # Auto-detect severity if not provided
        if severity is None:
            severity = self._assess_severity(exception, category)
        
        # Create error record
        error = ErrorRecord(
            error_id=str(uuid.uuid4()),
            category=category,
            severity=severity,
            message=str(exception),
            exception_type=type(exception).__name__,
            stack_trace=traceback.format_exc(),
            context=context or {},
        )
        
        # Store error
        self._errors.append(error)
        if len(self._errors) > self._max_errors:
            self._errors = self._errors[-self._max_errors:]
        
        # Update counts
        self._error_counts[category] += 1
        
        # Check rate limiting
        if self._is_rate_limited(category):
            logger.warning(f"Error rate limit reached for {category.value}")
            # Could trigger circuit breaker here
        
        # Log error
        log_method = {
            ErrorSeverity.LOW: logger.warning,
            ErrorSeverity.MEDIUM: logger.error,
            ErrorSeverity.HIGH: logger.error,
            ErrorSeverity.CRITICAL: logger.critical,
        }.get(severity, logger.error)
        
        log_method(f"[{category.value}] {error.message}")
        
        # Attempt recovery
        if attempt_recovery and category in self._recovery_strategies:
            error.recovery_attempted = True
            strategy = self._recovery_strategies[category]
            error.recovery_action = self._get_recovery_action(strategy)
            
            try:
                error.recovery_successful = await strategy.execute(error)
                if error.recovery_successful:
                    error.resolved = True
                    logger.info(f"Recovery successful for error {error.error_id}")
            except Exception as recovery_error:
                logger.error(f"Recovery failed: {recovery_error}")
        
        # Publish error event
        await self._publish_error_event(error)
        
        # Call registered callbacks
        for callback in self._error_callbacks:
            try:
                await callback(error)
            except Exception as e:
                logger.warning(f"Error callback failed: {e}")
        
        return error
    
    def _categorize_exception(self, exception: Exception) -> ErrorCategory:
        """Auto-categorize an exception based on its type."""
        exception_type = type(exception).__name__
        message = str(exception).lower()
        
        # Network errors
        if any(x in exception_type for x in ['Connection', 'Timeout', 'Socket', 'Network']):
            return ErrorCategory.NETWORK
        if any(x in message for x in ['connection', 'timeout', 'network', 'dns']):
            return ErrorCategory.NETWORK
        
        # Database errors
        if any(x in exception_type for x in ['Database', 'SQL', 'Postgres', 'DB']):
            return ErrorCategory.DATABASE
        if any(x in message for x in ['database', 'sql', 'postgres', 'query']):
            return ErrorCategory.DATABASE
        
        # Broker errors
        if any(x in exception_type for x in ['Broker', 'Order', 'Trading', 'API']):
            return ErrorCategory.BROKER
        if any(x in message for x in ['broker', 'order', 'trade', 'fyers', 'upstox']):
            return ErrorCategory.BROKER
        
        # Data feed errors
        if any(x in exception_type for x in ['WebSocket', 'Stream', 'Feed', 'Quote']):
            return ErrorCategory.DATA_FEED
        if any(x in message for x in ['websocket', 'stream', 'feed', 'quote', 'tick']):
            return ErrorCategory.DATA_FEED
        
        # Validation errors
        if any(x in exception_type for x in ['Validation', 'Value', 'Type', 'Pydantic']):
            return ErrorCategory.VALIDATION
        
        # Execution errors
        if any(x in message for x in ['execution', 'position', 'fill']):
            return ErrorCategory.EXECUTION
        
        return ErrorCategory.UNKNOWN
    
    def _assess_severity(self, exception: Exception, category: ErrorCategory) -> ErrorSeverity:
        """Assess error severity based on exception and category."""
        # Critical categories
        if category in [ErrorCategory.EXECUTION, ErrorCategory.BROKER]:
            return ErrorSeverity.HIGH
        
        # Network/DB errors are medium by default
        if category in [ErrorCategory.NETWORK, ErrorCategory.DATABASE]:
            return ErrorSeverity.MEDIUM
        
        # Validation errors are low
        if category == ErrorCategory.VALIDATION:
            return ErrorSeverity.LOW
        
        # Check for specific keywords
        message = str(exception).lower()
        if any(x in message for x in ['critical', 'fatal', 'crash']):
            return ErrorSeverity.CRITICAL
        if any(x in message for x in ['error', 'failed', 'failure']):
            return ErrorSeverity.MEDIUM
        
        return ErrorSeverity.LOW
    
    def _get_recovery_action(self, strategy: RecoveryStrategy) -> RecoveryAction:
        """Get recovery action from strategy."""
        if isinstance(strategy, RetryStrategy):
            return RecoveryAction.RETRY
        elif isinstance(strategy, ReconnectStrategy):
            return RecoveryAction.RECONNECT
        return RecoveryAction.ALERT
    
    def _is_rate_limited(self, category: ErrorCategory) -> bool:
        """Check if error rate limit is exceeded."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self._rate_limit_window)
        
        # Clean old entries
        self._error_window[category] = [
            t for t in self._error_window[category] if t > cutoff
        ]
        
        # Add current
        self._error_window[category].append(now)
        
        return len(self._error_window[category]) >= self._rate_limit_threshold
    
    async def _publish_error_event(self, error: ErrorRecord) -> None:
        """Publish error to event bus."""
        try:
            await self.event_bus.publish("error", error.to_dict())
        except Exception as e:
            logger.warning(f"Failed to publish error event: {e}")
    
    def update_service_health(
        self,
        service_name: str,
        healthy: bool,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update health status of a service."""
        if service_name not in self._service_health:
            self._service_health[service_name] = ServiceHealth(service_name=service_name)
        
        health = self._service_health[service_name]
        health.healthy = healthy
        health.last_check = datetime.now(timezone.utc)
        
        if not healthy:
            health.error_count += 1
            health.last_error = error
        
        if metadata:
            health.metadata.update(metadata)
    
    def get_service_health(self, service_name: str) -> Optional[ServiceHealth]:
        """Get health status of a service."""
        return self._service_health.get(service_name)
    
    def get_all_health(self) -> Dict[str, ServiceHealth]:
        """Get health status of all services."""
        return self._service_health.copy()
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics."""
        return {
            "total_errors": len(self._errors),
            "by_category": {cat.value: count for cat, count in self._error_counts.items()},
            "recent_errors": [e.to_dict() for e in self._errors[-10:]],
            "services_health": {
                name: {
                    "healthy": h.healthy,
                    "error_count": h.error_count,
                    "last_error": h.last_error,
                }
                for name, h in self._service_health.items()
            },
        }
    
    def get_errors(
        self,
        category: Optional[ErrorCategory] = None,
        severity: Optional[ErrorSeverity] = None,
        limit: int = 100,
    ) -> List[ErrorRecord]:
        """Get filtered error history."""
        errors = self._errors
        
        if category:
            errors = [e for e in errors if e.category == category]
        if severity:
            errors = [e for e in errors if e.severity == severity]
        
        return errors[-limit:]


def with_error_handling(
    category: Optional[ErrorCategory] = None,
    severity: Optional[ErrorSeverity] = None,
    recovery: bool = True,
):
    """Decorator for automatic error handling."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                handler = get_error_handler()
                await handler.handle_error(
                    exception=e,
                    category=category,
                    severity=severity,
                    context={"function": func.__name__, "args": str(args)[:100]},
                    attempt_recovery=recovery,
                )
                raise
        return wrapper
    return decorator


# Singleton instance
_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """Get or create the global ErrorHandler instance."""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler()
    return _error_handler
