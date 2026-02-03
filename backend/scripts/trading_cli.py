#!/usr/bin/env python3
"""
Trading CLI Tool

Command-line interface for testing and controlling the trading system.

Usage:
    python trading_cli.py start --mode paper --capital 100000
    python trading_cli.py status
    python trading_cli.py add-strategy VOLROCKET
    python trading_cli.py simulate-signal RELIANCE 2500 2450 2600
    python trading_cli.py positions
    python trading_cli.py stop
"""

import asyncio
import argparse
import sys
from decimal import Decimal
from datetime import datetime
from typing import Optional

# Add the backend to path
sys.path.insert(0, ".")

from app.execution.orchestrator import (
    TradingOrchestrator, 
    TradingMode, 
    OrchestratorConfig,
    create_orchestrator
)
from app.execution.paper_trading import (
    PaperTradingEngine,
    PaperTradingConfig,
    OrderSide
)
from app.execution.position_sizing import (
    PositionSizer,
    SizingMethod
)
from app.services.strategy_engine import (
    Signal, 
    SignalType, 
    SignalStrength,
    VolumeRocketStrategy
)


# Global orchestrator instance
orchestrator: Optional[TradingOrchestrator] = None


async def start_trading(args):
    """Start the trading system."""
    global orchestrator
    
    print(f"\n{'='*60}")
    print("Starting KeepGaining Paper Trading System")
    print(f"{'='*60}")
    
    # Create configuration
    config = OrchestratorConfig(
        paper_capital=Decimal(str(args.capital)),
        max_daily_loss=Decimal(str(args.max_loss)),
        max_positions=args.max_positions
    )
    
    # Create orchestrator (without event bus for CLI testing)
    orchestrator = TradingOrchestrator(config=config, event_bus=None)
    
    # Parse mode
    mode = TradingMode.PAPER if args.mode == "paper" else TradingMode.LIVE
    
    # Start with strategies
    strategies = args.strategies.split(",") if args.strategies else None
    
    success = await orchestrator.start(mode=mode, strategies=strategies)
    
    if success:
        status = orchestrator.get_status()
        print(f"\n✅ Trading system started successfully!")
        print(f"   Mode: {status['mode']}")
        print(f"   Capital: ₹{config.paper_capital:,.2f}")
        print(f"   Max Loss: ₹{config.max_daily_loss:,.2f}")
        print(f"   Max Positions: {config.max_positions}")
        if strategies:
            print(f"   Strategies: {', '.join(strategies)}")
    else:
        print("\n❌ Failed to start trading system")
        return 1
    
    return 0


async def stop_trading(args):
    """Stop the trading system."""
    global orchestrator
    
    if not orchestrator:
        print("❌ Trading system not running")
        return 1
    
    await orchestrator.stop()
    print("\n✅ Trading system stopped")
    return 0


async def get_status(args):
    """Get system status."""
    global orchestrator
    
    if not orchestrator:
        print("❌ Trading system not running")
        return 1
    
    status = orchestrator.get_status()
    
    print(f"\n{'='*60}")
    print("Trading System Status")
    print(f"{'='*60}")
    print(f"Status: {status['status']}")
    print(f"Mode: {status['mode']}")
    print(f"Halted: {status['trading_halted']}")
    if status['halt_reason']:
        print(f"Halt Reason: {status['halt_reason']}")
    
    if status['session']:
        print(f"\nSession: {status['session']['id']}")
        print(f"Started: {status['session']['started_at']}")
        print(f"Initial Capital: ₹{status['session']['initial_capital']:,.2f}")
        print(f"Strategies: {', '.join(status['session']['strategies_active'])}")
    
    print(f"\nDaily Stats:")
    print(f"  P&L: ₹{status['daily_stats']['pnl']:,.2f}")
    print(f"  Trades: {status['daily_stats']['trades']}")
    
    return 0


