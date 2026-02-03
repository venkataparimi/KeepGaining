from typing import Type, Dict, Any
from app.strategies.base import BaseStrategy
from app.brokers.mock import MockBroker
from app.services.data_feed import DataFeedService
from loguru import logger

class BacktestEngine:
    """
    Simulates strategy execution over historical data.
    """
    def __init__(self):
        self.broker = MockBroker()
        self.data_feed = DataFeedService(self.broker)

    async def run(self, strategy_class: Type[BaseStrategy], config: Dict[str, Any], symbol: str, start_date: str, end_date: str):
        """
        Run a backtest for a specific strategy.
        """
        logger.info(f"Starting backtest for {strategy_class.__name__} on {symbol}")
        
        # 1. Initialize Strategy
        strategy = strategy_class(self.broker, self.data_feed, config)
        await strategy.start()
        
        # 2. Fetch Historical Data
        # In a real backtester, we would iterate candle-by-candle
        # and call strategy.on_candle() for each step.
        candles = await self.broker.get_historical_data(symbol, "1m", start_date, end_date)
        
        # 3. Simulation Loop
        for candle in candles:
            await strategy.on_candle(candle)
            
        await strategy.stop()
        
        # 4. Calculate Results
        positions = await self.broker.get_positions()
        logger.info(f"Backtest complete. Final Positions: {len(positions)}")
        return {
            "positions": positions,
            # "pnl": ... calculate PnL
        }
