"""
Indicator Computation Service
KeepGaining Trading Platform

Computes technical indicators from candle data.
Features:
- VWMA (22, 31) - Volume Weighted Moving Average
- ATR - Average True Range
- RSI - Relative Strength Index
- EMA/SMA - Exponential/Simple Moving Averages
- Supertrend
- Event bus integration
"""

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional, Deque
from enum import Enum
import math

from loguru import logger
import numpy as np

from app.core.events import (
    EventBus,
    EventType,
    CandleEvent,
    IndicatorEvent,
    get_event_bus,
)
from app.services.candle_builder import Candle, Timeframe


class IndicatorType(str, Enum):
    """Supported indicator types."""
    SMA = "SMA"
    EMA = "EMA"
    VWMA = "VWMA"
    RSI = "RSI"
    ATR = "ATR"
    SUPERTREND = "SUPERTREND"
    MACD = "MACD"
    BOLLINGER = "BOLLINGER"


@dataclass
class IndicatorValue:
    """Single indicator value."""
    name: str
    value: float
    timestamp: datetime
    symbol: str
    timeframe: str
    params: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "params": self.params,
        }


@dataclass
class IndicatorResult:
    """Result containing multiple indicator values."""
    symbol: str
    timeframe: str
    timestamp: datetime
    values: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "values": self.values,
        }


