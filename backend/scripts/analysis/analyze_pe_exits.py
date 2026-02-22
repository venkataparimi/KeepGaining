#!/usr/bin/env python3
"""
Analyze PE Exit Quality

This script analyzes what happened AFTER PE trade exits to determine:
1. Did we exit too early? What was the max potential profit we missed?
2. Would waiting for EMA/VWAP cross be better?
3. How did the stock move in the next 30-60 mins after exit?

Usage:
    python scripts/analyze_pe_exits.py --symbols "SBIN,TCS,NHPC" --days 60
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, date, timedelta, time, timezone
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import statistics

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
)
from app.strategies.base import SignalType
from app.services.data_providers.base import Candle


@dataclass
class PEExitAnalysis:
    """Analysis of what happened after a PE exit."""
    symbol: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    exit_reason: str
    actual_pnl_pct: float  # What we got
    
    # What happened AFTER exit
    price_30min_after: float = 0.0
    price_60min_after: float = 0.0
    lowest_price_after_exit: float = float('inf')  # Lowest in next hour (potential profit we missed)
    highest_price_after_exit: float = 0.0  # Highest in next hour (bounce confirmation)
    
    # Potential P&L if we held longer
    potential_pnl_30min: float = 0.0
    potential_pnl_60min: float = 0.0
    max_potential_pnl: float = 0.0  # Based on lowest price after exit
    
    # EMA/VWAP analysis
    ema9_at_exit: float = 0.0
    vwap_at_exit: float = 0.0
    candles_until_ema_cross: int = 0  # How many candles until price crossed above EMA9
    candles_until_vwap_cross: int = 0  # How many candles until price crossed above VWAP
    pnl_at_ema_cross: float = 0.0
    pnl_at_vwap_cross: float = 0.0
    
    # Was it a good/bad exit?
    exit_quality: str = ""  # "good" (price went up), "early" (missed more profit), "perfect" (near optimal)


def calculate_ema(prices: List[float], period: int) -> float:
    """Calculate EMA for a list of prices."""
    if len(prices) < period:
        return sum(prices) / len(prices) if prices else 0
    
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period  # Start with SMA
    
    for price in prices[period:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    
    return ema


def calculate_vwap(candles: List[Candle]) -> float:
    """Calculate VWAP from candles."""
    if not candles:
        return 0
    
    total_tp_volume = 0
    total_volume = 0
    
    for c in candles:
        typical_price = (c.high + c.low + c.close) / 3
        total_tp_volume += typical_price * c.volume
        total_volume += c.volume
    
    return total_tp_volume / total_volume if total_volume > 0 else 0


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


def analyze_pe_exits(symbol: str, candles: List[Candle]) -> List[PEExitAnalysis]:
    """Run PE-only backtest and analyze what happened after each exit."""
    
    config = IntradayMomentumConfig(
        enable_ce_trades=False,
        enable_pe_trades=True,
    )
    strategy = IntradayMomentumOIStrategy(config)
    
    analyses: List[PEExitAnalysis] = []
    current_entry: Dict[str, Any] = None
    
    # Build candle index by timestamp for post-exit analysis
    candle_index = {c.timestamp: i for i, c in enumerate(candles)}
    
    # Track day's candles for VWAP calculation
    day_candles: List[Candle] = []
    current_day = None
    
    # Track closes for EMA
    closes: List[float] = []
    
    print(f"\n{'='*60}")
    print(f"Analyzing PE exits for {symbol} ({len(candles):,} candles)")
    print(f"{'='*60}")
    
    for i, candle in enumerate(candles):
        # Track day change for VWAP reset
        candle_date = candle.timestamp.date()
        if candle_date != current_day:
            day_candles = []
            current_day = candle_date
        
        day_candles.append(candle)
        closes.append(candle.close)
        
        # Process candle through strategy
        signal = strategy.on_candle(candle)
        
        if signal is None:
            # Update tracking for open position
            if current_entry:
                current_entry["highest_price"] = max(current_entry["highest_price"], candle.high)
                current_entry["lowest_price"] = min(current_entry["lowest_price"], candle.low)
            continue
        
        if signal.signal_type == SignalType.SELL:  # PE entry
            direction = signal.metadata.get("direction", "PE")
            if direction == "PE":
                current_entry = {
                    "entry_time": candle.timestamp,
                    "entry_price": candle.close,
                    "highest_price": candle.high,
                    "lowest_price": candle.low,
                    "entry_candle_idx": i,
                }
                print(f"  📉 PE ENTRY: {candle.timestamp} @ {candle.close:.2f}")
            
        elif signal.signal_type == SignalType.EXIT and current_entry:
            # Calculate actual P&L (PE profit when price goes DOWN)
            actual_pnl = (current_entry["entry_price"] - candle.close) / current_entry["entry_price"] * 100
            
            # Create analysis object
            analysis = PEExitAnalysis(
                symbol=symbol,
                entry_time=current_entry["entry_time"],
                entry_price=current_entry["entry_price"],
                exit_time=candle.timestamp,
                exit_price=candle.close,
                exit_reason=signal.metadata.get("reason", "Unknown"),
                actual_pnl_pct=actual_pnl,
            )
            
            # Calculate EMA9 at exit
            if len(closes) >= 9:
                analysis.ema9_at_exit = calculate_ema(closes[-50:], 9)
            
            # Calculate VWAP at exit
            analysis.vwap_at_exit = calculate_vwap(day_candles)
            
            # Analyze what happened AFTER exit
            exit_idx = i
            candles_after_exit = candles[exit_idx + 1:exit_idx + 13]  # Next ~60 mins (12 x 5min)
            
            if candles_after_exit:
                # Track lowest/highest after exit
                analysis.lowest_price_after_exit = min(c.low for c in candles_after_exit)
                analysis.highest_price_after_exit = max(c.high for c in candles_after_exit)
                
                # Price 30min after (6 candles)
                if len(candles_after_exit) >= 6:
                    analysis.price_30min_after = candles_after_exit[5].close
                    analysis.potential_pnl_30min = (current_entry["entry_price"] - analysis.price_30min_after) / current_entry["entry_price"] * 100
                
                # Price 60min after (12 candles)
                if len(candles_after_exit) >= 12:
                    analysis.price_60min_after = candles_after_exit[11].close
                    analysis.potential_pnl_60min = (current_entry["entry_price"] - analysis.price_60min_after) / current_entry["entry_price"] * 100
                
                # Max potential P&L (if we exited at lowest)
                analysis.max_potential_pnl = (current_entry["entry_price"] - analysis.lowest_price_after_exit) / current_entry["entry_price"] * 100
                
                # Check when price crossed above EMA9 / VWAP
                post_closes = closes.copy()
                for j, post_candle in enumerate(candles_after_exit):
                    post_closes.append(post_candle.close)
                    day_candles.append(post_candle)  # Add to day for VWAP
                    
                    ema9 = calculate_ema(post_closes[-50:], 9)
                    vwap = calculate_vwap(day_candles)
                    
                    # Check EMA9 cross (price crosses above EMA = bearish signal over for PE)
                    if analysis.candles_until_ema_cross == 0 and post_candle.close > ema9:
                        analysis.candles_until_ema_cross = j + 1
                        analysis.pnl_at_ema_cross = (current_entry["entry_price"] - post_candle.close) / current_entry["entry_price"] * 100
                    
                    # Check VWAP cross (price crosses above VWAP = bearish signal over for PE)
                    if analysis.candles_until_vwap_cross == 0 and post_candle.close > vwap:
                        analysis.candles_until_vwap_cross = j + 1
                        analysis.pnl_at_vwap_cross = (current_entry["entry_price"] - post_candle.close) / current_entry["entry_price"] * 100
                
                # Determine exit quality
                if analysis.max_potential_pnl <= analysis.actual_pnl_pct + 0.1:
                    analysis.exit_quality = "perfect"  # Within 0.1% of optimal
                elif analysis.max_potential_pnl > analysis.actual_pnl_pct + 0.3:
                    analysis.exit_quality = "early"  # Missed more than 0.3% profit
                elif analysis.highest_price_after_exit > candle.close * 1.003:
                    analysis.exit_quality = "good"  # Price bounced up after exit
                else:
                    analysis.exit_quality = "neutral"
            
            analyses.append(analysis)
            
            win_emoji = "✅" if actual_pnl > 0 else "❌"
            print(f"  {win_emoji}📉 PE EXIT: {candle.timestamp} @ {candle.close:.2f} ({actual_pnl:+.2f}%)")
            print(f"      Reason: {analysis.exit_reason}")
            
            if candles_after_exit:
                print(f"      After exit: Lowest={analysis.lowest_price_after_exit:.2f} (max potential: {analysis.max_potential_pnl:+.2f}%)")
                print(f"      EMA9 cross: {analysis.candles_until_ema_cross} candles ({analysis.pnl_at_ema_cross:+.2f}% at cross)")
                print(f"      VWAP cross: {analysis.candles_until_vwap_cross} candles ({analysis.pnl_at_vwap_cross:+.2f}% at cross)")
                print(f"      Exit quality: {analysis.exit_quality}")
            
            current_entry = None
    
    return analyses


def summarize_analyses(all_analyses: List[PEExitAnalysis]):
    """Summarize findings across all PE exits."""
    if not all_analyses:
        print("No PE exits to analyze.")
        return
    
    print(f"\n{'='*80}")
    print("PE EXIT ANALYSIS SUMMARY")
    print(f"{'='*80}")
    
    total = len(all_analyses)
    
    # Actual performance
    actual_wins = sum(1 for a in all_analyses if a.actual_pnl_pct > 0)
    actual_total_pnl = sum(a.actual_pnl_pct for a in all_analyses)
    
    print(f"\n📊 ACTUAL PERFORMANCE (Current Strategy):")
    print(f"   Total PE Trades: {total}")
    print(f"   Win Rate: {actual_wins/total*100:.1f}%")
    print(f"   Total P&L: {actual_total_pnl:+.2f}%")
    print(f"   Avg P&L per trade: {actual_total_pnl/total:+.2f}%")
    
    # What if we waited for EMA9 cross?
    ema_exits = [a for a in all_analyses if a.candles_until_ema_cross > 0]
    if ema_exits:
        ema_wins = sum(1 for a in ema_exits if a.pnl_at_ema_cross > 0)
        ema_total_pnl = sum(a.pnl_at_ema_cross for a in ema_exits)
        ema_avg_candles = statistics.mean(a.candles_until_ema_cross for a in ema_exits)
        
        print(f"\n📈 IF WE WAITED FOR EMA9 CROSS (price above EMA9):")
        print(f"   Trades with EMA cross: {len(ema_exits)}/{total}")
        print(f"   Win Rate: {ema_wins/len(ema_exits)*100:.1f}%")
        print(f"   Total P&L: {ema_total_pnl:+.2f}%")
        print(f"   Avg P&L per trade: {ema_total_pnl/len(ema_exits):+.2f}%")
        print(f"   Avg candles until EMA cross: {ema_avg_candles:.1f} ({ema_avg_candles*5:.0f} mins)")
    
    # What if we waited for VWAP cross?
    vwap_exits = [a for a in all_analyses if a.candles_until_vwap_cross > 0]
    if vwap_exits:
        vwap_wins = sum(1 for a in vwap_exits if a.pnl_at_vwap_cross > 0)
        vwap_total_pnl = sum(a.pnl_at_vwap_cross for a in vwap_exits)
        vwap_avg_candles = statistics.mean(a.candles_until_vwap_cross for a in vwap_exits)
        
        print(f"\n📊 IF WE WAITED FOR VWAP CROSS (price above VWAP):")
        print(f"   Trades with VWAP cross: {len(vwap_exits)}/{total}")
        print(f"   Win Rate: {vwap_wins/len(vwap_exits)*100:.1f}%")
        print(f"   Total P&L: {vwap_total_pnl:+.2f}%")
        print(f"   Avg P&L per trade: {vwap_total_pnl/len(vwap_exits):+.2f}%")
        print(f"   Avg candles until VWAP cross: {vwap_avg_candles:.1f} ({vwap_avg_candles*5:.0f} mins)")
    
    # Max potential analysis
    max_potential_pnl = sum(a.max_potential_pnl for a in all_analyses)
    missed_profits = [a.max_potential_pnl - a.actual_pnl_pct for a in all_analyses if a.max_potential_pnl > a.actual_pnl_pct]
    
    print(f"\n🎯 MAXIMUM POTENTIAL (Perfect Exits):")
    print(f"   Max potential P&L: {max_potential_pnl:+.2f}%")
    print(f"   Actual P&L: {actual_total_pnl:+.2f}%")
    print(f"   Profit left on table: {max_potential_pnl - actual_total_pnl:+.2f}%")
    if missed_profits:
        print(f"   Avg missed profit per trade: {statistics.mean(missed_profits):+.2f}%")
    
    # Exit quality breakdown
    perfect = sum(1 for a in all_analyses if a.exit_quality == "perfect")
    good = sum(1 for a in all_analyses if a.exit_quality == "good")
    early = sum(1 for a in all_analyses if a.exit_quality == "early")
    neutral = sum(1 for a in all_analyses if a.exit_quality == "neutral")
    
    print(f"\n📋 EXIT QUALITY BREAKDOWN:")
    print(f"   Perfect (optimal): {perfect}/{total} ({perfect/total*100:.1f}%)")
    print(f"   Good (bounced up): {good}/{total} ({good/total*100:.1f}%)")
    print(f"   Early (missed profit): {early}/{total} ({early/total*100:.1f}%)")
    print(f"   Neutral: {neutral}/{total} ({neutral/total*100:.1f}%)")
    
    # Exit reason breakdown
    print(f"\n📋 EXIT REASON BREAKDOWN:")
    reason_stats = defaultdict(list)
    for a in all_analyses:
        reason_stats[a.exit_reason].append(a.actual_pnl_pct)
    
    for reason, pnls in sorted(reason_stats.items()):
        wins = sum(1 for p in pnls if p > 0)
        total_pnl = sum(pnls)
        print(f"   {reason}:")
        print(f"      Count: {len(pnls)}, Win rate: {wins/len(pnls)*100:.1f}%, P&L: {total_pnl:+.2f}%")
    
    # Recommendation
    print(f"\n{'='*80}")
    print("💡 RECOMMENDATION:")
    
    # Compare strategies
    strategies = [
        ("Current (Big candle)", actual_total_pnl, actual_wins/total*100 if total > 0 else 0),
    ]
    
    if ema_exits:
        strategies.append(("EMA9 Cross", ema_total_pnl, ema_wins/len(ema_exits)*100))
    if vwap_exits:
        strategies.append(("VWAP Cross", vwap_total_pnl, vwap_wins/len(vwap_exits)*100))
    
    best = max(strategies, key=lambda x: x[1])
    print(f"   Best exit strategy: {best[0]} (P&L: {best[1]:+.2f}%, Win: {best[2]:.1f}%)")
    
    if best[0] != "Current (Big candle)":
        improvement = best[1] - actual_total_pnl
        print(f"   Potential improvement: {improvement:+.2f}% over current strategy")


async def main():
    parser = argparse.ArgumentParser(description="Analyze PE exit quality")
    parser.add_argument("--symbols", type=str, default="SBIN,TCS,NHPC,ETERNAL,PNB",
                       help="Comma-separated list of symbols")
    parser.add_argument("--days", type=int, default=60,
                       help="Number of days to backtest")
    args = parser.parse_args()
    
    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    
    all_analyses: List[PEExitAnalysis] = []
    
    for symbol in symbols:
        candles = await get_candles_for_symbol(symbol, args.days)
        
        if len(candles) < 1000:
            print(f"Skipping {symbol} - insufficient data ({len(candles)} candles)")
            continue
        
        analyses = analyze_pe_exits(symbol, candles)
        all_analyses.extend(analyses)
    
    summarize_analyses(all_analyses)


if __name__ == "__main__":
    asyncio.run(main())