async def get_portfolio(args):
    """Get portfolio status."""
    global orchestrator
    
    if not orchestrator:
        print("❌ Trading system not running")
        return 1
    
    portfolio = orchestrator.get_portfolio()
    
    if not portfolio:
        print("❌ No portfolio data available")
        return 1
    
    print(f"\n{'='*60}")
    print("Portfolio Summary")
    print(f"{'='*60}")
    print(f"Initial Capital: ₹{portfolio['initial_capital']:,.2f}")
    print(f"Current Capital: ₹{portfolio['current_capital']:,.2f}")
    print(f"Available: ₹{portfolio['available_capital']:,.2f}")
    print(f"Used Margin: ₹{portfolio['used_margin']:,.2f}")
    print(f"\nUnrealized P&L: ₹{portfolio['unrealized_pnl']:,.2f}")
    print(f"Realized P&L: ₹{portfolio['realized_pnl']:,.2f}")
    print(f"Total P&L: ₹{portfolio['total_pnl']:,.2f}")
    print(f"Return: {portfolio['total_return_percent']:.2f}%")
    print(f"\nOpen Positions: {portfolio['open_positions']}")
    print(f"Total Trades: {portfolio['total_trades']}")
    
    if portfolio['positions']:
        print(f"\n{'='*60}")
        print("Open Positions")
        print(f"{'='*60}")
        for pos in portfolio['positions']:
            pnl_str = f"₹{pos['unrealized_pnl']:+,.2f}"
            print(f"  {pos['symbol']}: {pos['side']} {pos['quantity']} @ {pos['avg_price']:.2f}")
            print(f"    LTP: {pos['current_price']:.2f} | P&L: {pnl_str}")
            if pos['stop_loss']:
                print(f"    SL: {pos['stop_loss']:.2f} | Target: {pos['target']:.2f}")
    
    return 0


async def get_positions(args):
    """Get open positions."""
    global orchestrator
    
    if not orchestrator:
        print("❌ Trading system not running")
        return 1
    
    positions = orchestrator.get_positions()
    
    if not positions:
        print("\n📭 No open positions")
        return 0
    
    print(f"\n{'='*60}")
    print(f"Open Positions ({len(positions)})")
    print(f"{'='*60}")
    
    for pos in positions:
        pnl = pos['unrealized_pnl']
        pnl_color = "🟢" if pnl >= 0 else "🔴"
        print(f"\n{pnl_color} {pos['symbol']}")
        print(f"   Side: {pos['side']} | Qty: {pos['quantity']}")
        print(f"   Entry: {pos['avg_price']:.2f} | Current: {pos['current_price']:.2f}")
        print(f"   P&L: ₹{pnl:+,.2f}")
        if pos['stop_loss']:
            print(f"   SL: {pos['stop_loss']:.2f} | Target: {pos['target']:.2f}")
        print(f"   Entry Time: {pos['entry_time']}")
    
    return 0


async def get_trades(args):
    """Get trade history."""
    global orchestrator
    
    if not orchestrator:
        print("❌ Trading system not running")
        return 1
    
    trades = orchestrator.get_trades()
    
    if not trades:
        print("\n📭 No trades yet")
        return 0
    
    print(f"\n{'='*60}")
    print(f"Trade History ({len(trades)} trades)")
    print(f"{'='*60}")
    
    for trade in trades[-10:]:  # Last 10 trades
        pnl = trade['net_pnl']
        pnl_color = "🟢" if pnl >= 0 else "🔴"
        print(f"\n{pnl_color} {trade['trade_id']}")
        print(f"   {trade['symbol']} {trade['side']} {trade['quantity']}")
        print(f"   Entry: {trade['entry_price']:.2f} → Exit: {trade['exit_price']:.2f}")
        print(f"   P&L: ₹{pnl:+,.2f} ({trade['pnl_percent']:+.2f}%)")
        print(f"   Reason: {trade['exit_reason']}")
        print(f"   Holding: {trade['holding_minutes']} mins")
    
    return 0


