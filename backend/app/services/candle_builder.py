"""
Candle Builder Service
KeepGaining Trading Platform

Aggregates tick data into OHLCV candles of various timeframes.
Features:
- Real-time tick to candle aggregation
- Multi-timeframe support (1m, 5m, 15m, 1h, 1D)
- Proper market hour alignment
- Event bus integration for publishing completed candles
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from enum import Enum
import copy

from loguru import logger

from app.core.config import settings
from app.core.events import (
    EventBus, 
    EventType, 
    CandleEvent, 
    TickEvent,
    get_event_bus,
)
from app.brokers.fyers_websocket import TickData


class Timeframe(str, Enum):
    """Supported timeframes."""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    D1 = "1D"


@dataclass
class Candle:
    """OHLCV candle data structure."""
    symbol: str
    timeframe: Timeframe
    timestamp: datetime  # Candle open time
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    oi: int = 0
    tick_count: int = 0
    is_complete: bool = False
    
    def update_with_tick(self, price: float, volume: int = 0, oi: int = 0) -> None:
        """Update candle with a new tick."""
        if self.tick_count == 0:
            self.open = price
            self.high = price
            self.low = price
        else:
            self.high = max(self.high, price)
            self.low = min(self.low, price)
        
        self.close = price
        self.volume += volume
        self.oi = oi  # OI is typically the latest value
        self.tick_count += 1
    
    def merge_candle(self, other: "Candle") -> None:
        """Merge another candle into this one (for building higher timeframes)."""
        if self.tick_count == 0:
            self.open = other.open
            self.high = other.high
            self.low = other.low
        else:
            self.high = max(self.high, other.high)
            self.low = min(self.low, other.low)
        
        self.close = other.close
        self.volume += other.volume
        self.oi = other.oi
        self.tick_count += other.tick_count
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "oi": self.oi,
            "tick_count": self.tick_count,
            "is_complete": self.is_complete,
        }
    
    def copy(self) -> "Candle":
        """Create a copy of this candle."""
        return copy.deepcopy(self)


def get_candle_start_time(dt: datetime, timeframe: Timeframe) -> datetime:
    """
    Get the candle start time for a given datetime and timeframe.
    
    Args:
        dt: Datetime to align
        timeframe: Target timeframe
        
    Returns:
        Aligned candle start datetime.
    """
    if timeframe == Timeframe.M1:
        return dt.replace(second=0, microsecond=0)
    
    elif timeframe == Timeframe.M5:
        minute = (dt.minute // 5) * 5
        return dt.replace(minute=minute, second=0, microsecond=0)
    
    elif timeframe == Timeframe.M15:
        minute = (dt.minute // 15) * 15
        return dt.replace(minute=minute, second=0, microsecond=0)
    
    elif timeframe == Timeframe.M30:
        minute = (dt.minute // 30) * 30
        return dt.replace(minute=minute, second=0, microsecond=0)
    
    elif timeframe == Timeframe.H1:
        return dt.replace(minute=0, second=0, microsecond=0)
    
    elif timeframe == Timeframe.D1:
        # Daily candle starts at market open (09:15 IST)
        market_open = time(9, 15)
        return datetime.combine(dt.date(), market_open)
    
    return dt


def get_next_candle_time(current: datetime, timeframe: Timeframe) -> datetime:
    """Get the next candle start time after current."""
    if timeframe == Timeframe.M1:
        return current + timedelta(minutes=1)
    elif timeframe == Timeframe.M5:
        return current + timedelta(minutes=5)
    elif timeframe == Timeframe.M15:
        return current + timedelta(minutes=15)
    elif timeframe == Timeframe.M30:
        return current + timedelta(minutes=30)
    elif timeframe == Timeframe.H1:
        return current + timedelta(hours=1)
    elif timeframe == Timeframe.D1:
        return current + timedelta(days=1)
    return current


class CandleBuilder:
    """
    Builds candles from tick data for a single symbol.
    
    Maintains candles for multiple timeframes simultaneously.
    """
    
    def __init__(
        self,
        symbol: str,
        timeframes: List[Timeframe] = None,
        on_candle_complete: Optional[Callable[[Candle], Coroutine[Any, Any, None]]] = None,
    ):
        """
        Initialize candle builder.
        
        Args:
            symbol: Trading symbol
            timeframes: List of timeframes to build (default: all)
            on_candle_complete: Callback when candle completes
        """
        self.symbol = symbol
        self.timeframes = timeframes or list(Timeframe)
        self._on_candle_complete = on_candle_complete
        
        # Current candles by timeframe
        self._current_candles: Dict[Timeframe, Candle] = {}
        
        # History for building higher timeframes
        self._m1_history: List[Candle] = []
        self._max_history = 60  # Keep last 60 1m candles for building hourly
        
        # Stats
        self._tick_count = 0
        self._candle_count = 0
    
    async def process_tick(self, tick: TickData) -> List[Candle]:
        """
        Process a tick and update candles.
        
        Args:
            tick: Incoming tick data
            
        Returns:
            List of completed candles (if any).
        """
        self._tick_count += 1
        completed_candles: List[Candle] = []
        
        tick_time = tick.timestamp
        if tick_time.tzinfo is None:
            tick_time = tick_time.replace(tzinfo=timezone.utc)
        
        # Process 1-minute candle from ticks
        completed_1m = await self._process_tick_to_candle(
            tick, Timeframe.M1, tick_time
        )
        if completed_1m:
            completed_candles.append(completed_1m)
            
            # Store in history for higher timeframes
            self._m1_history.append(completed_1m)
            if len(self._m1_history) > self._max_history:
                self._m1_history.pop(0)
            
            # Build higher timeframes from 1m candles
            for tf in self.timeframes:
                if tf == Timeframe.M1:
                    continue
                
                completed = await self._check_higher_timeframe(tf, completed_1m)
                if completed:
                    completed_candles.append(completed)
        else:
            # Update 1m candle with tick
            candle = self._get_or_create_candle(Timeframe.M1, tick_time)
            candle.update_with_tick(tick.ltp, tick.volume, tick.oi)
        
        return completed_candles
    
    async def _process_tick_to_candle(
        self,
        tick: TickData,
        timeframe: Timeframe,
        tick_time: datetime,
    ) -> Optional[Candle]:
        """Process tick for a specific timeframe."""
        candle_start = get_candle_start_time(tick_time, timeframe)
        next_candle = get_next_candle_time(candle_start, timeframe)
        
        current = self._current_candles.get(timeframe)
        
        # Check if we've moved to a new candle period
        if current and tick_time >= next_candle:
            # Complete current candle
            current.is_complete = True
            self._candle_count += 1
            
            # Callback
            if self._on_candle_complete:
                await self._on_candle_complete(current)
            
            # Start new candle
            new_candle_start = get_candle_start_time(tick_time, timeframe)
            self._current_candles[timeframe] = Candle(
                symbol=self.symbol,
                timeframe=timeframe,
                timestamp=new_candle_start,
            )
            self._current_candles[timeframe].update_with_tick(
                tick.ltp, tick.volume, tick.oi
            )
            
            return current
        
        # Update current candle
        if not current:
            self._current_candles[timeframe] = Candle(
                symbol=self.symbol,
                timeframe=timeframe,
                timestamp=candle_start,
            )
        
        self._current_candles[timeframe].update_with_tick(
            tick.ltp, tick.volume, tick.oi
        )
        
        return None
    
    async def _check_higher_timeframe(
        self,
        timeframe: Timeframe,
        completed_1m: Candle,
    ) -> Optional[Candle]:
        """Check if a higher timeframe candle should complete."""
        candle_start = get_candle_start_time(completed_1m.timestamp, timeframe)
        next_candle = get_next_candle_time(candle_start, timeframe)
        
        # Get or create higher timeframe candle
        current = self._current_candles.get(timeframe)
        
        if current is None:
            current = Candle(
                symbol=self.symbol,
                timeframe=timeframe,
                timestamp=candle_start,
            )
            self._current_candles[timeframe] = current
        
        # Merge 1m candle
        current.merge_candle(completed_1m)
        
        # Check if period complete
        # A higher TF candle completes when the 1m candle that just completed
        # is the last one of that period
        next_1m = get_next_candle_time(completed_1m.timestamp, Timeframe.M1)
        if next_1m >= next_candle:
            current.is_complete = True
            self._candle_count += 1
            
            # Callback
            if self._on_candle_complete:
                await self._on_candle_complete(current)
            
            # Start new candle
            self._current_candles[timeframe] = Candle(
                symbol=self.symbol,
                timeframe=timeframe,
                timestamp=next_candle,
            )
            
            return current
        
        return None
    
    def _get_or_create_candle(
        self,
        timeframe: Timeframe,
        tick_time: datetime,
    ) -> Candle:
        """Get current candle or create new one."""
        if timeframe not in self._current_candles:
            candle_start = get_candle_start_time(tick_time, timeframe)
            self._current_candles[timeframe] = Candle(
                symbol=self.symbol,
                timeframe=timeframe,
                timestamp=candle_start,
            )
        return self._current_candles[timeframe]
    
    def get_current_candle(self, timeframe: Timeframe) -> Optional[Candle]:
        """Get the current (incomplete) candle for a timeframe."""
        return self._current_candles.get(timeframe)
    
    def force_complete(self) -> List[Candle]:
        """Force complete all current candles (e.g., at market close)."""
        completed = []
        for tf, candle in self._current_candles.items():
            if candle.tick_count > 0:
                candle.is_complete = True
                completed.append(candle.copy())
        return completed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get builder statistics."""
        return {
            "symbol": self.symbol,
            "tick_count": self._tick_count,
            "candle_count": self._candle_count,
            "current_candles": {
                tf.value: c.to_dict() if c else None
                for tf, c in self._current_candles.items()
            },
        }


