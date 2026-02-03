"""
MCP (Model Context Protocol) Integration Base Classes

Production-grade abstractions for browser automation in algo trading.
Provides reusable base classes for scrapers, automators, and monitors.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)


class ModuleStatus(Enum):
    """Status of an MCP module."""
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class ModuleHealth:
    """Health status of an MCP module."""
    status: ModuleStatus
    last_run: Optional[datetime] = None
    last_success: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Result of an automator action."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: float = 0
    screenshots: List[str] = field(default_factory=list)


class MCPModule(ABC):
    """
    Base class for all MCP-powered modules.
    
    Provides lifecycle management, health tracking, and error handling.
    All modules integrate with the EventBus for loose coupling.
    """
    
    def __init__(self, name: str, event_bus: Optional[Any] = None):
        self.name = name
        self.event_bus = event_bus
        self._status = ModuleStatus.IDLE
        self._health = ModuleHealth(status=ModuleStatus.IDLE)
        self._running = False
        self._lock = asyncio.Lock()
    
    @property
    def status(self) -> ModuleStatus:
        return self._status
    
    @property
    def health(self) -> ModuleHealth:
        return self._health
    
    async def start(self) -> None:
        """Start the module."""
        async with self._lock:
            if self._running:
                logger.warning(f"{self.name}: Already running")
                return
            
            try:
                await self._on_start()
                self._running = True
                self._status = ModuleStatus.RUNNING
                self._health.status = ModuleStatus.RUNNING
                logger.info(f"{self.name}: Started successfully")
            except Exception as e:
                self._status = ModuleStatus.ERROR
                self._health.status = ModuleStatus.ERROR
                self._health.last_error = str(e)
                self._health.error_count += 1
                logger.error(f"{self.name}: Failed to start: {e}")
                raise
    
    async def stop(self) -> None:
        """Stop the module."""
        async with self._lock:
            if not self._running:
                return
            
            try:
                await self._on_stop()
                self._running = False
                self._status = ModuleStatus.STOPPED
                self._health.status = ModuleStatus.STOPPED
                logger.info(f"{self.name}: Stopped")
            except Exception as e:
                logger.error(f"{self.name}: Error during stop: {e}")
    
    async def health_check(self) -> ModuleHealth:
        """Get current health status."""
        return self._health
    
    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit event to EventBus if available."""
        if self.event_bus:
            self.event_bus.publish(event_type, {
                "module": self.name,
                "timestamp": datetime.now().isoformat(),
                **data
            })
    
    @abstractmethod
    async def _on_start(self) -> None:
        """Override to implement startup logic."""
        pass
    
    @abstractmethod
    async def _on_stop(self) -> None:
        """Override to implement shutdown logic."""
        pass


class BaseScraper(MCPModule):
    """
    Base class for data scrapers.
    
    Scrapers extract structured data from web pages.
    Examples: NSE OI data, Chartink screeners, Sensibull analytics.
    """
    
    def __init__(
        self,
        name: str,
        event_bus: Optional[Any] = None,
        interval_seconds: int = 60,
        max_retries: int = 3,
        retry_delay_seconds: float = 5.0
    ):
        super().__init__(name, event_bus)
        self.interval_seconds = interval_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self._scrape_task: Optional[asyncio.Task] = None
    
    async def _on_start(self) -> None:
        """Start periodic scraping."""
        self._scrape_task = asyncio.create_task(self._scrape_loop())
    
    async def _on_stop(self) -> None:
        """Stop scraping."""
        if self._scrape_task:
            self._scrape_task.cancel()
            try:
                await self._scrape_task
            except asyncio.CancelledError:
                pass
    
    async def _scrape_loop(self) -> None:
        """Periodic scraping loop with retries."""
        while self._running:
            try:
                data = await self._scrape_with_retry()
                if data:
                    self._health.last_success = datetime.now()
                    self._emit_event("MCP_DATA_UPDATE", {
                        "scraper": self.name,
                        "data": data
                    })
            except Exception as e:
                self._health.error_count += 1
                self._health.last_error = str(e)
                logger.error(f"{self.name}: Scrape failed: {e}")
            
            self._health.last_run = datetime.now()
            await asyncio.sleep(self.interval_seconds)
    
    async def _scrape_with_retry(self) -> Optional[Dict[str, Any]]:
        """Execute scrape with retries."""
        for attempt in range(self.max_retries):
            try:
                return await self.scrape()
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"{self.name}: Attempt {attempt + 1} failed, retrying...")
                    await asyncio.sleep(self.retry_delay_seconds)
                else:
                    raise
        return None
    
    @abstractmethod
    async def scrape(self) -> Dict[str, Any]:
        """
        Execute the scraping logic.
        
        Returns:
            Scraped data as dictionary
        """
        pass
    
    async def scrape_once(self) -> Dict[str, Any]:
        """Execute a single scrape (for manual invocation)."""
        return await self._scrape_with_retry()


