#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest Script for Sector Momentum Strategy

Tests the sector-based trading strategy on historical data.
At market open, identifies strong sectors and trades stocks within them.

Usage:
    python scripts/backtest_sector_momentum.py --days 30
    python scripts/backtest_sector_momentum.py --days 60 --top-sectors 2
    python scripts/backtest_sector_momentum.py --days 30 --direction bullish
"""

import argparse
import asyncio
import io
import os
import sys
import logging
from datetime import datetime, date, timedelta, time, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

# Suppress SQLAlchemy logging BEFORE any imports
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.CRITICAL)
logging.getLogger('sqlalchemy.engine.Engine').setLevel(logging.CRITICAL)
logging.getLogger('sqlalchemy.pool').setLevel(logging.CRITICAL)
logging.getLogger('sqlalchemy').setLevel(logging.CRITICAL)
logging.getLogger('sqlalchemy.dialects').setLevel(logging.CRITICAL)

# Force production mode to disable SQL echo
import os
os.environ['ENVIRONMENT'] = 'production'

# Fix unicode output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# IST timezone offset (UTC+5:30)
IST_OFFSET = timedelta(hours=5, minutes=30)

# Setup path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text
from app.db.session import get_db_context
from app.strategies.sector_momentum import (
    SectorMomentumStrategy,
    SectorConfig,
    SectorDirection,
    SectorScore,
    StockSignal,
    SECTOR_INDEX_MAP,
    INDEX_SECTOR_MAP,
    create_sector_momentum_strategy,
)
from app.services.data_providers.base import Candle


@dataclass
class Trade:
    """Record of a completed trade."""
    symbol: str
    sector: str
    sector_index: str
    direction: str  # "CE" or "PE"
    
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    sl_price: float
    target_price: float
    
    sector_score: float
    stock_alignment: float
    
    pnl_percent: float
    exit_reason: str
    
    @property
    def is_win(self) -> bool:
        return self.pnl_percent > 0


@dataclass
class DayResult:
    """Results for a single trading day."""
    trading_date: date
    top_sectors: List[Tuple[str, float, str]]  # (sector, score, direction)
    trades: List[Trade]
    total_pnl: float
    
    @property
    def win_count(self) -> int:
        return sum(1 for t in self.trades if t.is_win)
    
    @property
    def win_rate(self) -> float:
        return (self.win_count / len(self.trades) * 100) if self.trades else 0.0


# Sector index to track
SECTOR_INDICES = [
    "NIFTY BANK",
    "NIFTY IT",
    "NIFTY AUTO",
    "NIFTY PHARMA",
    "NIFTY METAL",
    "NIFTY REALTY",
    "NIFTY ENERGY",
    "NIFTY FMCG",
    "NIFTY INFRA",
    "NIFTY FIN SERVICE",
]


async def get_stocks_for_sector(sector: str) -> List[str]:
    """Get all F&O stocks for a given sector."""
    async with get_db_context() as db:
        result = await db.execute(text("""
            SELECT im.trading_symbol
            FROM equity_master em
            JOIN instrument_master im ON em.instrument_id = im.instrument_id
            WHERE em.sector = :sector
            AND em.is_fno = true
            ORDER BY im.trading_symbol
        """), {"sector": sector})
        rows = result.fetchall()
        return [row[0] for row in rows]


def resample_to_5min(candles_1m: List[Candle]) -> List[Candle]:
    """Resample 1-minute candles to 5-minute candles."""
    if not candles_1m:
        return []
    
    candles_5m = []
    bucket = []
    
    for candle in candles_1m:
        # Get 5-min bucket based on minute
        minute = candle.timestamp.minute
        bucket_minute = (minute // 5) * 5
        bucket_time = candle.timestamp.replace(minute=bucket_minute, second=0, microsecond=0)
        
        if not bucket:
            bucket = [candle]
            current_bucket_time = bucket_time
        elif bucket_time == current_bucket_time:
            bucket.append(candle)
        else:
            # Close out previous bucket
            if bucket:
                candles_5m.append(Candle(
                    timestamp=current_bucket_time,
                    open=bucket[0].open,
                    high=max(c.high for c in bucket),
                    low=min(c.low for c in bucket),
                    close=bucket[-1].close,
                    volume=sum(c.volume for c in bucket),
                ))
            bucket = [candle]
            current_bucket_time = bucket_time
    
    # Don't forget last bucket
    if bucket:
        candles_5m.append(Candle(
            timestamp=current_bucket_time,
            open=bucket[0].open,
            high=max(c.high for c in bucket),
            low=min(c.low for c in bucket),
            close=bucket[-1].close,
            volume=sum(c.volume for c in bucket),
        ))
    
    return candles_5m


async def get_sector_index_candles(index_symbol: str, trading_date: date) -> List[Candle]:
    """Get 5-minute candles for a sector index on a specific date (from 1m data)."""
    async with get_db_context() as db:
        # Get candles for the date (IST trading hours: 9:15 - 15:30)
        start_time = datetime.combine(trading_date, time(9, 15)) - IST_OFFSET
        end_time = datetime.combine(trading_date, time(15, 30)) - IST_OFFSET
        
        # Get 1-minute candles
        result = await db.execute(text("""
            SELECT cd.timestamp, cd.open, cd.high, cd.low, cd.close, cd.volume
            FROM candle_data cd
            JOIN instrument_master im ON cd.instrument_id = im.instrument_id
            WHERE im.trading_symbol = :symbol
            AND im.instrument_type = 'INDEX'
            AND cd.timestamp >= :start_time
            AND cd.timestamp <= :end_time
            ORDER BY cd.timestamp ASC
        """), {"symbol": index_symbol, "start_time": start_time, "end_time": end_time})
        
        rows = result.fetchall()
        candles_1m = []
        for row in rows:
            candles_1m.append(Candle(
                timestamp=row[0],
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=int(row[5]) if row[5] else 0,
            ))
        
        # Resample to 5-minute
        return resample_to_5min(candles_1m)


async def get_prev_day_close(symbol: str, trading_date: date, is_index: bool = False) -> Optional[float]:
    """Get previous day's closing price."""
    async with get_db_context() as db:
        prev_date = trading_date - timedelta(days=1)
        # Go back up to 5 days to find previous trading day
        for _ in range(5):
            end_time = datetime.combine(prev_date, time(15, 30)) - IST_OFFSET
            start_time = datetime.combine(prev_date, time(15, 20)) - IST_OFFSET
            
            itype = 'INDEX' if is_index else 'EQUITY'
            result = await db.execute(text("""
                SELECT cd.close
                FROM candle_data cd
                JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                WHERE im.trading_symbol = :symbol
                AND im.instrument_type = :itype
                AND cd.timestamp >= :start_time
                AND cd.timestamp <= :end_time
                ORDER BY cd.timestamp DESC
                LIMIT 1
            """), {"symbol": symbol, "itype": itype, "start_time": start_time, "end_time": end_time})
            
            row = result.fetchone()
            if row:
                return float(row[0])
            prev_date -= timedelta(days=1)
        
        return None


