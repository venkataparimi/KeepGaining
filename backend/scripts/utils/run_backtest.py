"""
Backtest Runner Script
KeepGaining Trading Platform

Run backtests on the historical data with pre-computed indicators.
Tests multiple strategies across F&O symbols.

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --strategy EMA_CROSS --symbols RELIANCE,TCS
"""

import asyncio
import argparse
import logging
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.backtest.backtest_engine import (
    BacktestEngine,
    BacktestConfig,
    format_backtest_report,
)
from app.strategies.indicator_strategies import (
    AVAILABLE_STRATEGIES,
    get_strategy,
    EMACrossoverStrategy,
    RSIMomentumStrategy,
    SupertrendStrategy,
    VWAPBounceStrategy,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Default F&O symbols to test
DEFAULT_SYMBOLS = [
    "NSE:RELIANCE-EQ",
    "NSE:TCS-EQ",
    "NSE:HDFCBANK-EQ",
    "NSE:INFY-EQ",
    "NSE:ICICIBANK-EQ",
    "NSE:SBIN-EQ",
    "NSE:BHARTIARTL-EQ",
    "NSE:KOTAKBANK-EQ",
    "NSE:LT-EQ",
    "NSE:ITC-EQ",
]


async def run_single_backtest(
    strategy_id: str,
    symbols: list,
    start_date: date,
    end_date: date,
    initial_capital: float = 1_000_000,
):
    """Run backtest for a single strategy."""
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Running Backtest: {strategy_id}")
    logger.info(f"{'='*60}")
    
    # Get strategy
    strategy = get_strategy(strategy_id)
    
    # Configure backtest
    config = BacktestConfig(
        initial_capital=Decimal(str(initial_capital)),
        position_size_pct=Decimal("5.0"),
        max_positions=5,
        slippage_pct=Decimal("0.1"),
        commission_per_trade=Decimal("20"),
        allow_shorting=False,
        exit_at_eod=True,
    )
    
    # Create engine and run
    engine = BacktestEngine(config=config)
    
    try:
        result = await engine.run_backtest(
            strategy=strategy,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            config=config,
        )
        
        # Print report
        report = format_backtest_report(result)
        print(report)
        
        # Print recent trades
        if result.trades:
            print("\nRecent Trades (last 10):")
            print("-" * 100)
            print(f"{'Symbol':<20} {'Side':<8} {'Entry':<12} {'Exit':<12} {'P&L':>12} {'%':>8} {'Reason':<15}")
            print("-" * 100)
            
            for trade in result.trades[-10:]:
                print(
                    f"{trade.symbol:<20} "
                    f"{trade.side.value:<8} "
                    f"{float(trade.entry_price):<12.2f} "
                    f"{float(trade.exit_price):<12.2f} "
                    f"{float(trade.pnl):>12.2f} "
                    f"{float(trade.pnl_percent):>8.2f}% "
                    f"{trade.exit_reason:<15}"
                )
        
        return result
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        return None


async def run_all_strategies(
    symbols: list,
    start_date: date,
    end_date: date,
    initial_capital: float = 1_000_000,
):
    """Run backtests for all available strategies and compare."""
    
    results = {}
    
    for strategy_id in AVAILABLE_STRATEGIES.keys():
        result = await run_single_backtest(
            strategy_id=strategy_id,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )
        if result:
            results[strategy_id] = result
    
    # Print comparison summary
    if results:
        print("\n" + "=" * 80)
        print("STRATEGY COMPARISON SUMMARY")
        print("=" * 80)
        print(f"{'Strategy':<20} {'Trades':>8} {'Win%':>8} {'Net P&L':>15} {'Return%':>10} {'MaxDD%':>10}")
        print("-" * 80)
        
        for strategy_id, result in results.items():
            m = result.metrics
            print(
                f"{strategy_id:<20} "
                f"{m.total_trades:>8} "
                f"{m.win_rate:>8.1f} "
                f"₹{float(m.net_profit):>14,.0f} "
                f"{m.return_pct:>10.2f} "
                f"{m.max_drawdown_pct:>10.2f}"
            )
        
        print("=" * 80)
    
    return results


async def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(description="Run backtests on trading strategies")
    parser.add_argument(
        "--strategy",
        type=str,
        choices=list(AVAILABLE_STRATEGIES.keys()) + ["ALL"],
        default="ALL",
        help="Strategy to backtest (default: ALL)"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols (e.g., RELIANCE,TCS,INFY)"
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1_000_000,
        help="Initial capital (default: 1000000)"
    )
    
    args = parser.parse_args()
    
    # Parse symbols
    if args.symbols:
        symbols = [f"NSE:{s.strip()}-EQ" for s in args.symbols.split(",")]
    else:
        symbols = DEFAULT_SYMBOLS
    
    # Parse dates (default: last 3 months)
    end_date = date.today() if args.end is None else date.fromisoformat(args.end)
    start_date = end_date - timedelta(days=90) if args.start is None else date.fromisoformat(args.start)
    
    logger.info(f"Backtest Configuration:")
    logger.info(f"  Symbols: {len(symbols)} ({symbols[0]}...)")
    logger.info(f"  Period: {start_date} to {end_date}")
    logger.info(f"  Capital: ₹{args.capital:,.0f}")
    
    if args.strategy == "ALL":
        await run_all_strategies(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_capital=args.capital,
        )
    else:
        await run_single_backtest(
            strategy_id=args.strategy,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_capital=args.capital,
        )


if __name__ == "__main__":
    asyncio.run(main())
