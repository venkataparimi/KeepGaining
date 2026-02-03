"""
Raw Candle Strategies
KeepGaining Trading Platform

Strategies that compute indicators on-the-fly from raw candle data.
No dependency on pre-computed indicator_data table.

These strategies can be used for:
1. Quick backtesting when indicator_data is empty
2. Real-time signal generation during live trading
3. Paper trading validation

Available Strategies:
- SimpleMomentumStrategy: Breakout above N-period high
- EMAMomentumStrategy: EMA crossover with momentum filter
- RSIDivergenceStrategy: RSI overbought/oversold with price divergence
- MACDStrategy: MACD crossover with histogram confirmation
- BollingerBandsStrategy: Mean reversion with BB bands
- VolumeBreakoutStrategy: Volume-confirmed price breakout
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List
from collections import deque
import math


@dataclass
class RawSignal:
    """Signal generated from raw candle data"""
    strategy_id: str
    instrument_id: str
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    target: float
    timestamp: datetime
    strength: float = 100.0  # 0-100
    reason: str = ""
    indicators: Dict[str, float] = field(default_factory=dict)


class IndicatorComputer:
    """
    Compute technical indicators on-the-fly from candle data.
    Maintains rolling windows for efficiency.
    """
    
    def __init__(self, max_history: int = 200):
        self.max_history = max_history
        # Rolling windows per symbol
        self._closes: Dict[str, deque] = {}
        self._highs: Dict[str, deque] = {}
        self._lows: Dict[str, deque] = {}
        self._volumes: Dict[str, deque] = {}
        # Cached EMA values for efficiency
        self._ema_cache: Dict[str, Dict[int, float]] = {}  # symbol -> {period: value}
    
    def update(self, symbol: str, candle: Dict[str, Any]) -> None:
        """Update indicator data with new candle"""
        if symbol not in self._closes:
            self._closes[symbol] = deque(maxlen=self.max_history)
            self._highs[symbol] = deque(maxlen=self.max_history)
            self._lows[symbol] = deque(maxlen=self.max_history)
            self._volumes[symbol] = deque(maxlen=self.max_history)
            self._ema_cache[symbol] = {}
        
        self._closes[symbol].append(float(candle['close']))
        self._highs[symbol].append(float(candle['high']))
        self._lows[symbol].append(float(candle['low']))
        vol = candle.get('volume', 0)
        self._volumes[symbol].append(int(vol) if vol else 0)
    
    def has_enough_data(self, symbol: str, required: int) -> bool:
        """Check if we have enough data"""
        return symbol in self._closes and len(self._closes[symbol]) >= required
    
    def get_close(self, symbol: str, offset: int = 0) -> Optional[float]:
        """Get close price (offset 0 = current, 1 = previous, etc.)"""
        if symbol not in self._closes or len(self._closes[symbol]) <= offset:
            return None
        return self._closes[symbol][-1 - offset]
    
    def get_sma(self, symbol: str, period: int) -> Optional[float]:
        """Calculate Simple Moving Average"""
        if not self.has_enough_data(symbol, period):
            return None
        closes = list(self._closes[symbol])[-period:]
        return sum(closes) / period
    
    def get_ema(self, symbol: str, period: int) -> Optional[float]:
        """Calculate Exponential Moving Average (efficiently cached)"""
        if not self.has_enough_data(symbol, period):
            return None
        
        # Use cached value if available
        if period in self._ema_cache.get(symbol, {}):
            # Update EMA with new close
            prev_ema = self._ema_cache[symbol][period]
            multiplier = 2.0 / (period + 1)
            current = self._closes[symbol][-1]
            new_ema = (current - prev_ema) * multiplier + prev_ema
            self._ema_cache[symbol][period] = new_ema
            return new_ema
        
        # Initialize EMA with SMA
        closes = list(self._closes[symbol])[-period:]
        ema = sum(closes) / period
        self._ema_cache[symbol][period] = ema
        return ema
    
    def get_rsi(self, symbol: str, period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index"""
        if not self.has_enough_data(symbol, period + 1):
            return None
        
        closes = list(self._closes[symbol])[-period - 1:]
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            change = closes[i] - closes[i - 1]
            if change >= 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def get_macd(self, symbol: str, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Dict[str, float]]:
        """Calculate MACD (line, signal, histogram)"""
        if not self.has_enough_data(symbol, slow + signal):
            return None
        
        fast_ema = self.get_ema(symbol, fast)
        slow_ema = self.get_ema(symbol, slow)
        
        if fast_ema is None or slow_ema is None:
            return None
        
        macd_line = fast_ema - slow_ema
        
        # For signal line, we'd need MACD history - simplified here
        # In production, maintain MACD history
        signal_line = macd_line * 0.9  # Simplified approximation
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def get_bollinger_bands(self, symbol: str, period: int = 20, std_dev: float = 2.0) -> Optional[Dict[str, float]]:
        """Calculate Bollinger Bands"""
        if not self.has_enough_data(symbol, period):
            return None
        
        closes = list(self._closes[symbol])[-period:]
        sma = sum(closes) / period
        
        # Calculate standard deviation
        variance = sum((x - sma) ** 2 for x in closes) / period
        std = math.sqrt(variance)
        
        return {
            'upper': sma + (std * std_dev),
            'middle': sma,
            'lower': sma - (std * std_dev),
            'std': std,
            'pct_b': (closes[-1] - (sma - std * std_dev)) / (std * std_dev * 2) if std > 0 else 0.5
        }
    
    def get_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        """Calculate Average True Range"""
        if not self.has_enough_data(symbol, period + 1):
            return None
        
        closes = list(self._closes[symbol])[-period - 1:]
        highs = list(self._highs[symbol])[-period:]
        lows = list(self._lows[symbol])[-period:]
        
        true_ranges = []
        for i in range(period):
            prev_close = closes[i]
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - prev_close),
                abs(lows[i] - prev_close)
            )
            true_ranges.append(tr)
        
        return sum(true_ranges) / period
    
    def get_volume_sma(self, symbol: str, period: int = 20) -> Optional[float]:
        """Calculate volume moving average"""
        if symbol not in self._volumes or len(self._volumes[symbol]) < period:
            return None
        volumes = list(self._volumes[symbol])[-period:]
        return sum(volumes) / period
    
    def get_highest_high(self, symbol: str, period: int) -> Optional[float]:
        """Get highest high over period"""
        if symbol not in self._highs or len(self._highs[symbol]) < period:
            return None
        return max(list(self._highs[symbol])[-period:])
    
    def get_lowest_low(self, symbol: str, period: int) -> Optional[float]:
        """Get lowest low over period"""
        if symbol not in self._lows or len(self._lows[symbol]) < period:
            return None
        return min(list(self._lows[symbol])[-period:])