async def get_stock_candles(symbol: str, trading_date: date) -> List[Candle]:
    """Get 5-minute candles for a stock on a specific date (from 1m data)."""
    async with get_db_context() as db:
        start_time = datetime.combine(trading_date, time(9, 15)) - IST_OFFSET
        end_time = datetime.combine(trading_date, time(15, 30)) - IST_OFFSET
        
        # Get 1-minute candles
        result = await db.execute(text("""
            SELECT cd.timestamp, cd.open, cd.high, cd.low, cd.close, cd.volume
            FROM candle_data cd
            JOIN instrument_master im ON cd.instrument_id = im.instrument_id
            WHERE im.trading_symbol = :symbol
            AND im.instrument_type = 'EQUITY'
            AND cd.timestamp >= :start_time
            AND cd.timestamp <= :end_time
            ORDER BY cd.timestamp ASC
        """), {"symbol": symbol, "start_time": start_time, "end_time": end_time})
        
        rows = result.fetchall()
        candles_1m = []
        for row in rows:
            candles_1m.append(Candle(
                timestamp=row[0],
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=int(row[5]) if row[5] else 0,
            ))
        
        # Resample to 5-minute
        return resample_to_5min(candles_1m)


async def get_stock_avg_volume(symbol: str, trading_date: date, days: int = 20) -> float:
    """Get average daily volume for a stock."""
    async with get_db_context() as db:
        from_date = trading_date - timedelta(days=days + 5)  # Buffer for non-trading days
        to_date = trading_date - timedelta(days=1)
        
        result = await db.execute(text("""
            SELECT AVG(daily_vol) as avg_vol
            FROM (
                SELECT DATE(cd.timestamp + interval '5 hours 30 minutes') as trade_date,
                       SUM(cd.volume) as daily_vol
                FROM candle_data cd
                JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                WHERE im.trading_symbol = :symbol
                AND im.instrument_type = 'EQUITY'
                AND cd.timestamp >= :from_date
                AND cd.timestamp <= :to_date
                GROUP BY DATE(cd.timestamp + interval '5 hours 30 minutes')
                ORDER BY trade_date DESC
                LIMIT :days
            ) daily_volumes
        """), {"symbol": symbol, "from_date": from_date, "to_date": to_date, "days": days})
        
        row = result.fetchone()
        return float(row[0]) if row and row[0] else 0.0


