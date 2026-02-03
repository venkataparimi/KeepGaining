#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sector Momentum Strategy

Identifies strong sectors at market open and trades stocks within those sectors.

Strategy Logic:
1. At market open (9:15-9:30 AM), rank all sector indices by:
   - Gap up/down from previous close
   - First 15-min candle strength (body %, high-low range)
   - Momentum (price vs 9 EMA)
   
2. Select top N strongest sectors for bullish trades (or weakest for bearish)

3. Within selected sectors, identify stocks with:
   - Strong alignment with sector direction
   - Good volume (above average)
   - Clear breakout/breakdown pattern

4. Entry: Buy CE/PE based on sector direction with tight stop loss
   Exit: 1:2 or 1:3 RR, or time-based exit
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, time, timedelta
from enum import Enum
import math
from collections import defaultdict


class SectorDirection(Enum):
    """Sector momentum direction."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass
class SectorConfig:
    """Configuration for sector momentum strategy."""
    # Sector selection
    min_gap_percent: float = 0.3  # Minimum gap % to consider sector strong
    min_candle_body_ratio: float = 0.5  # Min body to range ratio for strong candle
    top_sectors_count: int = 3  # Number of top sectors to trade
    
    # Stock selection within sector
    min_stock_volume_multiplier: float = 1.2  # Min volume vs 20-day avg
    min_stock_alignment: float = 0.7  # Min correlation with sector direction
    
    # Trade parameters
    entry_window_start: time = field(default_factory=lambda: time(9, 20))  # After initial volatility
    entry_window_end: time = field(default_factory=lambda: time(11, 30))  # First half of day
    max_trades_per_sector: int = 2  # Max concurrent trades per sector
    max_total_trades: int = 5  # Max total trades per day
    
    # Risk management
    risk_reward_ratio: float = 2.0  # Target 1:2 RR
    sl_buffer_percent: float = 0.2  # SL buffer below swing low
    max_sl_percent: float = 1.5  # Maximum SL % of entry price
    
    # Option selection
    use_itm_options: bool = True  # Prefer ITM options
    itm_strikes: int = 1  # How many strikes ITM
    
    # EMA settings
    fast_ema_period: int = 9
    slow_ema_period: int = 21


# Sector to Index mapping
SECTOR_INDEX_MAP = {
    "BANKING": "NIFTY BANK",
    "FINANCE": "NIFTY FIN SERVICE",
    "IT": "NIFTY IT",
    "AUTO": "NIFTY AUTO",
    "PHARMA": "NIFTY PHARMA",
    "METALS": "NIFTY METAL",
    "REALTY": "NIFTY REALTY",
    "POWER": "NIFTY ENERGY",  # Closest match
    "OIL_GAS": "NIFTY ENERGY",
    "FMCG": "NIFTY FMCG",
    "INFRASTRUCTURE": "NIFTY INFRA",
    # PSE is a mix - map to broad market
    "CAPITAL_GOODS": "NIFTY INFRA",
    "CEMENT": "NIFTY INFRA",
    "CONSUMER": "NIFTY FMCG",
    # No direct index for these
    "CHEMICALS": None,
    "MEDIA": None,
    "TELECOM": None,
    "LOGISTICS": None,
}

# Reverse mapping - Index to sectors it covers
INDEX_SECTOR_MAP = defaultdict(list)
for sector, index in SECTOR_INDEX_MAP.items():
    if index:
        INDEX_SECTOR_MAP[index].append(sector)


@dataclass
class SectorScore:
    """Score for a sector's momentum."""
    sector_name: str
    index_symbol: str
    direction: SectorDirection
    
    # Individual scores (0-100)
    gap_score: float = 0.0
    candle_strength_score: float = 0.0
    momentum_score: float = 0.0
    
    # Raw data
    gap_percent: float = 0.0
    candle_body_ratio: float = 0.0
    price_vs_ema: float = 0.0
    
    @property
    def total_score(self) -> float:
        """Calculate weighted total score."""
        return (
            self.gap_score * 0.4 +
            self.candle_strength_score * 0.3 +
            self.momentum_score * 0.3
        )
    
    def __str__(self) -> str:
        return f"{self.sector_name}: {self.total_score:.1f} ({self.direction.value})"


@dataclass
class StockSignal:
    """Trading signal for a stock in a strong sector."""
    symbol: str
    sector: str
    sector_index: str
    direction: SectorDirection
    
    entry_price: float
    sl_price: float
    target_price: float
    
    sector_score: float
    stock_alignment_score: float
    volume_score: float
    
    timestamp: datetime
    reason: str
    
    @property
    def total_score(self) -> float:
        """Overall signal quality."""
        return (
            self.sector_score * 0.4 +
            self.stock_alignment_score * 0.4 +
            self.volume_score * 0.2
        )