class CandleBuilderService:
    """
    Service for managing multiple candle builders.
    
    Subscribes to tick events from event bus and publishes completed candles.
    """
    
    def __init__(
        self,
        timeframes: List[Timeframe] = None,
        on_candle: Optional[Callable[[Candle], Coroutine[Any, Any, None]]] = None,
    ):
        """
        Initialize candle builder service.
        
        Args:
            timeframes: Timeframes to build for all symbols
            on_candle: Optional callback for completed candles
        """
        self.timeframes = timeframes or [
            Timeframe.M1,
            Timeframe.M5,
            Timeframe.M15,
            Timeframe.H1,
        ]
        self._on_candle = on_candle
        
        # Builders by symbol
        self._builders: Dict[str, CandleBuilder] = {}
        
        # Event bus
        self._event_bus: Optional[EventBus] = None
        
        # Running state
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the candle builder service."""
        if self._running:
            return
        
        self._event_bus = await get_event_bus()
        
        # Subscribe to tick events
        await self._event_bus.subscribe(
            EventType.TICK_RECEIVED,
            self._handle_tick_event,
        )
        
        self._running = True
        logger.info(f"✓ Candle builder service started (timeframes: {[tf.value for tf in self.timeframes]})")
    
    async def stop(self) -> None:
        """Stop the candle builder service."""
        self._running = False
        
        # Force complete all candles
        for builder in self._builders.values():
            completed = builder.force_complete()
            for candle in completed:
                await self._publish_candle(candle)
        
        logger.info("Candle builder service stopped")
    
    def add_symbol(self, symbol: str) -> None:
        """Add a symbol for candle building."""
        if symbol not in self._builders:
            self._builders[symbol] = CandleBuilder(
                symbol=symbol,
                timeframes=self.timeframes,
                on_candle_complete=self._on_candle_complete,
            )
            logger.debug(f"Added candle builder for {symbol}")
    
    def remove_symbol(self, symbol: str) -> None:
        """Remove a symbol from candle building."""
        if symbol in self._builders:
            del self._builders[symbol]
            logger.debug(f"Removed candle builder for {symbol}")
    
    async def _handle_tick_event(self, event: TickEvent) -> None:
        """Handle incoming tick event from event bus."""
        symbol = event.symbol
        
        # Auto-add builder if not exists
        if symbol not in self._builders:
            self.add_symbol(symbol)
        
        # Convert event to TickData
        tick = TickData(
            symbol=symbol,
            ltp=event.ltp,
            volume=event.volume or 0,
            oi=event.oi or 0,
            bid=event.bid or 0,
            ask=event.ask or 0,
            timestamp=event.timestamp,
        )
        
        # Process tick
        completed = await self._builders[symbol].process_tick(tick)
        
        # Publish completed candles
        for candle in completed:
            await self._publish_candle(candle)
    
    async def process_tick(self, symbol: str, tick: TickData) -> List[Candle]:
        """
        Process a tick directly (without event bus).
        
        Args:
            symbol: Trading symbol
            tick: Tick data
            
        Returns:
            List of completed candles.
        """
        if symbol not in self._builders:
            self.add_symbol(symbol)
        
        completed = await self._builders[symbol].process_tick(tick)
        
        for candle in completed:
            await self._publish_candle(candle)
        
        return completed
    
    async def _on_candle_complete(self, candle: Candle) -> None:
        """Internal callback when candle completes."""
        if self._on_candle:
            await self._on_candle(candle)
    
    async def _publish_candle(self, candle: Candle) -> None:
        """Publish completed candle to event bus."""
        if self._event_bus:
            event = CandleEvent(
                event_type=EventType.CANDLE_FORMED,
                instrument_id=candle.symbol,
                symbol=candle.symbol,
                timeframe=candle.timeframe.value,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                is_complete=candle.is_complete,
            )
            await self._event_bus.publish(event)
    
    def get_current_candle(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> Optional[Candle]:
        """Get current (incomplete) candle for a symbol and timeframe."""
        builder = self._builders.get(symbol)
        if builder:
            return builder.get_current_candle(timeframe)
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "running": self._running,
            "symbol_count": len(self._builders),
            "timeframes": [tf.value for tf in self.timeframes],
            "builders": {
                symbol: builder.get_stats()
                for symbol, builder in self._builders.items()
            },
        }


# =============================================================================
# Factory Function
# =============================================================================

async def create_candle_builder_service(
    timeframes: Optional[List[Timeframe]] = None,
) -> CandleBuilderService:
    """
    Factory function to create and start candle builder service.
    
    Args:
        timeframes: Optional list of timeframes
        
    Returns:
        Started CandleBuilderService instance.
    """
    service = CandleBuilderService(timeframes=timeframes)
    await service.start()
    return service


__all__ = [
    "Timeframe",
    "Candle",
    "CandleBuilder",
    "CandleBuilderService",
    "get_candle_start_time",
    "get_next_candle_time",
    "create_candle_builder_service",
]