async def get_trading_days(days_back: int) -> List[date]:
    """Get list of trading days from database."""
    async with get_db_context() as db:
        from_date = date.today() - timedelta(days=days_back + 10)
        
        result = await db.execute(text("""
            SELECT DISTINCT DATE(timestamp + interval '5 hours 30 minutes') as trade_date
            FROM candle_data
            WHERE timestamp >= :from_date
            ORDER BY trade_date DESC
            LIMIT :days
        """), {"from_date": from_date, "days": days_back})
        
        rows = result.fetchall()
        return [row[0] for row in rows]


def calculate_ema(closes: List[float], period: int) -> float:
    """Calculate EMA from list of closes."""
    if len(closes) < period:
        return closes[-1] if closes else 0.0
    
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    
    for close in closes[period:]:
        ema = (close * multiplier) + (ema * (1 - multiplier))
    
    return ema


async def analyze_sectors_for_day(
    trading_date: date,
    strategy: SectorMomentumStrategy,
    verbose: bool = False
) -> Tuple[List[SectorScore], List[SectorScore]]:
    """
    Analyze all sector indices at market open and rank them.
    
    Returns tuple of (top_bullish_sectors, top_bearish_sectors)
    """
    sector_scores = []
    
    for index_symbol in SECTOR_INDICES:
        # Get candles for the day
        candles = await get_sector_index_candles(index_symbol, trading_date)
        if len(candles) < 3:  # Need at least first 15 mins (3 candles)
            continue
        
        # Get previous day close
        prev_close = await get_prev_day_close(index_symbol, trading_date, is_index=True)
        if not prev_close:
            continue
        
        # First candle data (9:15-9:20)
        first_candle = candles[0]
        
        # Aggregate first 15 mins for sector analysis (3 x 5-min candles)
        first_15_min = candles[:3]
        combined_high = max(c.high for c in first_15_min)
        combined_low = min(c.low for c in first_15_min)
        combined_close = first_15_min[-1].close
        combined_open = first_15_min[0].open
        
        # Calculate 9 EMA using recent closes
        closes = [c.close for c in candles[:20]]  # Use up to 20 candles if available
        ema_9 = calculate_ema(closes, 9) if len(closes) >= 9 else closes[-1]
        
        # Score the sector
        score = strategy.score_sector(
            index_symbol=index_symbol,
            prev_close=prev_close,
            open_price=combined_open,
            first_candle_high=combined_high,
            first_candle_low=combined_low,
            first_candle_close=combined_close,
            current_price=candles[3].close if len(candles) > 3 else combined_close,  # Use 9:30 price
            ema_9=ema_9,
        )
        
        sector_scores.append(score)
        
        if verbose:
            print(f"  {index_symbol}: Gap={score.gap_percent:+.2f}%, "
                  f"Body={score.candle_body_ratio:.2f}, "
                  f"Score={score.total_score:.1f}, "
                  f"Dir={score.direction.value}")
    
    # Rank sectors
    return strategy.rank_sectors(sector_scores)


