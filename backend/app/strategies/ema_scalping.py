#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EMA Scalping Strategy - 9/15 EMA Crossover with Slope Filter

A high-accuracy scalping strategy using:
1. 9 EMA above 15 EMA for bullish bias (below for bearish)
2. Slope >= 30 degrees for momentum confirmation
3. Dual-index confirmation (Nifty/BankNifty alignment)
4. Specific entry candle patterns (Pin Bar, Engulfing, Big Body)
5. Fixed 1:2 Risk/Reward ratio
6. Very tight stop losses (entry candle low/high)

Timeframe: 5-minute
Trading Window: 9:15 AM - 11:15 AM (first 2 hours)
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.strategies.base import Signal, SignalType
from app.services.data_providers.base import Candle


# IST timezone offset (UTC+5:30)
IST_OFFSET = timedelta(hours=5, minutes=30)


class TradeDirection(Enum):
    """Direction of trade."""
    BULLISH = "BULLISH"  # Buy CE
    BEARISH = "BEARISH"  # Buy PE


class CandlePattern(Enum):
    """Valid entry candle patterns."""
    PIN_BAR = "PIN_BAR"
    BIG_BODY = "BIG_BODY"
    ENGULFING = "ENGULFING"
    EMA_REJECTION = "EMA_REJECTION"
    NONE = "NONE"


@dataclass
class EMAScalpingConfig:
    """Configuration for EMA Scalping Strategy."""
    
    # EMA periods
    fast_ema_period: int = 9
    slow_ema_period: int = 15
    
    # Slope filter (degrees)
    min_slope_degrees: float = 30.0
    slope_lookback_candles: int = 3  # Candles to calculate slope
    
    # Trading window (IST)
    entry_window_start: time = time(9, 15)
    entry_window_end: time = time(11, 15)
    
    # Risk/Reward
    risk_reward_ratio: float = 2.0  # 1:2 RR
    
    # Entry candle filters
    min_body_ratio: float = 0.6  # For big body candles (body/range)
    pin_bar_wick_ratio: float = 2.0  # Wick must be 2x body for pin bar
    
    # Position management
    max_trades_per_day: int = 3
    
    # Dual-index confirmation
    require_dual_index_confirm: bool = True
    
    # Direction control
    enable_bullish_trades: bool = True
    enable_bearish_trades: bool = True


@dataclass
class TradingContext:
    """Maintains state during a trading day."""
    current_date: datetime = None
    
    # EMA values
    fast_ema: float = 0.0
    slow_ema: float = 0.0
    
    # EMA history for slope calculation
    fast_ema_history: List[float] = field(default_factory=list)
    slow_ema_history: List[float] = field(default_factory=list)
    
    # Slope values
    fast_ema_slope: float = 0.0
    slow_ema_slope: float = 0.0
    
    # Position tracking
    in_position: bool = False
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    entry_time: datetime = None
    direction: TradeDirection = None
    entry_pattern: CandlePattern = None
    
    # Daily tracking
    trades_today: int = 0
    daily_pnl: float = 0.0
    
    # Dual-index state (for Nifty/BankNifty)
    nifty_at_resistance: bool = False
    banknifty_at_resistance: bool = False
    nifty_at_support: bool = False
    banknifty_at_support: bool = False


