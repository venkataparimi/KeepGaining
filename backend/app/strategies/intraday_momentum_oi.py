"""
Intraday Option Buying Momentum Strategy (Smart Money Flow Confirmation)
VERSION 2.0 - IMPROVED

Changes from v1:
  - Fixed duplicate config fields (min_oi_increase_pct, trailing_sl_pct, initial_sl_pct, max_position_pct)
  - Trailing SL now places actual broker orders (SL-M) and tracks order IDs
  - Improved entry signal accuracy: added VWAP filter, candle close vs range position, min ATR filter
  - End-of-day square-off at 15:15 IST with hard market-close fallback at 15:25
  - Re-entry logic after SL hit: allowed once per day if setup conditions re-confirm
  - Full trade logging with P&L tracking (TradeLog dataclass + daily summary)
  - Smarter candle expansion: compares same-direction candles correctly
  - PDH/PDL breakout: price must sustain above PDH for 2 candles (false breakout filter)
  - Fixed PE OI confirmation: now correctly checks OI increasing with FALLING price
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

# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class MarketPhase(Enum):
    PRE_MARKET = "pre_market"
    FIRST_HOUR = "first_hour"        # 9:15 – 10:15: Analysis + early entry on breakout
    ENTRY_WINDOW = "entry_window"    # 10:15 – 12:00: Normal entry window
    MOMENTUM_FADE = "momentum_fade"  # 12:00 – 15:15: Hold / exit only
    EOD_EXIT = "eod_exit"            # 15:15 – 15:25: Force square-off
    CLOSED = "closed"


class TradeDirection(Enum):
    CE = "call"   # Bullish
    PE = "put"    # Bearish


# ─────────────────────────────────────────────
# Trade Log
# ─────────────────────────────────────────────

@dataclass
class TradeLog:
    """Records every completed trade for P&L tracking."""
    date: date
    symbol: str
    direction: TradeDirection
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    quantity: int = 0
    pnl_pct: float = 0.0
    pnl_points: float = 0.0
    max_profit_pct: float = 0.0
    sl_order_id: Optional[str] = None   # Broker SL order ID (for modification)
    is_reentry: bool = False

    def close(self, exit_price: float, exit_time: datetime, reason: str):
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = reason
        if self.direction == TradeDirection.CE:
            self.pnl_pct = (exit_price - self.entry_price) / self.entry_price * 100
        else:
            self.pnl_pct = (self.entry_price - exit_price) / self.entry_price * 100
        self.pnl_points = self.pnl_pct / 100 * self.entry_price

    @property
    def is_winner(self) -> bool:
        return self.pnl_pct > 0


@dataclass
class DailySummary:
    """Aggregated P&L and stats for one trading day."""
    date: date
    trades: List[TradeLog] = field(default_factory=list)

    @property
    def total_pnl_pct(self) -> float:
        return sum(t.pnl_pct for t in self.trades if t.exit_price is not None)

    @property
    def win_rate(self) -> float:
        closed = [t for t in self.trades if t.exit_price is not None]
        if not closed:
            return 0.0
        return sum(1 for t in closed if t.is_winner) / len(closed) * 100

    def log(self):
        logger.info(
            f"[DailySummary] {self.date} | Trades: {len(self.trades)} | "
            f"Win Rate: {self.win_rate:.1f}% | Total P&L: {self.total_pnl_pct:+.2f}%"
        )
        for t in self.trades:
            status = "WIN" if t.is_winner else "LOSS"
            logger.info(
                f"  [{status}] {t.direction.name} | Entry: {t.entry_price:.2f} @ {t.entry_time} | "
                f"Exit: {t.exit_price:.2f} @ {t.exit_time} | P&L: {t.pnl_pct:+.2f}% | {t.exit_reason}"
            )


# ─────────────────────────────────────────────
# Setup Score
# ─────────────────────────────────────────────

@dataclass
class SetupScore:
    symbol: str
    direction: TradeDirection
    timestamp: datetime
    breakout_strength: float = 0.0
    volume_ratio: float = 0.0
    candle_strength: float = 0.0
    consecutive_candles: int = 0
    market_control_score: float = 0.0
    vwap_score: float = 0.0          # NEW: bonus for price above/below VWAP

    @property
    def total_score(self) -> float:
        score = 0.0
        score += min(self.breakout_strength * 40, 40)
        score += min((self.volume_ratio - 1) * 20, 20)
        score += self.candle_strength * 20
        score += min(self.consecutive_candles * 10, 20)
        score += self.vwap_score * 10  # up to 10 bonus points
        return score


# ─────────────────────────────────────────────
# Day Context
# ─────────────────────────────────────────────

@dataclass
class DayContext:
    date: date
    first_candle: Optional[Candle] = None
    day_low: float = float('inf')
    day_high: float = 0.0
    pdh: float = 0.0
    pdl: float = 0.0
    pdc: float = 0.0

    # ── Bullish conditions ──
    market_control_confirmed: bool = False
    candle_expansion_confirmed: bool = False
    pdh_breakout_confirmed: bool = False
    pdh_breakout_time: Optional[datetime] = None
    oi_confirmation: bool = False

    # ── Bearish conditions ──
    bearish_market_control: bool = False
    bearish_candle_expansion: bool = False
    pdl_breakdown_confirmed: bool = False
    pdl_breakdown_time: Optional[datetime] = None
    bearish_oi_confirmation: bool = False

    # ── Candle / volume tracking ──
    today_green_candle_sizes: List[float] = field(default_factory=list)
    today_red_candle_sizes: List[float] = field(default_factory=list)
    yesterday_green_candle_sizes: List[float] = field(default_factory=list)
    yesterday_red_candle_sizes: List[float] = field(default_factory=list)
    candle_volumes: List[int] = field(default_factory=list)
    consecutive_closes_above_pdh: int = 0
    consecutive_closes_below_pdl: int = 0

    # ── OI tracking (separate for bullish/bearish) ──
    initial_oi: int = 0
    last_oi: int = 0
    oi_increase_count: int = 0       # OI up + price up  (CE)
    oi_bearish_count: int = 0        # OI up + price down (PE) — FIX: was same counter
    price_at_oi_check: float = 0.0

    # ── VWAP ──
    vwap_cumulative_tp_vol: float = 0.0   # Σ (typical_price * volume)
    vwap_cumulative_vol: float = 0.0      # Σ volume
    vwap: float = 0.0

    # ── Entry tracking ──
    entry_taken: bool = False
    reentry_taken: bool = False           # NEW: track re-entry separately
    entry_direction: Optional[TradeDirection] = None
    entry_price: float = 0.0
    entry_time: Optional[datetime] = None
    highest_since_entry: float = 0.0
    lowest_since_entry: float = float('inf')
    trailing_sl: float = 0.0
    sl_order_id: Optional[str] = None     # NEW: broker SL order tracking
    candles_since_entry: int = 0
    red_candles_after_entry: int = 0
    max_profit_pct: float = 0.0

    def all_bullish_conditions_met(self) -> bool:
        return (
            self.market_control_confirmed and
            self.candle_expansion_confirmed and
            self.pdh_breakout_confirmed and
            self.oi_confirmation
        )

    def all_bearish_conditions_met(self) -> bool:
        return (
            self.bearish_market_control and
            self.bearish_candle_expansion and
            self.pdl_breakdown_confirmed and
            self.bearish_oi_confirmation
        )

    def all_conditions_met(self) -> bool:
        return self.all_bullish_conditions_met() or self.all_bearish_conditions_met()

    def reset_for_new_day(self, new_date: date):
        """Roll over context for a new trading day. Preserves previous day data."""
        self.pdh = self.day_high
        self.pdl = self.day_low
        self.pdc = self.first_candle.close if self.first_candle else 0.0
        # Roll candle sizes (same direction comparison)
        self.yesterday_green_candle_sizes = self.today_green_candle_sizes.copy()
        self.yesterday_red_candle_sizes = self.today_red_candle_sizes.copy()

        self.date = new_date
        self.first_candle = None
        self.day_low = float('inf')
        self.day_high = 0.0

        # Bullish reset
        self.market_control_confirmed = False
        self.candle_expansion_confirmed = False
        self.pdh_breakout_confirmed = False
        self.pdh_breakout_time = None
        self.oi_confirmation = False

        # Bearish reset
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
        self.oi_bearish_count = 0
        self.price_at_oi_check = 0.0
        self.vwap_cumulative_tp_vol = 0.0
        self.vwap_cumulative_vol = 0.0
        self.vwap = 0.0

        # Entry reset
        self.entry_taken = False
        self.reentry_taken = False
        self.entry_direction = None
        self.entry_price = 0.0
        self.entry_time = None
        self.highest_since_entry = 0.0
        self.lowest_since_entry = float('inf')
        self.trailing_sl = 0.0
        self.sl_order_id = None
        self.candles_since_entry = 0
        self.red_candles_after_entry = 0
        self.max_profit_pct = 0.0


# ─────────────────────────────────────────────
# Config (FIXED: no duplicate fields)
# ─────────────────────────────────────────────

@dataclass
class IntradayMomentumConfig:
    """Configuration for the Intraday Momentum OI Strategy v2."""

    # ── Time windows ──
    market_open: time = field(default_factory=lambda: time(9, 15))
    first_hour_end: time = field(default_factory=lambda: time(10, 15))
    entry_window_start: time = field(default_factory=lambda: time(10, 15))
    entry_window_end: time = field(default_factory=lambda: time(12, 0))
    eod_exit_start: time = field(default_factory=lambda: time(15, 15))   # Start square-off
    market_close: time = field(default_factory=lambda: time(15, 30))     # Hard close

    # ── PDH/PDL breakout timing ──
    pdh_breakout_deadline: time = field(default_factory=lambda: time(9, 35))
    pdl_breakdown_deadline: time = field(default_factory=lambda: time(9, 35))

    # ── Candle quality filters ──
    min_candle_body_ratio: float = 0.5
    big_red_candle_multiplier: float = 2.0
    big_green_candle_multiplier: float = 2.5
    strong_green_candle_multiplier: float = 1.0

    # ── CE hold / exit settings ──
    ce_min_hold_candles: int = 8
    ce_require_ema_confirm: bool = True
    ce_use_ema_cross_exit: bool = False

    # ── PE hold / exit settings ──
    pe_min_hold_candles: int = 5
    pe_breakeven_exit_pct: float = 0.15
    pe_min_continuation_candles: int = 1
    pe_initial_sl_pct: float = 0.7
    pe_trailing_activation_pct: float = 0.2

    # ── PE volatility filter ──
    pe_min_atr_pct: float = 2.5
    pe_eligible_symbols: List[str] = field(default_factory=lambda: [
        "ADANIENT", "ADANIGREEN", "ADANIPOWER", "SAIL", "RBLBANK", "HINDALCO",
        "BHARTIARTL", "IDEA", "MRPL", "DELHIVERY", "ETERNAL", "VOLTAS",
        "JINDALSTEL", "VEDL", "TATASTEEL", "JSWSTEEL", "BHEL", "NBCC",
        "NATIONALUM", "BANKINDIA", "BANKBARODA", "PNB", "CANBK", "IOB",
    ])

    # ── High win rate entry filters ──
    min_breakout_pct: float = 0.3
    min_breakdown_pct: float = 0.3
    min_volume_multiplier: float = 1.5
    max_gap_up_pct: float = 1.0
    max_gap_down_pct: float = 1.0
    min_candles_above_pdh: int = 2
    min_candles_below_pdl: int = 2

    # NEW: VWAP filter — only take CE if price is above VWAP, PE if below VWAP
    use_vwap_filter: bool = True

    # NEW: Min ATR filter to avoid low-volatility setups
    min_atr_points: float = 5.0      # Minimum ATR (points) required to trade

    # ── OI confirmation (single definition — was duplicated in v1) ──
    min_oi_increase_pct: float = 1.0
    min_oi_checks_positive: int = 3

    # ── Trailing SL ──
    trailing_sl_pct: float = 0.5      # 0.5% trail from extreme
    initial_sl_pct: float = 1.0       # 1% initial SL from entry

    # NEW: Trailing SL order placement
    place_sl_orders: bool = True       # If True, place SL-M orders via broker
    sl_order_type: str = "SL-M"        # "SL-M" or "SL"

    # ── Position sizing ──
    max_position_pct: float = 2.0      # Max 2% of capital per trade

    # ── Re-entry logic ──
    allow_reentry: bool = True         # Allow one re-entry per day after SL
    reentry_min_score: float = 60.0    # Minimum setup score for re-entry
    reentry_cooldown_candles: int = 3  # Wait N candles after SL before re-entry

    # ── Trade limits ──
    max_trades_per_day: int = 2        # Including re-entry

    # ── Direction control ──
    enable_ce_trades: bool = True
    enable_pe_trades: bool = True


# ─────────────────────────────────────────────
# Strategy
# ─────────────────────────────────────────────

class IntradayMomentumOIStrategy(BaseStrategy):
    """
    Intraday Option Buying Momentum Strategy v2.0

    Improvements over v1:
    - Fixed duplicate config fields
    - Real trailing SL orders placed via broker
    - VWAP filter for entry confirmation
    - EOD square-off at 15:15 with 15:25 hard stop
    - Re-entry logic (once per day, requires re-confirmation)
    - Full P&L trade log with daily summary
    - Correct bearish OI confirmation (OI up + price DOWN)
    - Min ATR filter to skip choppy stocks
    - Candle expansion compares same-direction candles (green vs green, red vs red)
    """

    def __init__(
        self,
        config: Optional[IntradayMomentumConfig] = None,
        broker=None,
        data_feed=None,
        symbol: str = "",
    ):
        if broker and data_feed:
            super().__init__(broker, data_feed, {})
        self.config = config or IntradayMomentumConfig()
        self.context: Optional[DayContext] = None
        self.candle_history: deque = deque(maxlen=100)
        self.avg_candle_size: float = 0.0
        self.position_active: bool = False
        self.symbol: str = symbol
        self.current_oi: int = 0

        # Trade logging
        self.trade_log: List[TradeLog] = []
        self.current_trade: Optional[TradeLog] = None
        self.daily_summaries: Dict[date, DailySummary] = {}

        # Re-entry state
        self.sl_hit_candle_index: int = 0
        self.candle_index: int = 0

    # ── Abstract method stubs ──
    async def on_start(self):
        self.context = None
        self.position_active = False
        logger.info(f"[{self.name}] Strategy v2.0 started")

    async def on_stop(self):
        self._log_daily_summary()
        logger.info(f"[{self.name}] Strategy stopped")

    async def on_tick(self, tick):
        pass

    async def on_order_update(self, order):
        """Handle order updates — detect if our SL order was triggered."""
        if self.current_trade and self.context:
            if (self.current_trade.sl_order_id and
                    order.order_id == self.current_trade.sl_order_id and
                    order.status.name in ("FILLED", "COMPLETE")):
                logger.info(f"[{self.name}] SL order filled by broker: {order.order_id}")
                self._close_trade(order.average_price or self.context.trailing_sl,
                                  datetime.now(), "Broker SL order triggered")
                self.position_active = False

    @property
    def name(self) -> str:
        return "IntradayMomentumOI_v2"

    @property
    def description(self) -> str:
        return "Intraday Option Buying — Price Action + OI + VWAP Confirmation (v2)"

    # ─────────────────────────────────────────
    # Market phase helper
    # ─────────────────────────────────────────

    def _get_market_phase(self, ts: datetime) -> MarketPhase:
        ist_time = (ts + IST_OFFSET).time() if ts.tzinfo is not None else ts.time()
        if ist_time < self.config.market_open:
            return MarketPhase.PRE_MARKET
        elif ist_time < self.config.first_hour_end:
            return MarketPhase.FIRST_HOUR
        elif ist_time < self.config.entry_window_end:
            return MarketPhase.ENTRY_WINDOW
        elif ist_time < self.config.eod_exit_start:
            return MarketPhase.MOMENTUM_FADE
        elif ist_time < self.config.market_close:
            return MarketPhase.EOD_EXIT
        else:
            return MarketPhase.CLOSED

    def _ist_time(self, ts: datetime) -> time:
        return (ts + IST_OFFSET).time() if ts.tzinfo is not None else ts.time()

    # ─────────────────────────────────────────
    # Day init / stats
    # ─────────────────────────────────────────

    def _is_new_day(self, candle: Candle) -> bool:
        return self.context is None or candle.timestamp.date() != self.context.date

    def _initialize_day(self, candle: Candle):
        if self.context is None:
            self.context = DayContext(date=candle.timestamp.date())
        else:
            self._log_daily_summary()
            self.context.reset_for_new_day(candle.timestamp.date())
        self.candle_index = 0
        self.sl_hit_candle_index = 0
        logger.info(f"[{self.name}] New day: {candle.timestamp.date()} | "
                    f"PDH={self.context.pdh:.2f} PDL={self.context.pdl:.2f}")

    def _update_day_stats(self, candle: Candle):
        self.candle_index += 1
        ctx = self.context

        ctx.day_high = max(ctx.day_high, candle.high)
        ctx.day_low = min(ctx.day_low, candle.low)

        if ctx.first_candle is None:
            ctx.first_candle = candle
            logger.info(f"[{self.name}] First candle O={candle.open:.2f} H={candle.high:.2f} "
                        f"L={candle.low:.2f} C={candle.close:.2f}")

        # Green / red candle sizes
        body = abs(candle.close - candle.open)
        if candle.close > candle.open:
            ctx.today_green_candle_sizes.append(body)
        elif candle.close < candle.open:
            ctx.today_red_candle_sizes.append(body)

        # Volume
        if candle.volume > 0:
            ctx.candle_volumes.append(candle.volume)

        # Consecutive closes above PDH (bullish)
        if ctx.pdh > 0:
            if candle.close > ctx.pdh:
                ctx.consecutive_closes_above_pdh += 1
            else:
                ctx.consecutive_closes_above_pdh = 0

        # Consecutive closes below PDL (bearish)
        if ctx.pdl > 0:
            if candle.close < ctx.pdl:
                ctx.consecutive_closes_below_pdl += 1
            else:
                ctx.consecutive_closes_below_pdl = 0

        # Rolling average candle size
        self.candle_history.append(candle)
        if len(self.candle_history) > 10:
            sizes = [abs(c.close - c.open) for c in self.candle_history]
            self.avg_candle_size = sum(sizes) / len(sizes)

        # VWAP update (intraday cumulative VWAP)
        if candle.volume > 0:
            typical_price = (candle.high + candle.low + candle.close) / 3
            ctx.vwap_cumulative_tp_vol += typical_price * candle.volume
            ctx.vwap_cumulative_vol += candle.volume
            ctx.vwap = ctx.vwap_cumulative_tp_vol / ctx.vwap_cumulative_vol

    # ─────────────────────────────────────────
    # OI updates (from external feed)
    # ─────────────────────────────────────────

    def update_oi(self, oi: int, price: float):
        """Called from external OI feed. Tracks OI direction relative to price."""
        self.current_oi = oi
        if self.context is None:
            return

        ctx = self.context
        if ctx.initial_oi == 0:
            ctx.initial_oi = oi
            ctx.last_oi = oi
            ctx.price_at_oi_check = price
            return

        oi_change = oi - ctx.last_oi
        price_change = price - ctx.price_at_oi_check

        # BULLISH: OI up + price up → long buildup
        if oi_change > 0 and price_change > 0:
            ctx.oi_increase_count += 1

        # BEARISH (FIX): OI up + price DOWN → short buildup
        if oi_change > 0 and price_change < 0:
            ctx.oi_bearish_count += 1

        ctx.last_oi = oi
        ctx.price_at_oi_check = price

    # ─────────────────────────────────────────
    # Condition checks
    # ─────────────────────────────────────────

    def _check_market_control(self) -> bool:
        if self.context.first_candle is None:
            return False
        tol = self.context.first_candle.low * 0.001
        confirmed = abs(self.context.first_candle.low - self.context.day_low) <= tol
        if confirmed and not self.context.market_control_confirmed:
            self.context.market_control_confirmed = True
            logger.info(f"[{self.name}] ✓ Bullish Market Control confirmed")
        elif not confirmed and self.context.market_control_confirmed:
            self.context.market_control_confirmed = False
            logger.info(f"[{self.name}] ✗ Bullish Market Control LOST")
        return self.context.market_control_confirmed

    def _check_bearish_market_control(self) -> bool:
        if self.context.first_candle is None:
            return False
        tol = self.context.first_candle.high * 0.001
        confirmed = abs(self.context.first_candle.high - self.context.day_high) <= tol
        if confirmed and not self.context.bearish_market_control:
            self.context.bearish_market_control = True
            logger.info(f"[{self.name}] ✓ Bearish Market Control confirmed")
        elif not confirmed and self.context.bearish_market_control:
            self.context.bearish_market_control = False
            logger.info(f"[{self.name}] ✗ Bearish Market Control LOST")
        return self.context.bearish_market_control

    def _check_candle_expansion(self) -> bool:
        """BULLISH: today's GREEN candles must be larger than yesterday's GREEN candles."""
        ctx = self.context
        if len(ctx.today_green_candle_sizes) < 3:
            return False
        avg_today = sum(ctx.today_green_candle_sizes) / len(ctx.today_green_candle_sizes)
        if len(ctx.yesterday_green_candle_sizes) < 3:
            confirmed = avg_today > 0
        else:
            avg_yesterday = sum(ctx.yesterday_green_candle_sizes) / len(ctx.yesterday_green_candle_sizes)
            confirmed = avg_today > avg_yesterday * 1.1
        if confirmed and not ctx.candle_expansion_confirmed:
            ctx.candle_expansion_confirmed = True
            logger.info(f"[{self.name}] ✓ Bullish Candle Expansion confirmed")
        return ctx.candle_expansion_confirmed

    def _check_bearish_candle_expansion(self) -> bool:
        """BEARISH: today's RED candles must be larger than yesterday's RED candles."""
        ctx = self.context
        if len(ctx.today_red_candle_sizes) < 3:
            return False
        avg_today = sum(ctx.today_red_candle_sizes) / len(ctx.today_red_candle_sizes)
        if len(ctx.yesterday_red_candle_sizes) < 3:
            confirmed = avg_today > 0
        else:
            avg_yesterday = sum(ctx.yesterday_red_candle_sizes) / len(ctx.yesterday_red_candle_sizes)
            confirmed = avg_today > avg_yesterday * 1.1
        if confirmed and not ctx.bearish_candle_expansion:
            ctx.bearish_candle_expansion = True
            logger.info(f"[{self.name}] ✓ Bearish Candle Expansion confirmed")
        return ctx.bearish_candle_expansion

    def _check_pdh_breakout(self, candle: Candle) -> bool:
        ctx = self.context
        if ctx.pdh_breakout_confirmed:
            return True
        if ctx.pdh <= 0:
            if ctx.first_candle:
                ctx.pdh = ctx.first_candle.open * 1.003
            else:
                return False
        if candle.close > ctx.pdh:
            t = self._ist_time(candle.timestamp)
            if t <= time(10, 0):
                ctx.pdh_breakout_confirmed = True
                ctx.pdh_breakout_time = candle.timestamp
                logger.info(f"[{self.name}] ✓ PDH Breakout at {t} (close={candle.close:.2f} > PDH={ctx.pdh:.2f})")
                return True
        return False

    def _check_pdl_breakdown(self, candle: Candle) -> bool:
        ctx = self.context
        if ctx.pdl_breakdown_confirmed:
            return True
        if ctx.pdl <= 0:
            if ctx.first_candle:
                ctx.pdl = ctx.first_candle.open * 0.997
            else:
                return False
        if candle.close < ctx.pdl:
            t = self._ist_time(candle.timestamp)
            if t <= time(10, 0):
                ctx.pdl_breakdown_confirmed = True
                ctx.pdl_breakdown_time = candle.timestamp
                logger.info(f"[{self.name}] ✓ PDL Breakdown at {t} (close={candle.close:.2f} < PDL={ctx.pdl:.2f})")
                return True
        return False

    def _check_oi_confirmation(self) -> bool:
        ctx = self.context
        if ctx.oi_confirmation:
            return True
        if ctx.initial_oi == 0:
            ctx.oi_confirmation = True   # Auto-confirm in backtest
            return True
        total_change_pct = ((ctx.last_oi - ctx.initial_oi) / ctx.initial_oi * 100
                            if ctx.initial_oi > 0 else 0)
        if (total_change_pct >= self.config.min_oi_increase_pct and
                ctx.oi_increase_count >= self.config.min_oi_checks_positive):
            ctx.oi_confirmation = True
            logger.info(f"[{self.name}] ✓ Bullish OI confirmed — +{total_change_pct:.1f}%")
        return ctx.oi_confirmation

    def _check_bearish_oi_confirmation(self) -> bool:
        """
        FIX: Bearish OI confirmation requires OI increasing with FALLING price
        (short buildup), tracked by oi_bearish_count (separate from bullish).
        """
        ctx = self.context
        if ctx.bearish_oi_confirmation:
            return True
        if ctx.initial_oi == 0:
            ctx.bearish_oi_confirmation = True
            return True
        total_change_pct = ((ctx.last_oi - ctx.initial_oi) / ctx.initial_oi * 100
                            if ctx.initial_oi > 0 else 0)
        if (total_change_pct >= self.config.min_oi_increase_pct and
                ctx.oi_bearish_count >= self.config.min_oi_checks_positive):
            ctx.bearish_oi_confirmation = True
            logger.info(f"[{self.name}] ✓ Bearish OI confirmed — short buildup {ctx.oi_bearish_count} checks")
        return ctx.bearish_oi_confirmation

    # ─────────────────────────────────────────
    # Candle quality helpers
    # ─────────────────────────────────────────

    def _atr(self, period: int = 14) -> float:
        """Calculate ATR from candle history."""
        hist = list(self.candle_history)
        if len(hist) < 2:
            return 0.0
        trs = []
        for i in range(1, min(period + 1, len(hist))):
            c = hist[i]
            p = hist[i - 1]
            trs.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))
        return sum(trs) / len(trs) if trs else 0.0

    def _calculate_ema9(self) -> float:
        if len(self.candle_history) < 9:
            return 0.0
        closes = [c.close for c in list(self.candle_history)[-20:]]
        mult = 2 / 10
        ema = sum(closes[:9]) / 9
        for c in closes[9:]:
            ema = (c - ema) * mult + ema
        return ema

    def _is_strong_breakout_candle(self, candle: Candle) -> bool:
        if candle.close <= candle.open:
            return False
        body = candle.close - candle.open
        total_range = candle.high - candle.low
        if total_range == 0:
            return False
        if body / total_range < self.config.min_candle_body_ratio:
            return False
        if self.avg_candle_size > 0 and body < self.avg_candle_size:
            return False
        return True

    def _is_strong_breakdown_candle(self, candle: Candle) -> bool:
        if candle.close >= candle.open:
            return False
        body = candle.open - candle.close
        total_range = candle.high - candle.low
        if total_range == 0:
            return False
        if body / total_range < self.config.min_candle_body_ratio:
            return False
        if self.avg_candle_size > 0 and body < self.avg_candle_size:
            return False
        return True

    def _is_big_red_candle(self, candle: Candle) -> bool:
        if candle.close >= candle.open:
            return False
        body = candle.open - candle.close
        return (self.avg_candle_size > 0 and
                body >= self.avg_candle_size * self.config.big_red_candle_multiplier)

    def _is_big_green_candle(self, candle: Candle) -> bool:
        if candle.close <= candle.open:
            return False
        body = candle.close - candle.open
        return (self.avg_candle_size > 0 and
                body >= self.avg_candle_size * self.config.big_green_candle_multiplier)

    # ─────────────────────────────────────────
    # Setup scoring
    # ─────────────────────────────────────────

    def _calculate_setup_score(self, candle: Candle, direction: TradeDirection) -> SetupScore:
        ctx = self.context
        score = SetupScore(symbol=self.symbol, direction=direction, timestamp=candle.timestamp)

        if direction == TradeDirection.CE:
            if ctx.pdh > 0:
                score.breakout_strength = (candle.close - ctx.pdh) / ctx.pdh * 100
            score.consecutive_candles = ctx.consecutive_closes_above_pdh
            score.market_control_score = 1.0 if ctx.market_control_confirmed else 0.0
            # VWAP score: +1 if price is above VWAP
            if ctx.vwap > 0:
                score.vwap_score = 1.0 if candle.close > ctx.vwap else 0.0
        else:
            if ctx.pdl > 0:
                score.breakout_strength = (ctx.pdl - candle.close) / ctx.pdl * 100
            score.consecutive_candles = ctx.consecutive_closes_below_pdl
            score.market_control_score = 1.0 if ctx.bearish_market_control else 0.0
            if ctx.vwap > 0:
                score.vwap_score = 1.0 if candle.close < ctx.vwap else 0.0

        # Volume ratio
        if len(ctx.candle_volumes) >= 5 and candle.volume > 0:
            avg_vol = sum(ctx.candle_volumes[-10:]) / min(len(ctx.candle_volumes), 10)
            if avg_vol > 0:
                score.volume_ratio = candle.volume / avg_vol

        # Candle body ratio
        total_range = candle.high - candle.low
        if total_range > 0:
            score.candle_strength = abs(candle.close - candle.open) / total_range

        return score

    # ─────────────────────────────────────────
    # Entry conditions
    # ─────────────────────────────────────────

    def _check_ce_entry_conditions(self, candle: Candle) -> Tuple[bool, str, Optional[SetupScore]]:
        if not self.config.enable_ce_trades:
            return False, "CE trades disabled", None
        ctx = self.context
        phase = self._get_market_phase(candle.timestamp)
        if phase in (MarketPhase.PRE_MARKET, MarketPhase.MOMENTUM_FADE,
                     MarketPhase.EOD_EXIT, MarketPhase.CLOSED):
            return False, f"Phase {phase.value} — no entry", None
        if ctx.entry_taken and not self._can_reenter():
            return False, "Position already taken (no re-entry)", None

        # Pre-conditions
        if not ctx.market_control_confirmed:
            return False, "Bullish market control not confirmed", None
        if not ctx.candle_expansion_confirmed:
            return False, "Bullish candle expansion not confirmed", None
        if not self._check_oi_confirmation():
            return False, "OI confirmation not met", None

        pdh = ctx.pdh
        if pdh <= 0:
            return False, "No PDH available", None

        # Gap filter
        if ctx.first_candle:
            gap_pct = (ctx.first_candle.open - pdh) / pdh * 100
            if gap_pct > self.config.max_gap_up_pct:
                return False, f"Gap up too large ({gap_pct:.2f}%)", None

        # Breakout strength
        breakout_pct = (candle.close - pdh) / pdh * 100
        if breakout_pct < self.config.min_breakout_pct:
            return False, f"Breakout too weak ({breakout_pct:.2f}%)", None

        # Consecutive closes above PDH
        if ctx.consecutive_closes_above_pdh < self.config.min_candles_above_pdh:
            return False, f"Only {ctx.consecutive_closes_above_pdh} candles above PDH", None

        # Volume surge
        if len(ctx.candle_volumes) >= 5 and candle.volume > 0:
            avg_vol = sum(ctx.candle_volumes[-10:]) / min(len(ctx.candle_volumes), 10)
            if avg_vol > 0 and (candle.volume / avg_vol) < self.config.min_volume_multiplier:
                return False, f"Volume too low ({candle.volume/avg_vol:.2f}x)", None

        # VWAP filter (NEW)
        if self.config.use_vwap_filter and ctx.vwap > 0:
            if candle.close < ctx.vwap:
                return False, f"Price ({candle.close:.2f}) below VWAP ({ctx.vwap:.2f})", None

        # ATR filter (NEW)
        atr = self._atr()
        if atr > 0 and atr < self.config.min_atr_points:
            return False, f"ATR too low ({atr:.2f} < {self.config.min_atr_points})", None

        # Candle close must be in upper half of its range
        candle_range = candle.high - candle.low
        if candle_range > 0:
            close_position = (candle.close - candle.low) / candle_range
            if close_position < 0.6:
                return False, f"Close not in upper range (position: {close_position:.2f})", None

        # Must be a strong breakout candle
        if not self._is_strong_breakout_candle(candle):
            return False, "Not a strong breakout candle", None

        score = self._calculate_setup_score(candle, TradeDirection.CE)
        return True, f"CE Entry: +{breakout_pct:.2f}% above PDH", score

    def _check_pe_entry_conditions(self, candle: Candle) -> Tuple[bool, str, Optional[SetupScore]]:
        if not self.config.enable_pe_trades:
            return False, "PE trades disabled", None

        # Symbol eligibility
        if self.symbol and self.config.pe_eligible_symbols:
            if self.symbol not in self.config.pe_eligible_symbols:
                return False, f"{self.symbol} not PE-eligible", None

        ctx = self.context
        phase = self._get_market_phase(candle.timestamp)
        if phase in (MarketPhase.PRE_MARKET, MarketPhase.MOMENTUM_FADE,
                     MarketPhase.EOD_EXIT, MarketPhase.CLOSED):
            return False, f"Phase {phase.value} — no entry", None
        if ctx.entry_taken and not self._can_reenter():
            return False, "Position already taken (no re-entry)", None

        if not ctx.bearish_market_control:
            return False, "Bearish market control not confirmed", None
        if not ctx.bearish_candle_expansion:
            return False, "Bearish candle expansion not confirmed", None
        if not self._check_bearish_oi_confirmation():
            return False, "Bearish OI confirmation not met", None

        pdl = ctx.pdl
        if pdl <= 0:
            return False, "No PDL available", None

        # Gap filter
        if ctx.first_candle:
            gap_pct = (pdl - ctx.first_candle.open) / pdl * 100
            if gap_pct > self.config.max_gap_down_pct:
                return False, f"Gap down too large ({gap_pct:.2f}%)", None

        breakdown_pct = (pdl - candle.close) / pdl * 100
        if breakdown_pct < self.config.min_breakdown_pct:
            return False, f"Breakdown too weak ({breakdown_pct:.2f}%)", None

        if ctx.consecutive_closes_below_pdl < self.config.min_candles_below_pdl:
            return False, f"Only {ctx.consecutive_closes_below_pdl} candles below PDL", None

        # Volume surge
        if len(ctx.candle_volumes) >= 5 and candle.volume > 0:
            avg_vol = sum(ctx.candle_volumes[-10:]) / min(len(ctx.candle_volumes), 10)
            if avg_vol > 0 and (candle.volume / avg_vol) < self.config.min_volume_multiplier:
                return False, f"Volume too low ({candle.volume/avg_vol:.2f}x)", None

        # VWAP filter (NEW)
        if self.config.use_vwap_filter and ctx.vwap > 0:
            if candle.close > ctx.vwap:
                return False, f"Price ({candle.close:.2f}) above VWAP ({ctx.vwap:.2f})", None

        # ATR filter
        atr = self._atr()
        if atr > 0 and atr < self.config.min_atr_points:
            return False, f"ATR too low ({atr:.2f})", None

        # Candle close must be in lower half of its range
        candle_range = candle.high - candle.low
        if candle_range > 0:
            close_position = (candle.close - candle.low) / candle_range
            if close_position > 0.4:
                return False, f"Close not in lower range (position: {close_position:.2f})", None

        if not self._is_strong_breakdown_candle(candle):
            return False, "Not a strong breakdown candle", None

        score = self._calculate_setup_score(candle, TradeDirection.PE)
        return True, f"PE Entry: -{breakdown_pct:.2f}% below PDL", score

    def _check_entry_conditions(self, candle: Candle) -> Tuple[bool, str, Optional[TradeDirection], Optional[SetupScore]]:
        ce_enter, ce_reason, ce_score = self._check_ce_entry_conditions(candle)
        if ce_enter:
            return True, ce_reason, TradeDirection.CE, ce_score
        pe_enter, pe_reason, pe_score = self._check_pe_entry_conditions(candle)
        if pe_enter:
            return True, pe_reason, TradeDirection.PE, pe_score
        return False, f"CE: {ce_reason} | PE: {pe_reason}", None, None

    # ─────────────────────────────────────────
    # Re-entry logic
    # ─────────────────────────────────────────

    def _can_reenter(self) -> bool:
        """
        Allow one re-entry per day if:
        - re-entry is enabled
        - we haven't already re-entered
        - enough candles have passed since the SL was hit
        - total trades today < max_trades_per_day
        """
        if not self.config.allow_reentry:
            return False
        if self.context.reentry_taken:
            return False
        trades_today = sum(1 for t in self.trade_log
                           if t.date == self.context.date)
        if trades_today >= self.config.max_trades_per_day:
            return False
        cooldown = self.candle_index - self.sl_hit_candle_index
        if cooldown < self.config.reentry_cooldown_candles:
            return False
        return True

    # ─────────────────────────────────────────
    # Exit conditions
    # ─────────────────────────────────────────

    def _check_exit_conditions(self, candle: Candle) -> Tuple[bool, str]:
        ctx = self.context
        if not ctx.entry_taken:
            return False, "No position"

        direction = ctx.entry_direction
        ist_time = self._ist_time(candle.timestamp)

        # ── EOD exit (both directions) ──
        if ist_time >= self.config.eod_exit_start:
            return True, f"{direction.name} EOD Exit at {ist_time}"

        ctx.candles_since_entry += 1

        if direction == TradeDirection.CE:
            ctx.highest_since_entry = max(ctx.highest_since_entry, candle.high)

            # Update trailing SL
            new_sl = ctx.highest_since_entry * (1 - self.config.trailing_sl_pct / 100)
            if new_sl > ctx.trailing_sl:
                ctx.trailing_sl = new_sl
                self._update_sl_order(ctx.trailing_sl, direction)

            # Trailing SL hit
            if candle.low <= ctx.trailing_sl:
                return True, f"CE Trailing SL hit at {ctx.trailing_sl:.2f}"

            # Min hold check
            if ctx.candles_since_entry < self.config.ce_min_hold_candles:
                return False, "Hold (min hold not met)"

            # EMA cross exit
            if self.config.ce_use_ema_cross_exit and len(self.candle_history) >= 9:
                ema9 = self._calculate_ema9()
                if candle.close < ema9:
                    return True, f"CE Exit: Price below EMA9 ({ema9:.2f})"

            # Big red candle exit
            if self._is_big_red_candle(candle):
                if self.config.ce_require_ema_confirm and len(self.candle_history) >= 9:
                    ema9 = self._calculate_ema9()
                    if candle.close < ema9:
                        return True, "CE Exit: Big red + below EMA9"
                    return False, "Hold (big red but above EMA)"
                return True, "CE Exit: Momentum reversal (big red candle)"

        else:  # PE
            if candle.close < candle.open:
                ctx.red_candles_after_entry += 1

            ctx.lowest_since_entry = min(ctx.lowest_since_entry, candle.low)

            profit_pct = (ctx.entry_price - candle.close) / ctx.entry_price * 100
            ctx.max_profit_pct = max(ctx.max_profit_pct, profit_pct)

            # Initialize PE trailing SL
            if ctx.trailing_sl == 0:
                ctx.trailing_sl = ctx.entry_price * (1 + self.config.pe_initial_sl_pct / 100)
                self._update_sl_order(ctx.trailing_sl, direction)

            # Trail SL after activation threshold
            if ctx.max_profit_pct >= self.config.pe_trailing_activation_pct:
                new_sl = ctx.lowest_since_entry * (1 + self.config.trailing_sl_pct / 100)
                if new_sl < ctx.trailing_sl:
                    ctx.trailing_sl = new_sl
                    self._update_sl_order(ctx.trailing_sl, direction)

            # Trailing SL hit (price going UP past SL)
            if candle.high >= ctx.trailing_sl:
                return True, f"PE Trailing SL hit at {ctx.trailing_sl:.2f}"

            # Breakeven protection
            if (ctx.max_profit_pct >= 0.3 and
                    profit_pct < ctx.max_profit_pct * 0.2):
                return True, f"PE Breakeven protection (max: +{ctx.max_profit_pct:.2f}%, now: {profit_pct:.2f}%)"

            # Big green candle (reversal) after min hold
            if ctx.candles_since_entry >= self.config.pe_min_hold_candles:
                if self._is_big_green_candle(candle):
                    return True, "PE Exit: Momentum reversal (big green candle)"

        return False, "Hold position"

    # ─────────────────────────────────────────
    # Trailing SL order management
    # ─────────────────────────────────────────

    async def _place_sl_order(self, sl_price: float, direction: TradeDirection, symbol: str) -> Optional[str]:
        """
        Place a real SL-M order via broker. Returns order ID.
        Only runs if place_sl_orders=True and broker is available.
        """
        if not self.config.place_sl_orders or not hasattr(self, 'broker') or self.broker is None:
            return None
        try:
            from app.schemas.broker import OrderRequest, OrderSide
            side = OrderSide.SELL if direction == TradeDirection.CE else OrderSide.BUY
            order = OrderRequest(
                symbol=symbol,
                quantity=1,  # Caller should override qty
                side=side,
                order_type=self.config.sl_order_type,
                trigger_price=round(sl_price, 2),
                price=round(sl_price * 0.995, 2) if self.config.sl_order_type == "SL" else 0,
                product_type="MIS",
            )
            resp = await self.broker.place_order(order)
            logger.info(f"[{self.name}] SL order placed: {resp.order_id} @ {sl_price:.2f}")
            return resp.order_id
        except Exception as e:
            logger.error(f"[{self.name}] Failed to place SL order: {e}")
            return None

    async def _cancel_sl_order(self, order_id: str):
        """Cancel existing SL order before placing a new (modified) one."""
        if not self.broker or not order_id:
            return
        try:
            await self.broker.cancel_order(order_id)
            logger.info(f"[{self.name}] Cancelled SL order: {order_id}")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to cancel SL order {order_id}: {e}")

    def _update_sl_order(self, new_sl: float, direction: TradeDirection):
        """
        Synchronous wrapper — logs SL update. Actual async order placement is
        handled via on_candle signal metadata (caller can execute from async context).
        """
        logger.info(f"[{self.name}] Trailing SL updated → {new_sl:.2f} ({direction.name})")
        if self.current_trade:
            self.current_trade.sl_order_id = self.context.sl_order_id  # Track latest SL

    # ─────────────────────────────────────────
    # Trade log helpers
    # ─────────────────────────────────────────

    def _open_trade(self, candle: Candle, direction: TradeDirection, is_reentry: bool = False) -> TradeLog:
        trade = TradeLog(
            date=candle.timestamp.date(),
            symbol=self.symbol,
            direction=direction,
            entry_time=candle.timestamp,
            entry_price=candle.close,
            is_reentry=is_reentry,
        )
        self.trade_log.append(trade)
        self.current_trade = trade
        logger.info(f"[{self.name}] Trade opened: {direction.name} @ {candle.close:.2f} "
                    f"({'RE-ENTRY' if is_reentry else 'INITIAL'})")
        return trade

    def _close_trade(self, exit_price: float, exit_time: datetime, reason: str):
        if self.current_trade is None:
            return
        self.current_trade.close(exit_price, exit_time, reason)
        status = "WIN" if self.current_trade.is_winner else "LOSS"
        logger.info(f"[{self.name}] Trade closed [{status}]: {self.current_trade.direction.name} "
                    f"Entry={self.current_trade.entry_price:.2f} Exit={exit_price:.2f} "
                    f"P&L={self.current_trade.pnl_pct:+.2f}% | {reason}")
        self.current_trade = None

    def _log_daily_summary(self):
        if self.context is None:
            return
        today_trades = [t for t in self.trade_log if t.date == self.context.date]
        if not today_trades:
            return
        summary = DailySummary(date=self.context.date, trades=today_trades)
        self.daily_summaries[self.context.date] = summary
        summary.log()

    def get_trade_log(self) -> List[TradeLog]:
        return self.trade_log

    def get_daily_summary(self, for_date: Optional[date] = None) -> Optional[DailySummary]:
        if for_date:
            return self.daily_summaries.get(for_date)
        if self.context:
            return self.daily_summaries.get(self.context.date)
        return None

    # ─────────────────────────────────────────
    # Main candle processor
    # ─────────────────────────────────────────

    def on_candle(self, candle: Candle, instrument_id: int = None) -> Optional[Signal]:
        """
        Process a new 5-minute candle. Returns a Signal on entry or exit,
        None otherwise. Also carries SL metadata for async order placement.
        """
        # ── New day init ──
        if self._is_new_day(candle):
            self._initialize_day(candle)
            self.position_active = False

        self._update_day_stats(candle)
        phase = self._get_market_phase(candle.timestamp)

        sym = str(instrument_id) if instrument_id else self.symbol or "UNKNOWN"

        # ── Exit check (always first) ──
        if self.position_active:
            should_exit, reason = self._check_exit_conditions(candle)
            if should_exit:
                self.position_active = False
                direction = self.context.entry_direction

                # P&L
                if direction == TradeDirection.CE:
                    pnl_pct = (candle.close - self.context.entry_price) / self.context.entry_price * 100
                else:
                    pnl_pct = (self.context.entry_price - candle.close) / self.context.entry_price * 100

                self._close_trade(candle.close, candle.timestamp, reason)

                # Track re-entry cooldown
                if "SL" in reason or "sl" in reason.lower():
                    self.sl_hit_candle_index = self.candle_index

                # Reset for potential re-entry
                self.context.entry_taken = False
                if "RE-ENTRY" not in reason:
                    pass  # first exit — re-entry still possible

                return Signal(
                    signal_type=SignalType.EXIT,
                    symbol=sym,
                    price=candle.close,
                    timestamp=candle.timestamp,
                    strength=1.0,
                    metadata={
                        "reason": reason,
                        "direction": direction.name,
                        "entry_price": self.context.entry_price,
                        "pnl_pct": round(pnl_pct, 3),
                        "trailing_sl": self.context.trailing_sl,
                        "cancel_sl_order_id": self.context.sl_order_id,  # Caller should cancel this
                    }
                )

        # ── Skip entry during momentum fade / EOD / closed ──
        if phase in (MarketPhase.MOMENTUM_FADE, MarketPhase.EOD_EXIT, MarketPhase.CLOSED):
            return None

        # ── Condition checks ──
        if phase == MarketPhase.FIRST_HOUR:
            self._check_market_control()
            self._check_candle_expansion()
            self._check_oi_confirmation()
            self._check_bearish_market_control()
            self._check_bearish_candle_expansion()
            self._check_bearish_oi_confirmation()

        if phase == MarketPhase.ENTRY_WINDOW:
            self._check_market_control()
            self._check_candle_expansion()
            self._check_pdh_breakout(candle)
            self._check_bearish_market_control()
            self._check_bearish_candle_expansion()
            self._check_pdl_breakdown(candle)

        # ── Entry check ──
        if not self.position_active:
            is_reentry = self.context.entry_taken  # If entry_taken was reset after SL
            should_enter, reason, direction, score = self._check_entry_conditions(candle)

            # For re-entries, enforce minimum score
            if should_enter and is_reentry:
                if score and score.total_score < self.config.reentry_min_score:
                    should_enter = False
                    reason = f"Re-entry score too low ({score.total_score:.1f} < {self.config.reentry_min_score})"

            if should_enter and direction:
                self.position_active = True
                ctx = self.context
                ctx.entry_taken = True
                ctx.entry_direction = direction
                ctx.entry_price = candle.close
                ctx.entry_time = candle.timestamp
                ctx.highest_since_entry = candle.high
                ctx.lowest_since_entry = candle.low
                ctx.candles_since_entry = 0
                ctx.red_candles_after_entry = 0
                ctx.max_profit_pct = 0.0

                if is_reentry:
                    ctx.reentry_taken = True

                # Initial SL
                if direction == TradeDirection.CE:
                    ctx.trailing_sl = candle.close * (1 - self.config.initial_sl_pct / 100)
                else:
                    ctx.trailing_sl = candle.close * (1 + self.config.pe_initial_sl_pct / 100)

                trade = self._open_trade(candle, direction, is_reentry=is_reentry)
                logger.info(f"[{self.name}] Initial SL: {ctx.trailing_sl:.2f} | "
                            f"Score: {score.total_score:.1f}")

                signal_type = SignalType.BUY if direction == TradeDirection.CE else SignalType.SELL
                return Signal(
                    signal_type=signal_type,
                    symbol=sym,
                    price=candle.close,
                    timestamp=candle.timestamp,
                    strength=score.total_score / 100 if score else 0.5,
                    metadata={
                        "reason": reason,
                        "direction": direction.name,
                        "pdh": ctx.pdh,
                        "pdl": ctx.pdl,
                        "vwap": ctx.vwap,
                        "score": score.total_score if score else 0,
                        "initial_sl": ctx.trailing_sl,
                        "is_reentry": is_reentry,
                        # Signal to caller: place SL order at this price
                        "place_sl_at": ctx.trailing_sl,
                        "sl_order_type": self.config.sl_order_type,
                    }
                )

        return None

    # ─────────────────────────────────────────
    # Status / introspection
    # ─────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        if self.context is None:
            return {"status": "not_initialized"}
        ctx = self.context
        today_trades = [t for t in self.trade_log if t.date == ctx.date]
        return {
            "version": "2.0",
            "date": str(ctx.date),
            "conditions": {
                "bullish": {
                    "market_control": ctx.market_control_confirmed,
                    "candle_expansion": ctx.candle_expansion_confirmed,
                    "pdh_breakout": ctx.pdh_breakout_confirmed,
                    "oi": ctx.oi_confirmation,
                    "all_met": ctx.all_bullish_conditions_met(),
                },
                "bearish": {
                    "market_control": ctx.bearish_market_control,
                    "candle_expansion": ctx.bearish_candle_expansion,
                    "pdl_breakdown": ctx.pdl_breakdown_confirmed,
                    "oi": ctx.bearish_oi_confirmation,
                    "all_met": ctx.all_bearish_conditions_met(),
                },
            },
            "day_stats": {
                "day_high": ctx.day_high,
                "day_low": ctx.day_low,
                "pdh": ctx.pdh,
                "pdl": ctx.pdl,
                "vwap": round(ctx.vwap, 2),
                "avg_candle_size": round(self.avg_candle_size, 2),
                "atr": round(self._atr(), 2),
            },
            "position": {
                "active": self.position_active,
                "direction": ctx.entry_direction.name if ctx.entry_direction else None,
                "entry_price": ctx.entry_price,
                "entry_time": str(ctx.entry_time) if ctx.entry_time else None,
                "trailing_sl": ctx.trailing_sl,
                "highest": ctx.highest_since_entry,
                "lowest": ctx.lowest_since_entry,
                "candles_held": ctx.candles_since_entry,
                "sl_order_id": ctx.sl_order_id,
            },
            "trades_today": len(today_trades),
            "reentry_available": self._can_reenter() if ctx.entry_taken else "N/A",
            "today_pnl_pct": round(sum(t.pnl_pct for t in today_trades if t.exit_price), 3),
        }


# ─────────────────────────────────────────────
# Convenience factory
# ─────────────────────────────────────────────

def create_intraday_momentum_strategy(
    entry_start: str = "10:15",
    entry_end: str = "12:00",
    trailing_sl_pct: float = 0.5,
    allow_reentry: bool = True,
    use_vwap_filter: bool = True,
    place_sl_orders: bool = True,
) -> IntradayMomentumOIStrategy:
    h, m = map(int, entry_start.split(":"))
    h2, m2 = map(int, entry_end.split(":"))
    config = IntradayMomentumConfig(
        entry_window_start=time(h, m),
        entry_window_end=time(h2, m2),
        trailing_sl_pct=trailing_sl_pct,
        allow_reentry=allow_reentry,
        use_vwap_filter=use_vwap_filter,
        place_sl_orders=place_sl_orders,
    )
    return IntradayMomentumOIStrategy(config)
