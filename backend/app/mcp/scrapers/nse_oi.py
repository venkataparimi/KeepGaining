"""
NSE OI and FII/DII Data Scraper

Scrapes NSE India website for:
- Open Interest data
- FII/DII buy/sell data
- Delivery percentage
- Bulk/block deals
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from app.mcp.base import BaseScraper

logger = logging.getLogger(__name__)


@dataclass
class OIData:
    """Open Interest data for a symbol."""
    symbol: str
    expiry: date
    strike: Optional[float] = None
    option_type: Optional[str] = None  # CE/PE
    oi: int = 0
    oi_change: int = 0
    oi_change_percent: float = 0.0
    volume: int = 0
    last_price: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class FIIDIIData:
    """FII/DII trading data."""
    date: date
    fii_buy: float = 0.0
    fii_sell: float = 0.0
    fii_net: float = 0.0
    dii_buy: float = 0.0
    dii_sell: float = 0.0
    dii_net: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DeliveryData:
    """Delivery percentage data."""
    symbol: str
    date: date
    traded_qty: int = 0
    deliverable_qty: int = 0
    delivery_percent: float = 0.0


@dataclass
class BulkDeal:
    """Bulk/Block deal information."""
    symbol: str
    date: date
    client_name: str
    deal_type: str  # BUY/SELL
    quantity: int
    price: float


class NSE_OI_Scraper(BaseScraper):
    """
    Scrapes NSE India for OI, FII/DII, and market data.
    
    Data Sources:
    - https://www.nseindia.com/api/option-chain-indices
    - https://www.nseindia.com/api/fiidiiTradeReact
    - https://www.nseindia.com/api/equity-stockIndices
    
    Schedule: Every 15 minutes during market hours
    """
    
    # NSE API endpoints
    BASE_URL = "https://www.nseindia.com"
    OPTION_CHAIN_URL = "/api/option-chain-indices"
    FII_DII_URL = "/api/fiidiiTradeReact"
    EQUITY_URL = "/api/equity-stockIndices"
    DELIVERY_URL = "/api/corporate-announcements"
    
    # Supported indices for option chain
    SUPPORTED_INDICES = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]
    
    def __init__(
        self,
        event_bus: Optional[Any] = None,
        symbols: Optional[List[str]] = None,
        interval_seconds: int = 900,  # 15 minutes
    ):
        super().__init__(
            name="NSE_OI",
            event_bus=event_bus,
            interval_seconds=interval_seconds,
            max_retries=3,
            retry_delay_seconds=10.0
        )
        
        self.symbols = symbols or self.SUPPORTED_INDICES
        self._cache: Dict[str, Any] = {}
    
    async def scrape(self) -> Dict[str, Any]:
        """
        Scrape all NSE data.
        
        Returns:
            Dictionary with oi_data, fii_dii, delivery data
        """
        logger.info("NSE_OI: Starting scrape...")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "oi_data": {},
            "fii_dii": None,
            "errors": []
        }
        
        try:
            # Scrape option chain for each index
            for symbol in self.symbols:
                try:
                    oi = await self._scrape_option_chain(symbol)
                    if oi:
                        results["oi_data"][symbol] = oi
                except Exception as e:
                    results["errors"].append(f"{symbol}: {str(e)}")
            
            # Scrape FII/DII data
            try:
                fii_dii = await self._scrape_fii_dii()
                results["fii_dii"] = fii_dii
            except Exception as e:
                results["errors"].append(f"FII/DII: {str(e)}")
            
            logger.info(f"NSE_OI: Scraped {len(results['oi_data'])} indices, FII/DII: {results['fii_dii'] is not None}")
            
        except Exception as e:
            logger.error(f"NSE_OI: Scrape failed: {e}")
            results["errors"].append(str(e))
        
        return results
    
    async def _scrape_option_chain(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Scrape option chain data for a symbol.
        
        Uses Playwright to:
        1. Visit home page (to establish session/cookies)
        2. Fetch internal API data directly
        """
        logger.debug(f"NSE_OI: Scraping option chain for {symbol}")
        
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                # Use specific user agent to mimic real user
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, right Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                # 1. Visit Home Page (Crucial for NSE cookies)
                await page.goto(self.BASE_URL, timeout=30000)
                
                # 2. Fetch Option Chain API
                api_url = f"{self.BASE_URL}{self.OPTION_CHAIN_URL}?symbol={symbol}"
                
                # Wait a bit after home page load
                await asyncio.sleep(1)
                
                response = await page.goto(api_url)
                if not response.ok:
                    logger.error(f"NSE_OI: API request failed: {response.status}")
                    await browser.close()
                    return None
                    
                data = await response.json()
                await browser.close()
                
                return data

        except Exception as e:
            logger.error(f"NSE_OI: Scrape error for {symbol}: {e}")
            return None
    
    async def _scrape_fii_dii(self) -> Optional[Dict[str, Any]]:
        """
        Scrape FII/DII data.
        
        Uses Chrome DevTools MCP to:
        1. Navigate to FII/DII page
        2. Extract trading data
        """
        logger.debug("NSE_OI: Scraping FII/DII data")
        
        # MCP Integration:
        # 1. Navigate to NSE FII/DII page
        # 2. Extract data from tables
        
        return {
            "date": date.today().isoformat(),
            "timestamp": datetime.now().isoformat(),
            "fii": {"buy": 0, "sell": 0, "net": 0},
            "dii": {"buy": 0, "sell": 0, "net": 0},
            "note": "MCP integration pending"
        }
    
    async def get_oi_data(self, symbol: str) -> Optional[OIData]:
        """Get latest OI data for a symbol."""
        if symbol in self._cache:
            return self._cache[symbol]
        
        data = await self._scrape_option_chain(symbol)
        return data
    
    async def get_fii_dii(self) -> Optional[FIIDIIData]:
        """Get latest FII/DII data."""
        return await self._scrape_fii_dii()
    
    async def get_max_pain(self, symbol: str) -> Optional[float]:
        """Calculate max pain for a symbol."""
        oi_data = await self.get_oi_data(symbol)
        if not oi_data:
            return None
        
        # Max pain calculation would go here
        # Sum of (strike - current_price) * OI for all strikes
        # Strike with minimum value is max pain
        
        return oi_data.get("max_pain", 0.0)
    
    async def get_pcr(self, symbol: str) -> Optional[float]:
        """Get Put-Call Ratio for a symbol."""
        oi_data = await self.get_oi_data(symbol)
        if not oi_data:
            return None
        
        return oi_data.get("pcr", 0.0)
