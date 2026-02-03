"""
Backtesting Engine
KeepGaining Trading Platform

A comprehensive backtesting engine that:
- Loads historical data from SQLite database with pre-computed indicators
- Simulates order execution with realistic fills
- Tracks positions, P&L, and performance metrics
- Supports multiple strategies and symbols
- Generates detailed trade logs and analytics

Usage:
    engine = BacktestEngine()
    results = await engine.run_backtest(
        strategy=VolumeRocketStrategy(),
        symbols=["NSE:RELIANCE-EQ", "NSE:TCS-EQ"],
        start_date=date(2024, 6, 1),
        end_date=date(2024, 11, 30),
        initial_capital=1_000_000,
    )
"""

import asyncio
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type
from zoneinfo import ZoneInfo

import pandas as pd
import numpy as np

from app.services.strategy_engine import (
    BaseStrategy,
    Signal,
    SignalType,
    SignalStrength,
)

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class OrderSide(str, Enum):
    """Order side."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionSide(str, Enum):
    """Position direction."""
    LONG = "long"
    SHORT = "short"


@dataclass
class BacktestOrder:
    """Order in backtest simulation."""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: Decimal
    order_type: str = "MARKET"
    status: OrderStatus = OrderStatus.PENDING
    fill_price: Optional[Decimal] = None
    fill_time: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(IST))
    signal_id: Optional[str] = None


@dataclass
class BacktestPosition:
    """Open position in backtest."""
    position_id: str
    symbol: str
    side: PositionSide
    quantity: int
    entry_price: Decimal
    entry_time: datetime
    stop_loss: Decimal
    target: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    signal_id: Optional[str] = None
    strategy_name: str = ""


@dataclass
class BacktestTrade:
    """Completed trade record."""
    trade_id: str
    symbol: str
    side: PositionSide
    entry_price: Decimal
    exit_price: Decimal
    quantity: int
    entry_time: datetime
    exit_time: datetime
    pnl: Decimal
    pnl_percent: Decimal
    exit_reason: str  # "target", "stop_loss", "signal", "eod"
    strategy_name: str = ""
    holding_duration: timedelta = field(default_factory=timedelta)


@dataclass
class BacktestConfig:
    """Configuration for backtest run."""
    initial_capital: Decimal = Decimal("1000000")
    position_size_pct: Decimal = Decimal("5.0")  # % of capital per trade
    max_positions: int = 5
    slippage_pct: Decimal = Decimal("0.1")  # 0.1% slippage
    commission_per_trade: Decimal = Decimal("20")  # Flat fee per order
    allow_shorting: bool = False
    exit_at_eod: bool = True  # Exit all positions end of day
    trade_start_time: time = time(9, 20)  # 5 mins after market open
    trade_end_time: time = time(15, 15)  # 15 mins before close
    market_close_time: time = time(15, 30)


@dataclass
class BacktestMetrics:
    """Performance metrics for backtest."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    gross_profit: Decimal = Decimal("0")
    gross_loss: Decimal = Decimal("0")
    net_profit: Decimal = Decimal("0")
    profit_factor: float = 0.0
    
    max_drawdown: Decimal = Decimal("0")
    max_drawdown_pct: float = 0.0
    
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    avg_trade: Decimal = Decimal("0")
    largest_win: Decimal = Decimal("0")
    largest_loss: Decimal = Decimal("0")
    
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    
    total_commission: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")
    
    capital_used: Decimal = Decimal("0")
    return_pct: float = 0.0
    
    avg_holding_time: timedelta = field(default_factory=timedelta)
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0


@dataclass
class BacktestResult:
    """Complete backtest result."""
    strategy_name: str
    symbols: List[str]
    start_date: date
    end_date: date
    config: BacktestConfig
    metrics: BacktestMetrics
    trades: List[BacktestTrade]
    equity_curve: List[Tuple[datetime, Decimal]]
    signals_generated: int = 0
    signals_executed: int = 0