async def find_trades_in_sector(
    sector_score: SectorScore,
    trading_date: date,
    strategy: SectorMomentumStrategy,
    config: SectorConfig,
    verbose: bool = False
) -> List[Trade]:
    """Find and execute trades within a strong sector."""
    trades = []
    
    # Get sectors covered by this index
    sectors_covered = INDEX_SECTOR_MAP.get(sector_score.index_symbol, [])
    if not sectors_covered:
        return trades
    
    # Get all stocks in these sectors
    all_stocks = []
    for sector in sectors_covered:
        stocks = await get_stocks_for_sector(sector)
        for s in stocks:
            all_stocks.append((s, sector))
    
    if verbose:
        print(f"\n  Analyzing {len(all_stocks)} stocks in {sector_score.index_symbol}...")
    
    stocks_checked = 0
    stocks_with_candles = 0
    
    for symbol, sector in all_stocks:
        stocks_checked += 1
        
        # Get stock candles
        candles = await get_stock_candles(symbol, trading_date)
        if len(candles) < 10:
            if verbose and stocks_checked <= 3:
                print(f"    {symbol}: Skipped - only {len(candles)} candles")
            continue
        
        stocks_with_candles += 1
        
        # Get previous close
        prev_close = await get_prev_day_close(symbol, trading_date, is_index=False)
        if not prev_close:
            if verbose and stocks_checked <= 3:
                print(f"    {symbol}: Skipped - no prev close")
            continue
        
        # Get average volume
        avg_volume = await get_stock_avg_volume(symbol, trading_date)
        if avg_volume <= 0:
            avg_volume = sum(c.volume for c in candles) / len(candles) * 75  # Fallback
        
        # Use candle at entry window start (9:20 = candle index 1)
        entry_candle_idx = 1  # 9:20 candle
        if entry_candle_idx >= len(candles):
            continue
        
        entry_candle = candles[entry_candle_idx]
        
        # Calculate EMA
        closes = [c.close for c in candles[:entry_candle_idx + 1]]
        for i in range(max(0, entry_candle_idx - 20), entry_candle_idx):
            closes.insert(0, candles[i].close)
        ema_9 = calculate_ema(closes, 9)
        
        # Current day's volume up to entry candle
        current_volume = sum(c.volume for c in candles[:entry_candle_idx + 1])
        
        # Scale average volume to match time window (2 candles = 10 mins out of 375 mins trading day)
        scaled_avg_volume = int(avg_volume * (entry_candle_idx + 1) / 75)  # 75 = 375 mins / 5 mins per candle
        
        if verbose and stocks_with_candles <= 5:
            print(f"    {symbol}: Vol={current_volume:,.0f}, AvgDayVol={avg_volume:,.0f}, ScaledAvg={scaled_avg_volume:,.0f}")
            # Debug score_stock inputs
            stock_gap_pct = ((entry_candle.close - candles[0].open) / candles[0].open) * 100
            stock_vs_ema = ((entry_candle.close - ema_9) / ema_9) * 100 if ema_9 > 0 else 0
            print(f"           Gap={stock_gap_pct:+.2f}%, vsEMA={stock_vs_ema:+.2f}%")
            print(f"           Open={candles[0].open:.2f}, Close={entry_candle.close:.2f}, EMA={ema_9:.2f}")
            print(f"           SectorDir={sector_score.direction.value}")
        
        # Generate signal
        signal = strategy.score_stock(
            symbol=symbol,
            sector=sector,
            sector_score=sector_score,
            stock_open=candles[0].open,
            stock_close=entry_candle.close,
            stock_high=max(c.high for c in candles[:entry_candle_idx + 1]),
            stock_low=min(c.low for c in candles[:entry_candle_idx + 1]),
            stock_volume=current_volume,
            avg_volume=scaled_avg_volume,
            stock_ema_9=ema_9,
        )
        
        if not signal:
            if verbose and stocks_with_candles <= 3:
                print(f"    {symbol}: No signal generated (alignment or volume filter)")
            continue
        
        # Simulate trade
        entry_price = signal.entry_price
        sl_price = signal.sl_price
        target_price = signal.target_price
        direction = "CE" if signal.direction == SectorDirection.BULLISH else "PE"
        
        # Walk through remaining candles to find exit
        exit_time = None
        exit_price = None
        exit_reason = "TIME"
        
        for candle in candles[entry_candle_idx + 1:]:
            candle_time = (candle.timestamp + IST_OFFSET).time()
            
            # Check time exit (3:15 PM)
            if candle_time >= time(15, 15):
                exit_time = candle.timestamp
                exit_price = candle.close
                exit_reason = "TIME"
                break
            
            should_exit, reason, price = strategy.check_exit(
                entry_price=entry_price,
                sl_price=sl_price,
                target_price=target_price,
                current_price=candle.close,
                current_high=candle.high,
                current_low=candle.low,
                direction=signal.direction,
            )
            
            if should_exit:
                exit_time = candle.timestamp
                exit_price = price
                exit_reason = reason
                break
        
        if exit_time is None:
            # Use last candle
            exit_time = candles[-1].timestamp
            exit_price = candles[-1].close
            exit_reason = "EOD"
        
        # Calculate P&L
        if direction == "CE":
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        else:
            pnl_percent = ((entry_price - exit_price) / entry_price) * 100
        
        trade = Trade(
            symbol=symbol,
            sector=sector,
            sector_index=sector_score.index_symbol,
            direction=direction,
            entry_time=entry_candle.timestamp,
            exit_time=exit_time,
            entry_price=entry_price,
            exit_price=exit_price,
            sl_price=sl_price,
            target_price=target_price,
            sector_score=sector_score.total_score,
            stock_alignment=signal.stock_alignment_score,
            pnl_percent=pnl_percent,
            exit_reason=exit_reason,
        )
        
        trades.append(trade)
        strategy.daily_trades += 1
        strategy.trades_per_sector[sector] += 1
        
        if verbose:
            win_str = "WIN" if trade.is_win else "LOSS"
            print(f"    {symbol} ({sector}): {direction} | "
                  f"Entry={entry_price:.2f} Exit={exit_price:.2f} | "
                  f"P&L={pnl_percent:+.2f}% | {exit_reason} | {win_str}")
        
        # Check trade limits
        if strategy.daily_trades >= config.max_total_trades:
            break
    
    if verbose:
        print(f"    Checked {stocks_checked} stocks, {stocks_with_candles} had candles, {len(trades)} trades")
    
    return trades