class IndicatorCalculator:
    """
    Calculates technical indicators from candle data.
    
    Maintains rolling windows for efficient computation.
    """
    
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        max_history: int = 500,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.max_history = max_history
        
        # Candle history (OHLCV)
        self._opens: Deque[float] = deque(maxlen=max_history)
        self._highs: Deque[float] = deque(maxlen=max_history)
        self._lows: Deque[float] = deque(maxlen=max_history)
        self._closes: Deque[float] = deque(maxlen=max_history)
        self._volumes: Deque[int] = deque(maxlen=max_history)
        self._timestamps: Deque[datetime] = deque(maxlen=max_history)
        
        # Cached calculations
        self._tr_cache: Deque[float] = deque(maxlen=max_history)  # True Range
        self._ema_cache: Dict[int, float] = {}  # EMA by period
        
        # Supertrend state
        self._supertrend_direction: int = 1  # 1 = up, -1 = down
        self._supertrend_value: float = 0.0
    
    def add_candle(self, candle: Candle) -> None:
        """Add a new candle to history."""
        self._opens.append(candle.open)
        self._highs.append(candle.high)
        self._lows.append(candle.low)
        self._closes.append(candle.close)
        self._volumes.append(candle.volume)
        self._timestamps.append(candle.timestamp)
        
        # Calculate True Range
        if len(self._closes) >= 2:
            prev_close = self._closes[-2]
            tr = max(
                candle.high - candle.low,
                abs(candle.high - prev_close),
                abs(candle.low - prev_close)
            )
        else:
            tr = candle.high - candle.low
        self._tr_cache.append(tr)
    
    def compute_all(self) -> IndicatorResult:
        """Compute all configured indicators."""
        result = IndicatorResult(
            symbol=self.symbol,
            timeframe=self.timeframe,
            timestamp=self._timestamps[-1] if self._timestamps else datetime.now(timezone.utc),
        )
        
        closes = list(self._closes)
        volumes = list(self._volumes)
        
        if len(closes) < 2:
            return result
        
        # VWMA 22 and 31 (primary indicators per HLD)
        if len(closes) >= 22:
            result.values["vwma_22"] = self._compute_vwma(closes, volumes, 22)
        if len(closes) >= 31:
            result.values["vwma_31"] = self._compute_vwma(closes, volumes, 31)
        
        # ATR 14
        if len(self._tr_cache) >= 14:
            result.values["atr_14"] = self._compute_atr(14)
        
        # RSI 14
        if len(closes) >= 15:
            result.values["rsi_14"] = self._compute_rsi(closes, 14)
        
        # EMAs
        for period in [9, 21, 50, 200]:
            if len(closes) >= period:
                result.values[f"ema_{period}"] = self._compute_ema(closes, period)
        
        # SMAs
        for period in [20, 50, 200]:
            if len(closes) >= period:
                result.values[f"sma_{period}"] = self._compute_sma(closes, period)
        
        # Supertrend (10, 3)
        if len(closes) >= 10:
            st_value, st_direction = self._compute_supertrend(10, 3.0)
            result.values["supertrend"] = st_value
            result.values["supertrend_direction"] = float(st_direction)
        
        return result
    
    def _compute_sma(self, data: List[float], period: int) -> float:
        """Compute Simple Moving Average."""
        if len(data) < period:
            return 0.0
        return sum(data[-period:]) / period
    
    def _compute_ema(self, data: List[float], period: int) -> float:
        """Compute Exponential Moving Average."""
        if len(data) < period:
            return 0.0
        
        multiplier = 2 / (period + 1)
        
        # Use cached value if available
        if period in self._ema_cache:
            prev_ema = self._ema_cache[period]
            ema = (data[-1] - prev_ema) * multiplier + prev_ema
        else:
            # Initialize with SMA
            ema = sum(data[:period]) / period
            for price in data[period:]:
                ema = (price - ema) * multiplier + ema
        
        self._ema_cache[period] = ema
        return round(ema, 4)
    
    def _compute_vwma(
        self,
        closes: List[float],
        volumes: List[int],
        period: int,
    ) -> float:
        """
        Compute Volume Weighted Moving Average.
        
        VWMA = sum(close * volume) / sum(volume)
        """
        if len(closes) < period or len(volumes) < period:
            return 0.0
        
        recent_closes = closes[-period:]
        recent_volumes = volumes[-period:]
        
        total_volume = sum(recent_volumes)
        if total_volume == 0:
            return self._compute_sma(closes, period)
        
        weighted_sum = sum(c * v for c, v in zip(recent_closes, recent_volumes))
        return round(weighted_sum / total_volume, 4)
    
    def _compute_rsi(self, data: List[float], period: int) -> float:
        """Compute Relative Strength Index."""
        if len(data) < period + 1:
            return 50.0
        
        # Calculate price changes
        changes = [data[i] - data[i-1] for i in range(1, len(data))]
        recent_changes = changes[-(period):]
        
        gains = [c if c > 0 else 0 for c in recent_changes]
        losses = [-c if c < 0 else 0 for c in recent_changes]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
    
    def _compute_atr(self, period: int) -> float:
        """Compute Average True Range."""
        if len(self._tr_cache) < period:
            return 0.0
        
        tr_values = list(self._tr_cache)[-period:]
        return round(sum(tr_values) / period, 4)
    
    def _compute_supertrend(
        self,
        period: int = 10,
        multiplier: float = 3.0,
    ) -> tuple[float, int]:
        """
        Compute Supertrend indicator.
        
        Returns:
            Tuple of (supertrend value, direction: 1=up, -1=down)
        """
        if len(self._closes) < period or len(self._tr_cache) < period:
            return 0.0, 1
        
        closes = list(self._closes)
        highs = list(self._highs)
        lows = list(self._lows)
        
        # Calculate ATR
        atr = self._compute_atr(period)
        
        # Calculate basic bands
        hl2 = (highs[-1] + lows[-1]) / 2
        basic_upper = hl2 + (multiplier * atr)
        basic_lower = hl2 - (multiplier * atr)
        
        # Get previous values (simplified - full implementation would track history)
        prev_close = closes[-2] if len(closes) > 1 else closes[-1]
        
        # Determine trend direction
        if closes[-1] > self._supertrend_value:
            direction = 1  # Bullish
            final_band = basic_lower
        else:
            direction = -1  # Bearish
            final_band = basic_upper
        
        # Update state
        self._supertrend_value = final_band
        self._supertrend_direction = direction
        
        return round(final_band, 4), direction
    
    def compute_macd(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> Dict[str, float]:
        """Compute MACD indicator."""
        closes = list(self._closes)
        
        if len(closes) < slow + signal:
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
        
        ema_fast = self._compute_ema(closes, fast)
        ema_slow = self._compute_ema(closes, slow)
        
        macd_line = ema_fast - ema_slow
        
        # Signal line (EMA of MACD)
        # Simplified - would need MACD history for proper signal line
        signal_line = macd_line * 0.9  # Approximation
        
        histogram = macd_line - signal_line
        
        return {
            "macd": round(macd_line, 4),
            "signal": round(signal_line, 4),
            "histogram": round(histogram, 4),
        }
    
    def compute_bollinger(
        self,
        period: int = 20,
        std_dev: float = 2.0,
    ) -> Dict[str, float]:
        """Compute Bollinger Bands."""
        closes = list(self._closes)
        
        if len(closes) < period:
            return {"upper": 0.0, "middle": 0.0, "lower": 0.0}
        
        middle = self._compute_sma(closes, period)
        
        # Calculate standard deviation
        recent = closes[-period:]
        variance = sum((x - middle) ** 2 for x in recent) / period
        std = math.sqrt(variance)
        
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return {
            "upper": round(upper, 4),
            "middle": round(middle, 4),
            "lower": round(lower, 4),
        }
    
    def get_candle_count(self) -> int:
        """Get number of candles in history."""
        return len(self._closes)


class IndicatorService:
    """
    Service for computing indicators across multiple symbols and timeframes.
    
    Subscribes to candle events and publishes indicator updates.
    """
    
    def __init__(
        self,
        timeframes: Optional[List[str]] = None,
        on_indicator: Optional[Callable[[IndicatorResult], Coroutine[Any, Any, None]]] = None,
    ):
        """
        Initialize indicator service.
        
        Args:
            timeframes: List of timeframes to compute indicators for
            on_indicator: Callback for indicator updates
        """
        self.timeframes = timeframes or ["1m", "5m", "15m", "1h"]
        self._on_indicator = on_indicator
        
        # Calculators by (symbol, timeframe)
        self._calculators: Dict[tuple[str, str], IndicatorCalculator] = {}
        
        # Event bus
        self._event_bus: Optional[EventBus] = None
        
        # State
        self._running = False
    
    async def start(self) -> None:
        """Start the indicator service."""
        if self._running:
            return
        
        self._event_bus = await get_event_bus()
        
        # Subscribe to candle events
        await self._event_bus.subscribe(
            EventType.CANDLE_FORMED,
            self._handle_candle_event,
        )
        
        self._running = True
        logger.info(f"✓ Indicator service started (timeframes: {self.timeframes})")
    
    async def stop(self) -> None:
        """Stop the indicator service."""
        self._running = False
        logger.info("Indicator service stopped")
    
    def add_symbol(self, symbol: str, timeframe: str) -> None:
        """Add a symbol/timeframe for indicator computation."""
        key = (symbol, timeframe)
        if key not in self._calculators:
            self._calculators[key] = IndicatorCalculator(symbol, timeframe)
    
    async def _handle_candle_event(self, event: CandleEvent) -> None:
        """Handle incoming candle event."""
        if not event.is_complete:
            return  # Only compute on complete candles
        
        symbol = event.symbol
        timeframe = event.timeframe
        
        # Filter by configured timeframes
        if timeframe not in self.timeframes:
            return
        
        # Get or create calculator
        key = (symbol, timeframe)
        if key not in self._calculators:
            self.add_symbol(symbol, timeframe)
        
        calculator = self._calculators[key]
        
        # Create candle object
        candle = Candle(
            symbol=symbol,
            timeframe=Timeframe(timeframe),
            timestamp=event.timestamp,
            open=event.open,
            high=event.high,
            low=event.low,
            close=event.close,
            volume=event.volume,
            is_complete=True,
        )
        
        # Add candle and compute indicators
        calculator.add_candle(candle)
        result = calculator.compute_all()
        
        # Publish result
        await self._publish_indicators(result)
        
        # Callback
        if self._on_indicator:
            await self._on_indicator(result)
    
    async def compute_indicators(
        self,
        symbol: str,
        timeframe: str,
        candle: Candle,
    ) -> IndicatorResult:
        """
        Compute indicators for a candle directly.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            candle: Candle data
            
        Returns:
            Computed indicator values.
        """
        key = (symbol, timeframe)
        if key not in self._calculators:
            self.add_symbol(symbol, timeframe)
        
        calculator = self._calculators[key]
        calculator.add_candle(candle)
        
        result = calculator.compute_all()
        await self._publish_indicators(result)
        
        return result
    
    async def _publish_indicators(self, result: IndicatorResult) -> None:
        """Publish indicator values to event bus."""
        if not self._event_bus or not result.values:
            return
        
        event = IndicatorEvent(
            event_type=EventType.INDICATOR_UPDATED,
            instrument_id=result.symbol,
            symbol=result.symbol,
            timeframe=result.timeframe,
            indicators=result.values,
        )
        
        await self._event_bus.publish(event)
    
    def get_latest_indicators(
        self,
        symbol: str,
        timeframe: str,
    ) -> Optional[IndicatorResult]:
        """Get latest computed indicators for a symbol/timeframe."""
        key = (symbol, timeframe)
        calculator = self._calculators.get(key)
        
        if calculator and calculator.get_candle_count() > 0:
            return calculator.compute_all()
        
        return None
    
    def get_indicator_value(
        self,
        symbol: str,
        timeframe: str,
        indicator_name: str,
    ) -> Optional[float]:
        """Get a specific indicator value."""
        result = self.get_latest_indicators(symbol, timeframe)
        if result:
            return result.values.get(indicator_name)
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "running": self._running,
            "calculator_count": len(self._calculators),
            "timeframes": self.timeframes,
            "calculators": {
                f"{s}_{tf}": calc.get_candle_count()
                for (s, tf), calc in self._calculators.items()
            },
        }


# =============================================================================
# Factory Function
# =============================================================================

async def create_indicator_service(
    timeframes: Optional[List[str]] = None,
) -> IndicatorService:
    """
    Factory function to create and start indicator service.
    
    Args:
        timeframes: Optional list of timeframes
        
    Returns:
        Started IndicatorService instance.
    """
    service = IndicatorService(timeframes=timeframes)
    await service.start()
    return service


__all__ = [
    "IndicatorType",
    "IndicatorValue",
    "IndicatorResult",
    "IndicatorCalculator",
    "IndicatorService",
    "create_indicator_service",
]