async def get_performance(args):
    """Get performance metrics."""
    global orchestrator
    
    if not orchestrator:
        print("❌ Trading system not running")
        return 1
    
    perf = orchestrator.get_performance()
    
    if not perf or 'total_trades' not in perf or perf['total_trades'] == 0:
        print("\n📊 No performance data yet (no trades)")
        return 0
    
    print(f"\n{'='*60}")
    print("Performance Metrics")
    print(f"{'='*60}")
    print(f"Total Trades: {perf['total_trades']}")
    print(f"Winning: {perf['winning_trades']} | Losing: {perf['losing_trades']}")
    print(f"Win Rate: {perf['win_rate']:.1f}%")
    print(f"\nTotal P&L: ₹{perf['total_pnl']:,.2f}")
    print(f"Return: {perf['total_return_percent']:.2f}%")
    print(f"\nProfit Factor: {perf['profit_factor']:.2f}")
    print(f"Avg Win: ₹{perf['avg_win']:,.2f}")
    print(f"Avg Loss: ₹{perf['avg_loss']:,.2f}")
    print(f"Win/Loss Ratio: {perf['avg_win_loss_ratio']:.2f}")
    print(f"\nMax Drawdown: {perf['max_drawdown_percent']:.2f}%")
    print(f"Sharpe Ratio: {perf['sharpe_ratio']:.2f}")
    print(f"\nTotal Commission: ₹{perf['total_commission']:,.2f}")
    print(f"Total Slippage: ₹{perf['total_slippage']:,.2f}")
    print(f"Avg Holding Time: {perf['avg_holding_minutes']:.1f} mins")
    
    return 0


async def add_strategy(args):
    """Add a strategy."""
    global orchestrator
    
    if not orchestrator:
        print("❌ Trading system not running")
        return 1
    
    success = orchestrator.add_strategy(args.strategy_id)
    
    if success:
        print(f"\n✅ Strategy {args.strategy_id} added")
    else:
        print(f"\n❌ Failed to add strategy {args.strategy_id}")
        return 1
    
    return 0


async def simulate_signal(args):
    """Simulate a trading signal."""
    global orchestrator
    
    if not orchestrator:
        print("❌ Trading system not running")
        return 1
    
    if not orchestrator.paper_engine:
        print("❌ Paper trading engine not available")
        return 1
    
    symbol = f"NSE:{args.symbol}-EQ"
    entry = Decimal(str(args.entry))
    sl = Decimal(str(args.stop_loss))
    target = Decimal(str(args.target))
    
    print(f"\n📡 Simulating signal for {symbol}")
    print(f"   Entry: {entry} | SL: {sl} | Target: {target}")
    
    # Update price first
    await orchestrator.update_price(symbol, entry)
    
    # Create signal
    signal = Signal(
        signal_id=f"CLI-{datetime.now().strftime('%H%M%S')}",
        strategy_id="CLI",
        strategy_name="CLI Manual",
        symbol=symbol,
        exchange="NSE",
        signal_type=SignalType.LONG_ENTRY,
        strength=SignalStrength.MODERATE,
        entry_price=entry,
        stop_loss=sl,
        target_price=target,
        quantity_pct=5.0,
        timeframe="5m",
        indicators={},
        reason="Manual CLI signal",
        generated_at=datetime.now(),
        valid_until=datetime.now()
    )
    
    # Execute signal
    order = await orchestrator.paper_engine.execute_signal(signal)
    
    if order:
        print(f"\n✅ Order executed!")
        print(f"   Order ID: {order.order_id}")
        print(f"   Status: {order.status.value}")
        print(f"   Filled: {order.filled_quantity} @ {order.average_fill_price:.2f}")
    else:
        print("\n❌ Order execution failed")
        return 1
    
    return 0


async def update_price(args):
    """Update price for a symbol."""
    global orchestrator
    
    if not orchestrator:
        print("❌ Trading system not running")
        return 1
    
    symbol = f"NSE:{args.symbol}-EQ"
    price = Decimal(str(args.price))
    
    await orchestrator.update_price(symbol, price)
    print(f"\n✅ Price updated: {symbol} = {price}")
    
    # Check if SL/Target triggered
    positions = orchestrator.get_positions()
    for pos in positions:
        if pos['symbol'] == symbol:
            print(f"   Position P&L: ₹{pos['unrealized_pnl']:+,.2f}")
    
    return 0