async def run_backtest(
    days_back: int = 30,
    top_sectors: int = 3,
    direction_filter: str = "both",
    verbose: bool = False,
) -> List[DayResult]:
    """Run sector momentum backtest."""
    
    # Configuration with relaxed filters for testing
    config = SectorConfig(
        top_sectors_count=top_sectors,
        max_trades_per_sector=3,
        max_total_trades=8,
        risk_reward_ratio=2.0,
        min_stock_alignment=0.4,  # Relaxed from 0.7 
        min_stock_volume_multiplier=0.8,  # Relaxed from 1.2
    )
    
    strategy = create_sector_momentum_strategy(config)
    
    # Get trading days
    trading_days = await get_trading_days(days_back)
    print(f"\nBacktesting {len(trading_days)} trading days...")
    print(f"Configuration: Top {top_sectors} sectors, Max {config.max_total_trades} trades/day")
    print(f"Direction filter: {direction_filter}")
    print("=" * 80)
    
    results = []
    
    for trading_date in reversed(trading_days):  # Oldest first
        strategy.reset_for_new_day(trading_date)
        
        print(f"\n{'='*60}")
        print(f"Date: {trading_date}")
        print(f"{'='*60}")
        
        # Analyze sectors
        if verbose:
            print("\nSector Analysis (9:15-9:30):")
        
        top_bullish, top_bearish = await analyze_sectors_for_day(
            trading_date, strategy, verbose
        )
        
        # Print top sectors
        print(f"\nTop Bullish Sectors:")
        for s in top_bullish:
            print(f"  {s.index_symbol}: Score={s.total_score:.1f}, Gap={s.gap_percent:+.2f}%")
        
        print(f"\nTop Bearish Sectors:")
        for s in top_bearish:
            print(f"  {s.index_symbol}: Score={s.total_score:.1f}, Gap={s.gap_percent:+.2f}%")
        
        # Find trades based on direction filter
        day_trades = []
        
        if direction_filter in ["both", "bullish"]:
            for sector_score in top_bullish:
                trades = await find_trades_in_sector(
                    sector_score, trading_date, strategy, config, verbose
                )
                day_trades.extend(trades)
                if strategy.daily_trades >= config.max_total_trades:
                    break
        
        if direction_filter in ["both", "bearish"]:
            for sector_score in top_bearish:
                trades = await find_trades_in_sector(
                    sector_score, trading_date, strategy, config, verbose
                )
                day_trades.extend(trades)
                if strategy.daily_trades >= config.max_total_trades:
                    break
        
        # Day summary
        if day_trades:
            total_pnl = sum(t.pnl_percent for t in day_trades)
            win_count = sum(1 for t in day_trades if t.is_win)
            
            print(f"\nDay Summary:")
            print(f"  Trades: {len(day_trades)}")
            print(f"  Wins: {win_count} ({win_count/len(day_trades)*100:.1f}%)")
            print(f"  Total P&L: {total_pnl:+.2f}%")
            
            top_sectors_info = []
            for s in top_bullish:
                top_sectors_info.append((s.index_symbol, s.total_score, "BULLISH"))
            for s in top_bearish:
                top_sectors_info.append((s.index_symbol, s.total_score, "BEARISH"))
            
            results.append(DayResult(
                trading_date=trading_date,
                top_sectors=top_sectors_info,
                trades=day_trades,
                total_pnl=total_pnl,
            ))
        else:
            print("\n  No trades taken")
    
    return results