class BaseAutomator(MCPModule):
    """
    Base class for browser automators.
    
    Automators perform actions like login, form filling, order placement.
    Examples: Broker login, order fallback via web UI.
    """
    
    def __init__(
        self,
        name: str,
        event_bus: Optional[Any] = None,
        timeout_seconds: float = 30.0
    ):
        super().__init__(name, event_bus)
        self.timeout_seconds = timeout_seconds
    
    async def _on_start(self) -> None:
        """Initialize automator resources."""
        pass
    
    async def _on_stop(self) -> None:
        """Clean up automator resources."""
        pass
    
    async def execute(self, action: str, **params) -> ActionResult:
        """
        Execute an automation action.
        
        Args:
            action: Action name to execute
            **params: Action-specific parameters
            
        Returns:
            ActionResult with success status and data
        """
        start_time = datetime.now()
        try:
            result = await asyncio.wait_for(
                self._execute_action(action, **params),
                timeout=self.timeout_seconds
            )
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self._health.last_success = datetime.now()
            self._emit_event("MCP_ACTION_COMPLETE", {
                "automator": self.name,
                "action": action,
                "success": True,
                "duration_ms": duration
            })
            
            return ActionResult(success=True, data=result, duration_ms=duration)
            
        except asyncio.TimeoutError:
            error = f"Action '{action}' timed out after {self.timeout_seconds}s"
            self._health.error_count += 1
            self._health.last_error = error
            return ActionResult(success=False, error=error)
            
        except Exception as e:
            self._health.error_count += 1
            self._health.last_error = str(e)
            logger.error(f"{self.name}: Action '{action}' failed: {e}")
            return ActionResult(success=False, error=str(e))
        
        finally:
            self._health.last_run = datetime.now()
    
    @abstractmethod
    async def _execute_action(self, action: str, **params) -> Dict[str, Any]:
        """
        Implement the action execution logic.
        
        Args:
            action: Action name
            **params: Action parameters
            
        Returns:
            Action result data
        """
        pass


class BaseMonitor(MCPModule):
    """
    Base class for event monitors.
    
    Monitors watch for changes/events and trigger callbacks.
    Examples: News alerts, price alerts, corporate action announcements.
    """
    
    def __init__(
        self,
        name: str,
        event_bus: Optional[Any] = None,
        poll_interval_seconds: float = 30.0
    ):
        super().__init__(name, event_bus)
        self.poll_interval_seconds = poll_interval_seconds
        self._callbacks: List[Callable] = []
        self._monitor_task: Optional[asyncio.Task] = None
        self._last_state: Optional[Dict[str, Any]] = None
    
    async def _on_start(self) -> None:
        """Start monitoring loop."""
        self._monitor_task = asyncio.create_task(self._monitor_loop())
    
    async def _on_stop(self) -> None:
        """Stop monitoring."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
    
    def on_event(self, callback: Callable) -> None:
        """
        Register callback for events.
        
        Args:
            callback: Function to call when event detected
        """
        self._callbacks.append(callback)
    
    async def _monitor_loop(self) -> None:
        """Polling loop to detect changes."""
        while self._running:
            try:
                current_state = await self.check()
                changes = await self._detect_changes(current_state)
                
                if changes:
                    self._health.last_success = datetime.now()
                    await self._trigger_callbacks(changes)
                    self._emit_event("MCP_ALERT", {
                        "monitor": self.name,
                        "changes": changes
                    })
                
                self._last_state = current_state
                
            except Exception as e:
                self._health.error_count += 1
                self._health.last_error = str(e)
                logger.error(f"{self.name}: Monitor check failed: {e}")
            
            self._health.last_run = datetime.now()
            await asyncio.sleep(self.poll_interval_seconds)
    
    async def _detect_changes(self, current: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Detect changes between current and last state."""
        if self._last_state is None:
            return None  # First run, no changes to detect
        return await self.compare_states(self._last_state, current)
    
    async def _trigger_callbacks(self, changes: Dict[str, Any]) -> None:
        """Trigger all registered callbacks."""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(changes)
                else:
                    callback(changes)
            except Exception as e:
                logger.error(f"{self.name}: Callback error: {e}")
    
    @abstractmethod
    async def check(self) -> Dict[str, Any]:
        """
        Check current state.
        
        Returns:
            Current state as dictionary
        """
        pass
    
    async def compare_states(
        self,
        old_state: Dict[str, Any],
        new_state: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Compare states to detect changes.
        Override for custom comparison logic.
        
        Returns:
            Changes dict if any, None otherwise
        """
        if old_state != new_state:
            return {"old": old_state, "new": new_state}
        return None