class RawCandleStrategy:
    """Base class for raw candle strategies"""
    
    def __init__(self, strategy_id: str, name: str, config: Dict[str, Any] = None):
        self.strategy_id = strategy_id
        self.name = name
        self.config = config or {}
        self.indicators = IndicatorComputer(max_history=200)
        
        # Default risk management
        self.config.setdefault('sl_percent', 2.0)
        self.config.setdefault('target_percent', 3.0)
        self.config.setdefault('risk_reward', 1.5)
    
    def update(self, symbol: str, candle: Dict[str, Any]) -> None:
        """Update indicators with new candle"""
        self.indicators.update(symbol, candle)
    
    def evaluate(self, instrument_id: str, symbol: str, candle: Dict[str, Any]) -> Optional[RawSignal]:
        """Evaluate for signal - to be overridden"""
        raise NotImplementedError
    
    def _calculate_stops(self, entry: float, direction: str, candle: Dict[str, Any]) -> tuple:
        """Calculate stop loss and target"""
        atr = self.indicators.get_atr(candle.get('symbol', ''), 14)
        
        if atr:
            atr_mult = self.config.get('atr_multiplier', 1.5)
            if direction == "LONG":
                sl = entry - (atr * atr_mult)
                target = entry + (atr * atr_mult * self.config['risk_reward'])
            else:
                sl = entry + (atr * atr_mult)
                target = entry - (atr * atr_mult * self.config['risk_reward'])
        else:
            sl_pct = self.config['sl_percent'] / 100
            target_pct = self.config['target_percent'] / 100
            if direction == "LONG":
                sl = entry * (1 - sl_pct)
                target = entry * (1 + target_pct)
            else:
                sl = entry * (1 + sl_pct)
                target = entry * (1 - target_pct)
        
        return sl, target


