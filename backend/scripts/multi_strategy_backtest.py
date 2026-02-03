#!/usr/bin/env python3
"""
Multi-Strategy Backtest
KeepGaining Trading Platform

Tests multiple strategies on historical data and compares performance.
Uses raw candle data - no pre-computed indicators needed.

Usage:
    cd backend
    python scripts/multi_strategy_backtest.py
    python scripts/multi_strategy_backtest.py --strategy EMA_MOM --days 30
"""

import asyncio
import argparse
from datetime import date, timedelta, datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import text
from app.db.session import get_db_context
from app.strategies.raw_candle_strategies import (
    RawSignal, RawCandleStrategy, 
    CANDLE_STRATEGIES, get_candle_strategy, get_all_strategies
)


@dataclass
class Trade:
    """Trade record"""
    strategy_id: str
    symbol: str
    direction: str
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: float
    stop_loss: float
    target: float
    quantity: int
    pnl: float
    exit_reason: str
    signal_strength: float


class MultiStrategyBacktester:
    """
    Backtest engine that supports multiple strategies simultaneously.
    """
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        position_size_pct: float = 10.0,
        max_positions_per_strategy: int = 3,
        slippage_pct: float = 0.05,
        commission: float = 20.0
    ):
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.max_positions_per_strategy = max_positions_per_strategy
        self.slippage_pct = slippage_pct
        self.commission = commission
        
        # Per-strategy tracking
        self.capital: Dict[str, float] = {}
        self.positions: Dict[str, Dict[str, Dict]] = {}  # strategy -> instrument -> position
        self.trades: Dict[str, List[Trade]] = {}
        self.signal_counts: Dict[str, int] = {}
    
    def _init_strategy(self, strategy_id: str):
        """Initialize tracking for a strategy"""
        if strategy_id not in self.capital:
            self.capital[strategy_id] = self.initial_capital
            self.positions[strategy_id] = {}
            self.trades[strategy_id] = []
            self.signal_counts[strategy_id] = 0
    
    async def load_data(
        self,
        instrument_ids: List[str],
        start_date: date,
        end_date: date,
        timeframe: str = "1m"
    ) -> pd.DataFrame:
        """Load candle data from PostgreSQL"""
        async with get_db_context() as db:
            placeholders = ", ".join([f"'{id}'" for id in instrument_ids])
            
            query = text(f"""
                SELECT 
                    cd.instrument_id,
                    im.trading_symbol as symbol,
                    cd.timestamp, 
                    cd.open, cd.high, cd.low, cd.close, cd.volume
                FROM candle_data cd
                JOIN instrument_master im ON cd.instrument_id = im.instrument_id
                WHERE cd.instrument_id IN ({placeholders})
                AND cd.timeframe = :timeframe
                AND cd.timestamp >= :start_date
                AND cd.timestamp <= :end_date
                ORDER BY cd.timestamp, cd.instrument_id
            """)
            
            result = await db.execute(query, {
                'timeframe': timeframe,
                'start_date': start_date,
                'end_date': end_date
            })
            
            rows = result.fetchall()
            
            if not rows:
                return pd.DataFrame()
            
            df = pd.DataFrame(rows, columns=[
                'instrument_id', 'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume'
            ])
            
            return df
    
    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        """Apply slippage"""
        slip = price * (self.slippage_pct / 100)
        return price + slip if is_buy else price - slip
    
    def _check_exits(
        self, 
        strategy_id: str, 
        instrument_id: str, 
        candle: Dict[str, Any]
    ) -> Optional[Trade]:
        """Check if position should be exited"""
        if instrument_id not in self.positions[strategy_id]:
            return None
        
        pos = self.positions[strategy_id][instrument_id]
        high = float(candle['high'])
        low = float(candle['low'])
        timestamp = candle['timestamp']
        
        exit_price = None
        exit_reason = None
        
        if pos['direction'] == "LONG":
            # Check stop loss
            if low <= pos['stop_loss']:
                exit_price = pos['stop_loss']
                exit_reason = "stop_loss"
            # Check target
            elif high >= pos['target']:
                exit_price = pos['target']
                exit_reason = "target"
        else:  # SHORT
            # Check stop loss
            if high >= pos['stop_loss']:
                exit_price = pos['stop_loss']
                exit_reason = "stop_loss"
            # Check target
            elif low <= pos['target']:
                exit_price = pos['target']
                exit_reason = "target"
        
        if exit_price:
            is_buy = pos['direction'] == "SHORT"  # Closing short = buy
            exit_price = self._apply_slippage(exit_price, is_buy)
            
            if pos['direction'] == "LONG":
                pnl = (exit_price - pos['entry_price']) * pos['quantity'] - self.commission
            else:
                pnl = (pos['entry_price'] - exit_price) * pos['quantity'] - self.commission
            
            self.capital[strategy_id] += pos['entry_price'] * pos['quantity'] + pnl
            
            trade = Trade(
                strategy_id=strategy_id,
                symbol=pos['symbol'],
                direction=pos['direction'],
                entry_time=pos['entry_time'],
                exit_time=timestamp,
                entry_price=pos['entry_price'],
                exit_price=exit_price,
                stop_loss=pos['stop_loss'],
                target=pos['target'],
                quantity=pos['quantity'],
                pnl=pnl,
                exit_reason=exit_reason,
                signal_strength=pos.get('strength', 100)
            )
            
            del self.positions[strategy_id][instrument_id]
            self.trades[strategy_id].append(trade)
            return trade
        
        return None
    
    def _enter_position(self, strategy_id: str, signal: RawSignal) -> bool:
        """Enter a new position"""
        # Check if already in position
        if signal.instrument_id in self.positions[strategy_id]:
            return False
        
        # Check position limit
        if len(self.positions[strategy_id]) >= self.max_positions_per_strategy:
            return False
        
        is_buy = signal.direction == "LONG"
        entry_price = self._apply_slippage(signal.entry_price, is_buy)
        
        position_value = self.capital[strategy_id] * (self.position_size_pct / 100)
        quantity = int(position_value / entry_price)
        
        if quantity < 1:
            return False
        
        cost = entry_price * quantity + self.commission
        if cost > self.capital[strategy_id]:
            return False
        
        self.capital[strategy_id] -= cost
        self.positions[strategy_id][signal.instrument_id] = {
            'symbol': signal.symbol,
            'direction': signal.direction,
            'entry_price': entry_price,
            'quantity': quantity,
            'stop_loss': signal.stop_loss,
            'target': signal.target,
            'entry_time': signal.timestamp,
            'strength': signal.strength
        }
        
        return True
    
    def _close_all_positions(self, strategy_id: str, last_prices: Dict[str, float], timestamp: datetime):
        """Close all open positions at end of backtest"""
        for inst_id in list(self.positions[strategy_id].keys()):
            pos = self.positions[strategy_id][inst_id]
            exit_price = last_prices.get(inst_id, pos['entry_price'])
            is_buy = pos['direction'] == "SHORT"
            exit_price = self._apply_slippage(exit_price, is_buy)
            
            if pos['direction'] == "LONG":
                pnl = (exit_price - pos['entry_price']) * pos['quantity'] - self.commission
            else:
                pnl = (pos['entry_price'] - exit_price) * pos['quantity'] - self.commission
            
            self.capital[strategy_id] += pos['entry_price'] * pos['quantity'] + pnl
            
            self.trades[strategy_id].append(Trade(
                strategy_id=strategy_id,
                symbol=pos['symbol'],
                direction=pos['direction'],
                entry_time=pos['entry_time'],
                exit_time=timestamp,
                entry_price=pos['entry_price'],
                exit_price=exit_price,
                stop_loss=pos['stop_loss'],
                target=pos['target'],
                quantity=pos['quantity'],
                pnl=pnl,
                exit_reason="end_of_backtest",
                signal_strength=pos.get('strength', 100)
            ))
            
            del self.positions[strategy_id][inst_id]
    
    async def run(
        self,
        strategies: List[RawCandleStrategy],
        instrument_ids: List[str],
        start_date: date,
        end_date: date,
        timeframe: str = "1m"
    ) -> Dict[str, Dict[str, Any]]:
        """Run backtest for multiple strategies"""
        
        # Initialize tracking for each strategy
        for s in strategies:
            self._init_strategy(s.strategy_id)
        
        print(f"\n{'='*70}")
        print(f"MULTI-STRATEGY BACKTEST")
        print(f"{'='*70}")
        print(f"Strategies: {', '.join(s.strategy_id for s in strategies)}")
        print(f"Instruments: {len(instrument_ids)}")
        print(f"Period: {start_date} to {end_date}")
        print(f"Initial Capital: ₹{self.initial_capital:,.2f}")
        print(f"{'='*70}\n")
        
        # Load data
        print("Loading data from PostgreSQL...")
        df = await self.load_data(instrument_ids, start_date, end_date, timeframe)
        
        if df.empty:
            print("ERROR: No data loaded!")
            return {}
        
        print(f"Loaded {len(df):,} candles for {df['instrument_id'].nunique()} instruments")
        print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}\n")
        print("Running backtest...")
        
        # Track last prices for closing positions
        last_prices: Dict[str, float] = {}
        last_timestamp = None
        
        # Process candles
        total_candles = len(df)
        progress_interval = max(1, total_candles // 20)
        
        for idx, row in df.iterrows():
            instrument_id = str(row['instrument_id'])
            symbol = row['symbol']
            timestamp = row['timestamp']
            
            candle = {
                'timestamp': timestamp,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': int(row['volume']) if pd.notna(row['volume']) else 0,
                'symbol': symbol,
            }
            
            last_prices[instrument_id] = candle['close']
            last_timestamp = timestamp
            
            # Process each strategy
            for strategy in strategies:
                sid = strategy.strategy_id
                
                # Check exits first
                self._check_exits(sid, instrument_id, candle)
                
                # Evaluate for new signals
                signal = strategy.evaluate(instrument_id, symbol, candle)
                
                if signal:
                    self.signal_counts[sid] += 1
                    self._enter_position(sid, signal)
            
            # Progress indicator
            if idx > 0 and idx % progress_interval == 0:
                pct = (idx / total_candles) * 100
                print(f"  Progress: {pct:.0f}%")
        
        print(f"  Progress: 100%\n")
        
        # Close remaining positions
        for strategy in strategies:
            self._close_all_positions(strategy.strategy_id, last_prices, last_timestamp)
        
        # Calculate and return metrics
        results = {}
        for strategy in strategies:
            results[strategy.strategy_id] = self._calculate_metrics(strategy.strategy_id)
        
        return results
    
    def _calculate_metrics(self, strategy_id: str) -> Dict[str, Any]:
        """Calculate performance metrics for a strategy"""
        trades = self.trades[strategy_id]
        capital = self.capital[strategy_id]
        
        if not trades:
            return {
                'total_trades': 0,
                'signals_generated': self.signal_counts[strategy_id],
                'net_pnl': 0,
                'return_pct': 0,
                'final_capital': capital,
            }
        
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        
        target_exits = [t for t in trades if t.exit_reason == "target"]
        sl_exits = [t for t in trades if t.exit_reason == "stop_loss"]
        
        total_pnl = sum(t.pnl for t in trades)
        gross_profit = sum(t.pnl for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
        
        return {
            'strategy_id': strategy_id,
            'total_trades': len(trades),
            'signals_generated': self.signal_counts[strategy_id],
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': (len(wins) / len(trades) * 100) if trades else 0,
            'target_exits': len(target_exits),
            'sl_exits': len(sl_exits),
            'net_pnl': total_pnl,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': (gross_profit / gross_loss) if gross_loss > 0 else float('inf'),
            'return_pct': ((capital - self.initial_capital) / self.initial_capital * 100),
            'final_capital': capital,
            'avg_win': (gross_profit / len(wins)) if wins else 0,
            'avg_loss': (gross_loss / len(losses)) if losses else 0,
            'avg_trade': total_pnl / len(trades) if trades else 0,
            'trades': trades,
        }
    
    def print_comparison_report(self, results: Dict[str, Dict[str, Any]]):
        """Print comparative report"""
        print(f"\n{'='*90}")
        print(f"{'STRATEGY COMPARISON':^90}")
        print(f"{'='*90}")
        
        # Header
        print(f"{'Strategy':<12} {'Signals':>8} {'Trades':>7} {'Win%':>6} {'PF':>6} "
              f"{'Net P&L':>12} {'Return':>8} {'Avg Trade':>10}")
        print(f"{'-'*90}")
        
        # Sort by return
        sorted_results = sorted(results.values(), key=lambda x: x.get('return_pct', 0), reverse=True)
        
        for r in sorted_results:
            print(f"{r.get('strategy_id', 'N/A'):<12} "
                  f"{r.get('signals_generated', 0):>8} "
                  f"{r.get('total_trades', 0):>7} "
                  f"{r.get('win_rate', 0):>5.1f}% "
                  f"{r.get('profit_factor', 0):>6.2f} "
                  f"₹{r.get('net_pnl', 0):>10,.0f} "
                  f"{r.get('return_pct', 0):>7.2f}% "
                  f"₹{r.get('avg_trade', 0):>8,.0f}")
        
        print(f"{'='*90}")
        
        # Best strategy
        if sorted_results:
            best = sorted_results[0]
            print(f"\n🏆 Best Strategy: {best.get('strategy_id')} "
                  f"(Return: {best.get('return_pct', 0):.2f}%, "
                  f"PF: {best.get('profit_factor', 0):.2f})")


async def get_sample_instruments(limit: int = 10) -> List[Dict]:
    """Get sample equity instruments with data"""
    async with get_db_context() as db:
        result = await db.execute(text("""
            SELECT DISTINCT 
                cd.instrument_id,
                im.trading_symbol,
                COUNT(*) as candle_count
            FROM candle_data cd
            JOIN instrument_master im ON cd.instrument_id = im.instrument_id
            WHERE im.instrument_type = 'EQUITY'
            AND cd.timeframe = '1m'
            GROUP BY cd.instrument_id, im.trading_symbol
            HAVING COUNT(*) > 10000
            ORDER BY candle_count DESC
            LIMIT :limit
        """), {'limit': limit})
        
        rows = result.fetchall()
        return [{'id': str(r[0]), 'symbol': r[1], 'count': r[2]} for r in rows]


async def main():
    """Run multi-strategy backtest"""
    parser = argparse.ArgumentParser(description='Multi-Strategy Backtest')
    parser.add_argument('--strategy', type=str, help='Single strategy to test (e.g., EMA_MOM)')
    parser.add_argument('--days', type=int, default=7, help='Number of days to backtest')
    parser.add_argument('--instruments', type=int, default=10, help='Number of instruments')
    args = parser.parse_args()
    
    # Get instruments
    print("\nFinding instruments with data...")
    instruments = await get_sample_instruments(args.instruments)
    
    if not instruments:
        print("ERROR: No instruments found!")
        return
    
    print(f"\nSelected {len(instruments)} instruments:")
    for inst in instruments[:5]:
        print(f"  {inst['symbol']}: {inst['count']:,} candles")
    if len(instruments) > 5:
        print(f"  ... and {len(instruments) - 5} more")
    
    instrument_ids = [inst['id'] for inst in instruments]
    
    # Date range
    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)
    
    # Select strategies
    if args.strategy:
        if args.strategy not in CANDLE_STRATEGIES:
            print(f"ERROR: Unknown strategy '{args.strategy}'")
            print(f"Available: {list(CANDLE_STRATEGIES.keys())}")
            return
        strategies = [get_candle_strategy(args.strategy)]
    else:
        strategies = get_all_strategies()
    
    # Run backtest
    backtester = MultiStrategyBacktester(
        initial_capital=100000,
        position_size_pct=10,
        max_positions_per_strategy=5,
    )
    
    results = await backtester.run(
        strategies=strategies,
        instrument_ids=instrument_ids,
        start_date=start_date,
        end_date=end_date
    )
    
    # Print report
    backtester.print_comparison_report(results)
    
    # Print detailed results for single strategy
    if len(strategies) == 1 and strategies[0].strategy_id in results:
        r = results[strategies[0].strategy_id]
        if r.get('trades'):
            print(f"\n📋 Sample Trades (last 5):")
            for trade in r['trades'][-5:]:
                pnl_sign = "+" if trade.pnl > 0 else ""
                print(f"   {trade.symbol} {trade.direction}: "
                      f"{trade.entry_price:.2f} → {trade.exit_price:.2f} "
                      f"({pnl_sign}₹{trade.pnl:.0f}) [{trade.exit_reason}]")
    
    print("\n✅ Backtest complete!")


if __name__ == "__main__":
    asyncio.run(main())
