"""
News and Sentiment Monitor

Monitors financial news sources for market-moving events.
Tracks: MoneyControl, Economic Times, NSE Announcements.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

from app.mcp.base import BaseMonitor

logger = logging.getLogger(__name__)


class NewsSentiment(Enum):
    """Sentiment classification."""
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


class NewsCategory(Enum):
    """News categories."""
    EARNINGS = "earnings"
    CORPORATE_ACTION = "corporate_action"
    REGULATORY = "regulatory"
    MACRO = "macro"
    SECTOR = "sector"
    BREAKING = "breaking"
    ANALYST = "analyst"


@dataclass
class NewsItem:
    """A news article or announcement."""
    title: str
    source: str
    url: str
    timestamp: datetime
    symbols: List[str] = field(default_factory=list)
    category: Optional[NewsCategory] = None
    sentiment: NewsSentiment = NewsSentiment.NEUTRAL
    summary: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    importance: int = 1  # 1-5 scale


@dataclass
class NewsAlert:
    """Alert triggered by news detection."""
    news: NewsItem
    alert_type: str  # "breaking", "symbol_mention", "sentiment_shift"
    triggered_at: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False


class NewsMonitor(BaseMonitor):
    """
    Monitors news sources for market-moving events.
    
    Sources:
    - MoneyControl (Breaking news, stock updates)
    - Economic Times (Market news)
    - NSE Announcements (Corporate announcements)
    - LiveMint (Market analysis)
    
    Features:
    - Real-time news detection
    - Symbol mention extraction
    - Sentiment analysis
    - Breaking news alerts
    """
    
    # News source URLs
    SOURCES = {
        "moneycontrol": "https://www.moneycontrol.com/news/business/markets/",
        "economic_times": "https://economictimes.indiatimes.com/markets",
        "nse_announcements": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        "livemint": "https://www.livemint.com/market",
    }
    
    # Keywords that indicate market-moving news
    IMPORTANT_KEYWORDS = [
        "breaking", "urgent", "just in", "flash",
        "rbi", "fed", "rate", "inflation", "gdp",
        "earnings", "results", "profit", "loss",
        "merger", "acquisition", "buyback", "dividend",
        "upgrade", "downgrade", "target",
        "ban", "restriction", "suspension",
        "nifty", "sensex", "bank nifty",
    ]
    
    # Sentiment keywords
    BULLISH_KEYWORDS = [
        "surge", "soar", "jump", "rally", "gain", "up",
        "bullish", "positive", "upgrade", "beat", "strong",
        "record high", "breakout", "momentum",
    ]
    
    BEARISH_KEYWORDS = [
        "crash", "plunge", "fall", "drop", "decline", "down",
        "bearish", "negative", "downgrade", "miss", "weak",
        "record low", "breakdown", "selling",
    ]
    
    def __init__(
        self,
        event_bus: Optional[Any] = None,
        watchlist: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        poll_interval_seconds: float = 60.0,
    ):
        super().__init__(
            name="NewsMonitor",
            event_bus=event_bus,
            poll_interval_seconds=poll_interval_seconds
        )
        
        self.watchlist = set(watchlist or [])
        self.sources = sources or list(self.SOURCES.keys())
        
        # News cache to detect new items
        self._seen_news: Dict[str, datetime] = {}
        self._recent_news: List[NewsItem] = []
        self._alerts: List[NewsAlert] = []
        
        # Custom alert callbacks
        self._alert_callbacks: List[Callable] = []
    
    async def check(self) -> Dict[str, Any]:
        """
        Check all news sources for updates.
        
        Returns:
            Current state with latest news
        """
        logger.debug("NewsMonitor: Checking sources...")
        
        all_news = []
        
        for source in self.sources:
            try:
                news = await self._scrape_source(source)
                all_news.extend(news)
            except Exception as e:
                logger.error(f"NewsMonitor: Error scraping {source}: {e}")
        
        # Filter to new items only
        new_items = self._filter_new_items(all_news)
        
        # Analyze sentiment for each item
        for item in new_items:
            item.sentiment = self._analyze_sentiment(item.title, item.summary or "")
        
        # Check for watchlist mentions
        relevant_items = [
            item for item in new_items
            if self._is_relevant(item)
        ]
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_items": len(all_news),
            "new_items": len(new_items),
            "relevant_items": len(relevant_items),
            "news": [self._news_to_dict(n) for n in new_items[:10]],  # Top 10
            "alerts": len([a for a in self._alerts if not a.acknowledged])
        }
    
    async def compare_states(
        self,
        old_state: Dict[str, Any],
        new_state: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Compare states and detect significant changes."""
        if new_state["new_items"] > 0:
            return {
                "type": "new_news",
                "count": new_state["new_items"],
                "relevant_count": new_state["relevant_items"],
                "news": new_state["news"]
            }
        return None
    
    async def _scrape_source(self, source: str) -> List[NewsItem]:
        """Scrape a specific news source."""
        url = self.SOURCES.get(source)
        if not url:
            return []
        
        logger.debug(f"NewsMonitor: Scraping {source}")
        
        try:
            # We'll implementation extraction for MoneyControl as the primary example
            # Other sources would follow similar patterns with different selectors
            if source == "moneycontrol":
                return await self._scrape_moneycontrol(url)
            elif source == "economic_times":
                # Placeholder for ET implementation
                return []
            else:
                return []
        except Exception as e:
            logger.error(f"NewsMonitor: Scrape failed for {source}: {e}")
            return []
            
    async def _scrape_moneycontrol(self, url: str) -> List[NewsItem]:
        """Specific scraper for MoneyControl Markets News."""
        items = []
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Block images/css for speed
                await page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2}", lambda route: route.abort())
                
                await page.goto(url, timeout=30000)
                
                # MoneyControl news list items
                # Usually li.clearfix inside #cagetory (sic) or .clearfix
                articles = await page.locator("li.clearfix, .news-list li").all()
                
                for article in articles[:15]:  # Limit to top 15
                    try:
                        # Title and Link
                        link_el = article.locator("h2 a, h3 a").first
                        if await link_el.count() == 0:
                            continue
                            
                        title = await link_el.inner_text()
                        link = await link_el.get_attribute("href")
                        
                        # Timestamp (often text like "2 mins ago" or spans)
                        # MC uses span found inside the text or date class
                        time_text = ""
                        date_el = article.locator("span").first
                        if await date_el.count() > 0:
                            time_text = await date_el.inner_text()
                        
                        # Description/Summary
                        summary = ""
                        p_el = article.locator("p")
                        if await p_el.count() > 0:
                            summary = await p_el.inner_text()
                            
                        if title and link:
                            items.append(NewsItem(
                                title=title.strip(),
                                source="MoneyControl",
                                url=link,
                                timestamp=datetime.now(), # Approximation, parsing relative time is complex
                                summary=summary.strip()
                            ))
                    except Exception as e:
                        continue
                
                await browser.close()
                
        except Exception as e:
            logger.error(f"NewsMonitor: MoneyControl scrape error: {e}")
            
        return items
    
    def _filter_new_items(self, items: List[NewsItem]) -> List[NewsItem]:
        """Filter to only new items not seen before."""
        new_items = []
        now = datetime.now()
        
        for item in items:
            # Create unique key from title + source
            key = f"{item.source}:{item.title[:50]}"
            
            if key not in self._seen_news:
                self._seen_news[key] = now
                new_items.append(item)
        
        # Clean old entries (older than 24 hours)
        cutoff = now - timedelta(hours=24)
        self._seen_news = {
            k: v for k, v in self._seen_news.items()
            if v > cutoff
        }
        
        return new_items
    
    def _analyze_sentiment(self, title: str, content: str) -> NewsSentiment:
        """Analyze sentiment of news text."""
        text = (title + " " + content).lower()
        
        bullish_count = sum(1 for kw in self.BULLISH_KEYWORDS if kw in text)
        bearish_count = sum(1 for kw in self.BEARISH_KEYWORDS if kw in text)
        
        diff = bullish_count - bearish_count
        
        if diff >= 3:
            return NewsSentiment.VERY_BULLISH
        elif diff >= 1:
            return NewsSentiment.BULLISH
        elif diff <= -3:
            return NewsSentiment.VERY_BEARISH
        elif diff <= -1:
            return NewsSentiment.BEARISH
        else:
            return NewsSentiment.NEUTRAL
    
    def _is_relevant(self, item: NewsItem) -> bool:
        """Check if news item is relevant to watchlist."""
        # Check if any watchlist symbol is mentioned
        text = (item.title + " " + (item.summary or "")).upper()
        
        for symbol in self.watchlist:
            if symbol.upper() in text:
                item.symbols.append(symbol)
                return True
        
        # Check for breaking news keywords
        if any(kw in item.title.lower() for kw in ["breaking", "urgent", "flash"]):
            return True
        
        return False
    
    def _news_to_dict(self, news: NewsItem) -> Dict[str, Any]:
        """Convert NewsItem to dictionary."""
        return {
            "title": news.title,
            "source": news.source,
            "url": news.url,
            "timestamp": news.timestamp.isoformat(),
            "symbols": news.symbols,
            "category": news.category.value if news.category else None,
            "sentiment": news.sentiment.value,
            "importance": news.importance
        }
    
    def add_to_watchlist(self, symbol: str) -> None:
        """Add symbol to watchlist."""
        self.watchlist.add(symbol.upper())
        logger.info(f"NewsMonitor: Added {symbol} to watchlist")
    
    def remove_from_watchlist(self, symbol: str) -> None:
        """Remove symbol from watchlist."""
        self.watchlist.discard(symbol.upper())
    
    def get_recent_news(self, limit: int = 20) -> List[NewsItem]:
        """Get recent news items."""
        return self._recent_news[:limit]
    
    def get_news_for_symbol(self, symbol: str) -> List[NewsItem]:
        """Get news mentioning a specific symbol."""
        return [
            n for n in self._recent_news
            if symbol.upper() in [s.upper() for s in n.symbols]
        ]
    
    def get_unacknowledged_alerts(self) -> List[NewsAlert]:
        """Get alerts that haven't been acknowledged."""
        return [a for a in self._alerts if not a.acknowledged]
    
    def acknowledge_alert(self, index: int) -> None:
        """Acknowledge an alert by index."""
        if 0 <= index < len(self._alerts):
            self._alerts[index].acknowledged = True