class EMAScalpingStrategy:
    """
    EMA Scalping Strategy Implementation.
    
    Entry Rules (Bullish):
    1. 9 EMA > 15 EMA
    2. Slope of both EMAs >= 30 degrees
    3. Dual-index confirmation (other index not at resistance)
    4. Valid entry candle pattern
    5. Entry at high of confirmed candle
    
    Exit Rules:
    1. Stop Loss: Low of entry candle
    2. Target: 1:2 Risk/Reward
    
    Timeframe: 5-minute
    Window: 9:15 AM - 11:15 AM IST
    """
    
    def __init__(self, config: EMAScalpingConfig = None, symbol: str = ""):
        self.config = config or EMAScalpingConfig()
        self.symbol = symbol
        self.context: Optional[TradingContext] = None
        
        # Candle history for EMA calculation
        self.candle_history: List[Candle] = []
        
        # Track previous candle for pattern detection
        self.prev_candle: Optional[Candle] = None
        
    def _reset_daily_context(self, candle: Candle):
        """Reset context for a new trading day."""
        self.context = TradingContext(
            current_date=candle.timestamp.date(),
            fast_ema_history=[],
            slow_ema_history=[],
        )
        self.candle_history = []
        self.prev_candle = None
        
    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate EMA for given prices."""
        if len(prices) < period:
            # Use SMA for initial values
            return sum(prices) / len(prices) if prices else 0.0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Initial SMA
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
            
        return ema
    
    def _update_emas(self, candle: Candle):
        """Update EMA values with new candle."""
        self.candle_history.append(candle)
        closes = [c.close for c in self.candle_history]
        
        # Calculate EMAs
        if len(closes) >= self.config.fast_ema_period:
            self.context.fast_ema = self._calculate_ema(closes, self.config.fast_ema_period)
            self.context.fast_ema_history.append(self.context.fast_ema)
            
        if len(closes) >= self.config.slow_ema_period:
            self.context.slow_ema = self._calculate_ema(closes, self.config.slow_ema_period)
            self.context.slow_ema_history.append(self.context.slow_ema)
            
        # Keep history manageable
        max_history = max(self.config.fast_ema_period, self.config.slow_ema_period) + 50
        if len(self.candle_history) > max_history:
            self.candle_history = self.candle_history[-max_history:]
        if len(self.context.fast_ema_history) > 20:
            self.context.fast_ema_history = self.context.fast_ema_history[-20:]
        if len(self.context.slow_ema_history) > 20:
            self.context.slow_ema_history = self.context.slow_ema_history[-20:]
    
    def _calculate_slope_degrees(self, ema_history: List[float], lookback: int = 3) -> float:
        """
        Calculate slope of EMA in degrees.
        
        Uses the change in EMA over lookback candles, normalized by price level.
        30 degrees ≈ ~0.577 slope (tan(30°))
        """
        if len(ema_history) < lookback + 1:
            return 0.0
        
        # Get EMA values
        current_ema = ema_history[-1]
        past_ema = ema_history[-(lookback + 1)]
        
        if past_ema == 0:
            return 0.0
        
        # Calculate percentage change per candle
        pct_change_per_candle = ((current_ema - past_ema) / past_ema) / lookback
        
        # Convert to degrees
        # For 5-min candles, we scale: 0.1% per candle ≈ 30 degrees
        # This is calibrated empirically for typical index movement
        slope_factor = pct_change_per_candle * 1000  # Scale factor
        
        # Clamp to [-90, 90] degrees
        slope_degrees = math.degrees(math.atan(slope_factor * 5))  # 5 is tuning factor
        
        return slope_degrees
    
    def _check_ema_configuration(self) -> Tuple[bool, TradeDirection]:
        """
        Check if EMA configuration is valid for trading.
        Returns (is_valid, direction).
        """
        if self.context.fast_ema == 0 or self.context.slow_ema == 0:
            return False, None
        
        if self.context.fast_ema > self.context.slow_ema:
            if self.config.enable_bullish_trades:
                return True, TradeDirection.BULLISH
        elif self.context.fast_ema < self.context.slow_ema:
            if self.config.enable_bearish_trades:
                return True, TradeDirection.BEARISH
                
        return False, None
    
    def _check_slope_filter(self, direction: TradeDirection) -> bool:
        """
        Check if EMA slopes meet minimum threshold.
        Both EMAs must have slope >= 30 degrees in trade direction.
        """
        fast_slope = self._calculate_slope_degrees(
            self.context.fast_ema_history, 
            self.config.slope_lookback_candles
        )
        slow_slope = self._calculate_slope_degrees(
            self.context.slow_ema_history, 
            self.config.slope_lookback_candles
        )
        
        self.context.fast_ema_slope = fast_slope
        self.context.slow_ema_slope = slow_slope
        
        if direction == TradeDirection.BULLISH:
            return (fast_slope >= self.config.min_slope_degrees and 
                    slow_slope >= self.config.min_slope_degrees)
        else:  # BEARISH
            return (fast_slope <= -self.config.min_slope_degrees and 
                    slow_slope <= -self.config.min_slope_degrees)
    
    def _check_dual_index_confirmation(self, direction: TradeDirection) -> bool:
        """
        Check dual-index confirmation.
        
        For Bullish Nifty: BankNifty must NOT be at resistance
        For Bullish BankNifty: Nifty must NOT be at resistance
        For Bearish: Check support levels instead
        
        Note: This requires external data feed for the other index.
        For backtesting single symbols, this can be disabled.
        """
        if not self.config.require_dual_index_confirm:
            return True
        
        # Determine which index we're trading
        is_nifty = "NIFTY" in self.symbol.upper() and "BANK" not in self.symbol.upper()
        is_banknifty = "BANKNIFTY" in self.symbol.upper()
        
        if not (is_nifty or is_banknifty):
            # Not an index, skip dual confirmation
            return True
        
        if direction == TradeDirection.BULLISH:
            if is_nifty:
                return not self.context.banknifty_at_resistance
            else:  # BankNifty
                return not self.context.nifty_at_resistance
        else:  # BEARISH
            if is_nifty:
                return not self.context.banknifty_at_support
            else:  # BankNifty
                return not self.context.nifty_at_support
        
        return True
    
    def _detect_candle_pattern(self, candle: Candle, direction: TradeDirection) -> CandlePattern:
        """
        Detect valid entry candle patterns.
        
        Valid patterns:
        1. Pin Bar - Small body, long wick in opposite direction
        2. Big Body - Large body (>60% of range), small wicks
        3. Engulfing - Current candle engulfs previous
        4. EMA Rejection - Crosses below EMAs but closes above (bullish)
        """
        body = abs(candle.close - candle.open)
        total_range = candle.high - candle.low
        
        if total_range == 0:
            return CandlePattern.NONE
        
        body_ratio = body / total_range
        is_bullish_candle = candle.close > candle.open
        is_bearish_candle = candle.close < candle.open
        
        upper_wick = candle.high - max(candle.open, candle.close)
        lower_wick = min(candle.open, candle.close) - candle.low
        
        # 1. Pin Bar Detection
        if direction == TradeDirection.BULLISH:
            # Bullish pin bar: Long lower wick, small upper wick
            if lower_wick > body * self.config.pin_bar_wick_ratio and upper_wick < body:
                return CandlePattern.PIN_BAR
        else:  # BEARISH
            # Bearish pin bar: Long upper wick, small lower wick
            if upper_wick > body * self.config.pin_bar_wick_ratio and lower_wick < body:
                return CandlePattern.PIN_BAR
        
        # 2. Big Body Detection
        if body_ratio >= self.config.min_body_ratio:
            if direction == TradeDirection.BULLISH and is_bullish_candle:
                return CandlePattern.BIG_BODY
            elif direction == TradeDirection.BEARISH and is_bearish_candle:
                return CandlePattern.BIG_BODY
        
        # 3. Engulfing Detection
        if self.prev_candle:
            prev_body_high = max(self.prev_candle.open, self.prev_candle.close)
            prev_body_low = min(self.prev_candle.open, self.prev_candle.close)
            curr_body_high = max(candle.open, candle.close)
            curr_body_low = min(candle.open, candle.close)
            
            if direction == TradeDirection.BULLISH:
                # Bullish engulfing: Current body engulfs previous
                if (is_bullish_candle and 
                    curr_body_low < prev_body_low and 
                    curr_body_high > prev_body_high):
                    return CandlePattern.ENGULFING
            else:  # BEARISH
                if (is_bearish_candle and 
                    curr_body_low < prev_body_low and 
                    curr_body_high > prev_body_high):
                    return CandlePattern.ENGULFING
        
        # 4. EMA Rejection Detection
        if direction == TradeDirection.BULLISH:
            # Candle crosses below EMAs but closes above both
            if (candle.low < self.context.slow_ema and 
                candle.close > self.context.fast_ema and
                candle.close > self.context.slow_ema):
                return CandlePattern.EMA_REJECTION
        else:  # BEARISH
            # Candle crosses above EMAs but closes below both
            if (candle.high > self.context.slow_ema and 
                candle.close < self.context.fast_ema and
                candle.close < self.context.slow_ema):
                return CandlePattern.EMA_REJECTION
        
        return CandlePattern.NONE
    
    def _check_entry_conditions(self, candle: Candle) -> Tuple[bool, Dict[str, Any]]:
        """
        Check all entry conditions.
        
        Returns (should_enter, metadata dict).
        """
        metadata = {
            "fast_ema": self.context.fast_ema,
            "slow_ema": self.context.slow_ema,
            "fast_slope": self.context.fast_ema_slope,
            "slow_slope": self.context.slow_ema_slope,
            "direction": None,
            "pattern": None,
            "entry_price": 0,
            "stop_loss": 0,
            "target": 0,
        }
        
        # Check trading window
        if candle.timestamp.tzinfo is not None:
            ist_time = (candle.timestamp + IST_OFFSET).time()
        else:
            ist_time = candle.timestamp.time()
            
        if not (self.config.entry_window_start <= ist_time <= self.config.entry_window_end):
            return False, metadata
        
        # Check max trades per day
        if self.context.trades_today >= self.config.max_trades_per_day:
            return False, metadata
        
        # Check EMA configuration
        ema_valid, direction = self._check_ema_configuration()
        if not ema_valid:
            return False, metadata
        
        metadata["direction"] = direction.value
        
        # Check slope filter
        if not self._check_slope_filter(direction):
            return False, metadata
        
        metadata["fast_slope"] = self.context.fast_ema_slope
        metadata["slow_slope"] = self.context.slow_ema_slope
        
        # Check dual-index confirmation
        if not self._check_dual_index_confirmation(direction):
            return False, metadata
        
        # Check candle pattern
        pattern = self._detect_candle_pattern(candle, direction)
        if pattern == CandlePattern.NONE:
            return False, metadata
        
        metadata["pattern"] = pattern.value
        
        # Calculate entry, SL, and target
        if direction == TradeDirection.BULLISH:
            entry_price = candle.high  # Enter at high of candle
            stop_loss = candle.low     # SL at low of candle
            risk = entry_price - stop_loss
            target = entry_price + (risk * self.config.risk_reward_ratio)
        else:  # BEARISH
            entry_price = candle.low   # Enter at low of candle
            stop_loss = candle.high    # SL at high of candle
            risk = stop_loss - entry_price
            target = entry_price - (risk * self.config.risk_reward_ratio)
        
        # Validate risk is reasonable (at least 0.05%)
        risk_pct = abs(risk / entry_price) * 100
        if risk_pct < 0.05 or risk_pct > 2.0:  # Too small or too large
            return False, metadata
        
        metadata["entry_price"] = entry_price
        metadata["stop_loss"] = stop_loss
        metadata["target"] = target
        metadata["risk_pct"] = risk_pct
        
        return True, metadata
    
    def _check_exit_conditions(self, candle: Candle) -> Tuple[bool, str]:
        """
        Check exit conditions for open position.
        
        Returns (should_exit, reason).
        """
        if not self.context.in_position:
            return False, ""
        
        direction = self.context.direction
        
        if direction == TradeDirection.BULLISH:
            # Check stop loss (candle low breaches SL)
            if candle.low <= self.context.stop_loss:
                return True, f"Stop Loss hit at {self.context.stop_loss:.2f}"
            
            # Check target (candle high reaches target)
            if candle.high >= self.context.target_price:
                return True, f"Target hit at {self.context.target_price:.2f}"
                
        else:  # BEARISH
            # Check stop loss (candle high breaches SL)
            if candle.high >= self.context.stop_loss:
                return True, f"Stop Loss hit at {self.context.stop_loss:.2f}"
            
            # Check target (candle low reaches target)
            if candle.low <= self.context.target_price:
                return True, f"Target hit at {self.context.target_price:.2f}"
        
        # Check end of day
        if candle.timestamp.tzinfo is not None:
            ist_time = (candle.timestamp + IST_OFFSET).time()
        else:
            ist_time = candle.timestamp.time()
            
        if ist_time >= time(15, 15):
            return True, "End of day exit"
        
        return False, ""
    
    def _get_exit_price(self, candle: Candle, reason: str) -> float:
        """Calculate actual exit price based on exit reason."""
        direction = self.context.direction
        
        if "Target hit" in reason:
            return self.context.target_price
        elif "Stop Loss hit" in reason:
            return self.context.stop_loss
        else:
            # EOD or other exit - use close
            return candle.close
    
    def on_candle(self, candle: Candle, instrument_id: int = None) -> Optional[Signal]:
        """
        Process a new 5-minute candle.
        
        Returns Signal if entry/exit triggered, None otherwise.
        """
        # Initialize or reset daily context
        if self.context is None or candle.timestamp.date() != self.context.current_date:
            self._reset_daily_context(candle)
        
        # Update EMAs
        self._update_emas(candle)
        
        # Need enough history for EMA calculation
        if len(self.candle_history) < self.config.slow_ema_period + 5:
            self.prev_candle = candle
            return None
        
        # Check if in position - look for exit
        if self.context.in_position:
            should_exit, reason = self._check_exit_conditions(candle)
            
            if should_exit:
                exit_price = self._get_exit_price(candle, reason)
                
                # Calculate P&L
                if self.context.direction == TradeDirection.BULLISH:
                    pnl_pct = (exit_price - self.context.entry_price) / self.context.entry_price * 100
                else:
                    pnl_pct = (self.context.entry_price - exit_price) / self.context.entry_price * 100
                
                self.context.daily_pnl += pnl_pct
                self.context.in_position = False
                
                signal = Signal(
                    signal_type=SignalType.EXIT,
                    symbol=self.symbol,
                    price=exit_price,
                    timestamp=candle.timestamp,
                    metadata={
                        "reason": reason,
                        "direction": self.context.direction.value,
                        "entry_price": self.context.entry_price,
                        "exit_price": exit_price,
                        "pnl_pct": pnl_pct,
                        "pattern": self.context.entry_pattern.value if self.context.entry_pattern else None,
                    }
                )
                
                self.prev_candle = candle
                return signal
        
        # Not in position - look for entry
        else:
            should_enter, metadata = self._check_entry_conditions(candle)
            
            if should_enter:
                direction = TradeDirection(metadata["direction"])
                
                # Set position context
                self.context.in_position = True
                self.context.entry_price = metadata["entry_price"]
                self.context.stop_loss = metadata["stop_loss"]
                self.context.target_price = metadata["target"]
                self.context.entry_time = candle.timestamp
                self.context.direction = direction
                self.context.entry_pattern = CandlePattern(metadata["pattern"])
                self.context.trades_today += 1
                
                signal_type = SignalType.BUY if direction == TradeDirection.BULLISH else SignalType.SELL
                
                signal = Signal(
                    signal_type=signal_type,
                    symbol=self.symbol,
                    price=metadata["entry_price"],
                    timestamp=candle.timestamp,
                    metadata=metadata
                )
                
                self.prev_candle = candle
                return signal
        
        self.prev_candle = candle
        return None
    
    def set_dual_index_state(self, nifty_at_resistance: bool = False, 
                             banknifty_at_resistance: bool = False,
                             nifty_at_support: bool = False,
                             banknifty_at_support: bool = False):
        """
        Set dual-index state for confirmation filter.
        Called externally when index levels are updated.
        """
        if self.context:
            self.context.nifty_at_resistance = nifty_at_resistance
            self.context.banknifty_at_resistance = banknifty_at_resistance
            self.context.nifty_at_support = nifty_at_support
            self.context.banknifty_at_support = banknifty_at_support


def create_ema_scalping_strategy(symbol: str = "", config: EMAScalpingConfig = None) -> EMAScalpingStrategy:
    """Factory function to create EMA Scalping Strategy."""
    return EMAScalpingStrategy(config=config or EMAScalpingConfig(), symbol=symbol)
