import asyncio
from app.strategies.base import BaseStrategy
from app.strategies.registry import StrategyRegistry
from app.backtest.engine import BacktestEngine
from loguru import logger

# 1. Define a Test Strategy
@StrategyRegistry.register("TestStrategy")
class TestStrategy(BaseStrategy):
    async def on_start(self):
        logger.info("TestStrategy started")

    async def on_stop(self):
        logger.info("TestStrategy stopped")

    async def on_tick(self, tick):
        pass

    async def on_candle(self, candle):
        logger.info(f"Processing candle: {candle}")
        # Simple logic: Buy
        await self.buy("INFY", 1)

    async def on_order_update(self, order):
        logger.info(f"Order updated: {order}")

async def verify_strategy_engine():
    logger.info("Verifying Strategy Engine...")
    
    # 2. Run Backtest
    engine = BacktestEngine()
    result = await engine.run(
        strategy_class=TestStrategy,
        config={"name": "MyTestStrategy"},
        symbol="INFY",
        start_date="2023-01-01",
        end_date="2023-01-02"
    )
    
    logger.info(f"Backtest Result: {result}")

if __name__ == "__main__":
    asyncio.run(verify_strategy_engine())