class SectorMomentumStrategy:
    """
    Sector momentum strategy implementation.
    
    1. Ranks sectors by morning momentum
    2. Selects stocks from top sectors
    3. Generates trade signals with defined RR
    """
    
    def __init__(self, config: SectorConfig = None):
        self.config = config or SectorConfig()
        self.sector_scores: Dict[str, SectorScore] = {}
        self.active_trades: Dict[str, Any] = {}
        self.trades_per_sector: Dict[str, int] = defaultdict(int)
        self.daily_trades: int = 0
        self.current_date: Optional[date] = None
        
        # Caches
        self._ema_cache: Dict[str, Dict[int, float]] = {}
        self._prev_close_cache: Dict[str, float] = {}
    
    def reset_for_new_day(self, trading_date: date):
        """Reset state for a new trading day."""
        if self.current_date != trading_date:
            self.sector_scores.clear()
            self.trades_per_sector.clear()
            self.daily_trades = 0
            self.current_date = trading_date
            self._prev_close_cache.clear()
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate EMA for given prices."""
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def score_sector(
        self,
        index_symbol: str,
        prev_close: float,
        open_price: float,
        first_candle_high: float,
        first_candle_low: float,
        first_candle_close: float,
        current_price: float,
        ema_9: float,
    ) -> SectorScore:
        """
        Score a sector based on morning momentum.
        
        Args:
            index_symbol: Sector index symbol
            prev_close: Previous day close
            open_price: Today's open
            first_candle_high: High of first 15-min candle
            first_candle_low: Low of first 15-min candle
            first_candle_close: Close of first 15-min candle
            current_price: Current price
            ema_9: 9-period EMA value
        """
        # Find sectors for this index
        sectors = INDEX_SECTOR_MAP.get(index_symbol, [])
        sector_name = sectors[0] if sectors else index_symbol
        
        # Calculate gap
        gap_percent = ((open_price - prev_close) / prev_close) * 100
        
        # Calculate first candle strength
        candle_range = first_candle_high - first_candle_low
        candle_body = abs(first_candle_close - open_price)
        candle_body_ratio = candle_body / candle_range if candle_range > 0 else 0
        
        # Determine direction from first candle
        is_bullish_candle = first_candle_close > open_price
        
        # Calculate momentum (price vs EMA)
        price_vs_ema = ((current_price - ema_9) / ema_9) * 100 if ema_9 > 0 else 0
        
        # Determine overall direction
        bullish_signals = sum([
            gap_percent > 0,
            is_bullish_candle,
            price_vs_ema > 0
        ])
        
        if bullish_signals >= 2:
            direction = SectorDirection.BULLISH
        elif bullish_signals <= 1:
            direction = SectorDirection.BEARISH
        else:
            direction = SectorDirection.NEUTRAL
        
        # Score components (0-100)
        # Gap score - higher gap = higher score
        gap_score = min(abs(gap_percent) * 20, 100)  # Cap at 5% gap
        
        # Candle strength score
        candle_strength_score = min(candle_body_ratio * 100, 100)
        if is_bullish_candle and direction == SectorDirection.BULLISH:
            candle_strength_score *= 1.2  # Bonus for alignment
        elif not is_bullish_candle and direction == SectorDirection.BEARISH:
            candle_strength_score *= 1.2
        candle_strength_score = min(candle_strength_score, 100)
        
        # Momentum score
        momentum_score = min(abs(price_vs_ema) * 50, 100)  # Cap at 2% deviation
        
        return SectorScore(
            sector_name=sector_name,
            index_symbol=index_symbol,
            direction=direction,
            gap_score=gap_score,
            candle_strength_score=candle_strength_score,
            momentum_score=momentum_score,
            gap_percent=gap_percent,
            candle_body_ratio=candle_body_ratio,
            price_vs_ema=price_vs_ema,
        )
    
    def rank_sectors(self, sector_scores: List[SectorScore]) -> Tuple[List[SectorScore], List[SectorScore]]:
        """
        Rank sectors and return top bullish and bearish sectors.
        
        Returns:
            Tuple of (top_bullish_sectors, top_bearish_sectors)
        """
        bullish = [s for s in sector_scores if s.direction == SectorDirection.BULLISH]
        bearish = [s for s in sector_scores if s.direction == SectorDirection.BEARISH]
        
        # Sort by total score descending
        bullish.sort(key=lambda x: x.total_score, reverse=True)
        bearish.sort(key=lambda x: x.total_score, reverse=True)
        
        return (
            bullish[:self.config.top_sectors_count],
            bearish[:self.config.top_sectors_count]
        )
    
    def score_stock(
        self,
        symbol: str,
        sector: str,
        sector_score: SectorScore,
        stock_open: float,
        stock_close: float,
        stock_high: float,
        stock_low: float,
        stock_volume: int,
        avg_volume: int,
        stock_ema_9: float,
    ) -> Optional[StockSignal]:
        """
        Score a stock within a sector and generate signal if strong enough.
        
        Args:
            symbol: Stock symbol
            sector: Stock's sector
            sector_score: Parent sector's score
            stock_open: Stock's open price
            stock_close: Stock's current close
            stock_high: Stock's high
            stock_low: Stock's low
            stock_volume: Current volume
            avg_volume: 20-day average volume
            stock_ema_9: Stock's 9 EMA
        """
        # Check trade limits
        if self.daily_trades >= self.config.max_total_trades:
            return None
        if self.trades_per_sector[sector] >= self.config.max_trades_per_sector:
            return None
        
        # Calculate stock direction alignment
        stock_gap_pct = ((stock_close - stock_open) / stock_open) * 100
        stock_vs_ema = ((stock_close - stock_ema_9) / stock_ema_9) * 100 if stock_ema_9 > 0 else 0
        
        # Check if stock aligns with sector direction
        if sector_score.direction == SectorDirection.BULLISH:
            alignment_score = 0
            if stock_close > stock_open:  # Green candle
                alignment_score += 40
            if stock_close > stock_ema_9:  # Above EMA
                alignment_score += 40
            if stock_gap_pct > 0:  # Gap up
                alignment_score += 20
        else:  # Bearish
            alignment_score = 0
            if stock_close < stock_open:  # Red candle
                alignment_score += 40
            if stock_close < stock_ema_9:  # Below EMA
                alignment_score += 40
            if stock_gap_pct < 0:  # Gap down
                alignment_score += 20
        
        # Check minimum alignment
        if alignment_score < self.config.min_stock_alignment * 100:
            return None
        
        # Volume score
        volume_ratio = stock_volume / avg_volume if avg_volume > 0 else 0
        if volume_ratio < self.config.min_stock_volume_multiplier:
            return None
        volume_score = min(volume_ratio * 50, 100)  # Cap at 2x volume
        
        # Calculate entry/SL/target
        if sector_score.direction == SectorDirection.BULLISH:
            # For CE - buy on pullback or breakout
            entry_price = stock_close
            sl_price = stock_low * (1 - self.config.sl_buffer_percent / 100)
            
            # Cap SL
            max_sl = entry_price * (1 - self.config.max_sl_percent / 100)
            sl_price = max(sl_price, max_sl)
            
            # Calculate target based on RR
            risk = entry_price - sl_price
            target_price = entry_price + (risk * self.config.risk_reward_ratio)
            
        else:  # Bearish
            # For PE - sell on bounce or breakdown
            entry_price = stock_close
            sl_price = stock_high * (1 + self.config.sl_buffer_percent / 100)
            
            # Cap SL
            max_sl = entry_price * (1 + self.config.max_sl_percent / 100)
            sl_price = min(sl_price, max_sl)
            
            # Calculate target based on RR
            risk = sl_price - entry_price
            target_price = entry_price - (risk * self.config.risk_reward_ratio)
        
        # Build reason string
        reasons = []
        if sector_score.gap_percent > 0:
            reasons.append(f"Sector gap +{sector_score.gap_percent:.2f}%")
        else:
            reasons.append(f"Sector gap {sector_score.gap_percent:.2f}%")
        reasons.append(f"Sector score: {sector_score.total_score:.1f}")
        reasons.append(f"Stock alignment: {alignment_score}%")
        reasons.append(f"Volume: {volume_ratio:.1f}x avg")
        
        return StockSignal(
            symbol=symbol,
            sector=sector,
            sector_index=sector_score.index_symbol,
            direction=sector_score.direction,
            entry_price=entry_price,
            sl_price=sl_price,
            target_price=target_price,
            sector_score=sector_score.total_score,
            stock_alignment_score=alignment_score,
            volume_score=volume_score,
            timestamp=datetime.now(),
            reason=" | ".join(reasons),
        )
    
    def should_enter_trade(self, signal: StockSignal, current_time: time) -> bool:
        """Check if we should enter a trade based on signal and time."""
        # Check time window
        if current_time < self.config.entry_window_start:
            return False
        if current_time > self.config.entry_window_end:
            return False
        
        # Check signal quality
        if signal.total_score < 50:  # Minimum score threshold
            return False
        
        return True
    
    def check_exit(
        self,
        entry_price: float,
        sl_price: float,
        target_price: float,
        current_price: float,
        current_high: float,
        current_low: float,
        direction: SectorDirection,
    ) -> Tuple[bool, str, float]:
        """
        Check if trade should be exited.
        
        Returns:
            Tuple of (should_exit, reason, exit_price)
        """
        if direction == SectorDirection.BULLISH:
            # Check SL
            if current_low <= sl_price:
                return True, "SL_HIT", sl_price
            # Check target
            if current_high >= target_price:
                return True, "TARGET_HIT", target_price
        else:  # Bearish
            # Check SL
            if current_high >= sl_price:
                return True, "SL_HIT", sl_price
            # Check target
            if current_low <= target_price:
                return True, "TARGET_HIT", target_price
        
        return False, "", current_price


def create_sector_momentum_strategy(config: SectorConfig = None) -> SectorMomentumStrategy:
    """Factory function to create sector momentum strategy."""
    return SectorMomentumStrategy(config)
