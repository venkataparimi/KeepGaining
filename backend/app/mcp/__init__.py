"""
MCP (Model Context Protocol) Integration Package

Browser automation for algo trading: scrapers, automators, and monitors.
"""

from app.mcp.base import (
    MCPModule,
    BaseScraper,
    BaseAutomator,
    BaseMonitor,
    ModuleStatus,
    ModuleHealth,
    ActionResult,
)

from app.mcp.manager import (
    MCPManager,
    MCPConfig,
    MCPManagerStatus,
    BrowserType,
    get_mcp_manager,
    init_mcp_manager,
)

__all__ = [
    # Base classes
    "MCPModule",
    "BaseScraper",
    "BaseAutomator",
    "BaseMonitor",
    "ModuleStatus",
    "ModuleHealth",
    "ActionResult",
    # Manager
    "MCPManager",
    "MCPConfig",
    "MCPManagerStatus",
    "BrowserType",
    "get_mcp_manager",
    "init_mcp_manager",
]