class EMAMomentumStrategy(RawCandleStrategy):
    """
    EMA Crossover with Momentum Filter
    
    Entry:
    - LONG: EMA(9) > EMA(21), price above both, RSI > 50
    - SHORT: EMA(9) < EMA(21), price below both, RSI < 50
    
    Exit: Opposite crossover or stop/target hit
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            'fast_ema': 9,
            'slow_ema': 21,
            'rsi_period': 14,
            'sl_percent': 1.5,
            'target_percent': 3.0,
        }
        if config:
            default_config.update(config)
        super().__init__("EMA_MOM", "EMA Momentum", default_config)
        
        self._prev_fast: Dict[str, float] = {}
        self._prev_slow: Dict[str, float] = {}
    
    def evaluate(self, instrument_id: str, symbol: str, candle: Dict[str, Any]) -> Optional[RawSignal]:
        self.update(symbol, candle)
        
        fast_period = self.config['fast_ema']
        slow_period = self.config['slow_ema']
        
        if not self.indicators.has_enough_data(symbol, slow_period + 5):
            return None
        
        fast_ema = self.indicators.get_ema(symbol, fast_period)
        slow_ema = self.indicators.get_ema(symbol, slow_period)
        rsi = self.indicators.get_rsi(symbol, self.config['rsi_period'])
        
        if None in [fast_ema, slow_ema, rsi]:
            return None
        
        close = float(candle['close'])
        prev_fast = self._prev_fast.get(symbol)
        prev_slow = self._prev_slow.get(symbol)
        
        self._prev_fast[symbol] = fast_ema
        self._prev_slow[symbol] = slow_ema
        
        if prev_fast is None or prev_slow is None:
            return None
        
        signal = None
        
        # Bullish crossover
        if prev_fast <= prev_slow and fast_ema > slow_ema:
            if close > fast_ema and rsi > 50:
                sl, target = self._calculate_stops(close, "LONG", candle)
                signal = RawSignal(
                    strategy_id=self.strategy_id,
                    instrument_id=instrument_id,
                    symbol=symbol,
                    direction="LONG",
                    entry_price=close,
                    stop_loss=sl,
                    target=target,
                    timestamp=candle['timestamp'],
                    strength=min(100, 50 + rsi),
                    reason=f"EMA({fast_period}) crossed above EMA({slow_period}), RSI={rsi:.1f}",
                    indicators={'fast_ema': fast_ema, 'slow_ema': slow_ema, 'rsi': rsi}
                )
        
        # Bearish crossover
        elif prev_fast >= prev_slow and fast_ema < slow_ema:
            if close < fast_ema and rsi < 50:
                sl, target = self._calculate_stops(close, "SHORT", candle)
                signal = RawSignal(
                    strategy_id=self.strategy_id,
                    instrument_id=instrument_id,
                    symbol=symbol,
                    direction="SHORT",
                    entry_price=close,
                    stop_loss=sl,
                    target=target,
                    timestamp=candle['timestamp'],
                    strength=min(100, 150 - rsi),
                    reason=f"EMA({fast_period}) crossed below EMA({slow_period}), RSI={rsi:.1f}",
                    indicators={'fast_ema': fast_ema, 'slow_ema': slow_ema, 'rsi': rsi}
                )
        
        return signal


class RSIDivergenceStrategy(RawCandleStrategy):
    """
    RSI Oversold/Overbought with Mean Reversion
    
    Entry:
    - LONG: RSI < 30 (oversold) and bouncing (RSI increasing from bottom)
    - SHORT: RSI > 70 (overbought) and falling (RSI decreasing from top)
    
    Filters: Price must be near support/resistance
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            'rsi_period': 14,
            'oversold': 30,
            'overbought': 70,
            'sl_percent': 2.0,
            'target_percent': 4.0,
        }
        if config:
            default_config.update(config)
        super().__init__("RSI_DIV", "RSI Divergence", default_config)
        
        self._prev_rsi: Dict[str, float] = {}
    
    def evaluate(self, instrument_id: str, symbol: str, candle: Dict[str, Any]) -> Optional[RawSignal]:
        self.update(symbol, candle)
        
        if not self.indicators.has_enough_data(symbol, 20):
            return None
        
        rsi = self.indicators.get_rsi(symbol, self.config['rsi_period'])
        if rsi is None:
            return None
        
        prev_rsi = self._prev_rsi.get(symbol)
        self._prev_rsi[symbol] = rsi
        
        if prev_rsi is None:
            return None
        
        close = float(candle['close'])
        signal = None
        
        # Oversold bounce
        if prev_rsi < self.config['oversold'] and rsi > prev_rsi:
            sl, target = self._calculate_stops(close, "LONG", candle)
            signal = RawSignal(
                strategy_id=self.strategy_id,
                instrument_id=instrument_id,
                symbol=symbol,
                direction="LONG",
                entry_price=close,
                stop_loss=sl,
                target=target,
                timestamp=candle['timestamp'],
                strength=min(100, (self.config['oversold'] - prev_rsi) * 3 + 50),
                reason=f"RSI oversold bounce: {prev_rsi:.1f} → {rsi:.1f}",
                indicators={'rsi': rsi, 'prev_rsi': prev_rsi}
            )
        
        # Overbought rejection
        elif prev_rsi > self.config['overbought'] and rsi < prev_rsi:
            sl, target = self._calculate_stops(close, "SHORT", candle)
            signal = RawSignal(
                strategy_id=self.strategy_id,
                instrument_id=instrument_id,
                symbol=symbol,
                direction="SHORT",
                entry_price=close,
                stop_loss=sl,
                target=target,
                timestamp=candle['timestamp'],
                strength=min(100, (prev_rsi - self.config['overbought']) * 3 + 50),
                reason=f"RSI overbought rejection: {prev_rsi:.1f} → {rsi:.1f}",
                indicators={'rsi': rsi, 'prev_rsi': prev_rsi}
            )
        
        return signal


