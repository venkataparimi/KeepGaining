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
    
    async def _scrape_option_chain(self, symbol: str, headless: bool = True) -> Optional[Dict[str, Any]]:
        """
        Scrape option chain data using Playwright.
        Uses cookies from home page and fetches API data directly.
        """
        data = None
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless, args=["--disable-http2"])
                
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    extra_http_headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Upgrade-Insecure-Requests": "1"
                    }
                )
                
                page = await context.new_page()
                
                # 1. Visit Homepage to set cookies
                logger.info("NSE_OI: Visiting NSE Homepage for session...")
                try:
                    await page.goto("https://www.nseindia.com", timeout=45000)
                    await page.wait_for_timeout(2000) # Wait for cookies
                except Exception as e:
                     logger.warning(f"NSE_OI: Details - {e}")

                # 2. Determine API URL based on symbol type
                if symbol.upper() in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]:
                    api_url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol.upper()}"
                else:
                    api_url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol.upper()}"

                logger.info(f"NSE_OI: Fetching API data from {api_url}")

                # 3. Fetch Data via Page Context
                data = await page.evaluate(f"""async () => {{
                    try {{
                        const response = await fetch("{api_url}", {{
                            headers: {{
                                "Accept": "application/json, text/plain, */*",
                                "X-Requested-With": "XMLHttpRequest"
                            }}
                        }});
                        if (!response.ok) return null;
                        return await response.json();
                    }} catch (e) {{ return null; }}
                }}""")

                if not data:
                     logger.error(f"NSE_OI: Failed to fetch data for {symbol}")
                     # Try V3 fallback if NIFTY
                     if "NIFTY" in symbol.upper():
                         v3_url = f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={symbol.upper()}"
                         logger.info(f"NSE_OI: Retrying with V3 URL: {v3_url}")
                         data = await page.evaluate(f"""async () => {{
                            try {{
                                const response = await fetch("{v3_url}", {{
                                    headers: {{ "X-Requested-With": "XMLHttpRequest" }}
                                }});
                                return await response.json();
                            }} catch (e) {{ return null; }}
                        }}""")
                
                await browser.close()

        except Exception as e:
            logger.error(f"NSE_OI: Scrape error for {symbol}: {e}")
            return None
            
        return data           
    
    async def get_premarket_data(self, category: str = "NIFTY", headless: bool = True) -> Optional[Dict[str, Any]]:
        """
        Fetch pre-open market data.
        Category: 'NIFTY', 'BANKNIFTY', 'FO' (F&O stocks)
        """
        url_map = {
            "NIFTY": "https://www.nseindia.com/api/market-data-pre-open?key=NIFTY",
            "BANKNIFTY": "https://www.nseindia.com/api/market-data-pre-open?key=BANKNIFTY",
            "FO": "https://www.nseindia.com/api/market-data-pre-open?key=FO"
        }
        
        target_url = url_map.get(category, url_map["NIFTY"])
        
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless, args=["--disable-http2"])
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    extra_http_headers={"Upgrade-Insecure-Requests": "1"}
                )
                page = await context.new_page()
                
                # Visit Pre-open page directly to set cookies (lighter than homepage)
                try:
                    await page.goto("https://www.nseindia.com/market-data/pre-open-market-cm-and-emerge-market", timeout=45000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000) 
                except Exception as e:
                    logger.warning(f"NSE_OI: Page load warning: {e}")
                
                logger.info(f"NSE_OI: Fetching Pre-market data from {target_url}")
                data = await page.evaluate(f"""async () => {{
                    try {{
                        const response = await fetch("{target_url}", {{
                            headers: {{ "X-Requested-With": "XMLHttpRequest" }}
                        }});
                        return await response.json();
                    }} catch (e) {{ return null; }}
                }}""")
                
                if not data:
                    logger.error(f"NSE_OI: Premarket data null for {category}")
                    # Screenshot if visible or headless
                    try: await page.screenshot(path="nse_premarket_fail.png")
                    except: pass
                
                await browser.close()
                return data
        except Exception as e:
            logger.error(f"NSE_OI: Premarket fetch failed: {e}")
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
