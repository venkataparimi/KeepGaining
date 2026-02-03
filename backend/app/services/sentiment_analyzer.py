"""
Sentiment Analysis Integration Service

Aggregates sentiment data from multiple sources:
- News articles (Economic Times, Moneycontrol, etc.)
- Social media (Twitter/X, Reddit)
- Market data (FII/DII flows, options sentiment)
- Analyst ratings aggregation

Provides sentiment scores for:
- Individual stocks
- Sectors
- Overall market
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import aiohttp

logger = logging.getLogger(__name__)


class SentimentSource(str, Enum):
    """Sources of sentiment data."""
    NEWS = "news"
    TWITTER = "twitter"
    REDDIT = "reddit"
    OPTIONS = "options"  # Put/Call ratio, Max Pain
    FII_DII = "fii_dii"  # Institutional flows
    ANALYST = "analyst"  # Analyst ratings


class SentimentLevel(str, Enum):
    """Sentiment classification levels."""
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


@dataclass
class SentimentScore:
    """Sentiment score for a symbol/sector."""
    symbol: str
    score: float  # -1 to +1
    level: SentimentLevel
    confidence: float  # 0 to 1
    sources: Dict[str, float]  # Score per source
    sample_size: int
    timestamp: datetime = field(default_factory=datetime.now)
    

@dataclass
class NewsItem:
    """News article with sentiment."""
    title: str
    source: str
    url: str
    published_at: datetime
    sentiment_score: float
    relevance_score: float
    symbols: List[str]
    summary: Optional[str] = None


@dataclass
class SocialPost:
    """Social media post with sentiment."""
    platform: str
    content: str
    author: str
    posted_at: datetime
    sentiment_score: float
    engagement: int  # likes, retweets, upvotes
    symbols: List[str]


@dataclass
class MarketSentiment:
    """Overall market sentiment indicators."""
    fear_greed_index: float  # 0-100
    put_call_ratio: float
    vix_level: float
    fii_net_flow: float
    dii_net_flow: float
    advance_decline_ratio: float
    sentiment_level: SentimentLevel
    timestamp: datetime = field(default_factory=datetime.now)


class SentimentAnalyzer:
    """
    Sentiment Analysis Service.
    
    Aggregates and analyzes sentiment from multiple sources to provide
    trading signals enhancement.
    """
    
    # Keywords for basic sentiment analysis
    BULLISH_KEYWORDS = [
        'buy', 'bullish', 'long', 'upside', 'breakout', 'rally', 'surge',
        'outperform', 'upgrade', 'strong', 'growth', 'opportunity', 'beat',
        'positive', 'rise', 'gain', 'profit', 'momentum', 'support', 'accumulate'
    ]
    
    BEARISH_KEYWORDS = [
        'sell', 'bearish', 'short', 'downside', 'breakdown', 'crash', 'plunge',
        'underperform', 'downgrade', 'weak', 'decline', 'risk', 'miss',
        'negative', 'fall', 'loss', 'drop', 'resistance', 'distribute', 'avoid'
    ]
    
    # NSE sectors mapping
    SECTOR_KEYWORDS = {
        'banking': ['hdfc', 'icici', 'sbi', 'axis', 'kotak', 'bank', 'banking', 'npa', 'credit'],
        'it': ['tcs', 'infosys', 'wipro', 'hcl', 'tech mahindra', 'software', 'it sector', 'digital'],
        'pharma': ['sun pharma', 'cipla', 'dr reddy', 'lupin', 'pharma', 'drug', 'fda', 'healthcare'],
        'auto': ['tata motors', 'maruti', 'mahindra', 'hero', 'bajaj', 'auto', 'ev', 'vehicle'],
        'fmcg': ['hul', 'itc', 'nestle', 'britannia', 'fmcg', 'consumer', 'retail'],
        'energy': ['reliance', 'ongc', 'ioc', 'bpcl', 'oil', 'gas', 'energy', 'crude'],
        'metals': ['tata steel', 'jsw', 'hindalco', 'vedanta', 'steel', 'metal', 'aluminium', 'copper'],
        'realty': ['dlf', 'godrej', 'oberoi', 'prestige', 'real estate', 'property', 'housing'],
    }
    
    def __init__(
        self,
        news_api_key: Optional[str] = None,
        twitter_bearer_token: Optional[str] = None,
        cache_ttl_minutes: int = 15
    ):
        self.news_api_key = news_api_key
        self.twitter_bearer_token = twitter_bearer_token
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        
        # Caches
        self._sentiment_cache: Dict[str, Tuple[SentimentScore, datetime]] = {}
        self._news_cache: Dict[str, Tuple[List[NewsItem], datetime]] = {}
        self._market_sentiment_cache: Optional[Tuple[MarketSentiment, datetime]] = None
        
        # Rate limiting
        self._last_api_call: Dict[str, datetime] = {}
        self._min_api_interval = timedelta(seconds=1)
    
    def _simple_sentiment_score(self, text: str) -> float:
        """
        Calculate simple sentiment score from text using keyword matching.
        Returns score between -1 (bearish) and +1 (bullish).
        """
        text_lower = text.lower()
        
        bullish_count = sum(1 for kw in self.BULLISH_KEYWORDS if kw in text_lower)
        bearish_count = sum(1 for kw in self.BEARISH_KEYWORDS if kw in text_lower)
        
        total = bullish_count + bearish_count
        if total == 0:
            return 0.0
        
        return (bullish_count - bearish_count) / total
    
    def _score_to_level(self, score: float) -> SentimentLevel:
        """Convert numeric score to sentiment level."""
        if score >= 0.5:
            return SentimentLevel.VERY_BULLISH
        elif score >= 0.2:
            return SentimentLevel.BULLISH
        elif score <= -0.5:
            return SentimentLevel.VERY_BEARISH
        elif score <= -0.2:
            return SentimentLevel.BEARISH
        else:
            return SentimentLevel.NEUTRAL
    
    def _extract_symbols(self, text: str) -> List[str]:
        """Extract stock symbols from text."""
        # Common NSE symbols pattern
        symbols = []
        
        # Look for explicit mentions like $RELIANCE or NSE:RELIANCE
        patterns = [
            r'\$([A-Z]{2,20})',  # $SYMBOL
            r'NSE:([A-Z]{2,20})',  # NSE:SYMBOL
            r'BSE:([A-Z]{2,20})',  # BSE:SYMBOL
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text.upper())
            symbols.extend(matches)
        
        return list(set(symbols))
    
    async def analyze_text(self, text: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze sentiment of a text.
        
        Args:
            text: Text to analyze
            context: Optional context (stock symbol, sector, etc.)
            
        Returns:
            Dict with sentiment score, level, and extracted entities
        """
        score = self._simple_sentiment_score(text)
        level = self._score_to_level(score)
        symbols = self._extract_symbols(text)
        
        # Detect sector mentions
        sectors = []
        text_lower = text.lower()
        for sector, keywords in self.SECTOR_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                sectors.append(sector)
        
        return {
            "score": score,
            "level": level.value,
            "symbols": symbols,
            "sectors": sectors,
            "word_count": len(text.split()),
            "confidence": min(1.0, len(text.split()) / 50)  # More words = more confidence
        }
    
    async def get_news_sentiment(
        self,
        symbol: Optional[str] = None,
        sector: Optional[str] = None,
        limit: int = 20
    ) -> List[NewsItem]:
        """
        Get news articles with sentiment analysis.
        
        Args:
            symbol: Stock symbol to filter
            sector: Sector to filter
            limit: Maximum articles to return
            
        Returns:
            List of NewsItem with sentiment scores
        """
        cache_key = f"news_{symbol}_{sector}"
        
        # Check cache
        if cache_key in self._news_cache:
            cached, timestamp = self._news_cache[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                return cached[:limit]
        
        # Generate mock news for demo (replace with actual API calls)
        news_items = self._generate_mock_news(symbol, sector, limit)
        
        # Cache results
        self._news_cache[cache_key] = (news_items, datetime.now())
        
        return news_items
    
    def _generate_mock_news(
        self,
        symbol: Optional[str],
        sector: Optional[str],
        limit: int
    ) -> List[NewsItem]:
        """Generate mock news items for demonstration."""
        import random
        
        headlines = [
            ("NIFTY hits all-time high as banking stocks surge", 0.7, ["NIFTY", "HDFCBANK", "ICICIBANK"]),
            ("IT sector faces headwinds amid global slowdown", -0.4, ["TCS", "INFY", "WIPRO"]),
            ("Reliance announces major expansion plans", 0.6, ["RELIANCE"]),
            ("Auto sector sees strong demand in festive season", 0.5, ["TATAMOTORS", "MARUTI", "M&M"]),
            ("Metal stocks rally on China stimulus hopes", 0.65, ["TATASTEEL", "HINDALCO", "JSWSTEEL"]),
            ("Pharma stocks under pressure on FDA concerns", -0.5, ["SUNPHARMA", "CIPLA", "DRREDDY"]),
            ("FII outflows continue, markets remain volatile", -0.3, ["NIFTY"]),
            ("PSU banks outperform on strong Q2 results", 0.55, ["SBIN", "BANKBARODA", "PNB"]),
            ("Crude oil surge raises concerns for OMCs", -0.45, ["BPCL", "IOC", "HINDPETRO"]),
            ("Cement stocks gain on infrastructure push", 0.4, ["ULTRACEMCO", "ACC", "AMBUJACEMENT"]),
        ]
        
        news_items = []
        for i, (title, score, symbols) in enumerate(headlines[:limit]):
            # Filter by symbol if provided
            if symbol and symbol not in symbols:
                continue
            
            news_items.append(NewsItem(
                title=title,
                source=random.choice(["Economic Times", "Moneycontrol", "Business Standard", "NDTV Profit"]),
                url=f"https://example.com/news/{i}",
                published_at=datetime.now() - timedelta(hours=random.randint(1, 48)),
                sentiment_score=score + random.uniform(-0.1, 0.1),
                relevance_score=random.uniform(0.7, 1.0),
                symbols=symbols,
                summary=f"Summary of: {title}"
            ))
        
        return sorted(news_items, key=lambda x: x.published_at, reverse=True)
    
    async def get_social_sentiment(
        self,
        symbol: str,
        platforms: List[str] = ["twitter", "reddit"],
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get social media sentiment for a symbol.
        
        Args:
            symbol: Stock symbol
            platforms: Social platforms to check
            limit: Posts per platform
            
        Returns:
            Dict with aggregated social sentiment
        """
        posts = []
        platform_scores = {}
        
        for platform in platforms:
            platform_posts = self._generate_mock_social_posts(symbol, platform, limit // len(platforms))
            posts.extend(platform_posts)
            
            if platform_posts:
                avg_score = sum(p.sentiment_score for p in platform_posts) / len(platform_posts)
                platform_scores[platform] = avg_score
        
        overall_score = sum(platform_scores.values()) / len(platform_scores) if platform_scores else 0
        
        return {
            "symbol": symbol,
            "overall_score": overall_score,
            "level": self._score_to_level(overall_score).value,
            "platform_scores": platform_scores,
            "post_count": len(posts),
            "top_posts": [
                {
                    "platform": p.platform,
                    "content": p.content[:200],
                    "sentiment": p.sentiment_score,
                    "engagement": p.engagement
                }
                for p in sorted(posts, key=lambda x: x.engagement, reverse=True)[:5]
            ],
            "timestamp": datetime.now().isoformat()
        }
    
    def _generate_mock_social_posts(
        self,
        symbol: str,
        platform: str,
        limit: int
    ) -> List[SocialPost]:
        """Generate mock social posts for demonstration."""
        import random
        
        templates = [
            (f"${symbol} looking strong, expecting breakout soon 🚀", 0.7, 150),
            (f"Accumulated more ${symbol} on dip, long term bullish 📈", 0.6, 80),
            (f"${symbol} chart looks bearish, staying away for now", -0.5, 45),
            (f"Q2 results for ${symbol} were disappointing 📉", -0.4, 120),
            (f"${symbol} is the best stock in the sector IMO", 0.5, 200),
            (f"Technical analysis suggests ${symbol} support at current levels", 0.3, 90),
            (f"Sold my ${symbol} position, taking profits", -0.2, 60),
            (f"${symbol} management commentary very positive 💪", 0.65, 110),
        ]
        
        posts = []
        for i in range(min(limit, len(templates))):
            content, score, engagement = templates[i % len(templates)]
            posts.append(SocialPost(
                platform=platform,
                content=content,
                author=f"user_{random.randint(1000, 9999)}",
                posted_at=datetime.now() - timedelta(hours=random.randint(1, 72)),
                sentiment_score=score + random.uniform(-0.15, 0.15),
                engagement=engagement + random.randint(-30, 50),
                symbols=[symbol]
            ))
        
        return posts
    
    async def get_options_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Get options-based sentiment indicators.
        
        Args:
            symbol: Stock/Index symbol
            
        Returns:
            Dict with PCR, Max Pain, IV percentile, etc.
        """
        import random
        
        # Mock options data (replace with actual broker API call)
        pcr = random.uniform(0.7, 1.5)
        
        # PCR interpretation
        if pcr > 1.2:
            pcr_sentiment = "bullish"  # High PCR = more puts = contrarian bullish
        elif pcr < 0.8:
            pcr_sentiment = "bearish"  # Low PCR = more calls = contrarian bearish
        else:
            pcr_sentiment = "neutral"
        
        return {
            "symbol": symbol,
            "put_call_ratio": round(pcr, 2),
            "pcr_sentiment": pcr_sentiment,
            "max_pain": round(random.uniform(0.95, 1.05) * 24000, 0),  # Assuming NIFTY-like
            "iv_percentile": random.uniform(20, 80),
            "call_oi_change": random.randint(-50000, 100000),
            "put_oi_change": random.randint(-50000, 100000),
            "oi_sentiment": "bullish" if random.random() > 0.5 else "bearish",
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_fii_dii_sentiment(self) -> Dict[str, Any]:
        """
        Get FII/DII flow sentiment.
        
        Returns:
            Dict with institutional flow data and sentiment
        """
        import random
        
        fii_net = random.uniform(-2000, 2000)  # Crores
        dii_net = random.uniform(-1500, 2500)
        
        # Determine sentiment
        if fii_net > 500 and dii_net > 0:
            sentiment = "very_bullish"
        elif fii_net > 0:
            sentiment = "bullish"
        elif fii_net < -500 and dii_net < 0:
            sentiment = "very_bearish"
        elif fii_net < 0:
            sentiment = "bearish"
        else:
            sentiment = "neutral"
        
        return {
            "date": datetime.now().date().isoformat(),
            "fii_net_cash": round(fii_net, 2),
            "dii_net_cash": round(dii_net, 2),
            "fii_net_fo": round(random.uniform(-3000, 3000), 2),
            "sentiment": sentiment,
            "fii_mtd": round(fii_net * random.randint(5, 15), 2),
            "dii_mtd": round(dii_net * random.randint(5, 15), 2),
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_aggregate_sentiment(self, symbol: str) -> SentimentScore:
        """
        Get aggregated sentiment from all sources.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            SentimentScore with weighted average from all sources
        """
        # Check cache
        if symbol in self._sentiment_cache:
            cached, timestamp = self._sentiment_cache[symbol]
            if datetime.now() - timestamp < self.cache_ttl:
                return cached
        
        # Gather sentiment from all sources
        news = await self.get_news_sentiment(symbol=symbol, limit=10)
        social = await self.get_social_sentiment(symbol)
        options = await self.get_options_sentiment(symbol)
        fii_dii = await self.get_fii_dii_sentiment()
        
        # Calculate scores per source
        source_scores = {}
        
        # News sentiment
        if news:
            news_score = sum(n.sentiment_score * n.relevance_score for n in news) / len(news)
            source_scores[SentimentSource.NEWS.value] = news_score
        
        # Social sentiment
        source_scores[SentimentSource.TWITTER.value] = social.get("platform_scores", {}).get("twitter", 0)
        source_scores[SentimentSource.REDDIT.value] = social.get("platform_scores", {}).get("reddit", 0)
        
        # Options sentiment
        pcr = options.get("put_call_ratio", 1.0)
        options_score = (pcr - 1.0) * 0.5  # PCR > 1 = bullish (contrarian)
        source_scores[SentimentSource.OPTIONS.value] = max(-1, min(1, options_score))
        
        # FII/DII sentiment
        fii_score = 1 if fii_dii["sentiment"] in ["bullish", "very_bullish"] else (-1 if fii_dii["sentiment"] in ["bearish", "very_bearish"] else 0)
        source_scores[SentimentSource.FII_DII.value] = fii_score * 0.5
        
        # Weighted average
        weights = {
            SentimentSource.NEWS.value: 0.25,
            SentimentSource.TWITTER.value: 0.15,
            SentimentSource.REDDIT.value: 0.10,
            SentimentSource.OPTIONS.value: 0.30,
            SentimentSource.FII_DII.value: 0.20,
        }
        
        total_weight = sum(weights.get(k, 0) for k in source_scores.keys())
        weighted_score = sum(source_scores.get(k, 0) * weights.get(k, 0) for k in source_scores.keys())
        final_score = weighted_score / total_weight if total_weight > 0 else 0
        
        sentiment = SentimentScore(
            symbol=symbol,
            score=round(final_score, 3),
            level=self._score_to_level(final_score),
            confidence=min(1.0, len(source_scores) / 5),  # More sources = more confidence
            sources=source_scores,
            sample_size=len(news) + social.get("post_count", 0),
            timestamp=datetime.now()
        )
        
        # Cache result
        self._sentiment_cache[symbol] = (sentiment, datetime.now())
        
        return sentiment
    
    async def get_market_sentiment(self) -> MarketSentiment:
        """
        Get overall market sentiment indicators.
        
        Returns:
            MarketSentiment with fear/greed index and other indicators
        """
        # Check cache
        if self._market_sentiment_cache:
            cached, timestamp = self._market_sentiment_cache
            if datetime.now() - timestamp < self.cache_ttl:
                return cached
        
        import random
        
        # Mock market indicators (replace with actual data sources)
        fii_dii = await self.get_fii_dii_sentiment()
        options = await self.get_options_sentiment("NIFTY")
        
        fear_greed = random.uniform(30, 70)  # 0 = extreme fear, 100 = extreme greed
        vix = random.uniform(12, 25)
        
        # Determine overall sentiment
        if fear_greed > 70 and options["pcr_sentiment"] == "bullish":
            level = SentimentLevel.VERY_BULLISH
        elif fear_greed > 55:
            level = SentimentLevel.BULLISH
        elif fear_greed < 30 and options["pcr_sentiment"] == "bearish":
            level = SentimentLevel.VERY_BEARISH
        elif fear_greed < 45:
            level = SentimentLevel.BEARISH
        else:
            level = SentimentLevel.NEUTRAL
        
        market_sentiment = MarketSentiment(
            fear_greed_index=round(fear_greed, 1),
            put_call_ratio=options["put_call_ratio"],
            vix_level=round(vix, 2),
            fii_net_flow=fii_dii["fii_net_cash"],
            dii_net_flow=fii_dii["dii_net_cash"],
            advance_decline_ratio=round(random.uniform(0.6, 1.8), 2),
            sentiment_level=level,
            timestamp=datetime.now()
        )
        
        # Cache result
        self._market_sentiment_cache = (market_sentiment, datetime.now())
        
        return market_sentiment
    
    async def get_sector_sentiment(self, sector: str) -> Dict[str, Any]:
        """
        Get sentiment for a specific sector.
        
        Args:
            sector: Sector name (banking, it, pharma, etc.)
            
        Returns:
            Dict with sector sentiment analysis
        """
        news = await self.get_news_sentiment(sector=sector, limit=15)
        
        if not news:
            return {
                "sector": sector,
                "score": 0,
                "level": SentimentLevel.NEUTRAL.value,
                "news_count": 0,
                "timestamp": datetime.now().isoformat()
            }
        
        avg_score = sum(n.sentiment_score for n in news) / len(news)
        
        # Get sentiment for key stocks in sector
        sector_symbols = {
            "banking": ["HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK"],
            "it": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
            "pharma": ["SUNPHARMA", "CIPLA", "DRREDDY", "LUPIN", "AUROPHARMA"],
            "auto": ["TATAMOTORS", "MARUTI", "M&M", "BAJAJ-AUTO", "HEROMOTOCO"],
        }.get(sector.lower(), [])
        
        stock_sentiments = []
        for sym in sector_symbols[:3]:  # Top 3 stocks
            sent = await self.get_aggregate_sentiment(sym)
            stock_sentiments.append({
                "symbol": sym,
                "score": sent.score,
                "level": sent.level.value
            })
        
        return {
            "sector": sector,
            "score": round(avg_score, 3),
            "level": self._score_to_level(avg_score).value,
            "news_count": len(news),
            "recent_headlines": [n.title for n in news[:5]],
            "stock_sentiments": stock_sentiments,
            "timestamp": datetime.now().isoformat()
        }


# Singleton instance
_sentiment_analyzer: Optional[SentimentAnalyzer] = None


def get_sentiment_analyzer() -> SentimentAnalyzer:
    """Get or create sentiment analyzer singleton."""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        _sentiment_analyzer = SentimentAnalyzer()
    return _sentiment_analyzer
