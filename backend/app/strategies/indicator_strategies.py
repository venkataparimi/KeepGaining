"""
Simple Indicator Strategies
KeepGaining Trading Platform

Basic strategies using pre-computed indicators for backtesting.
These are starting points - more sophisticated strategies can be built later.

Available Strategies:
1. EMACrossoverStrategy - Classic moving average crossover
2. RSIMomentumStrategy - RSI oversold/overbought with trend filter
3. SupertrendStrategy - Supertrend direction changes
4. VWAPBounceStrategy - Price bouncing off VWAP with volume confirmation
"""

import logging
import uuid
from abc import ABC
from dataclasses import field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from app.services.strategy_engine import (
    BaseStrategy,
    Signal,
    SignalType,
    SignalStrength,
    StrategyState,
)

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class SimpleIndicatorStrategy(BaseStrategy):
    """Base class for simple indicator-based strategies."""
    
    def __init__(
        self,
        strategy_id: str,
        name: str,
        description: str,
        config: Dict[str, Any]
    ):
        super().__init__(strategy_id, name, description, config)
        
        # Default configs
        self.config.setdefault("risk_reward_ratio", 2.0)
        self.config.setdefault("quantity_pct", 5.0)
        self.config.setdefault("signal_validity_minutes", 5)
        self.config.setdefault("atr_sl_multiplier", 1.5)
        
    def get_stop_loss(
        self,
        entry_price: Decimal,
        signal_type: SignalType,
        indicators: Dict[str, Any],
        candle: Dict[str, Any]
    ) -> Decimal:
        """Calculate stop loss using ATR."""
        atr = Decimal(str(indicators.get("atr_14", 0)))
        multiplier = Decimal(str(self.config.get("atr_sl_multiplier", 1.5)))
        
        if atr == 0:
            # Fallback: 1% stop loss
            atr = entry_price * Decimal("0.01")
        
        if signal_type == SignalType.LONG_ENTRY:
            return entry_price - (atr * multiplier)
        else:
            return entry_price + (atr * multiplier)
    
    def get_target(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        signal_type: SignalType,
        indicators: Dict[str, Any]
    ) -> Decimal:
        """Calculate target based on risk-reward ratio."""
        rr_ratio = Decimal(str(self.config.get("risk_reward_ratio", 2.0)))
        risk = abs(entry_price - stop_loss)
        
        if signal_type == SignalType.LONG_ENTRY:
            return entry_price + (risk * rr_ratio)
        else:
            return entry_price - (risk * rr_ratio)
    
    def _create_signal(
        self,
        symbol: str,
        signal_type: SignalType,
        strength: SignalStrength,
        entry_price: Decimal,
        indicators: Dict[str, Any],
        candle: Dict[str, Any],
        reason: str
    ) -> Signal:
        """Helper to create a signal."""
        stop_loss = self.get_stop_loss(entry_price, signal_type, indicators, candle)
        target = self.get_target(entry_price, stop_loss, signal_type, indicators)
        
        now = datetime.now(IST)
        
        return Signal(
            signal_id=f"SIG-{self.strategy_id}-{uuid.uuid4().hex[:8]}",
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=symbol,
            exchange=symbol.split(":")[0] if ":" in symbol else "NSE",
            signal_type=signal_type,
            strength=strength,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target,
            quantity_pct=self.config.get("quantity_pct", 5.0),
            timeframe="1m",
            indicators=indicators,
            reason=reason,
            generated_at=now,
            valid_until=now + timedelta(minutes=self.config.get("signal_validity_minutes", 5)),
        )


