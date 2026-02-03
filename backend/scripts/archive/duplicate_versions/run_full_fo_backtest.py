#!/usr/bin/env python3
"""
Run backtest on ALL F&O stocks and generate a summary report.
"""

import asyncio
import sys
import os
from datetime import date, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text
from app.db.session import get_db_context


async def get_all_fo_symbols():
    """Get all F&O symbols with sufficient data."""
    async with get_db_context() as db:
        result = await db.execute(text("""
            SELECT im.trading_symbol
            FROM instrument_master im
            JOIN candle_data cd ON im.instrument_id = cd.instrument_id
            WHERE im.instrument_type = 'EQUITY'
            AND im.exchange = 'NSE'
            GROUP BY im.trading_symbol
            HAVING COUNT(*) > 5000
            ORDER BY trading_symbol
        """))
        rows = result.fetchall()
        return [row[0] for row in rows]


async def main():
    symbols = await get_all_fo_symbols()
    print(f"Found {len(symbols)} F&O symbols")
    
    # Build symbol list for command
    symbol_str = ",".join(symbols)
    
    # Run backtest
    from backtest_intraday_momentum import get_candles_for_symbol, run_backtest_for_symbol
    from app.strategies.intraday_momentum_oi import IntradayMomentumConfig
    from datetime import time
    
    config = IntradayMomentumConfig(
        entry_window_start=time(10, 15),
        entry_window_end=time(12, 0),
        trailing_sl_pct=0.5,
        enable_ce_trades=True,
        enable_pe_trades=True,
        ce_min_hold_candles=8,
        ce_require_ema_confirm=True,
    )
    
    # Collect results per symbol
    ce_results = {}  # symbol -> {trades, wins, pnl}
    pe_results = {}
    
    days = 30
    processed = 0
    
    for symbol in symbols:
        try:
            candles = await get_candles_for_symbol(symbol, days)
            if len(candles) < 100:
                continue
            
            result = run_backtest_for_symbol(symbol, candles, config, verbose=False)
            
            # Extract CE and PE stats
            ce_trades = [t for t in result.trades if t.direction == "CE"]
            pe_trades = [t for t in result.trades if t.direction == "PE"]
            
            if ce_trades:
                ce_pnl = sum(t.pnl_pct for t in ce_trades)
                ce_wins = sum(1 for t in ce_trades if t.pnl_pct > 0)
                ce_results[symbol] = {
                    'trades': len(ce_trades),
                    'wins': ce_wins,
                    'pnl': ce_pnl
                }
            
            if pe_trades:
                pe_pnl = sum(t.pnl_pct for t in pe_trades)
                pe_wins = sum(1 for t in pe_trades if t.pnl_pct > 0)
                pe_results[symbol] = {
                    'trades': len(pe_trades),
                    'wins': pe_wins,
                    'pnl': pe_pnl
                }
            
            processed += 1
            if processed % 20 == 0:
                print(f"Processed {processed}/{len(symbols)} symbols...")
                
        except Exception as e:
            pass
    
    # Print summary
    print("\n" + "=" * 80)
    print("F&O BACKTEST SUMMARY - 30 DAYS - ALL STOCKS")
    print("=" * 80)
    
    # Sort by P&L
    ce_sorted = sorted(ce_results.items(), key=lambda x: x[1]['pnl'], reverse=True)
    pe_sorted = sorted(pe_results.items(), key=lambda x: x[1]['pnl'], reverse=True)
    
    # CE Summary
    total_ce_trades = sum(r['trades'] for r in ce_results.values())
    total_ce_wins = sum(r['wins'] for r in ce_results.values())
    total_ce_pnl = sum(r['pnl'] for r in ce_results.values())
    
    print(f"\n📈 CE (CALL) TRADES:")
    print(f"   Total: {total_ce_trades} trades | Win Rate: {100*total_ce_wins/total_ce_trades:.1f}% | P&L: {total_ce_pnl:+.2f}%")
    print(f"\n   Top 10 Winners:")
    print(f"   {'Symbol':<15} {'Trades':>8} {'Win%':>8} {'P&L':>10}")
    print(f"   {'-'*45}")
    for symbol, data in ce_sorted[:10]:
        win_pct = 100 * data['wins'] / data['trades'] if data['trades'] > 0 else 0
        print(f"   {symbol:<15} {data['trades']:>8} {win_pct:>7.1f}% {data['pnl']:>+9.2f}%")
    
    print(f"\n   Bottom 10 Losers:")
    print(f"   {'Symbol':<15} {'Trades':>8} {'Win%':>8} {'P&L':>10}")
    print(f"   {'-'*45}")
    for symbol, data in ce_sorted[-10:]:
        win_pct = 100 * data['wins'] / data['trades'] if data['trades'] > 0 else 0
        print(f"   {symbol:<15} {data['trades']:>8} {win_pct:>7.1f}% {data['pnl']:>+9.2f}%")
    
    # PE Summary
    if pe_results:
        total_pe_trades = sum(r['trades'] for r in pe_results.values())
        total_pe_wins = sum(r['wins'] for r in pe_results.values())
        total_pe_pnl = sum(r['pnl'] for r in pe_results.values())
        
        print(f"\n📉 PE (PUT) TRADES:")
        print(f"   Total: {total_pe_trades} trades | Win Rate: {100*total_pe_wins/total_pe_trades:.1f}% | P&L: {total_pe_pnl:+.2f}%")
        print(f"\n   Top PE Performers:")
        print(f"   {'Symbol':<15} {'Trades':>8} {'Win%':>8} {'P&L':>10}")
        print(f"   {'-'*45}")
        for symbol, data in pe_sorted[:10]:
            win_pct = 100 * data['wins'] / data['trades'] if data['trades'] > 0 else 0
            print(f"   {symbol:<15} {data['trades']:>8} {win_pct:>7.1f}% {data['pnl']:>+9.2f}%")
    
    # Overall
    total_pnl = total_ce_pnl + (total_pe_pnl if pe_results else 0)
    total_trades = total_ce_trades + (total_pe_trades if pe_results else 0)
    
    print(f"\n{'=' * 80}")
    print(f"OVERALL: {total_trades} trades | P&L: {total_pnl:+.2f}%")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(main())
