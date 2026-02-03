"""
Intraday Option Buying Momentum Strategy (Smart Money Flow Confirmation)

A Price Action + Open Interest based strategy for option buying.
NO indicators (EMA, RSI, VWAP) - purely price action and OI analysis.

Key Components:
1. Market Control Check - First candle low = Day low (bulls in control)
2. Candle Expansion - Today's green candles larger than yesterday's
3. PDH Breakout - Price above Previous Day High by 9:30-9:35 AM
4. OI Confirmation - Increasing OI with rising price (smart money)
5. Entry after 10:15 AM on strong breakout candle
6. Dynamic exit on momentum reversal (big red candles) or trailing SL
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta, timezone
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any
from collections import deque

from app.strategies.base import BaseStrategy, Signal, SignalType
from app.services.data_providers.base import Candle

logger = logging.getLogger(__name__)

# IST timezone offset (UTC+5:30)
IST_OFFSET = timedelta(hours=5, minutes=30)


class MarketPhase(Enum):
    """Market phases during the trading day."""
    PRE_MARKET = "pre_market"
    FIRST_HOUR = "first_hour"          # 9:15 - 10:15: Analysis + early entry on breakout
    ENTRY_WINDOW = "entry_window"       # 10:15 - 12:00: Normal entry window
    MOMENTUM_FADE = "momentum_fade"     # 12:00 - 15:30: Momentum typically fades
    CLOSED = "closed"


class BullishSetupStatus(Enum):
    """Status of bullish setup conditions."""
    NOT_CHECKED = "not_checked"
    CHECKING = "checking"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class TradeDirection(Enum):
    """Trade direction - CE for bullish, PE for bearish."""
    CE = "call"  # Bullish - buy calls
    PE = "put"   # Bearish - buy puts


@dataclass
class SetupScore:
    """Score a setup for ranking across multiple stocks."""
    symbol: str
    direction: TradeDirection
    timestamp: datetime
    
    # Scoring components (higher = better)
    breakout_strength: float = 0.0  # How far above/below PDH/PDL (%)
    volume_ratio: float = 0.0       # Volume vs average
    candle_strength: float = 0.0    # Body size ratio
    consecutive_candles: int = 0    # Candles above/below level
    market_control_score: float = 0.0  # How clean is the trend
    
    @property
    def total_score(self) -> float:
        """Calculate total setup score (0-100)."""
        score = 0.0
        # Breakout strength: 0.3% = 10pts, 0.5% = 20pts, 1% = 40pts
        score += min(self.breakout_strength * 40, 40)
        # Volume ratio: 1.5x = 10pts, 2x = 20pts
        score += min((self.volume_ratio - 1) * 20, 20)
        # Candle strength: 0.5 ratio = 5pts, 0.8 = 16pts
        score += self.candle_strength * 20
        # Consecutive candles: 2 = 10pts, 3+ = 20pts
        score += min(self.consecutive_candles * 10, 20)
        return score


@dataclass
class DayContext:
    """Stores context for the current trading day."""
    date: date
    first_candle: Optional[Candle] = None
    day_low: float = float('inf')
    day_high: float = 0.0
    pdh: float = 0.0  # Previous Day High
    pdl: float = 0.0  # Previous Day Low
    pdc: float = 0.0  # Previous Day Close
    
    # BULLISH Setup status
    market_control_confirmed: bool = False  # Condition 1: First candle low = Day low
    candle_expansion_confirmed: bool = False  # Condition 2
    pdh_breakout_confirmed: bool = False  # Condition 3
    pdh_breakout_time: Optional[datetime] = None
    oi_confirmation: bool = False  # Condition 4
    
    # BEARISH Setup status (PE trade conditions)
    bearish_market_control: bool = False  # First candle high = Day high (bears in control)
    bearish_candle_expansion: bool = False  # Red candles expanding
    pdl_breakdown_confirmed: bool = False  # Price below Previous Day Low
    pdl_breakdown_time: Optional[datetime] = None
    bearish_oi_confirmation: bool = False  # OI increasing with falling price
    
    # Candle tracking
    today_green_candle_sizes: List[float] = field(default_factory=list)
    today_red_candle_sizes: List[float] = field(default_factory=list)  # For bearish
    yesterday_candle_sizes: List[float] = field(default_factory=list)
    yesterday_red_candle_sizes: List[float] = field(default_factory=list)  # For bearish
    
    # Volume tracking for high win rate filter
    candle_volumes: List[int] = field(default_factory=list)
    consecutive_closes_above_pdh: int = 0  # Track candles closing above PDH
    consecutive_closes_below_pdl: int = 0  # Track candles closing below PDL (bearish)
    
    # OI tracking
    initial_oi: int = 0
    last_oi: int = 0
    oi_increase_count: int = 0
    price_at_oi_check: float = 0.0
    
    # Entry tracking (supports both CE and PE)
    entry_taken: bool = False
    entry_direction: Optional[TradeDirection] = None
    entry_price: float = 0.0
    entry_time: Optional[datetime] = None
    highest_since_entry: float = 0.0
    lowest_since_entry: float = float('inf')
    trailing_sl: float = 0.0
    
    # PE-specific tracking
    candles_since_entry: int = 0  # Count candles since entry
    red_candles_after_entry: int = 0  # Confirmation candles for PE
    max_profit_pct: float = 0.0  # Track max profit for breakeven exit
    
    def all_bullish_conditions_met(self) -> bool:
        """Check if all bullish (CE) pre-entry conditions are met."""
        return (
            self.market_control_confirmed and
            self.candle_expansion_confirmed and
            self.pdh_breakout_confirmed and
            self.oi_confirmation
        )
    
    def all_bearish_conditions_met(self) -> bool:
        """Check if all bearish (PE) pre-entry conditions are met."""
        return (
            self.bearish_market_control and
            self.bearish_candle_expansion and
            self.pdl_breakdown_confirmed and
            self.bearish_oi_confirmation
        )
    
    def all_conditions_met(self) -> bool:
        """Check if any direction has all conditions met."""
        return self.all_bullish_conditions_met() or self.all_bearish_conditions_met()
    
    def reset_for_new_day(self, new_date: date):
        """Reset context for a new trading day."""
        # Save yesterday's data
        self.pdh = self.day_high
        self.pdl = self.day_low
        self.pdc = self.first_candle.close if self.first_candle else 0.0
        self.yesterday_candle_sizes = self.today_green_candle_sizes.copy()
        self.yesterday_red_candle_sizes = self.today_red_candle_sizes.copy()
        
        # Reset for new day
        self.date = new_date
        self.first_candle = None
        self.day_low = float('inf')
        self.day_high = 0.0
        
        # Bullish conditions reset
        self.market_control_confirmed = False
        self.candle_expansion_confirmed = False
        self.pdh_breakout_confirmed = False
        self.pdh_breakout_time = None
        self.oi_confirmation = False
        
        # Bearish conditions reset
        self.bearish_market_control = False
        self.bearish_candle_expansion = False
        self.pdl_breakdown_confirmed = False
        self.pdl_breakdown_time = None
        self.bearish_oi_confirmation = False
        
        # Tracking reset
        self.today_green_candle_sizes = []
        self.today_red_candle_sizes = []
        self.candle_volumes = []
        self.consecutive_closes_above_pdh = 0
        self.consecutive_closes_below_pdl = 0
        self.initial_oi = 0
        self.last_oi = 0
        self.oi_increase_count = 0
        self.price_at_oi_check = 0.0
        
        # Entry reset
        self.entry_taken = False
        self.entry_direction = None
        self.entry_price = 0.0
        self.entry_time = None
        self.highest_since_entry = 0.0
        self.lowest_since_entry = float('inf')
        self.trailing_sl = 0.0
        self.candles_since_entry = 0
        self.red_candles_after_entry = 0
        self.max_profit_pct = 0.0


@dataclass
class IntradayMomentumConfig:
    """Configuration for the Intraday Momentum OI Strategy."""
    # Time windows
    market_open: time = field(default_factory=lambda: time(9, 15))
    first_hour_end: time = field(default_factory=lambda: time(10, 15))
    entry_window_start: time = field(default_factory=lambda: time(10, 15))
    entry_window_end: time = field(default_factory=lambda: time(12, 0))
    market_close: time = field(default_factory=lambda: time(15, 30))
    
    # PDH/PDL breakout timing
    pdh_breakout_deadline: time = field(default_factory=lambda: time(9, 35))
    pdl_breakdown_deadline: time = field(default_factory=lambda: time(9, 35))  # For bearish
    
    # Candle analysis
    min_candle_body_ratio: float = 0.5  # Body must be 50% of total range
    big_red_candle_multiplier: float = 2.0  # Red candle 2x avg to trigger CE exit
    big_green_candle_multiplier: float = 2.5  # Green candle 2.5x avg to trigger PE exit (relaxed - allow bounces)
    strong_green_candle_multiplier: float = 1.0  # Entry candle must be 1x avg
    
    # CE-specific exit settings (optimized: +56% improvement over baseline)
    ce_min_hold_candles: int = 8  # Hold CE for at least 8 candles before momentum exit (was 3)
    ce_require_ema_confirm: bool = True  # Only exit on big red if also below EMA9
    ce_use_ema_cross_exit: bool = False  # If True, use EMA9 cross as primary CE exit
    
    # PE-specific settings
    pe_min_hold_candles: int = 5  # Hold PE for at least 5 candles before momentum exit (was 3)
    pe_breakeven_exit_pct: float = 0.15  # Exit PE at +0.15% profit on first green reversal
    pe_min_continuation_candles: int = 1  # Need 1 red candle after entry to confirm direction
    pe_initial_sl_pct: float = 0.7  # Wider initial SL for PE (0.7% vs 0.5%)
    pe_trailing_activation_pct: float = 0.2  # Only start trailing after 0.2% profit
    
    # PE Volatility Filter - Only allow PE on volatile stocks
    pe_min_atr_pct: float = 2.5  # Minimum ATR% required for PE trades (volatile stocks only)
    pe_eligible_symbols: List[str] = field(default_factory=lambda: [
        # Stocks that historically show positive edge in PE trades (ATR > 2.5%)
        "ADANIENT", "ADANIGREEN", "ADANIPOWER", "SAIL", "RBLBANK", "HINDALCO",
        "BHARTIARTL", "IDEA", "MRPL", "DELHIVERY", "ETERNAL", "VOLTAS",
        "JINDALSTEL", "VEDL", "TATASTEEL", "JSWSTEEL", "BHEL", "NBCC",
        "NATIONALUM", "BANKINDIA", "BANKBARODA", "PNB", "CANBK", "IOB",
    ])
    
    # HIGH WIN RATE FILTERS
    min_breakout_pct: float = 0.3  # Price must be 0.3% above PDH (not just 1 tick)
    min_breakdown_pct: float = 0.3  # Price must be 0.3% below PDL for PE
    min_volume_multiplier: float = 1.5  # Entry candle volume must be 1.5x average
    max_gap_up_pct: float = 1.0  # Skip CE if gaps up more than 1% above PDH
    max_gap_down_pct: float = 1.0  # Skip PE if gaps down more than 1% below PDL
    min_candles_above_pdh: int = 2  # Wait for 2 candles closing above PDH
    min_candles_below_pdl: int = 2  # Wait for 2 candles closing below PDL
    
    # OI confirmation
    min_oi_increase_pct: float = 1.0  # Minimum 1% OI increase
    min_oi_checks_positive: int = 3  # At least 3 positive OI increases
    
    # Trailing stop
    trailing_sl_pct: float = 0.5  # 0.5% trailing stop from high
    initial_sl_pct: float = 1.0  # 1% initial stop from entry
    
    # Position sizing
    max_position_pct: float = 2.0  # Max 2% of capital per trade
    
    # Trade direction control
    enable_ce_trades: bool = True  # Enable bullish (CE) trades
    enable_pe_trades: bool = True  # Enable bearish (PE) trades
    
    # Ranking / Selection
    max_trades_per_day: int = 2  # Max trades across all symbols per day
    
    # OI confirmation
    min_oi_increase_pct: float = 1.0  # Minimum 1% OI increase
    min_oi_checks_positive: int = 3  # At least 3 positive OI increases
    
    # Trailing stop
    trailing_sl_pct: float = 0.5  # 0.5% trailing stop from high
    initial_sl_pct: float = 1.0  # 1% initial stop from entry
    
    # Position sizing
    max_position_pct: float = 2.0  # Max 2% of capital per trade


class IntradayMomentumOIStrategy(BaseStrategy):
    """
    Intraday Option Buying Momentum Strategy with Smart Money (OI) Confirmation.
    
    This strategy is designed for buying options (CE for bullish, PE for bearish)
    based on price action and open interest analysis of the underlying stock.
    
    Entry Conditions (ALL must be true):
    1. Market Control: First 5min candle low = Day low
    2. Candle Expansion: Today's green candles bigger than yesterday's
    3. PDH Breakout: Price > Previous Day High by 9:35 AM
    4. OI Confirmation: Increasing OI with rising price
    5. Time: After 10:15 AM
    6. Trigger: Strong breakout candle
    
    Exit Conditions (ANY triggers exit):
    1. Big red candle (momentum reversal)
    2. Trailing stop loss hit
    """
    
    def __init__(self, config: Optional[IntradayMomentumConfig] = None, broker=None, data_feed=None, symbol: str = ""):
        # Skip parent init if no broker/data_feed (for backtesting)
        if broker and data_feed:
            super().__init__(broker, data_feed, {})
        self.config = config or IntradayMomentumConfig()
        self.context: Optional[DayContext] = None
        self.candle_history: deque = deque(maxlen=100)
        self.avg_candle_size: float = 0.0
        self.position_active: bool = False
        self.symbol: str = symbol  # Symbol for PE eligibility check
        
        # For OI tracking (will be updated via separate OI feed)
        self.current_oi: int = 0
    
    # Abstract method implementations
    async def on_start(self):
        """Strategy startup - reset state."""
        self.context = None
        self.position_active = False
        logger.info(f"[{self.name}] Strategy started")
    
    async def on_stop(self):
        """Strategy shutdown."""
        logger.info(f"[{self.name}] Strategy stopped")
    
    async def on_tick(self, tick):
        """Process tick data - not used, we use candles."""
        pass
    
    async def on_order_update(self, order):
        """Process order updates."""
        logger.info(f"[{self.name}] Order update: {order}")
        
    @property
    def name(self) -> str:
        return "IntradayMomentumOI"
    
    @property
    def description(self) -> str:
        return "Intraday Option Buying with Price Action + OI Confirmation"
    
    def _get_market_phase(self, ts: datetime) -> MarketPhase:
        """Determine current market phase based on time (handles UTC to IST conversion)."""
        # Convert to IST if timestamp is timezone-aware UTC
        if ts.tzinfo is not None:
            # Convert UTC to IST by adding offset
            ist_time = (ts + IST_OFFSET).time()
        else:
            # Assume already in IST or local time
            ist_time = ts.time()
        
        if ist_time < self.config.market_open:
            return MarketPhase.PRE_MARKET
        elif ist_time < self.config.first_hour_end:
            return MarketPhase.FIRST_HOUR
        elif ist_time < self.config.entry_window_end:
            return MarketPhase.ENTRY_WINDOW
        elif ist_time < self.config.market_close:
            return MarketPhase.MOMENTUM_FADE
        else:
            return MarketPhase.CLOSED
    
    def _is_new_day(self, candle: Candle) -> bool:
        """Check if this candle is from a new trading day."""
        if self.context is None:
            return True
        return candle.timestamp.date() != self.context.date
    
    def _initialize_day(self, candle: Candle):
        """Initialize context for a new trading day."""
        if self.context is None:
            self.context = DayContext(date=candle.timestamp.date())
        else:
            self.context.reset_for_new_day(candle.timestamp.date())
        
        logger.info(f"[{self.name}] New day initialized: {candle.timestamp.date()}")
        logger.info(f"[{self.name}] PDH: {self.context.pdh:.2f}, PDL: {self.context.pdl:.2f}")
    
    def _update_day_stats(self, candle: Candle):
        """Update daily statistics with new candle."""
        # Update day high/low
        self.context.day_high = max(self.context.day_high, candle.high)
        self.context.day_low = min(self.context.day_low, candle.low)
        
        # Track first candle
        if self.context.first_candle is None:
            self.context.first_candle = candle
            logger.info(f"[{self.name}] First candle: O={candle.open:.2f} H={candle.high:.2f} "
                       f"L={candle.low:.2f} C={candle.close:.2f}")
        
        # Track green candle sizes (for bullish)
        if candle.close > candle.open:
            body_size = candle.close - candle.open
            self.context.today_green_candle_sizes.append(body_size)
        
        # Track red candle sizes (for bearish)
        if candle.close < candle.open:
            body_size = candle.open - candle.close
            self.context.today_red_candle_sizes.append(body_size)
        
        # Track volume for high win rate filter
        if candle.volume > 0:
            self.context.candle_volumes.append(candle.volume)
        
        # Track consecutive closes above PDH (bullish)
        if self.context.pdh > 0:
            if candle.close > self.context.pdh:
                self.context.consecutive_closes_above_pdh += 1
            else:
                self.context.consecutive_closes_above_pdh = 0
        
        # Track consecutive closes below PDL (bearish)
        if self.context.pdl > 0:
            if candle.close < self.context.pdl:
                self.context.consecutive_closes_below_pdl += 1
            else:
                self.context.consecutive_closes_below_pdl = 0
        
        # Update average candle size
        self.candle_history.append(candle)
        if len(self.candle_history) > 10:
            sizes = [abs(c.close - c.open) for c in self.candle_history]
            self.avg_candle_size = sum(sizes) / len(sizes)
    
    def _check_market_control(self) -> bool:
        """
        Condition 1 (BULLISH): Market Control Check
        First 5-min candle low must equal day low (bulls in control from start).
        """
        if self.context.first_candle is None:
            return False
        
        # Allow small tolerance (0.1%)
        tolerance = self.context.first_candle.low * 0.001
        is_confirmed = abs(self.context.first_candle.low - self.context.day_low) <= tolerance
        
        if is_confirmed and not self.context.market_control_confirmed:
            self.context.market_control_confirmed = True
            logger.info(f"[{self.name}] ✓ Bullish Market Control CONFIRMED - First candle low = Day low")
        elif not is_confirmed and self.context.market_control_confirmed:
            # Day low was breached
            self.context.market_control_confirmed = False
            logger.info(f"[{self.name}] ✗ Bullish Market Control LOST - Day low breached")
        
        return self.context.market_control_confirmed
    
    def _check_bearish_market_control(self) -> bool:
        """
        Condition 1 (BEARISH): Market Control Check
        First 5-min candle high must equal day high (bears in control from start).
        """
        if self.context.first_candle is None:
            return False
        
        # Allow small tolerance (0.1%)
        tolerance = self.context.first_candle.high * 0.001
        is_confirmed = abs(self.context.first_candle.high - self.context.day_high) <= tolerance
        
        if is_confirmed and not self.context.bearish_market_control:
            self.context.bearish_market_control = True
            logger.info(f"[{self.name}] ✓ Bearish Market Control CONFIRMED - First candle high = Day high")
        elif not is_confirmed and self.context.bearish_market_control:
            # Day high was breached
            self.context.bearish_market_control = False
            logger.info(f"[{self.name}] ✗ Bearish Market Control LOST - Day high breached")
        
        return self.context.bearish_market_control
    
    def _check_candle_expansion(self) -> bool:
        """
        Condition 2 (BULLISH): Candle Expansion Check
        Today's green candles must be larger than yesterday's candles.
        """
        if len(self.context.today_green_candle_sizes) < 3:
            return False
        
        if len(self.context.yesterday_candle_sizes) < 3:
            # First day, assume expansion if candles are decent size
            avg_today = sum(self.context.today_green_candle_sizes) / len(self.context.today_green_candle_sizes)
            is_confirmed = avg_today > 0  # Just need some green candles
        else:
            avg_today = sum(self.context.today_green_candle_sizes) / len(self.context.today_green_candle_sizes)
            avg_yesterday = sum(self.context.yesterday_candle_sizes) / len(self.context.yesterday_candle_sizes)
            is_confirmed = avg_today > avg_yesterday * 1.1  # 10% larger
        
        if is_confirmed and not self.context.candle_expansion_confirmed:
            self.context.candle_expansion_confirmed = True
            logger.info(f"[{self.name}] ✓ Bullish Candle Expansion CONFIRMED - Aggressive buying")
        
        return self.context.candle_expansion_confirmed
    
    def _check_bearish_candle_expansion(self) -> bool:
        """
        Condition 2 (BEARISH): Candle Expansion Check
        Today's red candles must be larger than yesterday's candles.
        """
        if len(self.context.today_red_candle_sizes) < 3:
            return False
        
        if len(self.context.yesterday_red_candle_sizes) < 3:
            # First day, assume expansion if candles are decent size
            avg_today = sum(self.context.today_red_candle_sizes) / len(self.context.today_red_candle_sizes)
            is_confirmed = avg_today > 0  # Just need some red candles
        else:
            avg_today = sum(self.context.today_red_candle_sizes) / len(self.context.today_red_candle_sizes)
            avg_yesterday = sum(self.context.yesterday_red_candle_sizes) / len(self.context.yesterday_red_candle_sizes)
            is_confirmed = avg_today > avg_yesterday * 1.1  # 10% larger
        
        if is_confirmed and not self.context.bearish_candle_expansion:
            self.context.bearish_candle_expansion = True
            logger.info(f"[{self.name}] ✓ Bearish Candle Expansion CONFIRMED - Aggressive selling")
        
        return self.context.bearish_candle_expansion
    
    def _check_pdh_breakout(self, candle: Candle) -> bool:
        """
        Condition 3 (BULLISH): PDH Breakout Check
        Price must be above Previous Day High by 9:30-9:35 AM.
        """
        if self.context.pdh_breakout_confirmed:
            return True
        
        if self.context.pdh <= 0:
            # No previous day data yet - for backtesting, use first candle open as reference
            if self.context.first_candle:
                # Use opening price + 0.3% as pseudo-PDH
                self.context.pdh = self.context.first_candle.open * 1.003
                logger.debug(f"[{self.name}] Using pseudo-PDH: {self.context.pdh:.2f} (first candle open + 0.3%)")
            else:
                return False
        
        # Check if price is above PDH
        if candle.close > self.context.pdh:
            candle_time = candle.timestamp.time()
            
            # Check if breakout happened early enough
            if candle_time <= self.config.pdh_breakout_deadline:
                self.context.pdh_breakout_confirmed = True
                self.context.pdh_breakout_time = candle.timestamp
                logger.info(f"[{self.name}] PDH Breakout CONFIRMED at {candle_time} "
                           f"(Price: {candle.close:.2f} > PDH: {self.context.pdh:.2f})")
                return True
            elif candle_time <= time(10, 0):
                # Late breakout but still acceptable
                self.context.pdh_breakout_confirmed = True
                self.context.pdh_breakout_time = candle.timestamp
                logger.info(f"[{self.name}] PDH Breakout (late) at {candle_time}")
                return True
        
        return False
    
    def _check_pdl_breakdown(self, candle: Candle) -> bool:
        """
        Condition 3 (BEARISH): PDL Breakdown Check
        Price must be below Previous Day Low by 9:30-9:35 AM.
        """
        if self.context.pdl_breakdown_confirmed:
            return True
        
        if self.context.pdl <= 0:
            # No previous day data yet - for backtesting, use first candle open as reference
            if self.context.first_candle:
                # Use opening price - 0.3% as pseudo-PDL
                self.context.pdl = self.context.first_candle.open * 0.997
                logger.debug(f"[{self.name}] Using pseudo-PDL: {self.context.pdl:.2f} (first candle open - 0.3%)")
            else:
                return False
        
        # Check if price is below PDL
        if candle.close < self.context.pdl:
            candle_time = candle.timestamp.time()
            
            # Check if breakdown happened early enough
            if candle_time <= self.config.pdl_breakdown_deadline:
                self.context.pdl_breakdown_confirmed = True
                self.context.pdl_breakdown_time = candle.timestamp
                logger.info(f"[{self.name}] PDL Breakdown CONFIRMED at {candle_time} "
                           f"(Price: {candle.close:.2f} < PDL: {self.context.pdl:.2f})")
                return True
            elif candle_time <= time(10, 0):
                # Late breakdown but still acceptable
                self.context.pdl_breakdown_confirmed = True
                self.context.pdl_breakdown_time = candle.timestamp
                logger.info(f"[{self.name}] PDL Breakdown (late) at {candle_time}")
                return True
        
        return False
    
    def update_oi(self, oi: int, price: float):
        """
        Update Open Interest data (called from external OI feed).
        
        Args:
            oi: Current open interest
            price: Current price when OI was recorded
        """
        self.current_oi = oi
        
        if self.context is None:
            return
        
        # Initialize OI tracking
        if self.context.initial_oi == 0:
            self.context.initial_oi = oi
            self.context.last_oi = oi
            self.context.price_at_oi_check = price
            return
        
        # Check OI increase with price increase
        oi_change = oi - self.context.last_oi
        price_change = price - self.context.price_at_oi_check
        
        if oi_change > 0 and price_change > 0:
            self.context.oi_increase_count += 1
            logger.debug(f"[{self.name}] OI+Price increase #{self.context.oi_increase_count}: "
                        f"OI +{oi_change}, Price +{price_change:.2f}")
        
        self.context.last_oi = oi
        self.context.price_at_oi_check = price
    
    def _check_oi_confirmation(self) -> bool:
        """
        Condition 4 (BULLISH): OI Confirmation
        Open Interest must be increasing with rising price.
        """
        if self.context.oi_confirmation:
            return True
        
        if self.context.initial_oi == 0:
            # No OI data yet - for backtesting without OI, auto-confirm
            # In live trading, this would be required
            self.context.oi_confirmation = True  # Auto-confirm for backtest
            return True
        
        # Check total OI increase
        total_oi_change_pct = ((self.context.last_oi - self.context.initial_oi) / 
                               self.context.initial_oi * 100) if self.context.initial_oi > 0 else 0
        
        # Need minimum OI increase and multiple positive checks
        if (total_oi_change_pct >= self.config.min_oi_increase_pct and 
            self.context.oi_increase_count >= self.config.min_oi_checks_positive):
            self.context.oi_confirmation = True
            logger.info(f"[{self.name}] Bullish OI Confirmation CONFIRMED - "
                       f"OI +{total_oi_change_pct:.1f}%, {self.context.oi_increase_count} positive checks")
        
        return self.context.oi_confirmation
    
    def _check_bearish_oi_confirmation(self) -> bool:
        """
        Condition 4 (BEARISH): OI Confirmation
        Open Interest must be increasing with falling price (put writing / short buildup).
        """
        if self.context.bearish_oi_confirmation:
            return True
        
        if self.context.initial_oi == 0:
            # No OI data yet - for backtesting without OI, auto-confirm
            self.context.bearish_oi_confirmation = True
            return True
        
        # Check total OI increase (OI increasing while price falls = bearish)
        total_oi_change_pct = ((self.context.last_oi - self.context.initial_oi) / 
                               self.context.initial_oi * 100) if self.context.initial_oi > 0 else 0
        
        # For bearish, we want OI to increase while price falls
        # In backtest without OI, auto-confirm
        if total_oi_change_pct >= self.config.min_oi_increase_pct:
            self.context.bearish_oi_confirmation = True
            logger.info(f"[{self.name}] Bearish OI Confirmation CONFIRMED - OI +{total_oi_change_pct:.1f}%")
        
        return self.context.bearish_oi_confirmation
    
    def _is_strong_breakout_candle(self, candle: Candle) -> bool:
        """
        Check if candle qualifies as a strong BULLISH breakout candle.
        - Must be green (close > open)
        - Body must be large (> min_candle_body_ratio of total range)
        - Must be larger than average (or decent size if no avg yet)
        """
        if candle.close <= candle.open:
            return False
        
        body = candle.close - candle.open
        total_range = candle.high - candle.low
        
        if total_range == 0:
            return False
        
        # Check body ratio (relaxed from 0.6 to 0.5)
        body_ratio = body / total_range
        if body_ratio < 0.5:  # Relaxed requirement
            return False
        
        # Check if larger than average (if we have average)
        if self.avg_candle_size > 0:
            # Relaxed from 1.2x to 1.0x (just needs to be above average)
            if body < self.avg_candle_size:
                return False
        
        return True
    
    def _is_strong_breakdown_candle(self, candle: Candle) -> bool:
        """
        Check if candle qualifies as a strong BEARISH breakdown candle.
        - Must be red (close < open)
        - Body must be large (> min_candle_body_ratio of total range)
        - Must be larger than average (or decent size if no avg yet)
        """
        if candle.close >= candle.open:
            return False
        
        body = candle.open - candle.close
        total_range = candle.high - candle.low
        
        if total_range == 0:
            return False
        
        # Check body ratio
        body_ratio = body / total_range
        if body_ratio < 0.5:
            return False
        
        # Check if larger than average
        if self.avg_candle_size > 0:
            if body < self.avg_candle_size:
                return False
        
        return True
    
    def _calculate_ema9(self) -> float:
        """Calculate 9-period EMA from recent candle history."""
        if len(self.candle_history) < 9:
            return 0.0
        
        closes = [c.close for c in list(self.candle_history)[-20:]]  # Use last 20 candles max
        multiplier = 2 / (9 + 1)  # EMA multiplier
        
        # Start with SMA of first 9
        ema = sum(closes[:9]) / 9
        
        # Apply EMA formula for remaining
        for close in closes[9:]:
            ema = (close - ema) * multiplier + ema
        
        return ema
    
    def _is_big_red_candle(self, candle: Candle) -> bool:
        """
        Check if candle is a big red candle (momentum reversal signal for CE exit).
        """
        if candle.close >= candle.open:
            return False
        
        body = candle.open - candle.close
        
        if self.avg_candle_size > 0:
            return body >= self.avg_candle_size * self.config.big_red_candle_multiplier
        
        return False
    
    def _is_big_green_candle(self, candle: Candle) -> bool:
        """
        Check if candle is a big green candle (momentum reversal signal for PE exit).
        """
        if candle.close <= candle.open:
            return False
        
        body = candle.close - candle.open
        
        if self.avg_candle_size > 0:
            return body >= self.avg_candle_size * self.config.big_green_candle_multiplier
        
        return False
    
    def _calculate_setup_score(self, candle: Candle, direction: TradeDirection) -> SetupScore:
        """
        Calculate a score for ranking setups across multiple stocks.
        Higher score = better setup quality.
        """
        score = SetupScore(
            symbol="",  # Will be set by caller
            direction=direction,
            timestamp=candle.timestamp,
        )
        
        if direction == TradeDirection.CE:
            # Bullish setup scoring
            if self.context.pdh > 0:
                score.breakout_strength = (candle.close - self.context.pdh) / self.context.pdh * 100
            score.consecutive_candles = self.context.consecutive_closes_above_pdh
        else:
            # Bearish setup scoring
            if self.context.pdl > 0:
                score.breakout_strength = (self.context.pdl - candle.close) / self.context.pdl * 100
            score.consecutive_candles = self.context.consecutive_closes_below_pdl
        
        # Volume ratio
        if len(self.context.candle_volumes) >= 5 and candle.volume > 0:
            avg_volume = sum(self.context.candle_volumes[-10:]) / min(len(self.context.candle_volumes), 10)
            if avg_volume > 0:
                score.volume_ratio = candle.volume / avg_volume
        
        # Candle strength (body ratio)
        total_range = candle.high - candle.low
        if total_range > 0:
            body = abs(candle.close - candle.open)
            score.candle_strength = body / total_range
        
        # Market control score
        if direction == TradeDirection.CE:
            score.market_control_score = 1.0 if self.context.market_control_confirmed else 0.0
        else:
            score.market_control_score = 1.0 if self.context.bearish_market_control else 0.0
        
        return score
    
    def _check_ce_entry_conditions(self, candle: Candle) -> Tuple[bool, str, Optional[SetupScore]]:
        """
        Check all BULLISH (CE) entry conditions with HIGH WIN RATE FILTERS.
        Returns (should_enter, reason, setup_score).
        
        Entry requires:
        - CDH + PDH breakout
        - Price at least 0.3% above PDH (not just 1 tick)
        - Volume surge (1.5x average)
        - 2+ consecutive candles above PDH
        - No excessive gap up (>1% above PDH at open)
        """
        if not self.config.enable_ce_trades:
            return False, "CE trades disabled", None
            
        phase = self._get_market_phase(candle.timestamp)
        
        # No entries before market open or after momentum fade
        if phase == MarketPhase.PRE_MARKET:
            return False, "Pre-market", None
        if phase == MarketPhase.MOMENTUM_FADE or phase == MarketPhase.CLOSED:
            return False, "After entry window (momentum fade)", None
        
        # Already have a position
        if self.context.entry_taken:
            return False, "Position already taken today", None
        
        # Check all pre-conditions
        if not self.context.market_control_confirmed:
            return False, "Bullish market control not confirmed", None
        
        if not self.context.candle_expansion_confirmed:
            return False, "Bullish candle expansion not confirmed", None
        
        if not self._check_oi_confirmation():
            return False, "OI confirmation not met", None
        
        pdh = self.context.pdh
        if pdh <= 0:
            return False, "No PDH available", None
        
        # ===== HIGH WIN RATE FILTER 1: No excessive gap up =====
        if self.context.first_candle:
            gap_up_pct = (self.context.first_candle.open - pdh) / pdh * 100
            if gap_up_pct > self.config.max_gap_up_pct:
                return False, f"Gap up too large ({gap_up_pct:.2f}% > {self.config.max_gap_up_pct}%)", None
        
        # ===== HIGH WIN RATE FILTER 2: Minimum breakout % above PDH =====
        breakout_pct = (candle.close - pdh) / pdh * 100
        if breakout_pct < self.config.min_breakout_pct:
            return False, f"Breakout too weak ({breakout_pct:.2f}% < {self.config.min_breakout_pct}%)", None
        
        # ===== HIGH WIN RATE FILTER 3: Consecutive closes above PDH =====
        if self.context.consecutive_closes_above_pdh < self.config.min_candles_above_pdh:
            return False, f"Only {self.context.consecutive_closes_above_pdh} candles above PDH (need {self.config.min_candles_above_pdh})", None
        
        # ===== HIGH WIN RATE FILTER 4: Volume surge =====
        if len(self.context.candle_volumes) >= 5 and candle.volume > 0:
            avg_volume = sum(self.context.candle_volumes[-10:]) / min(len(self.context.candle_volumes), 10)
            if avg_volume > 0:
                volume_ratio = candle.volume / avg_volume
                if volume_ratio < self.config.min_volume_multiplier:
                    return False, f"Volume too low ({volume_ratio:.2f}x < {self.config.min_volume_multiplier}x)", None
        
        # KEY CONDITION: Candle must close above CDH (new high)
        cdh = self.context.day_high
        closes_above_cdh = candle.close > cdh
        
        # For early entry (first hour), require close above BOTH CDH and PDH
        if phase == MarketPhase.FIRST_HOUR:
            if not closes_above_cdh:
                return False, f"Close {candle.close:.2f} not above CDH {cdh:.2f}", None
            if self._is_strong_breakout_candle(candle):
                score = self._calculate_setup_score(candle, TradeDirection.CE)
                return True, f"CE EARLY ENTRY: Strong breakout +{breakout_pct:.2f}% above PDH", score
            return False, "Not a strong breakout candle", None
        
        # Normal entry window
        if not self._is_strong_breakout_candle(candle):
            return False, "Not a strong breakout candle", None
        
        score = self._calculate_setup_score(candle, TradeDirection.CE)
        return True, f"CE Entry: Strong breakout +{breakout_pct:.2f}% above PDH", score
    
    def _check_pe_entry_conditions(self, candle: Candle) -> Tuple[bool, str, Optional[SetupScore]]:
        """
        Check all BEARISH (PE) entry conditions with HIGH WIN RATE FILTERS.
        Returns (should_enter, reason, setup_score).
        
        Entry requires:
        - Symbol must be PE-eligible (volatile stock)
        - CDL + PDL breakdown
        - Price at least 0.3% below PDL (not just 1 tick)
        - Volume surge (1.5x average)
        - 2+ consecutive candles below PDL
        - No excessive gap down (>1% below PDL at open)
        """
        if not self.config.enable_pe_trades:
            return False, "PE trades disabled", None
        
        # ===== VOLATILITY FILTER: Check if symbol is PE-eligible =====
        if self.symbol and self.config.pe_eligible_symbols:
            if self.symbol not in self.config.pe_eligible_symbols:
                return False, f"Symbol {self.symbol} not PE-eligible (volatility filter)", None
            
        phase = self._get_market_phase(candle.timestamp)
        
        # No entries before market open or after momentum fade
        if phase == MarketPhase.PRE_MARKET:
            return False, "Pre-market", None
        if phase == MarketPhase.MOMENTUM_FADE or phase == MarketPhase.CLOSED:
            return False, "After entry window (momentum fade)", None
        
        # Already have a position
        if self.context.entry_taken:
            return False, "Position already taken today", None
        
        # Check all bearish pre-conditions
        if not self.context.bearish_market_control:
            return False, "Bearish market control not confirmed", None
        
        if not self.context.bearish_candle_expansion:
            return False, "Bearish candle expansion not confirmed", None
        
        if not self._check_bearish_oi_confirmation():
            return False, "Bearish OI confirmation not met", None
        
        pdl = self.context.pdl
        if pdl <= 0:
            return False, "No PDL available", None
        
        # ===== HIGH WIN RATE FILTER 1: No excessive gap down =====
        if self.context.first_candle:
            gap_down_pct = (pdl - self.context.first_candle.open) / pdl * 100
            if gap_down_pct > self.config.max_gap_down_pct:
                return False, f"Gap down too large ({gap_down_pct:.2f}% > {self.config.max_gap_down_pct}%)", None
        
        # ===== HIGH WIN RATE FILTER 2: Minimum breakdown % below PDL =====
        breakdown_pct = (pdl - candle.close) / pdl * 100
        if breakdown_pct < self.config.min_breakdown_pct:
            return False, f"Breakdown too weak ({breakdown_pct:.2f}% < {self.config.min_breakdown_pct}%)", None
        
        # ===== HIGH WIN RATE FILTER 3: Consecutive closes below PDL =====
        if self.context.consecutive_closes_below_pdl < self.config.min_candles_below_pdl:
            return False, f"Only {self.context.consecutive_closes_below_pdl} candles below PDL (need {self.config.min_candles_below_pdl})", None
        
        # ===== HIGH WIN RATE FILTER 4: Volume surge =====
        if len(self.context.candle_volumes) >= 5 and candle.volume > 0:
            avg_volume = sum(self.context.candle_volumes[-10:]) / min(len(self.context.candle_volumes), 10)
            if avg_volume > 0:
                volume_ratio = candle.volume / avg_volume
                if volume_ratio < self.config.min_volume_multiplier:
                    return False, f"Volume too low ({volume_ratio:.2f}x < {self.config.min_volume_multiplier}x)", None
        
        # KEY CONDITION: Candle must close below CDL (new low)
        cdl = self.context.day_low
        closes_below_cdl = candle.close < cdl
        
        # For early entry (first hour), require close below BOTH CDL and PDL
        if phase == MarketPhase.FIRST_HOUR:
            if not closes_below_cdl:
                return False, f"Close {candle.close:.2f} not below CDL {cdl:.2f}", None
            if self._is_strong_breakdown_candle(candle):
                score = self._calculate_setup_score(candle, TradeDirection.PE)
                return True, f"PE EARLY ENTRY: Strong breakdown -{breakdown_pct:.2f}% below PDL", score
            return False, "Not a strong breakdown candle", None
        
        # Normal entry window
        if not self._is_strong_breakdown_candle(candle):
            return False, "Not a strong breakdown candle", None
        
        score = self._calculate_setup_score(candle, TradeDirection.PE)
        return True, f"PE Entry: Strong breakdown -{breakdown_pct:.2f}% below PDL", score
    
    def _check_entry_conditions(self, candle: Candle) -> Tuple[bool, str, Optional[TradeDirection], Optional[SetupScore]]:
        """
        Check both CE and PE entry conditions.
        Returns (should_enter, reason, direction, setup_score).
        """
        # Check CE (bullish) first
        ce_enter, ce_reason, ce_score = self._check_ce_entry_conditions(candle)
        if ce_enter:
            return True, ce_reason, TradeDirection.CE, ce_score
        
        # Check PE (bearish)
        pe_enter, pe_reason, pe_score = self._check_pe_entry_conditions(candle)
        if pe_enter:
            return True, pe_reason, TradeDirection.PE, pe_score
        
        # Neither direction has a valid entry
        return False, f"CE: {ce_reason}, PE: {pe_reason}", None, None
    
    def _check_exit_conditions(self, candle: Candle) -> Tuple[bool, str]:
        """
        Check exit conditions for active position (both CE and PE).
        Returns (should_exit, reason).
        """
        if not self.context.entry_taken:
            return False, "No position"
        
        direction = self.context.entry_direction
        
        if direction == TradeDirection.CE:
            # ===== CE (BULLISH) EXIT CONDITIONS =====
            # Increment candle counter
            self.context.candles_since_entry += 1
            
            # Update highest since entry
            self.context.highest_since_entry = max(self.context.highest_since_entry, candle.high)
            
            # Update trailing stop (for CE, SL is below entry)
            new_trailing_sl = self.context.highest_since_entry * (1 - self.config.trailing_sl_pct / 100)
            self.context.trailing_sl = max(self.context.trailing_sl, new_trailing_sl)
            
            # Exit Condition 1: Trailing stop hit (check first - always active)
            if candle.low <= self.context.trailing_sl:
                return True, f"CE Exit: Trailing SL hit at {self.context.trailing_sl:.2f}"
            
            # Check minimum hold period
            if self.context.candles_since_entry < self.config.ce_min_hold_candles:
                return False, "Hold position (min hold not met)"
            
            # Exit Condition 2a: EMA cross exit (if enabled)
            if self.config.ce_use_ema_cross_exit:
                # Calculate EMA9 for exit
                if len(self.candle_history) >= 9:
                    ema9 = self._calculate_ema9()
                    if candle.close < ema9:
                        return True, f"CE Exit: Price closed below EMA9 ({ema9:.2f})"
            
            # Exit Condition 2b: Big red candle (momentum reversal)
            if self._is_big_red_candle(candle):
                # If EMA confirmation required, check that price is also below EMA
                if self.config.ce_require_ema_confirm:
                    if len(self.candle_history) >= 9:
                        ema9 = self._calculate_ema9()
                        if candle.close < ema9:
                            return True, "CE Exit: Big red candle + below EMA9"
                        # Big red but still above EMA - don't exit
                        return False, "Hold (big red but above EMA)"
                else:
                    return True, "CE Exit: Momentum reversal - Big red candle"
        
        else:  # PE (BEARISH)
            # ===== PE (BEARISH) EXIT CONDITIONS =====
            # Increment candle counter
            self.context.candles_since_entry += 1
            
            # Track red candles for confirmation
            if candle.close < candle.open:
                self.context.red_candles_after_entry += 1
            
            # Update lowest since entry
            self.context.lowest_since_entry = min(self.context.lowest_since_entry, candle.low)
            
            # Calculate current profit
            current_profit_pct = (self.context.entry_price - candle.close) / self.context.entry_price * 100
            self.context.max_profit_pct = max(self.context.max_profit_pct, current_profit_pct)
            
            # Initialize trailing SL at wider level for PE
            if self.context.trailing_sl == 0:
                self.context.trailing_sl = self.context.entry_price * (1 + self.config.pe_initial_sl_pct / 100)
            
            # Only trail SL AFTER we have profit (delayed trailing)
            if self.context.max_profit_pct >= self.config.pe_trailing_activation_pct:
                new_trailing_sl = self.context.lowest_since_entry * (1 + self.config.trailing_sl_pct / 100)
                self.context.trailing_sl = min(self.context.trailing_sl, new_trailing_sl)
            
            # Exit Condition 1: Trailing stop hit (price goes UP past SL)
            if candle.high >= self.context.trailing_sl:
                return True, f"PE Exit: Trailing SL hit at {self.context.trailing_sl:.2f}"
            
            # Exit Condition 2: Breakeven exit - if we had good profit and now reversing significantly
            if (self.context.max_profit_pct >= 0.3 and  # Had at least 0.3% profit
                current_profit_pct < self.context.max_profit_pct * 0.2):  # Lost 80% of max profit
                return True, f"PE Exit: Breakeven protection (max: +{self.context.max_profit_pct:.2f}%, now: +{current_profit_pct:.2f}%)"
            
            # Exit Condition 3: Big green candle (momentum reversal) - only after minimum hold
            if self.context.candles_since_entry >= self.config.pe_min_hold_candles:
                if self._is_big_green_candle(candle):
                    return True, "PE Exit: Momentum reversal - Big green candle"
        
        # Exit Condition 3: End of day (both directions)
        # Convert to IST for time check
        if candle.timestamp.tzinfo is not None:
            ist_time = (candle.timestamp + IST_OFFSET).time()
        else:
            ist_time = candle.timestamp.time()
            
        if ist_time >= time(15, 15):
            return True, f"{direction.name} Exit: End of day"
        
        return False, "Hold position"
    
    def on_candle(self, candle: Candle, instrument_id: int = None) -> Optional[Signal]:
        """
        Process a new candle and generate trading signals.
        Supports both CE (bullish) and PE (bearish) trades.
        
        Args:
            candle: The new 5-minute candle
            instrument_id: Optional instrument identifier
            
        Returns:
            Signal if entry/exit triggered, None otherwise
        """
        # Check for new day
        if self._is_new_day(candle):
            self._initialize_day(candle)
            self.position_active = False
        
        # Update daily statistics
        self._update_day_stats(candle)
        
        # Get current phase
        phase = self._get_market_phase(candle.timestamp)
        
        # Check exit first if we have a position
        if self.position_active:
            should_exit, reason = self._check_exit_conditions(candle)
            if should_exit:
                self.position_active = False
                direction = self.context.entry_direction
                
                # Calculate P&L based on direction
                if direction == TradeDirection.CE:
                    pnl_pct = ((candle.close - self.context.entry_price) / self.context.entry_price * 100)
                else:  # PE - profit when price goes DOWN
                    pnl_pct = ((self.context.entry_price - candle.close) / self.context.entry_price * 100)
                
                logger.info(f"[{self.name}] {direction.name} EXIT @ {candle.close:.2f} - {reason} "
                           f"(Entry: {self.context.entry_price:.2f}, P&L: {pnl_pct:+.2f}%)")
                return Signal(
                    signal_type=SignalType.EXIT,
                    symbol=str(instrument_id) if instrument_id else "UNKNOWN",
                    price=candle.close,
                    timestamp=candle.timestamp,
                    strength=1.0,
                    metadata={
                        "reason": reason,
                        "direction": direction.name,
                        "entry_price": self.context.entry_price,
                        "pnl_pct": pnl_pct,
                        "highest": self.context.highest_since_entry,
                        "lowest": self.context.lowest_since_entry,
                        "trailing_sl": self.context.trailing_sl,
                    }
                )
            return None
        
        # During first hour: Analyze conditions AND check for early breakout entry
        if phase == MarketPhase.FIRST_HOUR:
            # Check BULLISH conditions
            self._check_market_control()
            self._check_candle_expansion()
            self._check_oi_confirmation()
            
            # Check BEARISH conditions
            self._check_bearish_market_control()
            self._check_bearish_candle_expansion()
            self._check_bearish_oi_confirmation()
            
            # Log setup status periodically
            if candle.timestamp.minute % 15 == 0:
                logger.info(f"[{self.name}] Setup Status @ {candle.timestamp.time()}: "
                           f"Bullish: MC={self.context.market_control_confirmed} CE={self.context.candle_expansion_confirmed} | "
                           f"Bearish: MC={self.context.bearish_market_control} CE={self.context.bearish_candle_expansion}")
            
            # Check for EARLY ENTRY (both CE and PE)
            should_enter, reason, direction, score = self._check_entry_conditions(candle)
            if should_enter and direction:
                self.position_active = True
                self.context.entry_taken = True
                self.context.entry_direction = direction
                self.context.entry_price = candle.close
                self.context.entry_time = candle.timestamp
                self.context.highest_since_entry = candle.high
                self.context.lowest_since_entry = candle.low
                
                # Set initial SL based on direction
                if direction == TradeDirection.CE:
                    self.context.trailing_sl = candle.close * (1 - self.config.initial_sl_pct / 100)
                else:  # PE
                    self.context.trailing_sl = candle.close * (1 + self.config.initial_sl_pct / 100)
                
                logger.info(f"[{self.name}] {direction.name} EARLY ENTRY @ {candle.close:.2f} - {reason}")
                logger.info(f"[{self.name}] Initial SL: {self.context.trailing_sl:.2f}, Score: {score.total_score:.1f}")
                
                signal_type = SignalType.BUY if direction == TradeDirection.CE else SignalType.SELL
                return Signal(
                    signal_type=signal_type,
                    symbol=str(instrument_id) if instrument_id else "UNKNOWN",
                    price=candle.close,
                    timestamp=candle.timestamp,
                    strength=score.total_score / 100 if score else 0.5,
                    metadata={
                        "reason": reason,
                        "direction": direction.name,
                        "cdh": self.context.day_high,
                        "cdl": self.context.day_low,
                        "pdh": self.context.pdh,
                        "pdl": self.context.pdl,
                        "score": score.total_score if score else 0,
                        "early_entry": True,
                    }
                )
            return None
        
        # Check entry conditions during entry window
        if phase == MarketPhase.ENTRY_WINDOW:
            # Continue checking conditions
            self._check_market_control()
            self._check_candle_expansion()
            self._check_pdh_breakout(candle)
            self._check_bearish_market_control()
            self._check_bearish_candle_expansion()
            self._check_pdl_breakdown(candle)
            
            should_enter, reason, direction, score = self._check_entry_conditions(candle)
            if should_enter and direction:
                self.position_active = True
                self.context.entry_taken = True
                self.context.entry_direction = direction
                self.context.entry_price = candle.close
                self.context.entry_time = candle.timestamp
                self.context.highest_since_entry = candle.high
                self.context.lowest_since_entry = candle.low
                
                # Set initial SL based on direction
                if direction == TradeDirection.CE:
                    self.context.trailing_sl = candle.close * (1 - self.config.initial_sl_pct / 100)
                else:  # PE
                    self.context.trailing_sl = candle.close * (1 + self.config.initial_sl_pct / 100)
                
                logger.info(f"[{self.name}] {direction.name} ENTRY @ {candle.close:.2f} - {reason}")
                logger.info(f"[{self.name}] Initial SL: {self.context.trailing_sl:.2f}, Score: {score.total_score:.1f}")
                
                signal_type = SignalType.BUY if direction == TradeDirection.CE else SignalType.SELL
                return Signal(
                    signal_type=signal_type,
                    symbol=str(instrument_id) if instrument_id else "UNKNOWN",
                    price=candle.close,
                    timestamp=candle.timestamp,
                    strength=score.total_score / 100 if score else 0.5,
                    metadata={
                        "reason": reason,
                        "direction": direction.name,
                        "pdh": self.context.pdh,
                        "pdl": self.context.pdl,
                        "score": score.total_score if score else 0,
                        "initial_sl": self.context.trailing_sl,
                    }
                )
        
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get current strategy status."""
        if self.context is None:
            return {"status": "not_initialized"}
        
        return {
            "date": str(self.context.date),
            "conditions": {
                "market_control": self.context.market_control_confirmed,
                "candle_expansion": self.context.candle_expansion_confirmed,
                "pdh_breakout": self.context.pdh_breakout_confirmed,
                "oi_confirmation": self.context.oi_confirmation,
                "all_met": self.context.all_conditions_met(),
            },
            "day_stats": {
                "day_high": self.context.day_high,
                "day_low": self.context.day_low,
                "pdh": self.context.pdh,
                "pdl": self.context.pdl,
            },
            "position": {
                "active": self.position_active,
                "entry_taken": self.context.entry_taken,
                "entry_price": self.context.entry_price,
                "entry_time": str(self.context.entry_time) if self.context.entry_time else None,
                "trailing_sl": self.context.trailing_sl,
                "highest": self.context.highest_since_entry,
            }
        }


# Convenience function to create strategy
def create_intraday_momentum_strategy(
    entry_start: str = "10:15",
    entry_end: str = "12:00",
    trailing_sl_pct: float = 0.5,
) -> IntradayMomentumOIStrategy:
    """
    Create an Intraday Momentum OI Strategy with custom parameters.
    
    Args:
        entry_start: Entry window start time (HH:MM)
        entry_end: Entry window end time (HH:MM)
        trailing_sl_pct: Trailing stop loss percentage
        
    Returns:
        Configured strategy instance
    """
    h, m = map(int, entry_start.split(":"))
    entry_start_time = time(h, m)
    
    h, m = map(int, entry_end.split(":"))
    entry_end_time = time(h, m)
    
    config = IntradayMomentumConfig(
        entry_window_start=entry_start_time,
        entry_window_end=entry_end_time,
        trailing_sl_pct=trailing_sl_pct,
    )
    
    return IntradayMomentumOIStrategy(config)
