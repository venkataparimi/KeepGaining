from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime
from loguru import logger
import asyncio
import random

class CometJob(ABC):
    """
    Abstract Base Class for Comet Jobs.
    These jobs are READ-ONLY and cannot execute trades.
    """
    def __init__(self, name: str, interval_seconds: int):
        self.name = name
        self.interval_seconds = interval_seconds
        self.last_run: datetime = None

    @abstractmethod
    async def run(self) -> Dict[str, Any]:
        """Execute the job logic."""
        pass

class NewsScraperJob(CometJob):
    """
    Mock Job to scrape news from configured sources.
    """
    def __init__(self):
        super().__init__("NewsScraper", interval_seconds=60)

    async def run(self) -> Dict[str, Any]:
        logger.info(f"Running {self.name}...")
        # Simulate fetching news
        await asyncio.sleep(1) 
        
        # Mock News Items
        news_items = [
            {"title": "Tech stocks rally on AI news", "source": "Bloomberg", "timestamp": datetime.now()},
            {"title": "Fed signals rate cuts", "source": "Reuters", "timestamp": datetime.now()},
            {"title": "Oil prices drop", "source": "CNBC", "timestamp": datetime.now()},
        ]
        
        # In a real app, we would store these in the DB
        return {"items_fetched": len(news_items), "items": news_items}

class SentimentAnalyzerJob(CometJob):
    """
    Mock Job to analyze sentiment of fetched news.
    """
    def __init__(self):
        super().__init__("SentimentAnalyzer", interval_seconds=60)

    async def run(self) -> Dict[str, Any]:
        logger.info(f"Running {self.name}...")
        # Simulate analysis
        await asyncio.sleep(0.5)
        
        # Mock Sentiment Score (-1 to 1)
        sentiment_score = random.uniform(-0.5, 0.8)
        
        return {"sentiment_score": sentiment_score, "confidence": 0.9}