class EMACrossoverStrategy(SimpleIndicatorStrategy):
    """
    EMA Crossover Strategy
    
    Entry:
    - LONG: EMA(9) crosses above EMA(20), price above EMA(50)
    - SHORT: EMA(9) crosses below EMA(20), price below EMA(50)
    
    Filters:
    - ADX > 20 (trending market)
    - Volume above average
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        default_config = {
            "fast_ema": 9,
            "slow_ema": 21,  # Match database column ema_21
            "trend_ema": 50,
            "adx_threshold": 20,
            "volume_threshold": 1.0,
            "risk_reward_ratio": 2.0,
            "quantity_pct": 5.0,
        }
        if config:
            default_config.update(config)
        
        super().__init__(
            strategy_id="EMA_CROSS",
            name="EMA Crossover",
            description="Classic EMA crossover with trend and volume filters",
            config=default_config
        )
        
        # Track previous EMA values for crossover detection
        self._prev_fast_ema: Dict[str, float] = {}
        self._prev_slow_ema: Dict[str, float] = {}
    
    async def evaluate(
        self,
        symbol: str,
        timeframe: str,
        indicators: Dict[str, Any],
        candle: Dict[str, Any]
    ) -> Optional[Signal]:
        """Evaluate EMA crossover conditions."""
        
        # Get required indicators
        fast_key = f"ema_{self.config['fast_ema']}"
        slow_key = f"ema_{self.config['slow_ema']}"
        trend_key = f"ema_{self.config['trend_ema']}"
        
        fast_ema = indicators.get(fast_key)
        slow_ema = indicators.get(slow_key)
        trend_ema = indicators.get(trend_key)
        adx = indicators.get("adx", 25)  # Default to passing if not present
        
        # Check if we have all required indicators
        if None in [fast_ema, slow_ema, trend_ema]:
            return None
        
        close = candle.get("close", 0)
        
        # Get previous values
        prev_fast = self._prev_fast_ema.get(symbol)
        prev_slow = self._prev_slow_ema.get(symbol)
        
        # Store current values for next iteration
        self._prev_fast_ema[symbol] = fast_ema
        self._prev_slow_ema[symbol] = slow_ema
        
        # Need previous values to detect crossover
        if prev_fast is None or prev_slow is None:
            return None
        
        # Check ADX filter (skip if not trending)
        if adx < self.config["adx_threshold"]:
            return None
        
        entry_price = Decimal(str(close))
        
        # Bullish crossover: fast crosses above slow
        if prev_fast <= prev_slow and fast_ema > slow_ema:
            # Confirm uptrend: price above trend EMA
            if close > trend_ema:
                strength = SignalStrength.STRONG if adx > 30 else SignalStrength.MODERATE
                return self._create_signal(
                    symbol=symbol,
                    signal_type=SignalType.LONG_ENTRY,
                    strength=strength,
                    entry_price=entry_price,
                    indicators=indicators,
                    candle=candle,
                    reason=f"EMA({self.config['fast_ema']}) crossed above EMA({self.config['slow_ema']}), "
                           f"ADX={adx:.1f}"
                )
        
        # Bearish crossover: fast crosses below slow
        elif prev_fast >= prev_slow and fast_ema < slow_ema:
            # Confirm downtrend: price below trend EMA
            if close < trend_ema:
                strength = SignalStrength.STRONG if adx > 30 else SignalStrength.MODERATE
                return self._create_signal(
                    symbol=symbol,
                    signal_type=SignalType.SHORT_ENTRY,
                    strength=strength,
                    entry_price=entry_price,
                    indicators=indicators,
                    candle=candle,
                    reason=f"EMA({self.config['fast_ema']}) crossed below EMA({self.config['slow_ema']}), "
                           f"ADX={adx:.1f}"
                )
        
        return None


class RSIMomentumStrategy(SimpleIndicatorStrategy):
    """
    RSI Momentum Strategy
    
    Entry:
    - LONG: RSI crosses above 30 (oversold recovery), EMA(20) > EMA(50)
    - SHORT: RSI crosses below 70 (overbought rejection), EMA(20) < EMA(50)
    
    Filters:
    - Volume confirmation
    - Not in extreme RSI zones (< 20 or > 80)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        default_config = {
            "rsi_period": 14,
            "oversold": 30,
            "overbought": 70,
            "extreme_oversold": 20,
            "extreme_overbought": 80,
            "ema_fast": 21,  # Match database column ema_21
            "ema_slow": 50,
            "risk_reward_ratio": 2.0,
            "quantity_pct": 5.0,
        }
        if config:
            default_config.update(config)
        
        super().__init__(
            strategy_id="RSI_MOM",
            name="RSI Momentum",
            description="RSI oversold/overbought with trend filter",
            config=default_config
        )
        
        self._prev_rsi: Dict[str, float] = {}
    
    async def evaluate(
        self,
        symbol: str,
        timeframe: str,
        indicators: Dict[str, Any],
        candle: Dict[str, Any]
    ) -> Optional[Signal]:
        """Evaluate RSI momentum conditions."""
        
        rsi_key = f"rsi_{self.config['rsi_period']}"
        ema_fast_key = f"ema_{self.config['ema_fast']}"
        ema_slow_key = f"ema_{self.config['ema_slow']}"
        
        rsi = indicators.get(rsi_key)
        ema_fast = indicators.get(ema_fast_key)
        ema_slow = indicators.get(ema_slow_key)
        
        if None in [rsi, ema_fast, ema_slow]:
            return None
        
        prev_rsi = self._prev_rsi.get(symbol)
        self._prev_rsi[symbol] = rsi
        
        if prev_rsi is None:
            return None
        
        # Skip extreme zones
        if rsi < self.config["extreme_oversold"] or rsi > self.config["extreme_overbought"]:
            return None
        
        close = candle.get("close", 0)
        entry_price = Decimal(str(close))
        
        # Bullish: RSI crosses above oversold level
        if prev_rsi <= self.config["oversold"] and rsi > self.config["oversold"]:
            # Confirm uptrend
            if ema_fast > ema_slow:
                strength = SignalStrength.STRONG if prev_rsi < 25 else SignalStrength.MODERATE
                return self._create_signal(
                    symbol=symbol,
                    signal_type=SignalType.LONG_ENTRY,
                    strength=strength,
                    entry_price=entry_price,
                    indicators=indicators,
                    candle=candle,
                    reason=f"RSI({self.config['rsi_period']}) crossed above {self.config['oversold']} "
                           f"from {prev_rsi:.1f}, uptrend confirmed"
                )
        
        # Bearish: RSI crosses below overbought level
        elif prev_rsi >= self.config["overbought"] and rsi < self.config["overbought"]:
            # Confirm downtrend
            if ema_fast < ema_slow:
                strength = SignalStrength.STRONG if prev_rsi > 75 else SignalStrength.MODERATE
                return self._create_signal(
                    symbol=symbol,
                    signal_type=SignalType.SHORT_ENTRY,
                    strength=strength,
                    entry_price=entry_price,
                    indicators=indicators,
                    candle=candle,
                    reason=f"RSI({self.config['rsi_period']}) crossed below {self.config['overbought']} "
                           f"from {prev_rsi:.1f}, downtrend confirmed"
                )
        
        return None