async def close_position(args):
    """Close a position."""
    global orchestrator
    
    if not orchestrator:
        print("❌ Trading system not running")
        return 1
    
    symbol = f"NSE:{args.symbol}-EQ"
    
    success = await orchestrator.close_position(symbol, "CLI_CLOSE")
    
    if success:
        print(f"\n✅ Position closed: {symbol}")
    else:
        print(f"\n❌ Failed to close position: {symbol}")
        return 1
    
    return 0


async def test_position_sizing(args):
    """Test position sizing calculations."""
    print(f"\n{'='*60}")
    print("Position Sizing Calculator")
    print(f"{'='*60}")
    
    capital = Decimal(str(args.capital))
    entry = Decimal(str(args.entry))
    sl = Decimal(str(args.stop_loss))
    risk_pct = Decimal(str(args.risk_percent))
    
    sizer = PositionSizer(capital=capital, lot_size=args.lot_size)
    
    # Calculate using percent risk
    result = sizer.calculate_size(
        method=SizingMethod.PERCENT_RISK,
        entry_price=entry,
        stop_loss=sl,
        risk_percent=risk_pct
    )
    
    print(f"\nCapital: ₹{capital:,.2f}")
    print(f"Entry: {entry:.2f} | Stop Loss: {sl:.2f}")
    print(f"Risk: {risk_pct}%")
    print(f"Lot Size: {args.lot_size}")
    
    print(f"\n📊 Result:")
    print(f"   Quantity: {result.quantity}")
    print(f"   Position Value: ₹{result.position_value:,.2f}")
    print(f"   Risk Amount: ₹{result.risk_amount:,.2f}")
    print(f"   Risk %: {result.risk_percent:.2f}%")
    
    print(f"\nDetails: {result.calculation_details}")
    
    return 0


