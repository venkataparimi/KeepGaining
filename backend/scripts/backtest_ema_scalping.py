#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest Script for EMA Scalping Strategy

Tests the 9/15 EMA scalping strategy on historical data.
Uses 5-minute candles with slope filter and 1:2 RR.

Usage:
    python scripts/backtest_ema_scalping.py --symbol NIFTY --days 30
    python scripts/backtest_ema_scalping.py --symbol BANKNIFTY --days 60
    python scripts/backtest_ema_scalping.py --symbols RELIANCE,TCS,INFY --days 30
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
from app.strategies.ema_scalping import (
    EMAScalpingStrategy,
    EMAScalpingConfig,
    TradeDirection,
    CandlePattern,
    create_ema_scalping_strategy
)
from app.strategies.base import SignalType
from app.services.data_providers.base import Candle


@dataclass
class Trade:
    """Represents a completed trade."""
    symbol: str
    direction: str  # "BULLISH" or "BEARISH"
    entry_date: date
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    exit_reason: str
    pnl_pct: float
    stop_loss: float
    target: float
    risk_pct: float
    pattern: str
    fast_slope: float = 0.0
    slow_slope: float = 0.0


@dataclass
class BacktestResult:
    """Results from backtesting a symbol."""
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
    avg_duration_minutes: float
    bullish_trades: int = 0
    bullish_wins: int = 0
    bullish_pnl: float = 0.0
    bearish_trades: int = 0
    bearish_wins: int = 0
    bearish_pnl: float = 0.0
    trades: List[Trade] = field(default_factory=list)
    patterns: Dict[str, int] = field(default_factory=dict)


async def get_symbols_for_backtest(symbols_arg: Optional[str]) -> List[str]:
    """Get list of symbols to backtest."""
    if symbols_arg:
        return [s.strip().upper() for s in symbols_arg.split(",")]
    
    # Default: NIFTY 50 components
    return ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]


async def get_candles_for_symbol(symbol: str, days: int) -> List[Candle]:
    """Fetch historical candles from database."""
    from_date = date.today() - timedelta(days=days)
    
    async with get_db_context() as db:
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


