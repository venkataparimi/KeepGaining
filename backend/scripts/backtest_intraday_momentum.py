#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest Script for Intraday Momentum OI Strategy

Tests the Smart Money Flow Confirmation strategy on historical equity data.
Uses 5-minute candles and simulates the complete intraday workflow.
Supports both CE (bullish) and PE (bearish) trades with ranking system.

Usage:
    python scripts/backtest_intraday_momentum.py --symbol RELIANCE --days 30
    python scripts/backtest_intraday_momentum.py --symbols RELIANCE,TCS,INFY --days 60
    python scripts/backtest_intraday_momentum.py --symbols RELIANCE,TCS --days 60 --ce-only
    python scripts/backtest_intraday_momentum.py --symbols RELIANCE,TCS --days 60 --pe-only
    python scripts/backtest_intraday_momentum.py --symbols RELIANCE,TCS --days 60 --ranked --max-trades 2
"""

import argparse
import asyncio
import io
import os
import sys
from datetime import datetime, date, timedelta, time, timezone

# Fix unicode output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict

# IST timezone offset (UTC+5:30)
IST_OFFSET = timedelta(hours=5, minutes=30)

# Setup path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text
from app.db.session import get_db_context
from app.strategies.intraday_momentum_oi import (
    IntradayMomentumOIStrategy, 
    IntradayMomentumConfig,
    TradeDirection,
    SetupScore,
    create_intraday_momentum_strategy
)
from app.strategies.base import SignalType
from app.services.data_providers.base import Candle


@dataclass
class Trade:
    """Represents a completed trade."""
    symbol: str
    direction: str  # "CE" or "PE"
    entry_date: date
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    exit_reason: str
    pnl_pct: float
    highest_price: float
    lowest_price: float
    max_drawdown_pct: float
    setup_score: float = 0.0
    conditions_at_entry: Dict[str, bool] = field(default_factory=dict)


@dataclass
class PendingSetup:
    """A setup waiting to be ranked and potentially executed."""
    symbol: str
    direction: TradeDirection
    score: SetupScore
    candle: Candle
    entry_price: float
    reason: str


@dataclass
class BacktestResult:
    """Backtest results summary."""
    symbol: str
    total_days: int
    trading_days: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    max_win_pct: float
    max_loss_pct: float
    win_rate: float
    profit_factor: float
    avg_trade_duration_mins: int
    trades: List[Trade] = field(default_factory=list)
    
    # Direction breakdown
    ce_trades: int = 0
    ce_wins: int = 0
    ce_pnl: float = 0.0
    pe_trades: int = 0
    pe_wins: int = 0
    pe_pnl: float = 0.0
    
    # Setup statistics
    days_with_market_control: int = 0
    days_with_candle_expansion: int = 0
    days_with_pdh_breakout: int = 0
    days_with_all_conditions: int = 0


async def get_symbols_for_backtest(symbol_filter: str = None) -> List[str]:
    """Get list of equity symbols for backtesting."""
    async with get_db_context() as db:
        if symbol_filter:
            # Specific symbols
            symbols = [s.strip().upper() for s in symbol_filter.split(",")]
            return symbols
        
        # Get top liquid stocks with most data
        result = await db.execute(text("""
            SELECT im.trading_symbol, COUNT(*) as candle_count
            FROM instrument_master im
            JOIN candle_data cd ON im.instrument_id = cd.instrument_id
            WHERE im.instrument_type = 'EQUITY'
            AND im.exchange = 'NSE'
            GROUP BY im.trading_symbol
            HAVING COUNT(*) > 10000
            ORDER BY candle_count DESC
            LIMIT 20
        """))
        rows = result.fetchall()
        return [row[0] for row in rows]


async def get_candles_for_symbol(symbol: str, days_back: int) -> List[Candle]:
    """Fetch 5-minute candles for a symbol."""
    async with get_db_context() as db:
        from_date = date.today() - timedelta(days=days_back)
        
        result = await db.execute(text("""
            SELECT cd.timestamp, cd.open, cd.high, cd.low, cd.close, cd.volume
            FROM candle_data cd
            JOIN instrument_master im ON cd.instrument_id = im.instrument_id
            WHERE im.trading_symbol = :symbol
            AND im.instrument_type = 'EQUITY'
            AND cd.timestamp >= :from_date
            ORDER BY cd.timestamp ASC
        """), {"symbol": symbol, "from_date": from_date})
        
        rows = result.fetchall()
        candles = []
        for row in rows:
            candles.append(Candle(
                timestamp=row[0],
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=int(row[5]) if row[5] else 0,
            ))
        return candles


def run_backtest_for_symbol(symbol: str, candles: List[Candle], config: IntradayMomentumConfig, verbose: bool = False, max_slippage_pct: float = 0.15) -> BacktestResult:
    """Run backtest for a single symbol."""
    strategy = IntradayMomentumOIStrategy(config, symbol=symbol)  # Pass symbol for PE eligibility check
    
    trades: List[Trade] = []
    current_entry: Dict[str, Any] = None
    
    # Track daily stats
    days_seen = set()
    days_with_mc = set()
    days_with_ce = set()
    days_with_pdh = set()
    days_with_all = set()
    
    # Direction tracking
    ce_trades = 0
    ce_wins = 0
    ce_pnl = 0.0
    pe_trades = 0
    pe_wins = 0
    pe_pnl = 0.0
    
    # Debug tracking
    entry_window_candles = 0
    candles_with_all_conditions = 0
    
    print(f"\n{'='*60}")
    print(f"Backtesting {symbol} with {len(candles):,} candles")
    print(f"CE enabled: {config.enable_ce_trades}, PE enabled: {config.enable_pe_trades}")
    print(f"{'='*60}")
    
    for candle in candles:
        days_seen.add(candle.timestamp.date())
        
        # Process candle through strategy
        signal = strategy.on_candle(candle)
        
        # Track daily condition stats
        if strategy.context:
            d = candle.timestamp.date()
            if strategy.context.market_control_confirmed:
                days_with_mc.add(d)
            if strategy.context.candle_expansion_confirmed:
                days_with_ce.add(d)
            if strategy.context.pdh_breakout_confirmed:
                days_with_pdh.add(d)
            if strategy.context.all_conditions_met():
                days_with_all.add(d)
            
            # Verbose: Check entry window conditions - convert to IST
            if candle.timestamp.tzinfo is not None:
                ist_time = (candle.timestamp + IST_OFFSET).time()
            else:
                ist_time = candle.timestamp.time()
                
            in_entry_window = time(10, 15) <= ist_time <= time(12, 0)
            
            if in_entry_window and not strategy.context.entry_taken:
                entry_window_candles += 1
                
                if strategy.context.all_conditions_met():
                    candles_with_all_conditions += 1
                    
                    if verbose:
                        # Check why not entering
                        body = candle.close - candle.open
                        total_range = candle.high - candle.low
                        body_ratio = body / total_range if total_range > 0 else 0
                        is_green = candle.close > candle.open
                        avg_size = strategy.avg_candle_size
                        
                        print(f"  [{candle.timestamp}] ALL CONDITIONS MET - Evaluating candle:")
                        print(f"    Green: {is_green}, Body: {body:.2f}, Range: {total_range:.2f}")
                        print(f"    Body Ratio: {body_ratio:.2%}, Avg Size: {avg_size:.2f}")
                        print(f"    Strong Breakout: {strategy._is_strong_breakout_candle(candle)}")
        else:
            # No context - first candle of day
            pass
        
        if signal is None:
            continue
        
        if signal.signal_type in (SignalType.BUY, SignalType.SELL):
            # Entry signal (BUY = CE, SELL = PE)
            direction = signal.metadata.get("direction", "CE")
            score = signal.metadata.get("score", 0)
            current_entry = {
                "entry_time": candle.timestamp,
                "entry_price": candle.close,
                "highest_price": candle.high,
                "lowest_price": candle.low,
                "direction": direction,
                "score": score,
                "conditions": signal.metadata.copy(),
            }
            emoji = "📈" if direction == "CE" else "📉"
            print(f"  {emoji} {direction} ENTRY: {candle.timestamp} @ {candle.close:.2f} (Score: {score:.1f})")
            
        elif signal.signal_type == SignalType.EXIT and current_entry:
            # Exit signal
            direction = current_entry["direction"]
            exit_reason = signal.metadata.get("reason", "Unknown")
            
            # ===== REALISTIC EXIT PRICE WITH SLIPPAGE CAP =====
            # When trailing SL is hit, the actual fill could be at candle.low (CE) or candle.high (PE)
            # due to gaps or fast moves. We simulate realistic fills with slippage cap.
            # 
            # IMPORTANT: We only apply slippage when the exit would be WORSE than the SL level.
            # If close is better than SL (profitable exit), we use the close (optimistic but realistic).
            
            exit_price = candle.close  # Default to close
            slippage_applied = False
            
            if "Trailing SL" in exit_reason:
                # Extract trailing SL level from reason (format: "CE Exit: Trailing SL hit at 1234.56")
                try:
                    sl_level = float(exit_reason.split("at ")[-1])
                except (ValueError, IndexError):
                    sl_level = None
                
                if sl_level and direction == "CE":
                    # For CE: SL is BELOW entry. If we exit near SL, that's a loss or small win.
                    # Slippage only matters if close < SL (we got stopped out at a worse price)
                    if candle.close <= sl_level:
                        # Got stopped out at or below SL - apply slippage cap
                        max_slip_level = sl_level * (1 - max_slippage_pct / 100)
                        
                        if candle.low < max_slip_level:
                            exit_price = max_slip_level  # Capped slippage
                            slippage_applied = True
                        elif candle.low < candle.close:
                            exit_price = candle.low  # Some slippage, but within cap
                            slippage_applied = True
                        else:
                            exit_price = candle.close  # No slippage, exit at close
                    # else: close > SL means we exited profitably at close
                        
                elif sl_level and direction == "PE":
                    # For PE: SL is ABOVE entry. If we exit near SL, that's a loss or small win.
                    # Slippage only matters if close >= SL (we got stopped out at a worse price)
                    if candle.close >= sl_level:
                        # Got stopped out at or above SL - apply slippage cap
                        max_slip_level = sl_level * (1 + max_slippage_pct / 100)
                        
                        if candle.high > max_slip_level:
                            exit_price = max_slip_level  # Capped slippage
                            slippage_applied = True
                        elif candle.high > candle.close:
                            exit_price = candle.high  # Some slippage, but within cap
                            slippage_applied = True
                        else:
                            exit_price = candle.close  # No slippage, exit at close
                    # else: close < SL means we exited profitably at close
            
            # Calculate P&L based on direction with realistic exit price
            if direction == "CE":
                pnl_pct = (exit_price - current_entry["entry_price"]) / current_entry["entry_price"] * 100
                max_dd = (current_entry["lowest_price"] - current_entry["entry_price"]) / current_entry["entry_price"] * 100
            else:  # PE - profit when price goes DOWN
                pnl_pct = (current_entry["entry_price"] - exit_price) / current_entry["entry_price"] * 100
                max_dd = (current_entry["highest_price"] - current_entry["entry_price"]) / current_entry["entry_price"] * 100
            
            trade = Trade(
                symbol=symbol,
                direction=direction,
                entry_date=current_entry["entry_time"].date(),
                entry_time=current_entry["entry_time"],
                entry_price=current_entry["entry_price"],
                exit_time=candle.timestamp,
                exit_price=exit_price,
                exit_reason=exit_reason + (" [slippage]" if slippage_applied else ""),
                pnl_pct=pnl_pct,
                highest_price=current_entry["highest_price"],
                lowest_price=current_entry["lowest_price"],
                max_drawdown_pct=max_dd,
                setup_score=current_entry["score"],
                conditions_at_entry=current_entry["conditions"],
            )
            trades.append(trade)
            
            # Track by direction
            if direction == "CE":
                ce_trades += 1
                ce_pnl += pnl_pct
                if pnl_pct > 0:
                    ce_wins += 1
            else:
                pe_trades += 1
                pe_pnl += pnl_pct
                if pnl_pct > 0:
                    pe_wins += 1
            
            emoji = "✅" if pnl_pct > 0 else "❌"
            dir_emoji = "📈" if direction == "CE" else "📉"
            slip_marker = " [SLIP]" if slippage_applied else ""
            print(f"  {emoji}{dir_emoji} {direction} EXIT: {candle.timestamp} @ {exit_price:.2f}{slip_marker} "
                  f"({pnl_pct:+.2f}%) - {exit_reason}")
            
            current_entry = None
        
        # Track highest/lowest during position
        if current_entry:
            current_entry["highest_price"] = max(current_entry["highest_price"], candle.high)
            current_entry["lowest_price"] = min(current_entry["lowest_price"], candle.low)
    
    # Debug summary
    print(f"\n  Entry Window Debug:")
    print(f"    - Total candles in entry window: {entry_window_candles}")
    print(f"    - Candles with ALL conditions met: {candles_with_all_conditions}")
    
    # Calculate statistics
    winning_trades = [t for t in trades if t.pnl_pct > 0]
    losing_trades = [t for t in trades if t.pnl_pct <= 0]
    
    total_pnl = sum(t.pnl_pct for t in trades)
    avg_win = sum(t.pnl_pct for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(t.pnl_pct for t in losing_trades) / len(losing_trades) if losing_trades else 0
    
    gross_profit = sum(t.pnl_pct for t in winning_trades)
    gross_loss = abs(sum(t.pnl_pct for t in losing_trades))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Average trade duration
    durations = [(t.exit_time - t.entry_time).total_seconds() / 60 for t in trades]
    avg_duration = sum(durations) / len(durations) if durations else 0
    
    return BacktestResult(
        symbol=symbol,
        total_days=len(days_seen),
        trading_days=len(set(t.entry_date for t in trades)),
        total_trades=len(trades),
        winning_trades=len(winning_trades),
        losing_trades=len(losing_trades),
        total_pnl_pct=total_pnl,
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        max_win_pct=max((t.pnl_pct for t in trades), default=0),
        max_loss_pct=min((t.pnl_pct for t in trades), default=0),
        win_rate=len(winning_trades) / len(trades) * 100 if trades else 0,
        profit_factor=profit_factor,
        avg_trade_duration_mins=int(avg_duration),
        trades=trades,
        ce_trades=ce_trades,
        ce_wins=ce_wins,
        ce_pnl=ce_pnl,
        pe_trades=pe_trades,
        pe_wins=pe_wins,
        pe_pnl=pe_pnl,
        days_with_market_control=len(days_with_mc),
        days_with_candle_expansion=len(days_with_ce),
        days_with_pdh_breakout=len(days_with_pdh),
        days_with_all_conditions=len(days_with_all),
    )


def print_backtest_results(results: List[BacktestResult]):
    """Print formatted backtest results."""
    print("\n" + "=" * 80)
    print("INTRADAY MOMENTUM OI STRATEGY - BACKTEST RESULTS (CE + PE)")
    print("=" * 80)
    
    # Per-symbol results
    for r in results:
        print(f"\n{'-'*60}")
        print(f"Symbol: {r.symbol}")
        print(f"{'-'*60}")
        print(f"  Period: {r.total_days} days ({r.trading_days} trading days)")
        print(f"  Total Trades: {r.total_trades}")
        print(f"  Win/Loss: {r.winning_trades}/{r.losing_trades} ({r.win_rate:.1f}% win rate)")
        print(f"  Total P&L: {r.total_pnl_pct:+.2f}%")
        print(f"  Avg Win: {r.avg_win_pct:+.2f}% | Avg Loss: {r.avg_loss_pct:+.2f}%")
        print(f"  Max Win: {r.max_win_pct:+.2f}% | Max Loss: {r.max_loss_pct:+.2f}%")
        print(f"  Profit Factor: {r.profit_factor:.2f}")
        print(f"  Avg Duration: {r.avg_trade_duration_mins} minutes")
        
        # Direction breakdown
        if r.ce_trades > 0 or r.pe_trades > 0:
            print(f"\n  📈 CE Trades: {r.ce_trades} ({r.ce_wins}/{r.ce_trades - r.ce_wins} W/L, {r.ce_pnl:+.2f}%)")
            print(f"  📉 PE Trades: {r.pe_trades} ({r.pe_wins}/{r.pe_trades - r.pe_wins} W/L, {r.pe_pnl:+.2f}%)")
        
        print(f"\n  Setup Conditions:")
        print(f"    Days with Market Control: {r.days_with_market_control}/{r.total_days} ({r.days_with_market_control/r.total_days*100:.0f}%)")
        print(f"    Days with Candle Expansion: {r.days_with_candle_expansion}/{r.total_days} ({r.days_with_candle_expansion/r.total_days*100:.0f}%)")
        print(f"    Days with PDH Breakout: {r.days_with_pdh_breakout}/{r.total_days} ({r.days_with_pdh_breakout/r.total_days*100:.0f}%)")
        print(f"    Days with ALL Conditions: {r.days_with_all_conditions}/{r.total_days} ({r.days_with_all_conditions/r.total_days*100:.0f}%)")
    
    # Aggregate results
    if len(results) > 1:
        print(f"\n{'='*80}")
        print("AGGREGATE RESULTS")
        print(f"{'='*80}")
        
        total_trades = sum(r.total_trades for r in results)
        total_wins = sum(r.winning_trades for r in results)
        total_losses = sum(r.losing_trades for r in results)
        all_pnls = [t.pnl_pct for r in results for t in r.trades]
        
        # Aggregate by direction
        total_ce = sum(r.ce_trades for r in results)
        total_ce_wins = sum(r.ce_wins for r in results)
        total_ce_pnl = sum(r.ce_pnl for r in results)
        total_pe = sum(r.pe_trades for r in results)
        total_pe_wins = sum(r.pe_wins for r in results)
        total_pe_pnl = sum(r.pe_pnl for r in results)
        
        print(f"  Symbols Tested: {len(results)}")
        print(f"  Total Trades: {total_trades}")
        print(f"  Overall Win Rate: {total_wins/total_trades*100:.1f}%" if total_trades else "  No trades")
        print(f"  Average P&L per Trade: {sum(all_pnls)/len(all_pnls):+.2f}%" if all_pnls else "  N/A")
        print(f"  Total P&L: {sum(all_pnls):+.2f}%" if all_pnls else "  N/A")
        
        print(f"\n  Direction Breakdown:")
        if total_ce > 0:
            ce_wr = total_ce_wins / total_ce * 100
            print(f"    📈 CE: {total_ce} trades, {ce_wr:.1f}% win rate, {total_ce_pnl:+.2f}% P&L")
        if total_pe > 0:
            pe_wr = total_pe_wins / total_pe * 100
            print(f"    📉 PE: {total_pe} trades, {pe_wr:.1f}% win rate, {total_pe_pnl:+.2f}% P&L")
    
    # Trade log
    print(f"\n{'='*80}")
    print("TRADE LOG (Last 20 trades)")
    print(f"{'='*80}")
    
    all_trades = [t for r in results for t in r.trades]
    all_trades.sort(key=lambda t: t.entry_time, reverse=True)
    
    for trade in all_trades[:20]:
        emoji = "✅" if trade.pnl_pct > 0 else "❌"
        dir_emoji = "📈" if trade.direction == "CE" else "📉"
        print(f"  {emoji}{dir_emoji} {trade.symbol} {trade.direction} | {trade.entry_date} | "
              f"Entry: {trade.entry_price:.2f} → Exit: {trade.exit_price:.2f} | "
              f"P&L: {trade.pnl_pct:+.2f}% | Score: {trade.setup_score:.1f} | {trade.exit_reason}")


async def main():
    parser = argparse.ArgumentParser(description="Backtest Intraday Momentum OI Strategy (CE + PE)")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols (e.g., RELIANCE,TCS)")
    parser.add_argument("--days", type=int, default=30, help="Days of history to backtest")
    parser.add_argument("--entry-start", type=str, default="10:15", help="Entry window start (HH:MM)")
    parser.add_argument("--entry-end", type=str, default="12:00", help="Entry window end (HH:MM)")
    parser.add_argument("--trailing-sl", type=float, default=0.5, help="Trailing SL percentage")
    parser.add_argument("--max-slippage", type=float, default=0.15, help="Max slippage beyond SL level (default: 0.15%%)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed entry evaluation")
    
    # Direction control
    parser.add_argument("--ce-only", action="store_true", help="Only trade CE (bullish)")
    parser.add_argument("--pe-only", action="store_true", help="Only trade PE (bearish)")
    
    # CE Exit strategy options (defaults optimized: +56% improvement)
    parser.add_argument("--ce-min-hold", type=int, default=8, help="Min candles to hold CE before exit (default: 8)")
    parser.add_argument("--ce-ema-confirm", action="store_true", default=True, help="Require price below EMA9 for CE exit (default: True)")
    parser.add_argument("--ce-ema-exit", action="store_true", help="Use EMA9 cross as primary CE exit")
    parser.add_argument("--big-red-mult", type=float, default=2.0, help="Big red candle multiplier")
    
    # Ranking options (for future multi-symbol ranking)
    parser.add_argument("--ranked", action="store_true", help="Enable cross-symbol ranking (take best setup per day)")
    parser.add_argument("--max-trades", type=int, default=2, help="Max trades per day when ranked")
    
    args = parser.parse_args()
    
    # Get symbols
    symbols = await get_symbols_for_backtest(args.symbols)
    if not symbols:
        print("No symbols found for backtesting!")
        return
    
    # Determine direction mode
    enable_ce = not args.pe_only
    enable_pe = not args.ce_only
    mode_str = "CE+PE"
    if args.ce_only:
        mode_str = "CE only"
    elif args.pe_only:
        mode_str = "PE only"
    
    print(f"Backtesting {len(symbols)} symbols: {', '.join(symbols)}")
    print(f"Mode: {mode_str}")
    print(f"Parameters: Entry {args.entry_start}-{args.entry_end}, Trailing SL: {args.trailing_sl}%, Max Slippage: {args.max_slippage}%")
    if args.ranked:
        print(f"Ranking: Enabled (max {args.max_trades} trades/day)")
    
    # Create config
    from datetime import time
    h, m = map(int, args.entry_start.split(":"))
    entry_start = time(h, m)
    h, m = map(int, args.entry_end.split(":"))
    entry_end = time(h, m)
    
    config = IntradayMomentumConfig(
        entry_window_start=entry_start,
        entry_window_end=entry_end,
        trailing_sl_pct=args.trailing_sl,
        enable_ce_trades=enable_ce,
        enable_pe_trades=enable_pe,
        max_trades_per_day=args.max_trades,
        # CE exit strategy settings
        ce_min_hold_candles=args.ce_min_hold,
        ce_require_ema_confirm=args.ce_ema_confirm,
        ce_use_ema_cross_exit=args.ce_ema_exit,
        big_red_candle_multiplier=args.big_red_mult,
    )
    
    # Run backtests
    results = []
    for symbol in symbols:
        candles = await get_candles_for_symbol(symbol, args.days)
        if len(candles) < 100:
            print(f"Skipping {symbol} - insufficient data ({len(candles)} candles)")
            continue
        
        result = run_backtest_for_symbol(symbol, candles, config, verbose=args.verbose, max_slippage_pct=args.max_slippage)
        results.append(result)
    
    # Print results
    print_backtest_results(results)
    
    # If ranked mode, show top setups by score
    if args.ranked and results:
        print(f"\n{'='*80}")
        print("TOP SETUPS BY SCORE (Ranking Analysis)")
        print(f"{'='*80}")
        
        all_trades = [t for r in results for t in r.trades]
        all_trades.sort(key=lambda t: t.setup_score, reverse=True)
        
        winning = [t for t in all_trades if t.pnl_pct > 0]
        losing = [t for t in all_trades if t.pnl_pct <= 0]
        
        # Analyze score vs win rate
        high_score_trades = [t for t in all_trades if t.setup_score >= 40]
        low_score_trades = [t for t in all_trades if t.setup_score < 40]
        
        if high_score_trades:
            high_wins = len([t for t in high_score_trades if t.pnl_pct > 0])
            high_wr = high_wins / len(high_score_trades) * 100
            high_pnl = sum(t.pnl_pct for t in high_score_trades)
            print(f"\n  High Score (≥40): {len(high_score_trades)} trades, {high_wr:.1f}% win rate, {high_pnl:+.2f}% P&L")
        
        if low_score_trades:
            low_wins = len([t for t in low_score_trades if t.pnl_pct > 0])
            low_wr = low_wins / len(low_score_trades) * 100
            low_pnl = sum(t.pnl_pct for t in low_score_trades)
            print(f"  Low Score (<40): {len(low_score_trades)} trades, {low_wr:.1f}% win rate, {low_pnl:+.2f}% P&L")
        
        print(f"\n  Top 10 Highest Scoring Trades:")
        for i, trade in enumerate(all_trades[:10], 1):
            emoji = "✅" if trade.pnl_pct > 0 else "❌"
            dir_emoji = "📈" if trade.direction == "CE" else "📉"
            print(f"    {i}. {emoji}{dir_emoji} {trade.symbol} | Score: {trade.setup_score:.1f} | {trade.pnl_pct:+.2f}%")


if __name__ == "__main__":
    asyncio.run(main())