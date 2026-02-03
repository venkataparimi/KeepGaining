"""
Backtest: Intraday Option Buying Momentum Strategy (Smart Money Flow)
KeepGaining Trading Platform

Strategy Logic:
- Pre-Entry Filters (ALL must be true):
  1. Market Control: First 5-min candle low = Day's Low (bulls in control)
  2. Candle Expansion: Today's green candles larger than yesterday's
  3. PDH Breakout: Stock above Previous Day High by 9:30-9:35 AM
  4. OI Confirmation: OI increasing while price rising

- Entry (After 10:15 AM):
  - Breakout on 5-min chart
  - Strong green candle (large body, small wicks)

- Exit:
  - Big red candles (momentum reversal)
  - Trailing stop loss
  - NO fixed profit target
  - Exit by 12:00 PM (momentum fades)

Usage:
    python backtest_smart_money_momentum.py --symbols RELIANCE,TCS --start 2024-11-01 --end 2024-11-30
"""

import sys
import os
from pathlib import Path
from datetime import datetime, date, time, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal
import pandas as pd
import numpy as np
from loguru import logger
import click

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text


from enum import Enum

class IndicatorConfirmation(Enum):
    """Indicator confirmation modes for entry."""
    NONE = "none"  # No indicator confirmation
    RSI_EMA = "rsi_ema"  # RSI > 50 and EMA 9 > EMA 21
    SUPERTREND = "supertrend"  # Supertrend direction = UP
    ADX = "adx"  # ADX > 25 and +DI > -DI


@dataclass
class StrategyConfig:
    """Configuration for Smart Money Momentum Strategy."""
    # Timing (in UTC - data is UTC, subtract 5:30 from IST)
    # IST 9:15 = UTC 3:45, IST 9:20 = UTC 3:50, etc.
    market_open: time = time(3, 45)           # 9:15 IST
    first_candle_end: time = time(3, 50)      # 9:20 IST
    pdh_breakout_deadline: time = time(4, 5)  # 9:35 IST
    entry_window_start: time = time(4, 45)    # 10:15 IST
    entry_window_end: time = time(6, 30)      # 12:00 IST
    market_close: time = time(10, 0)          # 15:30 IST
    
    # Candle quality
    min_body_ratio: float = 0.5  # Body must be 50% of range for "strong" candle (relaxed from 60%)
    max_wick_ratio: float = 0.3  # Wicks must be < 30% each (relaxed from 20%)
    
    # Candle expansion factor
    candle_expansion_factor: float = 1.1  # Today's candles 10% larger (relaxed from 30%)
    
    # OI confirmation (disabled since most equity parquet files don't have real OI)
    min_oi_change_pct: float = 0.0  # Disabled - set to 0
    require_oi_confirmation: bool = False  # Skip OI check for equity
    
    # Trailing stop
    trailing_sl_pct: float = 0.5  # 0.5% trailing stop
    
    # Big red candle exit threshold
    exit_on_big_red_candle: bool = True  # Re-enabled
    big_red_body_ratio: float = 0.6  # 60% body = big candle (relaxed)
    big_red_min_range_pct: float = 0.2  # Must be at least 0.2% range
    
    # Anti-churning: One trade per stock per day
    one_trade_per_stock_per_day: bool = True  # Prevent re-entry after exit
    
    # Indicator confirmation
    indicator_confirmation: IndicatorConfirmation = IndicatorConfirmation.NONE
    rsi_threshold: float = 50.0  # RSI must be above this for bullish
    adx_threshold: float = 25.0  # ADX must be above this for trending
    
    # Position sizing
    capital_per_trade: float = 20000.0


@dataclass
class DayContext:
    """Context for a trading day."""
    date: date
    first_candle_low: float = 0
    first_candle_high: float = 0
    first_candle_close: float = 0
    day_low: float = float('inf')
    day_high: float = 0
    pdh: float = 0  # Previous day high
    pdl: float = 0  # Previous day low
    pdc: float = 0  # Previous day close
    prev_day_avg_green_size: float = 0
    curr_day_green_candle_sizes: List[float] = field(default_factory=list)
    pdh_broken_early: bool = False
    bulls_in_control: bool = False
    oi_confirming: bool = False
    
    # Anti-churning
    traded_today: bool = False  # Set to True after first trade exits
    
    # Trade state
    in_position: bool = False
    entry_price: float = 0  # Equity price at entry
    entry_time: datetime = None
    highest_since_entry: float = 0
    trailing_sl: float = 0
    
    # Option trade state
    option_symbol: str = None  # ATM CE option being traded
    option_entry_price: float = 0  # Option premium at entry
    option_quantity: int = 0  # Lot size