def run_backtest_for_symbol(symbol: str, candles: List[Candle], config: EMAScalpingConfig, verbose: bool = False) -> BacktestResult:
    """Run backtest for a single symbol."""
    strategy = EMAScalpingStrategy(config, symbol=symbol)
    
    trades: List[Trade] = []
    current_entry: Dict[str, Any] = None
    
    # Track daily stats
    days_seen = set()
    
    # Direction tracking
    bullish_trades = 0
    bullish_wins = 0
    bullish_pnl = 0.0
    bearish_trades = 0
    bearish_wins = 0
    bearish_pnl = 0.0
    
    # Pattern tracking
    pattern_counts = defaultdict(int)
    pattern_wins = defaultdict(int)
    
    print(f"\n{'='*60}")
    print(f"Backtesting {symbol} with {len(candles):,} candles")
    print(f"EMA: {config.fast_ema_period}/{config.slow_ema_period}, Min Slope: {config.min_slope_degrees}°")
    print(f"Risk/Reward: 1:{config.risk_reward_ratio}")
    print(f"{'='*60}")
    
    for candle in candles:
        days_seen.add(candle.timestamp.date())
        
        # Process candle through strategy
        signal = strategy.on_candle(candle)
        
        if signal is None:
            continue
        
        if signal.signal_type in (SignalType.BUY, SignalType.SELL):
            # Entry signal
            direction = signal.metadata.get("direction", "BULLISH")
            pattern = signal.metadata.get("pattern", "NONE")
            
            current_entry = {
                "entry_time": candle.timestamp,
                "entry_price": signal.metadata.get("entry_price", candle.close),
                "stop_loss": signal.metadata.get("stop_loss", 0),
                "target": signal.metadata.get("target", 0),
                "direction": direction,
                "pattern": pattern,
                "risk_pct": signal.metadata.get("risk_pct", 0),
                "fast_slope": signal.metadata.get("fast_slope", 0),
                "slow_slope": signal.metadata.get("slow_slope", 0),
            }
            
            emoji = "📈" if direction == "BULLISH" else "📉"
            print(f"  {emoji} {direction} ENTRY: {candle.timestamp} @ {current_entry['entry_price']:.2f}")
            print(f"      Pattern: {pattern}, SL: {current_entry['stop_loss']:.2f}, Target: {current_entry['target']:.2f}")
            print(f"      Slope: Fast={current_entry['fast_slope']:.1f}°, Slow={current_entry['slow_slope']:.1f}°")
            
        elif signal.signal_type == SignalType.EXIT and current_entry:
            # Exit signal
            direction = current_entry["direction"]
            exit_price = signal.metadata.get("exit_price", candle.close)
            pnl_pct = signal.metadata.get("pnl_pct", 0)
            reason = signal.metadata.get("reason", "Unknown")
            pattern = current_entry["pattern"]
            
            trade = Trade(
                symbol=symbol,
                direction=direction,
                entry_date=current_entry["entry_time"].date(),
                entry_time=current_entry["entry_time"],
                entry_price=current_entry["entry_price"],
                exit_time=candle.timestamp,
                exit_price=exit_price,
                exit_reason=reason,
                pnl_pct=pnl_pct,
                stop_loss=current_entry["stop_loss"],
                target=current_entry["target"],
                risk_pct=current_entry["risk_pct"],
                pattern=pattern,
                fast_slope=current_entry["fast_slope"],
                slow_slope=current_entry["slow_slope"],
            )
            trades.append(trade)
            
            # Track by direction
            if direction == "BULLISH":
                bullish_trades += 1
                bullish_pnl += pnl_pct
                if pnl_pct > 0:
                    bullish_wins += 1
            else:
                bearish_trades += 1
                bearish_pnl += pnl_pct
                if pnl_pct > 0:
                    bearish_wins += 1
            
            # Track by pattern
            pattern_counts[pattern] += 1
            if pnl_pct > 0:
                pattern_wins[pattern] += 1
            
            emoji = "✅" if pnl_pct > 0 else "❌"
            dir_emoji = "📈" if direction == "BULLISH" else "📉"
            print(f"  {emoji}{dir_emoji} {direction} EXIT: {candle.timestamp} @ {exit_price:.2f} "
                  f"({pnl_pct:+.2f}%) - {reason}")
            
            current_entry = None
    
    # Calculate statistics
    winning_trades = [t for t in trades if t.pnl_pct > 0]
    losing_trades = [t for t in trades if t.pnl_pct <= 0]
    
    total_pnl = sum(t.pnl_pct for t in trades)
    avg_win = sum(t.pnl_pct for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(t.pnl_pct for t in losing_trades) / len(losing_trades) if losing_trades else 0
    
    gross_profit = sum(t.pnl_pct for t in winning_trades)
    gross_loss = abs(sum(t.pnl_pct for t in losing_trades))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    win_rate = len(winning_trades) / len(trades) * 100 if trades else 0
    
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
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_duration_minutes=avg_duration,
        bullish_trades=bullish_trades,
        bullish_wins=bullish_wins,
        bullish_pnl=bullish_pnl,
        bearish_trades=bearish_trades,
        bearish_wins=bearish_wins,
        bearish_pnl=bearish_pnl,
        trades=trades,
        patterns=dict(pattern_counts),
    )


def print_backtest_results(results: List[BacktestResult]):
    """Print formatted backtest results."""
    print(f"\n{'='*80}")
    print("EMA SCALPING STRATEGY - BACKTEST RESULTS")
    print(f"{'='*80}")
    
    total_trades = sum(r.total_trades for r in results)
    total_wins = sum(r.winning_trades for r in results)
    total_pnl = sum(r.total_pnl_pct for r in results)
    
    for result in results:
        print(f"\n{'-'*60}")
        print(f"Symbol: {result.symbol}")
        print(f"{'-'*60}")
        print(f"  Period: {result.total_days} days ({result.trading_days} trading days)")
        print(f"  Total Trades: {result.total_trades}")
        print(f"  Win/Loss: {result.winning_trades}/{result.losing_trades} ({result.win_rate:.1f}% win rate)")
        print(f"  Total P&L: {result.total_pnl_pct:+.2f}%")
        print(f"  Avg Win: {result.avg_win_pct:+.2f}% | Avg Loss: {result.avg_loss_pct:+.2f}%")
        print(f"  Max Win: {result.max_win_pct:+.2f}% | Max Loss: {result.max_loss_pct:+.2f}%")
        print(f"  Profit Factor: {result.profit_factor:.2f}")
        print(f"  Avg Duration: {result.avg_duration_minutes:.0f} minutes")
        
        if result.bullish_trades > 0:
            bull_win_rate = result.bullish_wins / result.bullish_trades * 100
            print(f"\n  📈 Bullish: {result.bullish_trades} trades ({bull_win_rate:.1f}% win), P&L: {result.bullish_pnl:+.2f}%")
        
        if result.bearish_trades > 0:
            bear_win_rate = result.bearish_wins / result.bearish_trades * 100
            print(f"  📉 Bearish: {result.bearish_trades} trades ({bear_win_rate:.1f}% win), P&L: {result.bearish_pnl:+.2f}%")
        
        if result.patterns:
            print(f"\n  Patterns:")
            for pattern, count in sorted(result.patterns.items(), key=lambda x: -x[1]):
                print(f"    {pattern}: {count} trades")
    
    # Summary
    if len(results) > 1:
        print(f"\n{'='*80}")
        print("OVERALL SUMMARY")
        print(f"{'='*80}")
        print(f"  Symbols Tested: {len(results)}")
        print(f"  Total Trades: {total_trades}")
        print(f"  Win Rate: {total_wins/total_trades*100:.1f}%" if total_trades > 0 else "  Win Rate: N/A")
        print(f"  Total P&L: {total_pnl:+.2f}%")
    
    # Trade log
    all_trades = [t for r in results for t in r.trades]
    if all_trades:
        print(f"\n{'='*80}")
        print("TRADE LOG (Last 20 trades)")
        print(f"{'='*80}")
        
        for trade in sorted(all_trades, key=lambda t: t.entry_time, reverse=True)[:20]:
            emoji = "✅" if trade.pnl_pct > 0 else "❌"
            dir_emoji = "📈" if trade.direction == "BULLISH" else "📉"
            print(f"  {emoji}{dir_emoji} {trade.symbol} {trade.direction} | {trade.entry_date} | "
                  f"Entry: {trade.entry_price:.2f} → Exit: {trade.exit_price:.2f} | "
                  f"P&L: {trade.pnl_pct:+.2f}% | {trade.pattern} | {trade.exit_reason}")


