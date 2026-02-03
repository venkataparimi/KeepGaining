#!/usr/bin/env python3
"""
Unified Backtest CLI
KeepGaining Trading Platform

Command-line interface for running backtests with standardized output.

Usage:
    python backtest_cli.py single --strategy IntradayMomentumOI --symbols RELIANCE,TCS --start 2024-01-01 --end 2024-12-01
    python backtest_cli.py walk-forward --strategy EMAScalping --symbols NIFTY --training-days 180 --testing-days 30
    python backtest_cli.py compare --strategies IntradayMomentumOI,EMAScalping,SectorMomentum --symbols RELIANCE
    python backtest_cli.py full --strategy IntradayMomentumOI --symbols RELIANCE,TCS,INFY
"""

import sys
import os
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
import json
from datetime import datetime, date, timedelta
from typing import List, Optional
import pandas as pd
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")


def load_strategy(strategy_name: str):
    """Load strategy class by name."""
    strategies = {
        "IntradayMomentumOI": "app.strategies.intraday_momentum_oi.IntradayMomentumOIStrategy",
        "EMAScalping": "app.strategies.ema_scalping.EMAScalpingStrategy", 
        "SectorMomentum": "app.strategies.sector_momentum.SectorMomentumStrategy",
        "IndicatorStrategy": "app.strategies.indicator_strategies.VolumeRocketStrategy",
    }
    
    if strategy_name not in strategies:
        available = ", ".join(strategies.keys())
        raise click.ClickException(f"Unknown strategy: {strategy_name}. Available: {available}")
    
    # Import strategy class
    module_path, class_name = strategies[strategy_name].rsplit(".", 1)
    
    try:
        import importlib
        module = importlib.import_module(module_path)
        strategy_class = getattr(module, class_name)
        return strategy_class()
    except Exception as e:
        raise click.ClickException(f"Failed to load strategy {strategy_name}: {e}")


def load_data(
    symbols: List[str],
    start_date: date,
    end_date: date,
    source: str = "database",
) -> pd.DataFrame:
    """Load market data for backtesting."""
    
    if source == "database":
        # Load from PostgreSQL
        try:
            from app.db.session import get_sync_session
            from sqlalchemy import text
            
            with get_sync_session() as session:
                # Query candle data with indicators
                query = text("""
                    SELECT 
                        c.timestamp,
                        im.symbol,
                        c.open,
                        c.high,
                        c.low,
                        c.close,
                        c.volume,
                        c.oi,
                        i.ema_9,
                        i.ema_21,
                        i.rsi_14,
                        i.macd,
                        i.macd_signal,
                        i.atr_14,
                        i.supertrend,
                        i.supertrend_direction
                    FROM candle_data c
                    JOIN instrument_master im ON c.instrument_id = im.instrument_id
                    LEFT JOIN indicator_data i ON c.instrument_id = i.instrument_id 
                        AND c.timestamp = i.timestamp
                    WHERE im.symbol = ANY(:symbols)
                        AND c.timestamp >= :start_date
                        AND c.timestamp <= :end_date
                    ORDER BY c.timestamp
                """)
                
                result = session.execute(query, {
                    "symbols": symbols,
                    "start_date": start_date,
                    "end_date": end_date,
                })
                
                data = pd.DataFrame(result.fetchall(), columns=result.keys())
                data.set_index("timestamp", inplace=True)
                
                return data
                
        except Exception as e:
            logger.warning(f"Failed to load from database: {e}")
            logger.info("Falling back to CSV data")
            source = "csv"
    
    if source == "csv":
        # Load from CSV files in data_downloads/
        data_dir = Path(__file__).parent.parent / "data_downloads"
        frames = []
        
        for symbol in symbols:
            csv_path = data_dir / f"NSE_{symbol}_EQ.csv"
            if csv_path.exists():
                df = pd.read_csv(csv_path, parse_dates=["timestamp"])
                df["symbol"] = symbol
                df = df[(df["timestamp"].dt.date >= start_date) & (df["timestamp"].dt.date <= end_date)]
                frames.append(df)
            else:
                logger.warning(f"No data file for {symbol}")
        
        if frames:
            data = pd.concat(frames)
            data.set_index("timestamp", inplace=True)
            return data
    
    # Generate sample data if no real data available
    logger.warning("Using sample data - results are for demonstration only")
    return generate_sample_data(symbols, start_date, end_date)