class BacktestEngine:
    """
    Main backtesting engine.
    
    Loads historical data from SQLite, simulates strategy execution,
    and calculates comprehensive performance metrics.
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        config: Optional[BacktestConfig] = None
    ):
        # Default DB path
        if db_path is None:
            db_path = str(Path(__file__).parent.parent.parent / "keepgaining.db")
        
        self.db_path = db_path
        self.config = config or BacktestConfig()
        
        # State
        self._capital = self.config.initial_capital
        self._positions: Dict[str, BacktestPosition] = {}
        self._orders: List[BacktestOrder] = []
        self._trades: List[BacktestTrade] = []
        self._equity_curve: List[Tuple[datetime, Decimal]] = []
        
        # Counters
        self._order_counter = 0
        self._position_counter = 0
        self._trade_counter = 0
        self._signals_generated = 0
        self._signals_executed = 0
        
        # Peak for drawdown calculation
        self._peak_equity = self.config.initial_capital
        self._max_drawdown = Decimal("0")
        
    def _load_candle_data(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """
        Load candle data with indicators from SQLite database.
        
        Returns DataFrame with columns:
            symbol, timestamp, open, high, low, close, volume, 
            + all indicator columns
        """
        logger.info(f"Loading data for {len(symbols)} symbols from {start_date} to {end_date}")
        
        conn = sqlite3.connect(self.db_path)
        
        # Symbols in DB are stored as "NSE:RELIANCE-EQ" format
        # Just use them directly
        placeholders = ",".join(["?" for _ in symbols])
        
        query = f"""
            SELECT * FROM candle_data
            WHERE symbol IN ({placeholders})
            AND date(timestamp) >= ?
            AND date(timestamp) <= ?
            ORDER BY symbol, timestamp
        """
        
        params = symbols + [start_date.isoformat(), end_date.isoformat()]
        
        try:
            df = pd.read_sql_query(query, conn, params=params)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            logger.info(f"Loaded {len(df)} candles for {df['symbol'].nunique()} symbols")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            return pd.DataFrame()
        finally:
            conn.close()
    
    def _get_candle_dict(self, row: pd.Series) -> Dict[str, Any]:
        """Convert DataFrame row to candle dictionary."""
        return {
            "timestamp": row["timestamp"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]) if pd.notna(row.get("volume")) else 0,
        }
    
    def _get_indicator_dict(self, row: pd.Series) -> Dict[str, Any]:
        """Extract indicator values from DataFrame row."""
        indicators = {}
        
        # Known indicator columns (from indicator_computation.py)
        indicator_cols = [
            # Moving averages
            "sma_9", "sma_20", "sma_50", "sma_200",
            "ema_9", "ema_20", "ema_50", "ema_200",
            "vwma_9", "vwma_20", "vwma_22", "vwma_31",
            # RSI
            "rsi_14", "rsi_7", "rsi_21",
            # MACD
            "macd", "macd_signal", "macd_histogram",
            # Bollinger Bands
            "bb_upper", "bb_middle", "bb_lower", "bb_width",
            # Supertrend
            "supertrend", "supertrend_direction",
            # ATR
            "atr_14", "atr_7", "atr_21",
            # Volume
            "volume_sma_20", "volume_ratio",
            # Pivots
            "pivot", "r1", "r2", "r3", "s1", "s2", "s3",
            # VWAP
            "vwap",
            # ADX
            "adx", "plus_di", "minus_di",
            # Stochastic
            "stoch_k", "stoch_d",
            # CCI
            "cci",
            # Williams %R
            "williams_r",
            # OBV
            "obv",
            # MFI
            "mfi",
        ]
        
        for col in indicator_cols:
            if col in row.index and pd.notna(row[col]):
                indicators[col] = float(row[col])
        
        # Also include any other numeric columns as potential indicators
        for col in row.index:
            if col not in ["symbol", "timestamp", "open", "high", "low", "close", "volume"]:
                if col not in indicators and pd.notna(row[col]):
                    try:
                        indicators[col] = float(row[col])
                    except (ValueError, TypeError):
                        pass
        
        return indicators
    
    def _apply_slippage(
        self,
        price: Decimal,
        side: OrderSide
    ) -> Decimal:
        """Apply slippage to order price."""
        slippage = price * (self.config.slippage_pct / Decimal("100"))
        if side == OrderSide.BUY:
            return price + slippage  # Worse price for buy
        return price - slippage  # Worse price for sell
    
    def _calculate_position_size(
        self,
        price: Decimal,
        signal: Signal
    ) -> int:
        """Calculate position size based on capital allocation."""
        allocation = self._capital * (Decimal(str(signal.quantity_pct)) / Decimal("100"))
        quantity = int(allocation / price)
        return max(1, quantity)
    
    def _execute_signal(
        self,
        signal: Signal,
        candle: Dict[str, Any]
    ) -> Optional[BacktestPosition]:
        """Execute a trading signal."""
        
        # Check if we can open new position
        if len(self._positions) >= self.config.max_positions:
            logger.debug(f"Max positions reached, skipping signal")
            return None
        
        # Check if already in position for this symbol
        if signal.symbol in self._positions:
            logger.debug(f"Already in position for {signal.symbol}")
            return None
        
        # Determine order side
        if signal.signal_type in [SignalType.LONG_ENTRY]:
            side = OrderSide.BUY
            pos_side = PositionSide.LONG
        elif signal.signal_type in [SignalType.SHORT_ENTRY]:
            if not self.config.allow_shorting:
                return None
            side = OrderSide.SELL
            pos_side = PositionSide.SHORT
        else:
            return None
        
        # Calculate fill price with slippage
        entry_price = self._apply_slippage(signal.entry_price, side)
        
        # Calculate quantity
        quantity = self._calculate_position_size(entry_price, signal)
        
        # Check capital
        required_capital = entry_price * quantity + self.config.commission_per_trade
        if required_capital > self._capital:
            logger.debug(f"Insufficient capital: need {required_capital}, have {self._capital}")
            return None
        
        # Create and fill order
        self._order_counter += 1
        order = BacktestOrder(
            order_id=f"ORD-{self._order_counter:06d}",
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            price=signal.entry_price,
            fill_price=entry_price,
            fill_time=candle["timestamp"],
            status=OrderStatus.FILLED,
            signal_id=signal.signal_id,
        )
        self._orders.append(order)
        
        # Deduct capital and commission
        self._capital -= (entry_price * quantity + self.config.commission_per_trade)
        
        # Create position
        self._position_counter += 1
        # Convert timestamp to naive datetime for consistency
        entry_timestamp = candle["timestamp"]
        if hasattr(entry_timestamp, 'to_pydatetime'):
            entry_timestamp = entry_timestamp.to_pydatetime().replace(tzinfo=None)
        elif hasattr(entry_timestamp, 'tzinfo') and entry_timestamp.tzinfo:
            entry_timestamp = entry_timestamp.replace(tzinfo=None)
            
        position = BacktestPosition(
            position_id=f"POS-{self._position_counter:06d}",
            symbol=signal.symbol,
            side=pos_side,
            quantity=quantity,
            entry_price=entry_price,
            entry_time=entry_timestamp,
            stop_loss=signal.stop_loss,
            target=signal.target_price,
            signal_id=signal.signal_id,
            strategy_name=signal.strategy_name,
        )
        
        self._positions[signal.symbol] = position
        self._signals_executed += 1
        
        logger.debug(
            f"Opened {pos_side.value} position: {signal.symbol} "
            f"qty={quantity} @ {entry_price}"
        )
        
        return position
    
    def _check_exits(
        self,
        candle: Dict[str, Any],
        symbol: str
    ) -> Optional[BacktestTrade]:
        """Check if any position should be exited."""
        
        if symbol not in self._positions:
            return None
        
        position = self._positions[symbol]
        current_price = Decimal(str(candle["close"]))
        high = Decimal(str(candle["high"]))
        low = Decimal(str(candle["low"]))
        
        exit_price = None
        exit_reason = None
        
        if position.side == PositionSide.LONG:
            # Check stop loss (use low)
            if low <= position.stop_loss:
                exit_price = position.stop_loss
                exit_reason = "stop_loss"
            # Check target (use high)
            elif high >= position.target:
                exit_price = position.target
                exit_reason = "target"
                
        else:  # SHORT
            # Check stop loss (use high)
            if high >= position.stop_loss:
                exit_price = position.stop_loss
                exit_reason = "stop_loss"
            # Check target (use low)
            elif low <= position.target:
                exit_price = position.target
                exit_reason = "target"
        
        if exit_price:
            # Convert timestamp to naive datetime
            exit_timestamp = candle["timestamp"]
            if hasattr(exit_timestamp, 'to_pydatetime'):
                exit_timestamp = exit_timestamp.to_pydatetime().replace(tzinfo=None)
            elif hasattr(exit_timestamp, 'tzinfo') and exit_timestamp.tzinfo:
                exit_timestamp = exit_timestamp.replace(tzinfo=None)
            return self._close_position(position, exit_price, exit_reason, exit_timestamp)
        
        return None
    
    def _close_position(
        self,
        position: BacktestPosition,
        exit_price: Decimal,
        exit_reason: str,
        exit_time: datetime
    ) -> BacktestTrade:
        """Close a position and record the trade."""
        
        # Apply slippage on exit
        if position.side == PositionSide.LONG:
            exit_price = self._apply_slippage(exit_price, OrderSide.SELL)
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            exit_price = self._apply_slippage(exit_price, OrderSide.BUY)
            pnl = (position.entry_price - exit_price) * position.quantity
        
        # Deduct commission
        pnl -= self.config.commission_per_trade
        
        # Return capital + P&L
        self._capital += (position.entry_price * position.quantity) + pnl
        
        # Calculate P&L percentage
        pnl_pct = (pnl / (position.entry_price * position.quantity)) * 100
        
        # Record trade
        self._trade_counter += 1
        trade = BacktestTrade(
            trade_id=f"TRD-{self._trade_counter:06d}",
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            entry_time=position.entry_time,
            exit_time=exit_time,
            pnl=pnl,
            pnl_percent=Decimal(str(round(pnl_pct, 2))),
            exit_reason=exit_reason,
            strategy_name=position.strategy_name,
            holding_duration=exit_time - position.entry_time,
        )
        self._trades.append(trade)
        
        # Remove position
        del self._positions[position.symbol]
        
        logger.debug(
            f"Closed {position.side.value}: {position.symbol} "
            f"pnl={pnl:.2f} ({pnl_pct:.2f}%) reason={exit_reason}"
        )
        
        return trade
    
    def _close_all_positions_eod(self, candle_time: datetime) -> List[BacktestTrade]:
        """Close all positions at end of day."""
        trades = []
        
        # Get all symbols with positions
        symbols = list(self._positions.keys())
        
        for symbol in symbols:
            position = self._positions[symbol]
            # Use entry price as exit (simplified - in reality would use close)
            # For proper EOD, we'd need the last candle's close
            exit_price = position.entry_price  # Placeholder
            trade = self._close_position(position, exit_price, "eod", candle_time)
            trades.append(trade)
        
        return trades
    
    def _update_equity_curve(self, timestamp: datetime):
        """Update equity curve with current portfolio value."""
        total_value = self._capital
        
        # Add unrealized P&L from open positions
        # Note: In real implementation, we'd need current prices
        for position in self._positions.values():
            total_value += position.entry_price * position.quantity
        
        self._equity_curve.append((timestamp, total_value))
        
        # Update peak and drawdown
        if total_value > self._peak_equity:
            self._peak_equity = total_value
        
        drawdown = self._peak_equity - total_value
        if drawdown > self._max_drawdown:
            self._max_drawdown = drawdown
    
    def _calculate_metrics(self) -> BacktestMetrics:
        """Calculate performance metrics from trades."""
        metrics = BacktestMetrics()
        
        if not self._trades:
            return metrics
        
        # Basic trade stats
        metrics.total_trades = len(self._trades)
        
        wins = [t for t in self._trades if t.pnl > 0]
        losses = [t for t in self._trades if t.pnl <= 0]
        
        metrics.winning_trades = len(wins)
        metrics.losing_trades = len(losses)
        metrics.win_rate = len(wins) / len(self._trades) * 100 if self._trades else 0
        
        # P&L stats
        metrics.gross_profit = sum(t.pnl for t in wins) if wins else Decimal("0")
        metrics.gross_loss = abs(sum(t.pnl for t in losses)) if losses else Decimal("0")
        metrics.net_profit = metrics.gross_profit - metrics.gross_loss
        
        if metrics.gross_loss > 0:
            metrics.profit_factor = float(metrics.gross_profit / metrics.gross_loss)
        
        # Average stats
        if wins:
            metrics.avg_win = metrics.gross_profit / len(wins)
            metrics.largest_win = max(t.pnl for t in wins)
        if losses:
            metrics.avg_loss = metrics.gross_loss / len(losses)
            metrics.largest_loss = min(t.pnl for t in losses)
        
        metrics.avg_trade = metrics.net_profit / len(self._trades)
        
        # Drawdown
        metrics.max_drawdown = self._max_drawdown
        if self._peak_equity > 0:
            metrics.max_drawdown_pct = float(
                (self._max_drawdown / self._peak_equity) * 100
            )
        
        # Commission and slippage
        metrics.total_commission = self.config.commission_per_trade * len(self._trades) * 2
        
        # Holding time
        if self._trades:
            total_duration = sum(
                (t.holding_duration for t in self._trades),
                timedelta()
            )
            metrics.avg_holding_time = total_duration / len(self._trades)
        
        # Consecutive wins/losses
        current_streak = 0
        is_winning = None
        max_win_streak = 0
        max_loss_streak = 0
        
        for trade in self._trades:
            if trade.pnl > 0:
                if is_winning:
                    current_streak += 1
                else:
                    current_streak = 1
                    is_winning = True
                max_win_streak = max(max_win_streak, current_streak)
            else:
                if not is_winning:
                    current_streak += 1
                else:
                    current_streak = 1
                    is_winning = False
                max_loss_streak = max(max_loss_streak, current_streak)
        
        metrics.max_consecutive_wins = max_win_streak
        metrics.max_consecutive_losses = max_loss_streak
        
        # Returns
        metrics.capital_used = self.config.initial_capital
        if self._equity_curve:
            final_value = self._equity_curve[-1][1]
            metrics.return_pct = float(
                ((final_value - self.config.initial_capital) / self.config.initial_capital) * 100
            )
        
        # Sharpe Ratio (simplified - daily returns)
        if len(self._equity_curve) > 1:
            returns = []
            for i in range(1, len(self._equity_curve)):
                prev_val = float(self._equity_curve[i-1][1])
                curr_val = float(self._equity_curve[i][1])
                if prev_val > 0:
                    returns.append((curr_val - prev_val) / prev_val)
            
            if returns:
                avg_return = np.mean(returns)
                std_return = np.std(returns)
                if std_return > 0:
                    # Annualized (assuming 252 trading days)
                    metrics.sharpe_ratio = (avg_return / std_return) * np.sqrt(252)
        
        return metrics
    
    async def run_backtest(
        self,
        strategy: BaseStrategy,
        symbols: List[str],
        start_date: date,
        end_date: date,
        config: Optional[BacktestConfig] = None
    ) -> BacktestResult:
        """
        Run backtest for a strategy over historical data.
        
        Args:
            strategy: Strategy instance to test
            symbols: List of symbols to trade
            start_date: Backtest start date
            end_date: Backtest end date
            config: Optional backtest configuration
            
        Returns:
            BacktestResult with performance metrics and trade history
        """
        if config:
            self.config = config
        
        # Reset state
        self._capital = self.config.initial_capital
        self._positions = {}
        self._orders = []
        self._trades = []
        self._equity_curve = [(datetime.combine(start_date, time(9, 15), IST), self._capital)]
        self._peak_equity = self._capital
        self._max_drawdown = Decimal("0")
        self._signals_generated = 0
        self._signals_executed = 0
        
        logger.info(f"Starting backtest: {strategy.name} on {len(symbols)} symbols")
        logger.info(f"Period: {start_date} to {end_date}")
        logger.info(f"Initial capital: {self.config.initial_capital}")
        
        # Load historical data
        df = self._load_candle_data(symbols, start_date, end_date)
        
        if df.empty:
            logger.warning("No data loaded for backtest")
            return BacktestResult(
                strategy_name=strategy.name,
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                config=self.config,
                metrics=BacktestMetrics(),
                trades=[],
                equity_curve=[],
            )
        
        # Process candles chronologically
        current_date = None
        
        for idx, row in df.iterrows():
            timestamp = row["timestamp"]
            symbol = row["symbol"]
            
            # Symbol is already in correct format: NSE:RELIANCE-EQ
            trading_symbol = symbol
            
            # Get candle and indicators
            candle = self._get_candle_dict(row)
            indicators = self._get_indicator_dict(row)
            
            # Check for end of day
            if current_date and timestamp.date() != current_date:
                if self.config.exit_at_eod and self._positions:
                    # Close all positions at previous day's end
                    # Use a naive datetime for compatibility
                    eod_time = datetime.combine(current_date, self.config.market_close_time)
                    for pos_symbol in list(self._positions.keys()):
                        pos = self._positions[pos_symbol]
                        self._close_position(pos, pos.entry_price, "eod", eod_time)
                
                self._update_equity_curve(timestamp)
            
            current_date = timestamp.date()
            
            # Check trading hours
            current_time = timestamp.time()
            if not (self.config.trade_start_time <= current_time <= self.config.trade_end_time):
                continue
            
            # Check exits first
            trade = self._check_exits(candle, trading_symbol)
            
            # Evaluate strategy for new signals
            try:
                signal = await strategy.evaluate(
                    symbol=trading_symbol,
                    timeframe="1m",  # Assuming 1m data
                    indicators=indicators,
                    candle=candle
                )
                
                if signal:
                    self._signals_generated += 1
                    self._execute_signal(signal, candle)
                    
            except Exception as e:
                logger.error(f"Strategy evaluation error: {e}")
        
        # Close remaining positions at end
        if self._positions:
            last_time = df["timestamp"].iloc[-1] if not df.empty else datetime.now(IST)
            for pos_symbol in list(self._positions.keys()):
                pos = self._positions[pos_symbol]
                self._close_position(pos, pos.entry_price, "end_of_backtest", last_time)
        
        # Final equity update
        if not df.empty:
            self._update_equity_curve(df["timestamp"].iloc[-1])
        
        # Calculate metrics
        metrics = self._calculate_metrics()
        
        logger.info(f"Backtest complete: {metrics.total_trades} trades, "
                   f"Net P&L: {metrics.net_profit:.2f}, "
                   f"Win Rate: {metrics.win_rate:.1f}%")
        
        return BacktestResult(
            strategy_name=strategy.name,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            config=self.config,
            metrics=metrics,
            trades=self._trades.copy(),
            equity_curve=self._equity_curve.copy(),
            signals_generated=self._signals_generated,
            signals_executed=self._signals_executed,
        )


def format_backtest_report(result: BacktestResult) -> str:
    """Format backtest result as readable report."""
    m = result.metrics
    
    report = f"""
