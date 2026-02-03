"""
Chartink Screener Automation

Automates running stock screeners on Chartink.com.
Supports both predefined and custom screeners.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.mcp.base import BaseScraper

logger = logging.getLogger(__name__)


@dataclass
class ScreenerStock:
    """Stock returned from a screener."""
    symbol: str
    name: str
    price: float = 0.0
    change_percent: float = 0.0
    volume: int = 0
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    custom_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScreenerResult:
    """Result of running a screener."""
    screener_name: str
    screener_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    stocks: List[ScreenerStock] = field(default_factory=list)
    total_count: int = 0
    execution_time_ms: float = 0


class ChartinkScraper(BaseScraper):
    """
    Automates Chartink screeners.
    
    Features:
    - Run predefined screeners by ID
    - Run custom screener queries
    - Parse results into structured data
    
    Popular Screeners:
    - Volume breakout
    - 52-week high
    - RSI divergence
    - Moving average crossovers
    """
    
    BASE_URL = "https://chartink.com"
    SCREENER_URL = "/screener/process"
    
    # Predefined screener queries
    PREDEFINED_SCREENERS = {
        "volume_breakout": {
            "name": "Volume Breakout",
            "query": "( {cash} ( latest volume > 1.5 * latest sma( volume,20 ) and latest close > latest sma( close,20 ) ) )"
        },
        "52_week_high": {
            "name": "52 Week High",
            "query": "( {cash} ( latest high = latest max( 260 , latest high ) ) )"
        },
        "rsi_oversold": {
            "name": "RSI Oversold",
            "query": "( {cash} ( latest rsi( 14 ) < 30 ) )"
        },
        "rsi_overbought": {
            "name": "RSI Overbought", 
            "query": "( {cash} ( latest rsi( 14 ) > 70 ) )"
        },
        "macd_crossover": {
            "name": "MACD Bullish Crossover",
            "query": "( {cash} ( latest macd line( 26 , 12 , 9 ) > latest macd signal( 26 , 12 , 9 ) and 1 day ago macd line( 26 , 12 , 9 ) < 1 day ago macd signal( 26 , 12 , 9 ) ) )"
        },
        "gap_up": {
            "name": "Gap Up Opening",
            "query": "( {cash} ( latest open > 1 day ago high ) )"
        },
        "gap_down": {
            "name": "Gap Down Opening",
            "query": "( {cash} ( latest open < 1 day ago low ) )"
        },
        "bullish_engulfing": {
            "name": "Bullish Engulfing",
            "query": "( {cash} ( latest close > latest open and 1 day ago close < 1 day ago open and latest open < 1 day ago close and latest close > 1 day ago open ) )"
        },
    }
    
    def __init__(
        self,
        event_bus: Optional[Any] = None,
        screeners: Optional[List[str]] = None,
        interval_seconds: int = 300,  # 5 minutes
        custom_queries: Optional[Dict[str, str]] = None
    ):
        super().__init__(
            name="Chartink",
            event_bus=event_bus,
            interval_seconds=interval_seconds,
            max_retries=2,
            retry_delay_seconds=5.0
        )
        
        # Default to volume_breakout if no screeners specified
        self.screeners = screeners or ["volume_breakout"]
        self.custom_queries = custom_queries or {}
        
        # Results cache
        self._results_cache: Dict[str, ScreenerResult] = {}
    
    async def scrape(self) -> Dict[str, Any]:
        """
        Run all configured screeners.
        
        Returns:
            Dictionary with results from each screener
        """
        logger.info(f"Chartink: Running {len(self.screeners)} screeners...")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "screeners": {},
            "errors": []
        }
        
        for screener_id in self.screeners:
            try:
                result = await self.run_screener(screener_id)
                if result:
                    results["screeners"][screener_id] = {
                        "name": result.screener_name,
                        "count": result.total_count,
                        "stocks": [s.__dict__ for s in result.stocks],
                        "execution_time_ms": result.execution_time_ms
                    }
                    self._results_cache[screener_id] = result
            except Exception as e:
                results["errors"].append(f"{screener_id}: {str(e)}")
                logger.error(f"Chartink: Screener {screener_id} failed: {e}")
        
        # Also run custom queries
        for name, query in self.custom_queries.items():
            try:
                result = await self.run_custom_query(query, name)
                if result:
                    results["screeners"][f"custom_{name}"] = {
                        "name": result.screener_name,
                        "count": result.total_count,
                        "stocks": [s.__dict__ for s in result.stocks]
                    }
            except Exception as e:
                results["errors"].append(f"custom_{name}: {str(e)}")
        
        total_stocks = sum(r.get("count", 0) for r in results["screeners"].values())
        logger.info(f"Chartink: Found {total_stocks} stocks across {len(results['screeners'])} screeners")
        
        return results
    
    async def run_screener(self, screener_id: str) -> Optional[ScreenerResult]:
        """
        Run a predefined screener.
        
        Args:
            screener_id: ID from PREDEFINED_SCREENERS
            
        Returns:
            ScreenerResult with matching stocks
        """
        if screener_id not in self.PREDEFINED_SCREENERS:
            logger.warning(f"Chartink: Unknown screener '{screener_id}'")
            return None
        
        screener = self.PREDEFINED_SCREENERS[screener_id]
        return await self.run_custom_query(screener["query"], screener["name"])
    
    async def run_custom_query(
        self,
        query: str,
        name: str = "Custom"
    ) -> Optional[ScreenerResult]:
        """
        Run a custom Chartink query.
        
        Uses Chrome DevTools MCP to:
        1. Navigate to Chartink screener
        2. Enter custom query
        3. Execute and parse results
        """
        logger.debug(f"Chartink: Running query '{name}'")
        
        start_time = datetime.now()
        
        # MCP Integration:
        # 1. mcp_chrome-devtools_navigate_page to Chartink
        # 2. mcp_chrome-devtools_fill for query input
        # 3. mcp_chrome-devtools_click for submit
        # 4. mcp_chrome-devtools_wait_for results table
        # 5. mcp_chrome-devtools_evaluate_script to extract data
        
        # Placeholder until MCP integration
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return ScreenerResult(
            screener_name=name,
            timestamp=datetime.now(),
            stocks=[],
            total_count=0,
            execution_time_ms=execution_time
        )
    
    def get_latest_results(self, screener_id: str) -> Optional[ScreenerResult]:
        """Get cached results for a screener."""
        return self._results_cache.get(screener_id)
    
    def get_all_stocks(self) -> List[ScreenerStock]:
        """Get all unique stocks from all screeners."""
        seen = set()
        stocks = []
        
        for result in self._results_cache.values():
            for stock in result.stocks:
                if stock.symbol not in seen:
                    seen.add(stock.symbol)
                    stocks.append(stock)
        
        return stocks
    
    def add_custom_screener(self, name: str, query: str) -> None:
        """Add a custom screener query."""
        self.custom_queries[name] = query
        logger.info(f"Chartink: Added custom screener '{name}'")