async def demo(args):
    """Run a demo trading session."""
    global orchestrator
    
    print(f"\n{'='*60}")
    print("KeepGaining Paper Trading Demo")
    print(f"{'='*60}")
    
    # Start trading
    config = OrchestratorConfig(
        paper_capital=Decimal("100000"),
        max_daily_loss=Decimal("5000"),
        max_positions=5
    )
    
    orchestrator = TradingOrchestrator(config=config, event_bus=None)
    await orchestrator.start(mode=TradingMode.PAPER, strategies=["VOLROCKET"])
    
    print("\n✅ Paper trading started with ₹1,00,000 capital")
    print("   Strategy: VolumeRocket")
    
    # Simulate trades
    trades = [
        ("RELIANCE", 2500, 2450, 2600, "long_entry"),
        ("HDFCBANK", 1600, 1570, 1660, "long_entry"),
    ]
    
    for symbol, entry, sl, target, signal_type in trades:
        full_symbol = f"NSE:{symbol}-EQ"
        
        print(f"\n📡 Trading {symbol}...")
        
        # Update price
        await orchestrator.update_price(full_symbol, Decimal(str(entry)))
        
        # Create and execute signal
        signal = Signal(
            signal_id=f"DEMO-{symbol}",
            strategy_id="VOLROCKET",
            strategy_name="Volume Rocket",
            symbol=full_symbol,
            exchange="NSE",
            signal_type=SignalType.LONG_ENTRY,
            strength=SignalStrength.STRONG,
            entry_price=Decimal(str(entry)),
            stop_loss=Decimal(str(sl)),
            target_price=Decimal(str(target)),
            quantity_pct=10.0,
            timeframe="5m",
            indicators={"vwma_22": entry - 10, "supertrend": entry - 20},
            reason="Demo signal",
            generated_at=datetime.now(),
            valid_until=datetime.now()
        )
        
        order = await orchestrator.paper_engine.execute_signal(signal)
        if order:
            print(f"   ✅ Bought {order.filled_quantity} @ {order.average_fill_price:.2f}")
    
    # Show positions
    await asyncio.sleep(0.5)
    positions = orchestrator.get_positions()
    
    print(f"\n{'='*60}")
    print(f"Open Positions: {len(positions)}")
    
    for pos in positions:
        print(f"  • {pos['symbol']}: {pos['quantity']} @ {pos['avg_price']:.2f}")
    
    # Simulate price movement (target hit for RELIANCE)
    print("\n📈 Simulating price movement...")
    await orchestrator.update_price("NSE:RELIANCE-EQ", Decimal("2605"))
    
    await asyncio.sleep(0.5)
    
    # Show results
    portfolio = orchestrator.get_portfolio()
    print(f"\n{'='*60}")
    print("Portfolio After Price Movement")
    print(f"{'='*60}")
    print(f"Unrealized P&L: ₹{portfolio['unrealized_pnl']:,.2f}")
    print(f"Realized P&L: ₹{portfolio['realized_pnl']:,.2f}")
    
    trades = orchestrator.get_trades()
    if trades:
        print(f"\nCompleted Trades: {len(trades)}")
        for t in trades:
            print(f"  • {t['symbol']}: ₹{t['net_pnl']:+,.2f} ({t['exit_reason']})")
    
    # Stop
    await orchestrator.stop()
    print("\n✅ Demo complete!")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="KeepGaining Trading CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start trading system")
    start_parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    start_parser.add_argument("--capital", type=float, default=100000)
    start_parser.add_argument("--max-loss", type=float, default=10000)
    start_parser.add_argument("--max-positions", type=int, default=5)
    start_parser.add_argument("--strategies", type=str, default="VOLROCKET")
    
    # Stop command
    subparsers.add_parser("stop", help="Stop trading system")
    
    # Status command
    subparsers.add_parser("status", help="Get system status")
    
    # Portfolio command
    subparsers.add_parser("portfolio", help="Get portfolio summary")
    
    # Positions command
    subparsers.add_parser("positions", help="Get open positions")
    
    # Trades command
    subparsers.add_parser("trades", help="Get trade history")
    
    # Performance command
    subparsers.add_parser("performance", help="Get performance metrics")
    
    # Add strategy command
    strategy_parser = subparsers.add_parser("add-strategy", help="Add a strategy")
    strategy_parser.add_argument("strategy_id", type=str)
    
    # Simulate signal command
    signal_parser = subparsers.add_parser("simulate-signal", help="Simulate a signal")
    signal_parser.add_argument("symbol", type=str)
    signal_parser.add_argument("entry", type=float)
    signal_parser.add_argument("stop_loss", type=float)
    signal_parser.add_argument("target", type=float)
    
    # Update price command
    price_parser = subparsers.add_parser("update-price", help="Update price")
    price_parser.add_argument("symbol", type=str)
    price_parser.add_argument("price", type=float)
    
    # Close position command
    close_parser = subparsers.add_parser("close", help="Close a position")
    close_parser.add_argument("symbol", type=str)
    
    # Position sizing command
    sizing_parser = subparsers.add_parser("position-size", help="Calculate position size")
    sizing_parser.add_argument("--capital", type=float, default=100000)
    sizing_parser.add_argument("--entry", type=float, required=True)
    sizing_parser.add_argument("--stop-loss", type=float, required=True)
    sizing_parser.add_argument("--risk-percent", type=float, default=2.0)
    sizing_parser.add_argument("--lot-size", type=int, default=1)
    
    # Demo command
    subparsers.add_parser("demo", help="Run a demo session")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Map commands to functions
    commands = {
        "start": start_trading,
        "stop": stop_trading,
        "status": get_status,
        "portfolio": get_portfolio,
        "positions": get_positions,
        "trades": get_trades,
        "performance": get_performance,
        "add-strategy": add_strategy,
        "simulate-signal": simulate_signal,
        "update-price": update_price,
        "close": close_position,
        "position-size": test_position_sizing,
        "demo": demo,
    }
    
    func = commands.get(args.command)
    if func:
        return asyncio.run(func(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