╔══════════════════════════════════════════════════════════════╗
║                    BACKTEST REPORT                            ║
╠══════════════════════════════════════════════════════════════╣
║ Strategy: {result.strategy_name:<50} ║
║ Period: {result.start_date} to {result.end_date:<35} ║
║ Symbols: {len(result.symbols):<51} ║
╠══════════════════════════════════════════════════════════════╣
║                   PERFORMANCE SUMMARY                         ║
╠══════════════════════════════════════════════════════════════╣
║ Initial Capital:     ₹{float(result.config.initial_capital):>15,.2f}                 ║
║ Net Profit:          ₹{float(m.net_profit):>15,.2f}                 ║
║ Return:              {m.return_pct:>15.2f}%                 ║
║ Max Drawdown:        {m.max_drawdown_pct:>15.2f}%                 ║
╠══════════════════════════════════════════════════════════════╣
║                    TRADE STATISTICS                           ║
╠══════════════════════════════════════════════════════════════╣
║ Total Trades:        {m.total_trades:>15}                   ║
║ Winning Trades:      {m.winning_trades:>15}                   ║
║ Losing Trades:       {m.losing_trades:>15}                   ║
║ Win Rate:            {m.win_rate:>15.2f}%                 ║
║ Profit Factor:       {m.profit_factor:>15.2f}                   ║
╠══════════════════════════════════════════════════════════════╣
║ Gross Profit:        ₹{float(m.gross_profit):>15,.2f}                 ║
║ Gross Loss:          ₹{float(m.gross_loss):>15,.2f}                 ║
║ Avg Win:             ₹{float(m.avg_win):>15,.2f}                 ║
║ Avg Loss:            ₹{float(m.avg_loss):>15,.2f}                 ║
║ Largest Win:         ₹{float(m.largest_win):>15,.2f}                 ║
║ Largest Loss:        ₹{float(m.largest_loss):>15,.2f}                 ║
╠══════════════════════════════════════════════════════════════╣
║ Sharpe Ratio:        {m.sharpe_ratio:>15.2f}                   ║
║ Max Win Streak:      {m.max_consecutive_wins:>15}                   ║
║ Max Loss Streak:     {m.max_consecutive_losses:>15}                   ║
║ Avg Holding Time:    {str(m.avg_holding_time):>15}                   ║
╠══════════════════════════════════════════════════════════════╣
║ Signals Generated:   {result.signals_generated:>15}                   ║
║ Signals Executed:    {result.signals_executed:>15}                   ║
╚══════════════════════════════════════════════════════════════╝
"""
    return report