def print_summary(results: List[DayResult]):
    """Print comprehensive backtest summary."""
    print("\n" + "=" * 80)
    print("BACKTEST SUMMARY")
    print("=" * 80)
    
    if not results:
        print("No results to summarize.")
        return
    
    # Overall stats
    all_trades = [t for r in results for t in r.trades]
    total_pnl = sum(t.pnl_percent for t in all_trades)
    win_count = sum(1 for t in all_trades if t.is_win)
    
    print(f"\nOverall Performance:")
    print(f"  Days Traded: {len(results)}")
    print(f"  Total Trades: {len(all_trades)}")
    print(f"  Win Rate: {win_count/len(all_trades)*100:.1f}%")
    print(f"  Total P&L: {total_pnl:+.2f}%")
    print(f"  Avg P&L/Trade: {total_pnl/len(all_trades):+.3f}%")
    
    # By direction
    ce_trades = [t for t in all_trades if t.direction == "CE"]
    pe_trades = [t for t in all_trades if t.direction == "PE"]
    
    print(f"\nBy Direction:")
    if ce_trades:
        ce_pnl = sum(t.pnl_percent for t in ce_trades)
        ce_wins = sum(1 for t in ce_trades if t.is_win)
        print(f"  CE Trades: {len(ce_trades)}, Win Rate: {ce_wins/len(ce_trades)*100:.1f}%, P&L: {ce_pnl:+.2f}%")
    if pe_trades:
        pe_pnl = sum(t.pnl_percent for t in pe_trades)
        pe_wins = sum(1 for t in pe_trades if t.is_win)
        print(f"  PE Trades: {len(pe_trades)}, Win Rate: {pe_wins/len(pe_trades)*100:.1f}%, P&L: {pe_pnl:+.2f}%")
    
    # By sector index
    print(f"\nBy Sector Index:")
    sector_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
    for t in all_trades:
        sector_stats[t.sector_index]["trades"] += 1
        sector_stats[t.sector_index]["wins"] += 1 if t.is_win else 0
        sector_stats[t.sector_index]["pnl"] += t.pnl_percent
    
    for sector, stats in sorted(sector_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
        wr = stats["wins"] / stats["trades"] * 100 if stats["trades"] > 0 else 0
        print(f"  {sector}: {stats['trades']} trades, {wr:.1f}% WR, {stats['pnl']:+.2f}% P&L")
    
    # By exit reason
    print(f"\nBy Exit Reason:")
    exit_stats = defaultdict(lambda: {"count": 0, "pnl": 0.0})
    for t in all_trades:
        exit_stats[t.exit_reason]["count"] += 1
        exit_stats[t.exit_reason]["pnl"] += t.pnl_percent
    
    for reason, stats in exit_stats.items():
        print(f"  {reason}: {stats['count']} trades, {stats['pnl']:+.2f}% P&L")
    
    # Best/Worst days
    print(f"\nBest Days:")
    sorted_results = sorted(results, key=lambda x: x.total_pnl, reverse=True)
    for r in sorted_results[:3]:
        print(f"  {r.trading_date}: {r.total_pnl:+.2f}% ({len(r.trades)} trades)")
    
    print(f"\nWorst Days:")
    for r in sorted_results[-3:]:
        print(f"  {r.trading_date}: {r.total_pnl:+.2f}% ({len(r.trades)} trades)")
    
    # Consecutive wins/losses
    current_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    
    for t in all_trades:
        if t.is_win:
            if current_streak > 0:
                current_streak += 1
            else:
                current_streak = 1
            max_win_streak = max(max_win_streak, current_streak)
        else:
            if current_streak < 0:
                current_streak -= 1
            else:
                current_streak = -1
            max_loss_streak = min(max_loss_streak, current_streak)
    
    print(f"\nStreaks:")
    print(f"  Max Winning Streak: {max_win_streak}")
    print(f"  Max Losing Streak: {abs(max_loss_streak)}")


async def main():
    parser = argparse.ArgumentParser(description="Backtest Sector Momentum Strategy")
    parser.add_argument("--days", type=int, default=30, help="Days to backtest")
    parser.add_argument("--top-sectors", type=int, default=3, help="Top sectors to trade")
    parser.add_argument("--direction", choices=["bullish", "bearish", "both"], 
                        default="both", help="Direction filter")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    results = await run_backtest(
        days_back=args.days,
        top_sectors=args.top_sectors,
        direction_filter=args.direction,
        verbose=args.verbose,
    )
    
    print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