async def main():
    parser = argparse.ArgumentParser(description="Backtest EMA Scalping Strategy")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols (e.g., RELIANCE,TCS)")
    parser.add_argument("--days", type=int, default=30, help="Days of history to backtest")
    parser.add_argument("--fast-ema", type=int, default=9, help="Fast EMA period (default: 9)")
    parser.add_argument("--slow-ema", type=int, default=15, help="Slow EMA period (default: 15)")
    parser.add_argument("--min-slope", type=float, default=30.0, help="Minimum slope in degrees (default: 30)")
    parser.add_argument("--rr-ratio", type=float, default=2.0, help="Risk/Reward ratio (default: 2.0)")
    parser.add_argument("--entry-start", type=str, default="09:15", help="Entry window start (HH:MM)")
    parser.add_argument("--entry-end", type=str, default="11:15", help="Entry window end (HH:MM)")
    parser.add_argument("--bullish-only", action="store_true", help="Only take bullish trades")
    parser.add_argument("--bearish-only", action="store_true", help="Only take bearish trades")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    
    args = parser.parse_args()
    
    # Get symbols
    symbols = await get_symbols_for_backtest(args.symbols)
    if not symbols:
        print("No symbols found for backtesting!")
        return
    
    # Parse time windows
    h, m = map(int, args.entry_start.split(":"))
    entry_start = time(h, m)
    h, m = map(int, args.entry_end.split(":"))
    entry_end = time(h, m)
    
    # Direction control
    enable_bullish = not args.bearish_only
    enable_bearish = not args.bullish_only
    
    print(f"Backtesting {len(symbols)} symbols: {', '.join(symbols)}")
    print(f"EMA: {args.fast_ema}/{args.slow_ema}, Min Slope: {args.min_slope}°, RR: 1:{args.rr_ratio}")
    print(f"Entry Window: {args.entry_start} - {args.entry_end} IST")
    print(f"Direction: {'Bullish' if enable_bullish else ''}{' + ' if enable_bullish and enable_bearish else ''}{'Bearish' if enable_bearish else ''}")
    
    # Create config
    config = EMAScalpingConfig(
        fast_ema_period=args.fast_ema,
        slow_ema_period=args.slow_ema,
        min_slope_degrees=args.min_slope,
        risk_reward_ratio=args.rr_ratio,
        entry_window_start=entry_start,
        entry_window_end=entry_end,
        enable_bullish_trades=enable_bullish,
        enable_bearish_trades=enable_bearish,
        require_dual_index_confirm=False,  # Disable for single-symbol backtest
    )
    
    # Run backtests
    results = []
    for symbol in symbols:
        candles = await get_candles_for_symbol(symbol, args.days)
        if len(candles) < 100:
            print(f"Skipping {symbol} - insufficient data ({len(candles)} candles)")
            continue
        
        result = run_backtest_for_symbol(symbol, candles, config, verbose=args.verbose)
        results.append(result)
    
    # Print results
    print_backtest_results(results)


if __name__ == "__main__":
    asyncio.run(main())