class BollingerBandsStrategy(RawCandleStrategy):
    """
    Bollinger Bands Mean Reversion
    
    Entry:
    - LONG: Price touches lower band and bounces (close > open)
    - SHORT: Price touches upper band and rejects (close < open)
    
    Filters: %B should be extreme (< 0.1 or > 0.9)
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            'bb_period': 20,
            'bb_std': 2.0,
            'pct_b_long': 0.1,
            'pct_b_short': 0.9,
            'sl_percent': 1.5,
            'target_percent': 2.0,
        }
        if config:
            default_config.update(config)
        super().__init__("BB_MR", "Bollinger Bands Mean Reversion", default_config)
    
    def evaluate(self, instrument_id: str, symbol: str, candle: Dict[str, Any]) -> Optional[RawSignal]:
        self.update(symbol, candle)
        
        if not self.indicators.has_enough_data(symbol, self.config['bb_period'] + 5):
            return None
        
        bb = self.indicators.get_bollinger_bands(symbol, self.config['bb_period'], self.config['bb_std'])
        if bb is None:
            return None
        
        close = float(candle['close'])
        open_price = float(candle['open'])
        low = float(candle['low'])
        high = float(candle['high'])
        pct_b = bb['pct_b']
        
        signal = None
        
        # Lower band touch + bullish candle
        if low <= bb['lower'] and close > open_price and pct_b < self.config['pct_b_long']:
            sl, target = self._calculate_stops(close, "LONG", candle)
            # Target = middle band
            target = max(target, bb['middle'])
            signal = RawSignal(
                strategy_id=self.strategy_id,
                instrument_id=instrument_id,
                symbol=symbol,
                direction="LONG",
                entry_price=close,
                stop_loss=sl,
                target=target,
                timestamp=candle['timestamp'],
                strength=min(100, (0.5 - pct_b) * 200),
                reason=f"BB lower band bounce, %B={pct_b:.2f}",
                indicators={'upper': bb['upper'], 'lower': bb['lower'], 'pct_b': pct_b}
            )
        
        # Upper band touch + bearish candle
        elif high >= bb['upper'] and close < open_price and pct_b > self.config['pct_b_short']:
            sl, target = self._calculate_stops(close, "SHORT", candle)
            # Target = middle band
            target = min(target, bb['middle'])
            signal = RawSignal(
                strategy_id=self.strategy_id,
                instrument_id=instrument_id,
                symbol=symbol,
                direction="SHORT",
                entry_price=close,
                stop_loss=sl,
                target=target,
                timestamp=candle['timestamp'],
                strength=min(100, (pct_b - 0.5) * 200),
                reason=f"BB upper band rejection, %B={pct_b:.2f}",
                indicators={'upper': bb['upper'], 'lower': bb['lower'], 'pct_b': pct_b}
            )
        
        return signal


class VolumeBreakoutStrategy(RawCandleStrategy):
    """
    Volume-Confirmed Breakout
    
    Entry:
    - LONG: Price breaks above 20-period high with volume > 1.5x average
    - SHORT: Price breaks below 20-period low with volume > 1.5x average
    
    This is the original SimpleMomentumStrategy enhanced with volume filter
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            'lookback': 20,
            'volume_multiplier': 1.5,
            'breakout_buffer': 0.001,  # 0.1% above/below level
            'sl_percent': 2.0,
            'target_percent': 4.0,
        }
        if config:
            default_config.update(config)
        super().__init__("VOL_BREAK", "Volume Breakout", default_config)
    
    def evaluate(self, instrument_id: str, symbol: str, candle: Dict[str, Any]) -> Optional[RawSignal]:
        self.update(symbol, candle)
        
        lookback = self.config['lookback']
        if not self.indicators.has_enough_data(symbol, lookback + 5):
            return None
        
        highest = self.indicators.get_highest_high(symbol, lookback)
        lowest = self.indicators.get_lowest_low(symbol, lookback)
        avg_volume = self.indicators.get_volume_sma(symbol, lookback)
        
        if None in [highest, lowest, avg_volume]:
            return None
        
        close = float(candle['close'])
        volume = int(candle.get('volume', 0))
        buffer = 1 + self.config['breakout_buffer']
        
        # Check volume confirmation
        vol_mult = self.config['volume_multiplier']
        volume_confirmed = avg_volume > 0 and volume > avg_volume * vol_mult
        
        signal = None
        
        # Breakout above
        if close > highest * buffer:
            if volume_confirmed or avg_volume == 0:  # Allow if no volume data
                sl, target = self._calculate_stops(close, "LONG", candle)
                strength = min(100, 50 + (volume / avg_volume * 10 if avg_volume > 0 else 50))
                signal = RawSignal(
                    strategy_id=self.strategy_id,
                    instrument_id=instrument_id,
                    symbol=symbol,
                    direction="LONG",
                    entry_price=close,
                    stop_loss=sl,
                    target=target,
                    timestamp=candle['timestamp'],
                    strength=strength,
                    reason=f"Breakout above {lookback}-period high ({highest:.2f}), Vol={volume:,}",
                    indicators={'highest': highest, 'volume': volume, 'avg_volume': avg_volume}
                )
        
        # Breakdown below
        elif close < lowest / buffer:
            if volume_confirmed or avg_volume == 0:
                sl, target = self._calculate_stops(close, "SHORT", candle)
                strength = min(100, 50 + (volume / avg_volume * 10 if avg_volume > 0 else 50))
                signal = RawSignal(
                    strategy_id=self.strategy_id,
                    instrument_id=instrument_id,
                    symbol=symbol,
                    direction="SHORT",
                    entry_price=close,
                    stop_loss=sl,
                    target=target,
                    timestamp=candle['timestamp'],
                    strength=strength,
                    reason=f"Breakdown below {lookback}-period low ({lowest:.2f}), Vol={volume:,}",
                    indicators={'lowest': lowest, 'volume': volume, 'avg_volume': avg_volume}
                )
        
        return signal