def generate_sample_data(
    symbols: List[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Generate sample data for testing."""
    import numpy as np
    
    dates = pd.date_range(start=start_date, end=end_date, freq="1min")
    # Filter to market hours (9:15 - 15:30)
    dates = dates[(dates.hour >= 9) & (dates.hour < 16)]
    dates = dates[~((dates.hour == 9) & (dates.minute < 15))]
    dates = dates[~((dates.hour == 15) & (dates.minute > 30))]
    
    frames = []
    for symbol in symbols:
        np.random.seed(hash(symbol) % 2**32)
        
        # Generate random walk prices
        returns = np.random.normal(0.0001, 0.002, len(dates))
        price = 100 * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            "timestamp": dates,
            "symbol": symbol,
            "open": price * (1 + np.random.uniform(-0.001, 0.001, len(dates))),
            "high": price * (1 + np.abs(np.random.normal(0, 0.005, len(dates)))),
            "low": price * (1 - np.abs(np.random.normal(0, 0.005, len(dates)))),
            "close": price,
            "volume": np.random.randint(1000, 100000, len(dates)),
        })
        frames.append(df)
    
    data = pd.concat(frames)
    data.set_index("timestamp", inplace=True)
    return data


def format_report(report, format: str = "text") -> str:
    """Format report for output."""
    if format == "json":
        return json.dumps(report.to_dict(), indent=2, default=str)
    
    # Text format
    lines = [
        "=" * 60,
        f"BACKTEST REPORT: {report.strategy_name}",
        "=" * 60,
        f"Period: {report.start_date} to {report.end_date}",
        f"Symbols: {', '.join(report.symbols)}",
        "",
        "--- PERFORMANCE METRICS ---",
        f"Total Trades:     {report.total_trades}",
        f"Win Rate:         {report.win_rate:.1f}%",
        f"Profit Factor:    {report.profit_factor:.2f}",
        f"Sharpe Ratio:     {report.sharpe_ratio:.2f}",
        f"Max Drawdown:     {report.max_drawdown:.1f}%",
        f"Total Return:     {report.total_return:.2f}%",
        "",
    ]
    
    if report.walk_forward_efficiency > 0:
        lines.extend([
            "--- WALK-FORWARD ANALYSIS ---",
            f"Efficiency Ratio: {report.walk_forward_efficiency:.2f}",
            "",
        ])
    
    if report.monte_carlo_confidence > 0:
        lines.extend([
            "--- MONTE CARLO ANALYSIS ---",
            f"P(Profit):        {report.monte_carlo_confidence:.1%}",
            f"Path Dependency:  {report.path_dependency:.2f}",
            "",
        ])
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


@click.group()
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--format", "-f", type=click.Choice(["text", "json", "csv"]), default="text")
@click.pass_context
def cli(ctx, output, format):
    """Unified Backtest CLI for KeepGaining Trading Platform."""
    ctx.ensure_object(dict)
    ctx.obj["output"] = output
    ctx.obj["format"] = format


@cli.command()
@click.option("--strategy", "-s", required=True, help="Strategy name")
@click.option("--symbols", required=True, help="Comma-separated symbols")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", required=True, help="End date (YYYY-MM-DD)")
@click.option("--capital", default=100000, help="Initial capital")
@click.option("--position-size", default=10.0, help="Position size %")
@click.pass_context
def single(ctx, strategy, symbols, start, end, capital, position_size):
    """Run a single backtest."""
    from app.backtest.runner import BacktestRunner
    from app.backtest.enhanced_engine import BacktestConfig
    
    # Parse inputs
    symbol_list = [s.strip() for s in symbols.split(",")]
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    
    click.echo(f"Loading strategy: {strategy}")
    strategy_instance = load_strategy(strategy)
    
    click.echo(f"Loading data for {len(symbol_list)} symbols...")
    data = load_data(symbol_list, start_date, end_date)
    click.echo(f"Loaded {len(data)} candles")
    
    # Configure and run
    config = BacktestConfig(
        initial_capital=capital,
        position_size_percent=position_size,
    )
    
    runner = BacktestRunner(config=config)
    report = runner.run_single(strategy_instance, data, symbol_list, start_date, end_date)
    
    # Output
    output_text = format_report(report, ctx.obj["format"])
    
    if ctx.obj["output"]:
        Path(ctx.obj["output"]).write_text(output_text)
        click.echo(f"Report saved to {ctx.obj['output']}")
    else:
        click.echo(output_text)


@cli.command("walk-forward")
@click.option("--strategy", "-s", required=True, help="Strategy name")
@click.option("--symbols", required=True, help="Comma-separated symbols")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", required=True, help="End date (YYYY-MM-DD)")
@click.option("--training-days", default=180, help="Training period in days")
@click.option("--testing-days", default=30, help="Testing period in days")
@click.pass_context
def walk_forward(ctx, strategy, symbols, start, end, training_days, testing_days):
    """Run walk-forward validation."""
    from app.backtest.runner import BacktestRunner
    
    # Parse inputs
    symbol_list = [s.strip() for s in symbols.split(",")]
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    
    click.echo(f"Loading strategy: {strategy}")
    strategy_instance = load_strategy(strategy)
    
    click.echo(f"Loading data...")
    data = load_data(symbol_list, start_date, end_date)
    
    runner = BacktestRunner()
    report = runner.run_walk_forward(
        strategy_instance,
        data,
        training_days=training_days,
        testing_days=testing_days,
    )
    
    # Output
    output_text = format_report(report, ctx.obj["format"])
    
    if ctx.obj["output"]:
        Path(ctx.obj["output"]).write_text(output_text)
        click.echo(f"Report saved to {ctx.obj['output']}")
    else:
        click.echo(output_text)


@cli.command()
@click.option("--strategy", "-s", required=True, help="Strategy name")
@click.option("--symbols", required=True, help="Comma-separated symbols")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", required=True, help="End date (YYYY-MM-DD)")
@click.option("--simulations", default=1000, help="Monte Carlo simulations")
@click.pass_context
def full(ctx, strategy, symbols, start, end, simulations):
    """Run full analysis (single + walk-forward + Monte Carlo)."""
    from app.backtest.runner import BacktestRunner
    
    # Parse inputs
    symbol_list = [s.strip() for s in symbols.split(",")]
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    
    click.echo(f"Running full analysis for {strategy}...")
    strategy_instance = load_strategy(strategy)
    
    data = load_data(symbol_list, start_date, end_date)
    
    runner = BacktestRunner()
    report = runner.run_full(
        strategy_instance,
        data,
        mc_simulations=simulations,
    )
    
    # Output
    output_text = format_report(report, ctx.obj["format"])
    
    if ctx.obj["output"]:
        Path(ctx.obj["output"]).write_text(output_text)
        click.echo(f"Report saved to {ctx.obj['output']}")
    else:
        click.echo(output_text)


@cli.command()
@click.option("--strategies", required=True, help="Comma-separated strategy names")
@click.option("--symbols", required=True, help="Comma-separated symbols")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", required=True, help="End date (YYYY-MM-DD)")
@click.pass_context
def compare(ctx, strategies, symbols, start, end):
    """Compare multiple strategies."""
    from app.backtest.runner import BacktestRunner

    # Parse inputs
    strategy_names = [s.strip() for s in strategies.split(",")]
    symbol_list = [s.strip() for s in symbols.split(",")]
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    
    click.echo(f"Comparing {len(strategy_names)} strategies...")
    
    strategy_instances = [load_strategy(name) for name in strategy_names]
    data = load_data(symbol_list, start_date, end_date)
    
    runner = BacktestRunner()
    comparison = runner.compare(strategy_instances, data)
    
    # Format comparison output
    lines = [
        "=" * 70,
        "STRATEGY COMPARISON REPORT",
        "=" * 70,
        f"Period: {start_date} to {end_date}",
        f"Symbols: {', '.join(symbol_list)}",
        "",
        "--- RANKINGS ---",
        "",
        f"{'Strategy':<25} {'Sharpe':>10} {'Return':>10} {'Drawdown':>10} {'Win Rate':>10}",
        "-" * 70,
    ]
    
    for name, report in comparison.results.items():
        lines.append(
            f"{name:<25} {report.sharpe_ratio:>10.2f} {report.total_return:>9.1f}% "
            f"{report.max_drawdown:>9.1f}% {report.win_rate:>9.1f}%"
        )
    
    lines.extend([
        "",
        "--- BEST STRATEGIES ---",
        f"Best by Sharpe:      {comparison.best_by_sharpe}",
        f"Best by Return:      {comparison.best_by_return}",
        f"Best by Drawdown:    {comparison.best_by_drawdown}",
        f"Best by Consistency: {comparison.best_by_consistency}",
        "=" * 70,
    ])
    
    output_text = "\n".join(lines)
    
    if ctx.obj["output"]:
        Path(ctx.obj["output"]).write_text(output_text)
        click.echo(f"Report saved to {ctx.obj['output']}")
    else:
        click.echo(output_text)


@cli.command()
def list_strategies():
    """List available strategies."""
    strategies = {
        "IntradayMomentumOI": "Price action + OI based intraday options strategy",
        "EMAScalping": "9/15 EMA crossover with 30° slope filter",
        "SectorMomentum": "Morning sector ranking and stock selection",
        "IndicatorStrategy": "VWMA + Supertrend + RSI confirmation",
    }
    
    click.echo("\nAvailable Strategies:")
    click.echo("-" * 50)
    for name, desc in strategies.items():
        click.echo(f"  {name:<25} {desc}")
    click.echo()


if __name__ == "__main__":
    cli()