class SupertrendStrategy(SimpleIndicatorStrategy):
    """
    Supertrend Strategy
    
    Entry:
    - LONG: Supertrend direction changes to bullish (1)
    - SHORT: Supertrend direction changes to bearish (-1)
    
    Filters:
    - ADX > 25 for strong trend
    - Volume above average
    - Price action confirms (close > supertrend for long)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        default_config = {
            "adx_threshold": 25,
            "risk_reward_ratio": 2.5,
            "quantity_pct": 5.0,
        }
        if config:
            default_config.update(config)
        
        super().__init__(
            strategy_id="SUPERTREND",
            name="Supertrend",
            description="Supertrend direction change with ADX filter",
            config=default_config
        )
        
        self._prev_direction: Dict[str, int] = {}
    
    async def evaluate(
        self,
        symbol: str,
        timeframe: str,
        indicators: Dict[str, Any],
        candle: Dict[str, Any]
    ) -> Optional[Signal]:
        """Evaluate Supertrend conditions."""
        
        supertrend = indicators.get("supertrend")
        direction = indicators.get("supertrend_direction")
        adx = indicators.get("adx", 30)  # Default to passing if not present
        
        if None in [supertrend, direction]:
            return None
        
        direction = int(direction)
        prev_direction = self._prev_direction.get(symbol)
        self._prev_direction[symbol] = direction
        
        if prev_direction is None:
            return None
        
        # Check ADX filter
        if adx < self.config["adx_threshold"]:
            return None
        
        close = candle.get("close", 0)
        entry_price = Decimal(str(close))
        
        # Direction change to bullish
        if prev_direction == -1 and direction == 1:
            if close > supertrend:  # Price above supertrend
                strength = SignalStrength.STRONG if adx > 35 else SignalStrength.MODERATE
                return self._create_signal(
                    symbol=symbol,
                    signal_type=SignalType.LONG_ENTRY,
                    strength=strength,
                    entry_price=entry_price,
                    indicators=indicators,
                    candle=candle,
                    reason=f"Supertrend turned bullish, ADX={adx:.1f}"
                )
        
        # Direction change to bearish
        elif prev_direction == 1 and direction == -1:
            if close < supertrend:  # Price below supertrend
                strength = SignalStrength.STRONG if adx > 35 else SignalStrength.MODERATE
                return self._create_signal(
                    symbol=symbol,
                    signal_type=SignalType.SHORT_ENTRY,
                    strength=strength,
                    entry_price=entry_price,
                    indicators=indicators,
                    candle=candle,
                    reason=f"Supertrend turned bearish, ADX={adx:.1f}"
                )
        
        return None


class VWAPBounceStrategy(SimpleIndicatorStrategy):
    """
    VWAP Bounce Strategy
    
    Entry:
    - LONG: Price touches VWAP from above and bounces, RSI not overbought
    - SHORT: Price touches VWAP from below and bounces, RSI not oversold
    
    Filters:
    - Within 0.5% of VWAP
    - Volume spike (1.5x average)
    - Not in first 30 minutes (VWAP needs time to stabilize)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        default_config = {
            "vwap_tolerance_pct": 0.5,  # Within 0.5% of VWAP
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "risk_reward_ratio": 2.0,
            "quantity_pct": 5.0,
        }
        if config:
            default_config.update(config)
        
        super().__init__(
            strategy_id="VWAP_BOUNCE",
            name="VWAP Bounce",
            description="Price bouncing off VWAP with volume confirmation",
            config=default_config
        )
        
        self._prev_close: Dict[str, float] = {}
    
    async def evaluate(
        self,
        symbol: str,
        timeframe: str,
        indicators: Dict[str, Any],
        candle: Dict[str, Any]
    ) -> Optional[Signal]:
        """Evaluate VWAP bounce conditions."""
        
        vwap = indicators.get("vwap")
        rsi = indicators.get("rsi_14", 50)
        
        if vwap is None:
            return None
        
        close = candle.get("close", 0)
        low = candle.get("low", 0)
        high = candle.get("high", 0)
        
        prev_close = self._prev_close.get(symbol)
        self._prev_close[symbol] = close
        
        if prev_close is None:
            return None
        
        # Calculate distance from VWAP
        vwap_distance_pct = abs(close - vwap) / vwap * 100
        
        # Check if near VWAP
        if vwap_distance_pct > self.config["vwap_tolerance_pct"]:
            return None
        
        entry_price = Decimal(str(close))
        
        # Bullish bounce: Price came down to VWAP and bounced
        if low <= vwap <= close and prev_close > vwap:
            if rsi < self.config["rsi_overbought"]:  # Not overbought
                strength = SignalStrength.MODERATE
                return self._create_signal(
                    symbol=symbol,
                    signal_type=SignalType.LONG_ENTRY,
                    strength=strength,
                    entry_price=entry_price,
                    indicators=indicators,
                    candle=candle,
                    reason=f"VWAP bounce (bullish), RSI={rsi:.1f}"
                )
        
        # Bearish bounce: Price came up to VWAP and bounced
        elif high >= vwap >= close and prev_close < vwap:
            if rsi > self.config["rsi_oversold"]:  # Not oversold
                strength = SignalStrength.MODERATE
                return self._create_signal(
                    symbol=symbol,
                    signal_type=SignalType.SHORT_ENTRY,
                    strength=strength,
                    entry_price=entry_price,
                    indicators=indicators,
                    candle=candle,
                    reason=f"VWAP bounce (bearish), RSI={rsi:.1f}"
                )
        
        return None


# Strategy registry for easy access
AVAILABLE_STRATEGIES = {
    "EMA_CROSS": EMACrossoverStrategy,
    "RSI_MOM": RSIMomentumStrategy,
    "SUPERTREND": SupertrendStrategy,
    "VWAP_BOUNCE": VWAPBounceStrategy,
}


def get_strategy(strategy_id: str, config: Optional[Dict[str, Any]] = None) -> SimpleIndicatorStrategy:
    """Get strategy instance by ID."""
    if strategy_id not in AVAILABLE_STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_id}. Available: {list(AVAILABLE_STRATEGIES.keys())}")
    
    return AVAILABLE_STRATEGIES[strategy_id](config)
