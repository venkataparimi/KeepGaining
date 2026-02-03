"""
Data Pipeline Integration Test
KeepGaining Trading Platform

Tests the complete data pipeline:
1. InstrumentSyncService - Download instruments from brokers
2. DataFeedOrchestrator - Coordinate WebSocket and batch data
3. CandleBuilderService - Build candles from tick data
4. Event bus integration - Verify events flow correctly

This script tests the pipeline during market hours.
For testing outside market hours, use mock data.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import List, Dict, Any
from zoneinfo import ZoneInfo

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.instrument_sync import InstrumentSyncService, Exchange
from app.services.data_orchestrator import (
    DataFeedOrchestrator,
    create_data_orchestrator,
    SubscriptionPriority,
)
from app.services.candle_builder import (
    CandleBuilderService,
    Candle,
    Timeframe,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


class SimpleEventBus:
    """Simple event bus for testing (no Redis required)."""
    
    def __init__(self):
        self._handlers: Dict[str, List] = {}
        
    async def subscribe(self, event_type: str, handler, consumer_group: str = None):
        """Subscribe to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"Subscribed to {event_type}")
        
    async def unsubscribe(self, event_type: str, consumer_group: str = None):
        """Unsubscribe from an event type."""
        if event_type in self._handlers:
            self._handlers[event_type] = []
            
    async def publish(self, event_type: str, data: Dict[str, Any]):
        """Publish an event."""
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    await handler(data)
                except Exception as e:
                    logger.error(f"Handler error: {e}")