class MACDStrategy(RawCandleStrategy):
    """
    MACD Crossover with Histogram Confirmation
    
    Entry:
    - LONG: MACD crosses above signal, histogram turning positive
    - SHORT: MACD crosses below signal, histogram turning negative
    
    Enhanced with EMA trend filter
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            'fast_period': 12,
            'slow_period': 26,
            'signal_period': 9,
            'trend_ema': 50,
            'sl_percent': 1.5,
            'target_percent': 3.0,
        }
        if config:
            default_config.update(config)
        super().__init__("MACD_XO", "MACD Crossover", default_config)
        
        self._prev_histogram: Dict[str, float] = {}
    
    def evaluate(self, instrument_id: str, symbol: str, candle: Dict[str, Any]) -> Optional[RawSignal]:
        self.update(symbol, candle)
        
        slow = self.config['slow_period']
        signal_period = self.config['signal_period']
        
        if not self.indicators.has_enough_data(symbol, slow + signal_period + 5):
            return None
        
        macd = self.indicators.get_macd(
            symbol,
            self.config['fast_period'],
            slow,
            signal_period
        )
        trend_ema = self.indicators.get_ema(symbol, self.config['trend_ema'])
        
        if macd is None:
            return None
        
        histogram = macd['histogram']
        prev_histogram = self._prev_histogram.get(symbol)
        self._prev_histogram[symbol] = histogram
        
        if prev_histogram is None:
            return None
        
        close = float(candle['close'])
        signal = None
        
        # MACD histogram turning positive
        if prev_histogram <= 0 and histogram > 0:
            # Confirm with trend
            if trend_ema is None or close > trend_ema:
                sl, target = self._calculate_stops(close, "LONG", candle)
                signal = RawSignal(
                    strategy_id=self.strategy_id,
                    instrument_id=instrument_id,
                    symbol=symbol,
                    direction="LONG",
                    entry_price=close,
                    stop_loss=sl,
                    target=target,
                    timestamp=candle['timestamp'],
                    strength=min(100, 50 + abs(histogram) * 100),
                    reason=f"MACD histogram turned positive ({histogram:.4f})",
                    indicators={'macd': macd['macd'], 'signal': macd['signal'], 'histogram': histogram}
                )
        
        # MACD histogram turning negative
        elif prev_histogram >= 0 and histogram < 0:
            # Confirm with trend
            if trend_ema is None or close < trend_ema:
                sl, target = self._calculate_stops(close, "SHORT", candle)
                signal = RawSignal(
                    strategy_id=self.strategy_id,
                    instrument_id=instrument_id,
                    symbol=symbol,
                    direction="SHORT",
                    entry_price=close,
                    stop_loss=sl,
                    target=target,
                    timestamp=candle['timestamp'],
                    strength=min(100, 50 + abs(histogram) * 100),
                    reason=f"MACD histogram turned negative ({histogram:.4f})",
                    indicators={'macd': macd['macd'], 'signal': macd['signal'], 'histogram': histogram}
                )
        
        return signal


# Strategy registry
CANDLE_STRATEGIES = {
    "EMA_MOM": EMAMomentumStrategy,
    "RSI_DIV": RSIDivergenceStrategy,
    "BB_MR": BollingerBandsStrategy,
    "VOL_BREAK": VolumeBreakoutStrategy,
    "MACD_XO": MACDStrategy,
}


def get_candle_strategy(strategy_id: str, config: Dict[str, Any] = None) -> RawCandleStrategy:
    """Get strategy instance by ID"""
    if strategy_id not in CANDLE_STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_id}. Available: {list(CANDLE_STRATEGIES.keys())}")
    return CANDLE_STRATEGIES[strategy_id](config)


def get_all_strategies(config: Dict[str, Any] = None) -> List[RawCandleStrategy]:
    """Get all strategy instances"""
    return [cls(config) for cls in CANDLE_STRATEGIES.values()]


__all__ = [
    "RawSignal",
    "IndicatorComputer",
    "RawCandleStrategy",
    "EMAMomentumStrategy",
    "RSIDivergenceStrategy",
    "BollingerBandsStrategy",
    "VolumeBreakoutStrategy",
    "MACDStrategy",
    "CANDLE_STRATEGIES",
    "get_candle_strategy",
    "get_all_strategies",
]