@dataclass
class Trade:
    """Trade record."""
    symbol: str  # Underlying symbol
    entry_time: datetime
    exit_time: datetime
    entry_price: float  # Equity price
    exit_price: float  # Equity price
    quantity: int
    pnl: float
    pnl_pct: float
    exit_reason: str
    
    # Option trade details
    option_symbol: str = None  # CE option traded
    option_entry_price: float = 0  # Premium at entry
    option_exit_price: float = 0  # Premium at exit
    option_pnl: float = 0  # P&L from option trade
    option_pnl_pct: float = 0  # % P&L from option
    
    # Context at entry
    pdh: float = 0
    oi_change_pct: float = 0
    candle_expansion: float = 0


class SmartMoneyMomentumBacktest:
    """Backtester for Smart Money Momentum Strategy."""
    
    # Database URL with correct credentials
    DB_URL = "postgresql://user:password@localhost:5432/keepgaining"
    
    def __init__(self, config: StrategyConfig = None):
        self.config = config or StrategyConfig()
        self.trades: List[Trade] = []
        self.day_contexts: Dict[str, Dict[date, DayContext]] = {}
        self.engine = None
        self._option_cache: Dict[str, pd.DataFrame] = {}  # Cache for option data
        
    def _get_engine(self):
        """Get database engine (lazy init)."""
        if self.engine is None:
            self.engine = create_engine(self.DB_URL)
        return self.engine
        
    def load_data(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
        use_db: bool = True,
    ) -> pd.DataFrame:
        """Load 5-minute candle data from database or Parquet files."""
        
        # Use database first (has option data)
        if use_db:
            try:
                return self._load_equity_from_db(symbols, start_date, end_date)
            except Exception as e:
                logger.warning(f"Database load failed: {e}, falling back to Parquet")
        
        # Fallback to Parquet
        data_dir = Path(__file__).parent.parent / "data" / "strategy_dataset"
        if data_dir.exists():
            return self._load_from_parquet(symbols, start_date, end_date, data_dir)
        
        return pd.DataFrame()
    
    def _load_equity_from_db(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Load equity candle data from database."""
        
        engine = self._get_engine()
        symbols_str = ",".join([f"'{s}'" for s in symbols])
        
        # SQLAlchemy 2.x compatible query
        with engine.connect() as conn:
            query = text(f"""
                SELECT 
                    c.timestamp,
                    im.trading_symbol as symbol,
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume,
                    COALESCE(c.oi, 0) as oi
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol IN ({symbols_str})
                    AND im.instrument_type = 'EQUITY'
                    AND c.timestamp >= '{start_date}'
                    AND c.timestamp < '{end_date + timedelta(days=1)}'
                ORDER BY im.trading_symbol, c.timestamp
            """)
            
            logger.info(f"Loading equity data for {len(symbols)} symbols from database")
            result = conn.execute(query)
            rows = result.fetchall()
        
        if rows:
            df = pd.DataFrame(rows, columns=['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            # Convert Decimal to float for numeric columns
            for col in ['open', 'high', 'low', 'close', 'volume', 'oi']:
                df[col] = df[col].astype(float)
            logger.info(f"Loaded {len(df)} equity candles from database")
            return df
        
        return pd.DataFrame()
    
    def find_atm_ce_option(
        self,
        symbol: str,
        equity_price: float,
        trade_time: datetime,
    ) -> Optional[str]:
        """Find ATM CE option with nearest expiry for given symbol and price."""
        
        engine = self._get_engine()
        
        # Round to nearest strike (usually 10 or 20 for most stocks)
        strike_step = 10 if equity_price < 500 else 20 if equity_price < 2000 else 50
        atm_strike = round(equity_price / strike_step) * strike_step
        
        # Get trade date for expiry comparison
        trade_date = trade_time.date() if hasattr(trade_time, 'date') else trade_time
        
        # Find CE option with nearest expiry using option_master
        with engine.connect() as conn:
            query = text(f"""
                SELECT im.trading_symbol, om.expiry_date
                FROM instrument_master im
                JOIN option_master om ON im.instrument_id = om.instrument_id
                WHERE im.underlying = '{symbol}'
                    AND im.instrument_type = 'CE'
                    AND om.strike_price = {atm_strike}
                    AND om.expiry_date >= '{trade_date}'
                ORDER BY om.expiry_date
                LIMIT 1
            """)
            result = conn.execute(query)
            rows = result.fetchall()
        
        if len(rows) == 0:
            # Fallback to old method if option_master doesn't have data
            logger.debug(f"No ATM CE in option_master for {symbol} at strike {atm_strike}, trying fallback")
            return self._find_atm_ce_fallback(symbol, atm_strike)
        
        return rows[0][0]  # First column is trading_symbol
    
    def _find_atm_ce_fallback(self, symbol: str, atm_strike: int) -> Optional[str]:
        """Fallback: find any CE option with matching strike."""
        engine = self._get_engine()
        
        with engine.connect() as conn:
            query = text(f"""
                SELECT im.trading_symbol
                FROM instrument_master im
                WHERE im.underlying = '{symbol}'
                    AND im.instrument_type = 'CE'
                    AND im.trading_symbol LIKE '%{int(atm_strike)} CE%'
                ORDER BY im.trading_symbol
                LIMIT 1
            """)
            result = conn.execute(query)
            rows = result.fetchall()
        
        if len(rows) == 0:
            logger.debug(f"No ATM CE found for {symbol} at strike {atm_strike}")
            return None
        
        return rows[0][0]
    
    def get_option_price(
        self,
        option_symbol: str,
        timestamp: datetime,
    ) -> Optional[float]:
        """Get option price at given timestamp."""
        
        # Use cache if available
        if option_symbol not in self._option_cache:
            engine = self._get_engine()
            
            # SQLAlchemy 2.x compatible query
            with engine.connect() as conn:
                query = text(f"""
                    SELECT c.timestamp, c.close
                    FROM candle_data c
                    JOIN instrument_master im ON c.instrument_id = im.instrument_id
                    WHERE im.trading_symbol = '{option_symbol}'
                    ORDER BY c.timestamp
                """)
                result = conn.execute(query)
                rows = result.fetchall()
            
            # Convert to DataFrame
            if rows:
                self._option_cache[option_symbol] = pd.DataFrame(rows, columns=['timestamp', 'close'])
            else:
                self._option_cache[option_symbol] = pd.DataFrame()
        
        df = self._option_cache[option_symbol]
        
        if len(df) == 0:
            return None
        
        # Find closest candle at or after timestamp
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        matching = df[df['timestamp'] >= timestamp]
        
        if len(matching) == 0:
            return None
        
        # Convert Decimal to float
        price = matching.iloc[0]['close']
        return float(price) if price is not None else None
    
    def _load_from_parquet(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
        data_dir: Path,
    ) -> pd.DataFrame:
        """Load data from Parquet files."""
        
        frames = []
        for symbol in symbols:
            parquet_file = data_dir / f"{symbol}_EQUITY.parquet"
            
            if not parquet_file.exists():
                logger.warning(f"No Parquet file for {symbol}")
                continue
            
            df = pd.read_parquet(parquet_file)
            
            # Ensure timestamp column
            if 'timestamp' not in df.columns and 'datetime' in df.columns:
                df['timestamp'] = df['datetime']
            
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                # Filter date range
                df = df[
                    (df['timestamp'].dt.date >= start_date) &
                    (df['timestamp'].dt.date <= end_date)
                ]
            
            df['symbol'] = symbol
            
            # Ensure OI column exists
            if 'oi' not in df.columns:
                df['oi'] = 0
            
            frames.append(df)
            logger.info(f"Loaded {len(df)} candles for {symbol}")
        
        if not frames:
            return pd.DataFrame()
        
        result = pd.concat(frames, ignore_index=True)
        logger.info(f"Total: {len(result)} candles loaded")
        return result
    
    def _load_from_db(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
        db_url: str = None,
    ) -> pd.DataFrame:
        """Load data from PostgreSQL database."""
        
        db_url = db_url or os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost/keepgaining")
        engine = create_engine(db_url.replace("+asyncpg", ""))
        
        symbols_str = ",".join([f"'{s}'" for s in symbols])
        
        query = f"""
            SELECT 
                c.timestamp,
                im.symbol,
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                COALESCE(c.oi, 0) as oi
            FROM candle_data c
            JOIN instrument_master im ON c.instrument_id = im.instrument_id
            WHERE im.symbol IN ({symbols_str})
                AND im.instrument_type = 'EQUITY'
                AND c.timestamp >= '{start_date}'
                AND c.timestamp < '{end_date + timedelta(days=1)}'
            ORDER BY im.symbol, c.timestamp
        """
        
        logger.info(f"Loading data for {len(symbols)} symbols from database")
        df = pd.read_sql(query, engine)
        logger.info(f"Loaded {len(df)} candles")
        
        return df
    
    def _get_prev_day_data(
        self,
        df: pd.DataFrame,
        symbol: str,
        current_date: date,
    ) -> Tuple[float, float, float, float]:
        """Get previous day's high, low, close, and average green candle size."""
        
        prev_date = current_date - timedelta(days=1)
        
        # Handle weekends
        while prev_date.weekday() >= 5:
            prev_date -= timedelta(days=1)
        
        prev_df = df[
            (df['symbol'] == symbol) & 
            (df['timestamp'].dt.date == prev_date)
        ]
        
        if len(prev_df) == 0:
            # Try one more day back
            prev_date -= timedelta(days=1)
            while prev_date.weekday() >= 5:
                prev_date -= timedelta(days=1)
            prev_df = df[
                (df['symbol'] == symbol) & 
                (df['timestamp'].dt.date == prev_date)
            ]
        
        if len(prev_df) == 0:
            return 0, 0, 0, 0
        
        pdh = prev_df['high'].max()
        pdl = prev_df['low'].min()
        pdc = prev_df.iloc[-1]['close']
        
        # Calculate average green candle size
        green_candles = prev_df[prev_df['close'] > prev_df['open']]
        if len(green_candles) > 0:
            avg_green_size = (green_candles['close'] - green_candles['open']).mean()
        else:
            avg_green_size = 0
        
        return pdh, pdl, pdc, avg_green_size
    
    def _is_strong_green_candle(self, row: pd.Series) -> bool:
        """Check if candle is a strong green candle."""
        
        if row['close'] <= row['open']:
            return False
        
        candle_range = row['high'] - row['low']
        if candle_range == 0:
            return False
        
        body = row['close'] - row['open']
        body_ratio = body / candle_range
        
        upper_wick = row['high'] - row['close']
        lower_wick = row['open'] - row['low']
        upper_wick_ratio = upper_wick / candle_range
        lower_wick_ratio = lower_wick / candle_range
        
        return (
            body_ratio >= self.config.min_body_ratio and
            upper_wick_ratio <= self.config.max_wick_ratio and
            lower_wick_ratio <= self.config.max_wick_ratio
        )
    
    def _is_big_red_candle(self, row: pd.Series, reference_price: float) -> bool:
        """Check if candle is a big red candle (exit signal)."""
        
        if row['close'] >= row['open']:
            return False
        
        candle_range = row['high'] - row['low']
        if candle_range == 0:
            return False
        
        body = row['open'] - row['close']
        body_ratio = body / candle_range
        
        range_pct = (candle_range / reference_price) * 100
        
        return (
            body_ratio >= self.config.big_red_body_ratio and
            range_pct >= self.config.big_red_min_range_pct
        )
    
    def _check_oi_confirmation(
        self,
        df: pd.DataFrame,
        symbol: str,
        current_time: datetime,
    ) -> Tuple[bool, float]:
        """Check if OI is increasing with price."""
        
        # Get last hour of data
        lookback_start = current_time - timedelta(hours=1)
        recent = df[
            (df['symbol'] == symbol) &
            (df['timestamp'] >= lookback_start) &
            (df['timestamp'] <= current_time)
        ]
        
        if len(recent) < 5:
            return False, 0
        
        # Check if OI and price both increasing
        first_oi = recent.iloc[0]['oi']
        last_oi = recent.iloc[-1]['oi']
        first_close = recent.iloc[0]['close']
        last_close = recent.iloc[-1]['close']
        
        if first_oi == 0:
            return True, 0  # No OI data, accept anyway
        
        oi_change_pct = ((last_oi - first_oi) / first_oi) * 100
        price_up = last_close > first_close
        oi_up = oi_change_pct >= self.config.min_oi_change_pct
        
        return (price_up and oi_up), oi_change_pct
    
    def run_backtest(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Run backtest on given symbols and date range."""
        
        # Load data
        df = self.load_data(symbols, start_date, end_date)
        
        if len(df) == 0:
            logger.warning("No data loaded!")
            return {}
        
        # Process each symbol
        for symbol in symbols:
            logger.info(f"Processing {symbol}...")
            symbol_df = df[df['symbol'] == symbol].copy()
            symbol_df = symbol_df.sort_values('timestamp')
            
            self._process_symbol(symbol, symbol_df, df)
        
        # Calculate metrics
        return self._calculate_metrics()
    
    def _process_symbol(
        self,
        symbol: str,
        symbol_df: pd.DataFrame,
        full_df: pd.DataFrame,
    ):
        """Process a single symbol."""
        
        if symbol not in self.day_contexts:
            self.day_contexts[symbol] = {}
        
        # Group by date
        symbol_df['date'] = symbol_df['timestamp'].dt.date
        
        for trade_date, day_df in symbol_df.groupby('date'):
            day_df = day_df.sort_values('timestamp')
            
            if len(day_df) < 10:  # Skip incomplete days
                continue
            
            # Get previous day data
            pdh, pdl, pdc, prev_avg_green = self._get_prev_day_data(full_df, symbol, trade_date)
            
            if pdh == 0:
                continue
            
            # Initialize day context
            ctx = DayContext(
                date=trade_date,
                pdh=pdh,
                pdl=pdl,
                pdc=pdc,
                prev_day_avg_green_size=prev_avg_green,
            )
            
            self.day_contexts[symbol][trade_date] = ctx
            
            # Process each candle
            for idx, row in day_df.iterrows():
                self._process_candle(symbol, row, ctx, day_df, full_df)
            
            # Debug: Log filter status for this day
            logger.debug(
                f"{symbol} {trade_date}: Bulls={ctx.bulls_in_control}, "
                f"PDH_early={ctx.pdh_broken_early}, "
                f"GreenCandles={len(ctx.curr_day_green_candle_sizes)}, "
                f"Trade={'YES' if ctx.entry_time else 'NO'}"
            )
    
    def _process_candle(
        self,
        symbol: str,
        row: pd.Series,
        ctx: DayContext,
        day_df: pd.DataFrame,
        full_df: pd.DataFrame,
    ):
        """Process a single candle."""
        
        ts = row['timestamp']
        candle_time = ts.time()
        
        # Update day high/low
        ctx.day_high = max(ctx.day_high, row['high'])
        ctx.day_low = min(ctx.day_low, row['low'])
        
        # First candle logic
        if candle_time <= self.config.first_candle_end:
            ctx.first_candle_low = row['low']
            ctx.first_candle_high = row['high']
            ctx.first_candle_close = row['close']
            return
        
        # Check Filter 1: Bulls in control (first candle low = day low)
        if not ctx.bulls_in_control:
            ctx.bulls_in_control = (ctx.first_candle_low == ctx.day_low)
        
        # Track green candle sizes for expansion check
        if row['close'] > row['open']:
            ctx.curr_day_green_candle_sizes.append(row['close'] - row['open'])
        
        # Check Filter 3: PDH breakout by 9:35
        if candle_time <= self.config.pdh_breakout_deadline:
            if row['close'] > ctx.pdh:
                ctx.pdh_broken_early = True
        
        # If in position, manage trade
        if ctx.in_position:
            self._manage_position(symbol, row, ctx)
            return
        
        # Entry window check
        if candle_time < self.config.entry_window_start:
            return
        if candle_time > self.config.entry_window_end:
            return
        
        # Check all entry conditions
        entry_valid = self._check_entry_conditions(symbol, row, ctx, full_df)
        
        if entry_valid:
            self._enter_trade(symbol, row, ctx)
    
    def _check_entry_conditions(
        self,
        symbol: str,
        row: pd.Series,
        ctx: DayContext,
        full_df: pd.DataFrame,
    ) -> bool:
        """Check all entry conditions."""
        
        # Anti-churning: One trade per stock per day
        if self.config.one_trade_per_stock_per_day and ctx.traded_today:
            return False
        
        # Filter 1: Bulls in control
        if not ctx.bulls_in_control:
            return False
        
        # Filter 2: Candle expansion
        if len(ctx.curr_day_green_candle_sizes) < 3:
            return False
        
        avg_curr_green = np.mean(ctx.curr_day_green_candle_sizes)
        if ctx.prev_day_avg_green_size > 0:
            expansion = avg_curr_green / ctx.prev_day_avg_green_size
            if expansion < self.config.candle_expansion_factor:
                return False
        
        # Filter 3: PDH broken early
        if not ctx.pdh_broken_early:
            return False
        
        # Filter 4: OI confirmation (optional)
        if self.config.require_oi_confirmation:
            oi_ok, oi_change = self._check_oi_confirmation(full_df, symbol, row['timestamp'])
            if not oi_ok:
                return False
            ctx.oi_confirming = True
        
        # Filter 5: Indicator confirmation (optional)
        if not self._check_indicator_confirmation(row):
            return False
        
        # Entry candle quality: Strong green candle
        if not self._is_strong_green_candle(row):
            return False
        
        # Price must be above PDH (breakout confirmation)
        if row['close'] <= ctx.pdh:
            return False
        
        return True
    
    def _check_indicator_confirmation(self, row: pd.Series) -> bool:
        """Check indicator confirmation based on config."""
        
        mode = self.config.indicator_confirmation
        
        if mode == IndicatorConfirmation.NONE:
            return True
        
        if mode == IndicatorConfirmation.RSI_EMA:
            # RSI > 50 and EMA 9 > EMA 21
            rsi = row.get('rsi_14', 50)
            ema_9 = row.get('ema_9', 0)
            ema_21 = row.get('ema_21', 0)
            
            if pd.isna(rsi) or pd.isna(ema_9) or pd.isna(ema_21):
                return True  # Skip if indicators missing
            
            return rsi > self.config.rsi_threshold and ema_9 > ema_21
        
        if mode == IndicatorConfirmation.SUPERTREND:
            # Supertrend direction = 1 (bullish)
            supertrend_dir = row.get('supertrend_dir', 1)
            if pd.isna(supertrend_dir):
                return True
            return supertrend_dir == 1
        
        if mode == IndicatorConfirmation.ADX:
            # ADX > 25 and +DI > -DI
            adx = row.get('adx', 0)
            plus_di = row.get('plus_di', 0)
            minus_di = row.get('minus_di', 0)
            
            if pd.isna(adx) or pd.isna(plus_di) or pd.isna(minus_di):
                return True
            
            return adx > self.config.adx_threshold and plus_di > minus_di
        
        return True
    
    def _enter_trade(self, symbol: str, row: pd.Series, ctx: DayContext):
        """Execute entry - buy ATM CE option."""
        
        equity_price = row['close']
        entry_time = row['timestamp']
        
        # Find ATM CE option
        option_symbol = self.find_atm_ce_option(symbol, equity_price, entry_time)
        
        if option_symbol is None:
            logger.debug(f"{symbol} SKIP - No ATM CE option found at {equity_price:.2f}")
            return
        
        # Get option entry price
        option_price = self.get_option_price(option_symbol, entry_time)
        
        if option_price is None or option_price <= 0:
            logger.debug(f"{symbol} SKIP - No option price for {option_symbol}")
            return
        
        # Calculate quantity based on capital (minimum 1 lot = 1 for now)
        option_quantity = max(1, int(self.config.capital_per_trade / (option_price * 100)))
        
        ctx.in_position = True
        ctx.entry_price = equity_price
        ctx.entry_time = entry_time
        ctx.highest_since_entry = equity_price
        ctx.trailing_sl = equity_price * (1 - self.config.trailing_sl_pct / 100)
        
        # Option details
        ctx.option_symbol = option_symbol
        ctx.option_entry_price = option_price
        ctx.option_quantity = option_quantity
        
        logger.debug(
            f"{symbol} ENTRY at {entry_time} | Equity: {equity_price:.2f} | "
            f"Option: {option_symbol} @ {option_price:.2f}"
        )
    
    def _manage_position(self, symbol: str, row: pd.Series, ctx: DayContext):
        """Manage open position."""
        
        candle_time = row['timestamp'].time()
        
        # Update highest and trailing SL
        if row['high'] > ctx.highest_since_entry:
            ctx.highest_since_entry = row['high']
            ctx.trailing_sl = ctx.highest_since_entry * (1 - self.config.trailing_sl_pct / 100)
        
        exit_reason = None
        exit_price = None
        
        # Exit 1: Big red candle (momentum reversal) - optional
        if self.config.exit_on_big_red_candle and self._is_big_red_candle(row, ctx.entry_price):
            exit_reason = "BIG_RED_CANDLE"
            exit_price = row['close']
        
        # Exit 2: Trailing SL hit
        elif row['low'] <= ctx.trailing_sl:
            exit_reason = "TRAILING_SL"
            exit_price = ctx.trailing_sl
        
        # Exit 3: End of momentum window (12:00 PM)
        elif candle_time >= self.config.entry_window_end:
            exit_reason = "TIME_EXIT"
            exit_price = row['close']
        
        # Exit 4: End of day
        elif candle_time >= time(15, 15):
            exit_reason = "EOD_EXIT"
            exit_price = row['close']
        
        if exit_reason:
            self._exit_trade(symbol, row, ctx, exit_price, exit_reason)
    
    def _exit_trade(
        self,
        symbol: str,
        row: pd.Series,
        ctx: DayContext,
        exit_price: float,
        exit_reason: str,
    ):
        """Execute exit and record trade - sell CE option."""
        
        exit_time = row['timestamp']
        
        # Calculate equity-based P&L (for reference)
        quantity = int(self.config.capital_per_trade / ctx.entry_price)
        equity_pnl = (exit_price - ctx.entry_price) * quantity
        equity_pnl_pct = ((exit_price - ctx.entry_price) / ctx.entry_price) * 100
        
        # Get option exit price
        option_exit_price = 0
        option_pnl = 0
        option_pnl_pct = 0
        
        if ctx.option_symbol and ctx.option_entry_price > 0:
            option_exit_price = self.get_option_price(ctx.option_symbol, exit_time)
            
            if option_exit_price and option_exit_price > 0:
                option_pnl = (option_exit_price - ctx.option_entry_price) * ctx.option_quantity * 100
                option_pnl_pct = ((option_exit_price - ctx.option_entry_price) / ctx.option_entry_price) * 100
            else:
                # Fallback: estimate option P&L from equity movement (delta ~0.5 for ATM)
                option_pnl = equity_pnl * 2  # Approximate 2x leverage
                option_pnl_pct = equity_pnl_pct * 2
        
        trade = Trade(
            symbol=symbol,
            entry_time=ctx.entry_time,
            exit_time=exit_time,
            entry_price=ctx.entry_price,
            exit_price=exit_price,
            quantity=quantity,
            pnl=option_pnl if ctx.option_symbol else equity_pnl,  # Use option P&L if available
            pnl_pct=option_pnl_pct if ctx.option_symbol else equity_pnl_pct,
            exit_reason=exit_reason,
            pdh=ctx.pdh,
            # Option details
            option_symbol=ctx.option_symbol,
            option_entry_price=ctx.option_entry_price,
            option_exit_price=option_exit_price,
            option_pnl=option_pnl,
            option_pnl_pct=option_pnl_pct,
        )
        
        self.trades.append(trade)
        
        logger.debug(
            f"{symbol} EXIT ({exit_reason}) at {exit_time} | "
            f"Equity: {exit_price:.2f} ({equity_pnl_pct:+.2f}%) | "
            f"Option: {ctx.option_symbol} {option_exit_price:.2f} ({option_pnl_pct:+.2f}%)"
        )
        
        # Reset context
        ctx.in_position = False
        ctx.entry_price = 0
        ctx.entry_time = None
        ctx.option_symbol = None
        ctx.option_entry_price = 0
        ctx.option_quantity = 0
        ctx.traded_today = True  # Prevent re-entry on same day
    
    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate performance metrics."""
        
        if not self.trades:
            return {"error": "No trades generated"}
        
        trades_df = pd.DataFrame([{
            'symbol': t.symbol,
            'entry_time': t.entry_time,
            'exit_time': t.exit_time,
            'entry_price': t.entry_price,
            'exit_price': t.exit_price,
            'pnl': t.pnl,
            'pnl_pct': t.pnl_pct,
            'exit_reason': t.exit_reason,
        } for t in self.trades])
        
        total_trades = len(self.trades)
        winners = len([t for t in self.trades if t.pnl > 0])
        losers = len([t for t in self.trades if t.pnl <= 0])
        
        win_rate = (winners / total_trades) * 100 if total_trades > 0 else 0
        
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        total_pnl = sum(t.pnl for t in self.trades)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        
        avg_winner = gross_profit / winners if winners > 0 else 0
        avg_loser = gross_loss / losers if losers > 0 else 0
        
        # Sharpe (simplified - daily returns)
        pnl_series = pd.Series([t.pnl_pct for t in self.trades])
        sharpe = (pnl_series.mean() / pnl_series.std()) * np.sqrt(252) if len(pnl_series) > 1 and pnl_series.std() > 0 else 0
        
        # Max drawdown
        cumulative = np.cumsum([t.pnl for t in self.trades])
        running_max = np.maximum.accumulate(cumulative)
        drawdown = running_max - cumulative
        max_drawdown = drawdown.max()
        
        # Exit reason distribution
        exit_reasons = trades_df['exit_reason'].value_counts().to_dict()
        
        # Per-symbol breakdown
        symbol_stats = trades_df.groupby('symbol').agg({
            'pnl': ['count', 'sum', 'mean'],
            'pnl_pct': 'mean'
        }).round(2)
        
        metrics = {
            'total_trades': total_trades,
            'winners': winners,
            'losers': losers,
            'win_rate': round(win_rate, 2),
            'profit_factor': round(profit_factor, 2),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl': round(avg_pnl, 2),
            'avg_winner': round(avg_winner, 2),
            'avg_loser': round(avg_loser, 2),
            'sharpe_ratio': round(sharpe, 2),
            'max_drawdown': round(max_drawdown, 2),
            'exit_reasons': exit_reasons,
            'symbol_stats': {str(k): v for k, v in symbol_stats.to_dict().items()} if len(symbol_stats) > 0 else {},
            'trades': trades_df.to_dict('records'),
        }
        
        return metrics


@click.command()
@click.option('--symbols', required=True, help='Comma-separated symbols (e.g., RELIANCE,TCS,INFY)')
@click.option('--start', required=True, help='Start date (YYYY-MM-DD)')
@click.option('--end', required=True, help='End date (YYYY-MM-DD)')
@click.option('--output', default=None, help='Output file for results (JSON)')
@click.option('--indicator', default='none', type=click.Choice(['none', 'rsi_ema', 'supertrend', 'adx']), 
              help='Indicator confirmation mode')
def main(symbols: str, start: str, end: str, output: str, indicator: str):
    """Run Smart Money Momentum Strategy Backtest."""
    
    symbol_list = [s.strip().upper() for s in symbols.split(',')]
    start_date = datetime.strptime(start, '%Y-%m-%d').date()
    end_date = datetime.strptime(end, '%Y-%m-%d').date()
    
    # Create config with indicator confirmation
    indicator_mode = IndicatorConfirmation(indicator)
    config = StrategyConfig(indicator_confirmation=indicator_mode)
    
    logger.info(f"Backtesting Smart Money Momentum Strategy")
    logger.info(f"Symbols: {symbol_list}")
    logger.info(f"Period: {start_date} to {end_date}")
    logger.info(f"Indicator Confirmation: {indicator_mode.value}")
    
    # Run backtest
    backtester = SmartMoneyMomentumBacktest(config=config)
    results = backtester.run_backtest(symbol_list, start_date, end_date)
    
    # Print results
    print("\n" + "="*60)
    print("SMART MONEY MOMENTUM STRATEGY - BACKTEST RESULTS")
    print("="*60)
    
    if 'error' in results:
        print(f"Error: {results['error']}")
        return
    
    print(f"\nTotal Trades:    {results['total_trades']}")
    print(f"Winners:         {results['winners']}")
    print(f"Losers:          {results['losers']}")
    print(f"Win Rate:        {results['win_rate']:.1f}%")
    print(f"Profit Factor:   {results['profit_factor']:.2f}")
    print(f"Total P&L:       Rs.{results['total_pnl']:,.0f}")
    print(f"Avg P&L/Trade:   Rs.{results['avg_pnl']:,.0f}")
    print(f"Avg Winner:      Rs.{results['avg_winner']:,.0f}")
    print(f"Avg Loser:       Rs.{results['avg_loser']:,.0f}")
    print(f"Sharpe Ratio:    {results['sharpe_ratio']:.2f}")
    print(f"Max Drawdown:    Rs.{results['max_drawdown']:,.0f}")
    
    print(f"\nExit Reasons:")
    for reason, count in results['exit_reasons'].items():
        print(f"  {reason}: {count}")
    
    print("="*60)
    
    # Save to file if requested
    if output:
        import json
        with open(output, 'w') as f:
            # Convert non-serializable items
            results['trades'] = [
                {k: str(v) if isinstance(v, (datetime, date)) else v for k, v in t.items()}
                for t in results['trades']
            ]
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to {output}")


if __name__ == '__main__':
    main()