class DataPipelineTest:
    """Test harness for data pipeline integration."""
    
    def __init__(self):
        self.event_bus = SimpleEventBus()
        self.instrument_sync: InstrumentSyncService = None
        self.orchestrator: DataFeedOrchestrator = None
        self.candle_builder: CandleBuilderService = None
        
        # Test metrics
        self.events_received: Dict[str, int] = {
            "tick": 0,
            "candle": 0,
            "data_feed_status": 0,
        }
        self.candles_by_symbol: Dict[str, List[Dict]] = {}
        
    async def setup(self):
        """Initialize all services."""
        logger.info("="*60)
        logger.info("DATA PIPELINE INTEGRATION TEST")
        logger.info("="*60)
        
        # 1. Initialize Instrument Sync Service
        logger.info("\n1. Initializing Instrument Sync Service...")
        self.instrument_sync = InstrumentSyncService()
        
        # 2. Initialize Data Feed Orchestrator
        logger.info("2. Initializing Data Feed Orchestrator...")
        self.orchestrator = create_data_orchestrator(
            event_bus=self.event_bus,
            websocket_max_symbols=50,  # Use 50 for testing
            batch_scan_interval=30,  # Faster interval for testing
        )
        
        # 3. Initialize Candle Builder
        logger.info("3. Initializing Candle Builder Service...")
        self.candle_builder = CandleBuilderService(
            timeframes=[Timeframe.M1, Timeframe.M5],
            on_candle=self._on_candle_complete,
        )
        
        # 4. Setup event listeners
        await self._setup_event_listeners()
        
        logger.info("✓ All services initialized")
        
    async def _setup_event_listeners(self):
        """Subscribe to events for testing."""
        
        async def on_tick(event: Dict[str, Any]):
            self.events_received["tick"] += 1
            if self.events_received["tick"] % 100 == 0:
                logger.info(f"Received {self.events_received['tick']} ticks")
        
        async def on_candle(event: Dict[str, Any]):
            self.events_received["candle"] += 1
            symbol = event.get("symbol", "unknown")
            if symbol not in self.candles_by_symbol:
                self.candles_by_symbol[symbol] = []
            self.candles_by_symbol[symbol].append(event)
            
            if event.get("is_complete"):
                logger.info(
                    f"Candle: {symbol} {event.get('timeframe')} "
                    f"O:{event.get('open'):.2f} H:{event.get('high'):.2f} "
                    f"L:{event.get('low'):.2f} C:{event.get('close'):.2f}"
                )
        
        async def on_feed_status(event: Dict[str, Any]):
            self.events_received["data_feed_status"] += 1
            ws = event.get("websocket", {})
            batch = event.get("batch", {})
            logger.debug(
                f"Feed Status: WS={ws.get('symbols', 0)} symbols, "
                f"Batch={batch.get('symbols', 0)} symbols"
            )
        
        await self.event_bus.subscribe("tick", on_tick, consumer_group="test")
        await self.event_bus.subscribe("candle", on_candle, consumer_group="test")
        await self.event_bus.subscribe("data_feed_status", on_feed_status, consumer_group="test")
        
    async def _on_candle_complete(self, candle: Candle):
        """Callback when candle completes."""
        logger.debug(f"Candle complete: {candle.symbol} {candle.timeframe.value}")

    async def test_instrument_download(self) -> List[str]:
        """Test instrument download and return F&O symbols."""
        logger.info("\n" + "="*60)
        logger.info("TEST 1: Instrument Download")
        logger.info("="*60)
        
        # Download NSE instruments (equity)
        logger.info("Downloading Upstox NSE instruments...")
        upstox_instruments = await self.instrument_sync.download_upstox_instruments(
            exchange="NSE"
        )
        logger.info(f"Downloaded {len(upstox_instruments)} Upstox instruments")
        
        # Filter for F&O stocks (instrument type EQ from major indices)
        # For testing, get top liquid stocks
        nifty50_symbols = [
            "NSE_EQ|INE009A01021",  # INFY
            "NSE_EQ|INE040A01034",  # HDFC Bank
            "NSE_EQ|INE467B01029",  # TCS
            "NSE_EQ|INE002A01018",  # Reliance
            "NSE_EQ|INE154A01025",  # ITC
        ]
        
        # Extract trading symbols
        fo_symbols = []
        symbol_map = {}
        
        for inst in upstox_instruments[:100]:  # Take first 100 for testing
            symbol = inst.trading_symbol
            if symbol and inst.instrument_type == "EQ":
                fo_symbols.append(f"NSE:{symbol}")
                symbol_map[inst.instrument_key] = symbol
        
        logger.info(f"Selected {len(fo_symbols)} F&O symbols for testing")
        
        if fo_symbols[:5]:
            logger.info(f"Sample symbols: {fo_symbols[:5]}")
        
        return fo_symbols[:50]  # Limit to 50 for testing
    
    async def test_data_orchestrator_setup(self, symbols: List[str]):
        """Test data orchestrator setup with symbols."""
        logger.info("\n" + "="*60)
        logger.info("TEST 2: Data Orchestrator Setup")
        logger.info("="*60)
        
        # Note: In production, we'd inject real WebSocket and batch services
        # For this test, we're just testing the orchestrator logic
        
        # Set universe
        await self.orchestrator.set_universe(symbols)
        logger.info(f"Set universe with {len(symbols)} symbols")
        
        # Add some to watchlist
        for symbol in symbols[:10]:
            await self.orchestrator.add_to_watchlist(symbol)
        
        # Check subscription summary
        summary = self.orchestrator.get_subscription_summary()
        logger.info(f"Subscription summary: {summary}")
        
        # Check data source status
        status = self.orchestrator.get_data_source_status()
        logger.info(f"Data source status: {status}")
        
        return True
    
    async def test_candle_builder(self):
        """Test candle builder with mock ticks."""
        logger.info("\n" + "="*60)
        logger.info("TEST 3: Candle Builder")
        logger.info("="*60)
        
        from app.brokers.fyers_websocket import TickData
        
        # Create mock ticks
        base_time = datetime.now(IST)
        symbol = "NSE:INFY"
        base_price = 1500.0
        
        self.candle_builder.add_symbol(symbol)
        
        # Generate 60 mock ticks (1 minute worth)
        for i in range(60):
            tick_time = base_time + timedelta(seconds=i)
            price = base_price + (i % 10) * 0.1  # Small price variations
            
            tick = TickData(
                symbol=symbol,
                ltp=price,
                volume=100 + i * 10,
                oi=0,
                bid=price - 0.05,
                ask=price + 0.05,
                timestamp=tick_time,
            )
            
            completed = await self.candle_builder.process_tick(symbol, tick)
            
            for candle in completed:
                logger.info(
                    f"Completed candle: {candle.symbol} {candle.timeframe.value} "
                    f"O:{candle.open:.2f} H:{candle.high:.2f} "
                    f"L:{candle.low:.2f} C:{candle.close:.2f} V:{candle.volume}"
                )
        
        logger.info(f"Processed 60 ticks, events received: {self.events_received}")
        return True
    
    async def test_full_pipeline_simulation(self):
        """Simulate full pipeline with mock data."""
        logger.info("\n" + "="*60)
        logger.info("TEST 4: Full Pipeline Simulation")
        logger.info("="*60)
        
        from app.brokers.fyers_websocket import TickData
        
        # Simulate market data for multiple symbols
        symbols = ["NSE:INFY", "NSE:TCS", "NSE:HDFCBANK"]
        base_prices = {"NSE:INFY": 1500.0, "NSE:TCS": 3500.0, "NSE:HDFCBANK": 1600.0}
        
        for symbol in symbols:
            self.candle_builder.add_symbol(symbol)
        
        # Simulate 5 minutes of trading
        base_time = datetime.now(IST).replace(second=0, microsecond=0)
        
        logger.info("Simulating 5 minutes of market data...")
        
        for minute in range(5):
            for second in range(60):
                tick_time = base_time + timedelta(minutes=minute, seconds=second)
                
                for symbol in symbols:
                    # Generate realistic price movement
                    import random
                    base = base_prices[symbol]
                    price = base + random.uniform(-5, 5)
                    
                    tick = TickData(
                        symbol=symbol,
                        ltp=price,
                        volume=random.randint(100, 1000),
                        oi=0,
                        bid=price - 0.05,
                        ask=price + 0.05,
                        timestamp=tick_time,
                    )
                    
                    await self.candle_builder.process_tick(symbol, tick)
                
                # Small delay to simulate real-time
                if second % 10 == 0:
                    await asyncio.sleep(0.01)
            
            logger.info(f"Completed minute {minute + 1}/5")
        
        # Print summary
        logger.info("\nSimulation Summary:")
        logger.info(f"Total ticks processed: {self.events_received['tick']}")
        logger.info(f"Candles formed: {self.events_received['candle']}")
        logger.info(f"Symbols tracked: {len(self.candles_by_symbol)}")
        
        for symbol, candles in self.candles_by_symbol.items():
            complete_candles = [c for c in candles if c.get('is_complete')]
            logger.info(f"  {symbol}: {len(complete_candles)} complete candles")
        
        return True
    
    async def run_all_tests(self):
        """Run all integration tests."""
        try:
            await self.setup()
            
            # Test 1: Instrument download
            symbols = await self.test_instrument_download()
            
            # Test 2: Data orchestrator setup
            await self.test_data_orchestrator_setup(symbols)
            
            # Test 3: Candle builder
            await self.test_candle_builder()
            
            # Test 4: Full pipeline simulation
            await self.test_full_pipeline_simulation()
            
            logger.info("\n" + "="*60)
            logger.info("ALL TESTS COMPLETED SUCCESSFULLY")
            logger.info("="*60)
            
            # Print final metrics
            logger.info("\nFinal Metrics:")
            logger.info(f"  Ticks: {self.events_received['tick']}")
            logger.info(f"  Candles: {self.events_received['candle']}")
            logger.info(f"  Feed status updates: {self.events_received['data_feed_status']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Test failed: {e}", exc_info=True)
            return False
        
        finally:
            # Cleanup
            if self.candle_builder:
                await self.candle_builder.stop()


async def main():
    """Main entry point."""
    test = DataPipelineTest()
    success = await test.run_all_tests()
    
    if not success:
        sys.exit(1)
    
    logger.info("\n✓ Data pipeline integration test passed!")


if __name__ == "__main__":
    asyncio.run(main())
