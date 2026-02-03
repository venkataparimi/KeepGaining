"""
MCP Manager - Central coordinator for browser automation.

Manages Chrome DevTools and Playwright connections, module lifecycle,
and provides a unified interface for all MCP operations.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Type
from enum import Enum

from app.mcp.base import MCPModule, ModuleHealth, ModuleStatus

logger = logging.getLogger(__name__)


class BrowserType(Enum):
    """Browser automation backend types."""
    CHROME_DEVTOOLS = "chrome_devtools"  # Control existing Chrome
    PLAYWRIGHT = "playwright"             # Spawn new browser


@dataclass
class MCPConfig:
    """Configuration for MCP Manager."""
    # Chrome DevTools settings
    chrome_debug_port: int = 9222
    chrome_host: str = "localhost"
    
    # Playwright settings
    playwright_headless: bool = True
    playwright_browser: str = "chromium"  # chromium, firefox, webkit
    playwright_timeout_ms: int = 30000
    
    # Rate limiting
    requests_per_minute: int = 30
    request_delay_ms: int = 100
    
    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    
    # Circuit breaker
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_seconds: int = 60


@dataclass
class MCPManagerStatus:
    """Overall status of MCP Manager."""
    running: bool
    chrome_devtools_connected: bool
    playwright_available: bool
    active_modules: int
    total_modules: int
    modules_health: Dict[str, ModuleHealth] = field(default_factory=dict)


class MCPManager:
    """
    Central manager for all MCP browser automation.
    
    Responsibilities:
    - Manage Chrome DevTools connection (for live browser interaction)
    - Manage Playwright session pool (for background automation)
    - Module lifecycle management (register, start, stop)
    - Rate limiting and circuit breaker protection
    - Health monitoring
    
    Usage:
        manager = MCPManager(event_bus, config)
        await manager.start()
        
        # Register modules
        manager.register_module(NSE_OI_Scraper())
        manager.register_module(BrokerLoginAutomator())
        
        # Start all modules
        await manager.start_all_modules()
    """
    
    def __init__(
        self,
        event_bus: Optional[Any] = None,
        config: Optional[MCPConfig] = None
    ):
        self.event_bus = event_bus
        self.config = config or MCPConfig()
        
        # Module registry
        self._modules: Dict[str, MCPModule] = {}
        
        # State
        self._running = False
        self._chrome_connected = False
        self._playwright_available = False
        self._playwright = None
        self._browser = None
        
        # Rate limiting
        self._request_timestamps: List[datetime] = []
        self._rate_limit_lock = asyncio.Lock()
        
        # Circuit breaker
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_opened_at: Optional[datetime] = None
    
    async def start(self) -> None:
        """Start the MCP Manager."""
        logger.info("MCPManager: Starting...")
        self._running = True
        
        # Try to connect to Chrome DevTools
        await self._connect_chrome_devtools()
        
        # Initialize Playwright
        await self._init_playwright()
        
        logger.info(f"MCPManager: Started (Chrome: {self._chrome_connected}, Playwright: {self._playwright_available})")
    
    async def stop(self) -> None:
        """Stop the MCP Manager and all modules."""
        logger.info("MCPManager: Stopping...")
        
        # Stop all modules
        await self.stop_all_modules()
        
        # Close Playwright
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
            
        self._running = False
        logger.info("MCPManager: Stopped")
    
    async def _connect_chrome_devtools(self) -> None:
        """Attempt to connect to Chrome DevTools."""
        try:
            # Check if Chrome is running with debug port
            # This will be implemented when we use the actual MCP tools
            # For now, we assume it's available if port is open
            import asyncio
            try:
                reader, writer = await asyncio.open_connection(
                    self.config.chrome_host, 
                    self.config.chrome_debug_port
                )
                writer.close()
                await writer.wait_closed()
                self._chrome_connected = True
                logger.info(f"MCPManager: Chrome DevTools available on port {self.config.chrome_debug_port}")
            except (ConnectionRefusedError, OSError):
                self._chrome_connected = False
                logger.warning(f"MCPManager: Chrome DevTools not available on port {self.config.chrome_debug_port}")
                
        except Exception as e:
            self._chrome_connected = False
            logger.warning(f"MCPManager: Chrome DevTools check failed: {e}")
    
    async def _init_playwright(self) -> None:
        """Initialize Playwright and launch browser."""
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            
            browser_type = getattr(self._playwright, self.config.playwright_browser)
            self._browser = await browser_type.launch(
                headless=self.config.playwright_headless
            )
            
            self._playwright_available = True
            logger.info(f"MCPManager: Playwright browser ({self.config.playwright_browser}) launched")
            
        except ImportError:
            self._playwright_available = False
            logger.error("MCPManager: Playwright not installed. Run: pip install playwright && playwright install")
        except Exception as e:
            self._playwright_available = False
            logger.error(f"MCPManager: Playwright initialization failed: {e}")

    async def get_new_context(self) -> Any:
        """Get a new browser context from the managed browser."""
        if not self._playwright_available or not self._browser:
            raise RuntimeError("Playwright is not available")
        return await self._browser.new_context()
    
    def register_module(self, module: MCPModule) -> None:
        """
        Register an MCP module.
        
        Args:
            module: MCPModule instance to register
        """
        if module.name in self._modules:
            logger.warning(f"MCPManager: Module '{module.name}' already registered, replacing")
        
        # Inject event bus if module doesn't have one
        if module.event_bus is None:
            module.event_bus = self.event_bus
        
        self._modules[module.name] = module
        logger.info(f"MCPManager: Registered module '{module.name}'")
    
    def unregister_module(self, name: str) -> None:
        """Unregister a module by name."""
        if name in self._modules:
            del self._modules[name]
            logger.info(f"MCPManager: Unregistered module '{name}'")
    
    def get_module(self, name: str) -> Optional[MCPModule]:
        """Get a module by name."""
        return self._modules.get(name)
    
    async def start_module(self, name: str) -> bool:
        """Start a specific module."""
        module = self._modules.get(name)
        if not module:
            logger.error(f"MCPManager: Module '{name}' not found")
            return False
        
        try:
            await module.start()
            return True
        except Exception as e:
            logger.error(f"MCPManager: Failed to start '{name}': {e}")
            return False
    
    async def stop_module(self, name: str) -> bool:
        """Stop a specific module."""
        module = self._modules.get(name)
        if not module:
            return False
        
        try:
            await module.stop()
            return True
        except Exception as e:
            logger.error(f"MCPManager: Failed to stop '{name}': {e}")
            return False
    
    async def start_all_modules(self) -> Dict[str, bool]:
        """Start all registered modules."""
        results = {}
        for name in self._modules:
            results[name] = await self.start_module(name)
        return results
    
    async def stop_all_modules(self) -> Dict[str, bool]:
        """Stop all registered modules."""
        results = {}
        for name in self._modules:
            results[name] = await self.stop_module(name)
        return results
    
    async def rate_limit(self) -> None:
        """Apply rate limiting before making requests."""
        async with self._rate_limit_lock:
            now = datetime.now()
            
            # Remove old timestamps (older than 1 minute)
            cutoff = now.timestamp() - 60
            self._request_timestamps = [
                ts for ts in self._request_timestamps
                if ts.timestamp() > cutoff
            ]
            
            # Check if we're over the limit
            if len(self._request_timestamps) >= self.config.requests_per_minute:
                # Wait until oldest request expires
                oldest = min(self._request_timestamps)
                wait_time = 60 - (now.timestamp() - oldest.timestamp())
                if wait_time > 0:
                    logger.debug(f"MCPManager: Rate limiting, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
            
            # Add current timestamp
            self._request_timestamps.append(now)
            
            # Apply minimum delay between requests
            await asyncio.sleep(self.config.request_delay_ms / 1000)
    
    def check_circuit_breaker(self) -> bool:
        """
        Check if circuit breaker is open.
        
        Returns:
            True if requests should be blocked, False otherwise
        """
        if not self._circuit_open:
            return False
        
        # Check if reset time has passed
        if self._circuit_opened_at:
            elapsed = (datetime.now() - self._circuit_opened_at).total_seconds()
            if elapsed > self.config.circuit_breaker_reset_seconds:
                self._circuit_open = False
                self._consecutive_failures = 0
                logger.info("MCPManager: Circuit breaker reset")
                return False
        
        return True
    
    def record_success(self) -> None:
        """Record a successful request."""
        self._consecutive_failures = 0
    
    def record_failure(self) -> None:
        """Record a failed request, potentially opening circuit breaker."""
        self._consecutive_failures += 1
        
        if self._consecutive_failures >= self.config.circuit_breaker_threshold:
            self._circuit_open = True
            self._circuit_opened_at = datetime.now()
            logger.warning(
                f"MCPManager: Circuit breaker OPEN after {self._consecutive_failures} failures"
            )
    
    def get_status(self) -> MCPManagerStatus:
        """Get overall status of the MCP Manager."""
        modules_health = {
            name: module.health
            for name, module in self._modules.items()
        }
        
        active_count = sum(
            1 for m in self._modules.values()
            if m.status == ModuleStatus.RUNNING
        )
        
        return MCPManagerStatus(
            running=self._running,
            chrome_devtools_connected=self._chrome_connected,
            playwright_available=self._playwright_available,
            active_modules=active_count,
            total_modules=len(self._modules),
            modules_health=modules_health
        )


# Singleton instance
_mcp_manager: Optional[MCPManager] = None


def get_mcp_manager() -> Optional[MCPManager]:
    """Get the global MCP Manager instance."""
    return _mcp_manager


def init_mcp_manager(
    event_bus: Optional[Any] = None,
    config: Optional[MCPConfig] = None
) -> MCPManager:
    """Initialize the global MCP Manager instance."""
    global _mcp_manager
    _mcp_manager = MCPManager(event_bus, config)
    return _mcp_manager
