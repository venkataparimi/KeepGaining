import asyncio
from typing import Dict, List
from app.strategies.base import BaseStrategy
from app.brokers.base import BaseBroker
from app.services.data_feed import DataFeedService
from loguru import logger

class StrategyEngine:
    """
    Orchestrates the execution of multiple strategies.
    """
    def __init__(self, broker: BaseBroker, data_feed: DataFeedService):
        self.broker = broker
        self.data_feed = data_feed
        self.active_strategies: Dict[str, BaseStrategy] = {}

    async def load_strategy(self, strategy_class: type, config: dict):
        """Instantiate and register a strategy."""
        strategy = strategy_class(self.broker, self.data_feed, config)
        self.active_strategies[config.get("name", "unknown")] = strategy
        logger.info(f"Loaded strategy: {config.get('name')}")

    async def start_all(self):
        """Start all loaded strategies."""
        for name, strategy in self.active_strategies.items():
            await strategy.start()

    async def stop_all(self):
        """Stop all loaded strategies."""
        for name, strategy in self.active_strategies.items():
            await strategy.stop()

    async def process_tick(self, tick: dict):
        """Route tick data to all active strategies."""
        # In a real system, this would be optimized to only send relevant ticks
        for strategy in self.active_strategies.values():
            if strategy.is_running:
                await strategy.on_tick(tick)
