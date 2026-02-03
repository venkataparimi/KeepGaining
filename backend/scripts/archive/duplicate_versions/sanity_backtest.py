"""
Sanity Backtest Script
Quick validation that backtest engine works with PostgreSQL data

NOTE: Since indicator_data table is empty, this uses a simple price-based strategy
"""
import asyncio
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from uuid import UUID
import pandas as pd
from sqlalchemy import text
from app.db.session import get_db_context


@dataclass
class SimpleSignal:
    """Simple signal for testing"""
    instrument_id: str
    symbol: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    target: float
    timestamp: datetime


@dataclass
class SimpleTrade:
    """Trade record"""
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    exit_reason: str  # "target", "stop_loss", "eod"


class SimpleMomentumStrategy:
    """
    Simple momentum strategy - no indicators needed.
    - BUY when price breaks above previous 20-bar high
    - Uses ATR-style stop (2% below entry) and target (3% above entry)
    """
    
    def __init__(self, lookback: int = 20, sl_percent: float = 2.0, target_percent: float = 3.0):
        self.lookback = lookback
        self.sl_percent = sl_percent
        self.target_percent = target_percent
        self.price_history: Dict[str, List[float]] = {}  # symbol -> list of closes
    
    def evaluate(self, instrument_id: str, symbol: str, candle: Dict[str, Any]) -> Optional[SimpleSignal]:
        """Check for breakout signal"""
        close = candle['close']
        
        # Initialize history
        if instrument_id not in self.price_history:
            self.price_history[instrument_id] = []
        
        history = self.price_history[instrument_id]
        
        # Check for breakout
        signal = None
        if len(history) >= self.lookback:
            prev_high = max(history[-self.lookback:])
            
            # Breakout above previous high
            if close > prev_high * 1.001:  # 0.1% buffer
                signal = SimpleSignal(
                    instrument_id=instrument_id,
                    symbol=symbol,
                    direction="BUY",
                    entry_price=close,
                    stop_loss=close * (1 - self.sl_percent / 100),
                    target=close * (1 + self.target_percent / 100),
                    timestamp=candle['timestamp']
                )
        
        # Update history
        history.append(close)
        if len(history) > self.lookback + 10:
            history.pop(0)
        
        return signal


class SanityBacktestEngine:
    """Minimal backtest engine using PostgreSQL data"""
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        position_size_pct: float = 10.0,
        slippage_pct: float = 0.05,
        commission: float = 20.0
    ):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position_size_pct = position_size_pct
        self.slippage_pct = slippage_pct
        self.commission = commission
        
        self.positions: Dict[str, Dict] = {}
        self.trades: List[SimpleTrade] = []
    
    async def load_data(
        self,
        instrument_ids: List[str],
        start_date: date,
        end_date: date,
        timeframe: str = "1m"
    ) -> pd.DataFrame:
        """Load candle data from PostgreSQL with symbol join"""
        async with get_db_context() as db:
            # Build parameterized query with proper UUID handling
            # Use positional parameters for asyncpg
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
    
    def _check_exit(self, instrument_id: str, high: float, low: float, timestamp: datetime) -> Optional[SimpleTrade]:
        """Check if position should be exited"""
        if instrument_id not in self.positions:
            return None
        
        pos = self.positions[instrument_id]
        exit_price = None
        exit_reason = None
        
        # Check stop loss
        if low <= pos['stop_loss']:
            exit_price = pos['stop_loss']
            exit_reason = "stop_loss"
        # Check target
        elif high >= pos['target']:
            exit_price = pos['target']
            exit_reason = "target"
        
        if exit_price:
            exit_price = self._apply_slippage(exit_price, is_buy=False)
            pnl = (exit_price - pos['entry_price']) * pos['quantity'] - self.commission
            self.capital += pos['entry_price'] * pos['quantity'] + pnl
            
            trade = SimpleTrade(
                symbol=pos['symbol'],
                entry_time=pos['entry_time'],
                exit_time=timestamp,
                entry_price=pos['entry_price'],
                exit_price=exit_price,
                quantity=pos['quantity'],
                pnl=pnl,
                exit_reason=exit_reason
            )
            
            del self.positions[instrument_id]
            self.trades.append(trade)
            return trade
        
        return None
    
    def _enter_position(self, signal: SimpleSignal) -> bool:
        """Enter a position"""
        if signal.instrument_id in self.positions:
            return False
        
        if len(self.positions) >= 5:  # Max 5 positions
            return False
        
        entry_price = self._apply_slippage(signal.entry_price, is_buy=True)
        position_value = self.capital * (self.position_size_pct / 100)
        quantity = int(position_value / entry_price)
        
        if quantity < 1:
            return False
        
        cost = entry_price * quantity + self.commission
        if cost > self.capital:
            return False
        
        self.capital -= cost
        self.positions[signal.instrument_id] = {
            'symbol': signal.symbol,
            'entry_price': entry_price,
            'quantity': quantity,
            'stop_loss': signal.stop_loss,
            'target': signal.target,
            'entry_time': signal.timestamp
        }
        
        return True
    
    async def run(
        self,
        strategy: SimpleMomentumStrategy,
        instrument_ids: List[str],
        symbols_map: Dict[str, str],  # instrument_id -> symbol
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Run the backtest"""
        print(f"\n{'='*60}")
        print(f"Starting Sanity Backtest")
        print(f"Instruments: {len(instrument_ids)}")
        print(f"Period: {start_date} to {end_date}")
        print(f"Initial Capital: ₹{self.initial_capital:,.2f}")
        print(f"{'='*60}\n")
        
        # Load data
        print("Loading data from PostgreSQL...")
        df = await self.load_data(instrument_ids, start_date, end_date)
        
        if df.empty:
            print("ERROR: No data loaded!")
            return {'error': 'No data'}
        
        print(f"Loaded {len(df):,} candles for {df['instrument_id'].nunique()} instruments")
        print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        # Process candles
        signals_generated = 0
        signals_executed = 0
        
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
            }
            
            # Check exits
            self._check_exit(instrument_id, candle['high'], candle['low'], timestamp)
            
            # Check for new signals
            signal = strategy.evaluate(instrument_id, symbol, candle)
            if signal:
                signals_generated += 1
                if self._enter_position(signal):
                    signals_executed += 1
        
        # Close remaining positions at last price
        for inst_id in list(self.positions.keys()):
            pos = self.positions[inst_id]
            last_row = df[df['instrument_id'].astype(str) == inst_id].iloc[-1]
            exit_price = self._apply_slippage(float(last_row['close']), is_buy=False)
            pnl = (exit_price - pos['entry_price']) * pos['quantity'] - self.commission
            self.capital += pos['entry_price'] * pos['quantity'] + pnl
            
            self.trades.append(SimpleTrade(
                symbol=pos['symbol'],
                entry_time=pos['entry_time'],
                exit_time=last_row['timestamp'],
                entry_price=pos['entry_price'],
                exit_price=exit_price,
                quantity=pos['quantity'],
                pnl=pnl,
                exit_reason="end_of_backtest"
            ))
            del self.positions[inst_id]
        
        # Calculate metrics
        metrics = self._calculate_metrics()
        metrics['signals_generated'] = signals_generated
        metrics['signals_executed'] = signals_executed
        
        self._print_report(metrics)
        
        return metrics
    
    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate performance metrics"""
        if not self.trades:
            return {
                'total_trades': 0,
                'net_pnl': 0,
                'return_pct': 0,
            }
        
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        
        total_pnl = sum(t.pnl for t in self.trades)
        gross_profit = sum(t.pnl for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
        
        return {
            'total_trades': len(self.trades),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': (len(wins) / len(self.trades) * 100) if self.trades else 0,
            'net_pnl': total_pnl,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': (gross_profit / gross_loss) if gross_loss > 0 else 0,
            'return_pct': ((self.capital - self.initial_capital) / self.initial_capital * 100),
            'final_capital': self.capital,
            'avg_win': (gross_profit / len(wins)) if wins else 0,
            'avg_loss': (gross_loss / len(losses)) if losses else 0,
        }
    
    def _print_report(self, metrics: Dict[str, Any]):
        """Print backtest report"""
        print(f"\n{'='*60}")
        print(f"BACKTEST RESULTS")
        print(f"{'='*60}")
        print(f"Initial Capital:     ₹{self.initial_capital:>15,.2f}")
        print(f"Final Capital:       ₹{metrics.get('final_capital', 0):>15,.2f}")
        print(f"Net P&L:             ₹{metrics.get('net_pnl', 0):>15,.2f}")
        print(f"Return:              {metrics.get('return_pct', 0):>15.2f}%")
        print(f"{'-'*60}")
        print(f"Signals Generated:   {metrics.get('signals_generated', 0):>15}")
        print(f"Signals Executed:    {metrics.get('signals_executed', 0):>15}")
        print(f"Total Trades:        {metrics.get('total_trades', 0):>15}")
        print(f"Winning Trades:      {metrics.get('winning_trades', 0):>15}")
        print(f"Losing Trades:       {metrics.get('losing_trades', 0):>15}")
        print(f"Win Rate:            {metrics.get('win_rate', 0):>15.2f}%")
        print(f"Profit Factor:       {metrics.get('profit_factor', 0):>15.2f}")
        print(f"{'-'*60}")
        print(f"Gross Profit:        ₹{metrics.get('gross_profit', 0):>15,.2f}")
        print(f"Gross Loss:          ₹{metrics.get('gross_loss', 0):>15,.2f}")
        print(f"Avg Win:             ₹{metrics.get('avg_win', 0):>15,.2f}")
        print(f"Avg Loss:            ₹{metrics.get('avg_loss', 0):>15,.2f}")
        print(f"{'='*60}\n")


async def get_sample_instruments(limit: int = 5) -> List[Dict]:
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
    """Run sanity backtest"""
    print("\n" + "="*60)
    print("SANITY BACKTEST - Quick Validation")
    print("="*60)
    
    # Get sample instruments
    print("\nFinding instruments with most data...")
    instruments = await get_sample_instruments(5)
    
    if not instruments:
        print("ERROR: No instruments found with sufficient data!")
        return
    
    print(f"\nSelected instruments:")
    for inst in instruments:
        print(f"  {inst['symbol']}: {inst['count']:,} candles")
    
    instrument_ids = [inst['id'] for inst in instruments]
    symbols_map = {inst['id']: inst['symbol'] for inst in instruments}
    
    # Use recent 7 days for quick test
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    
    # Initialize
    strategy = SimpleMomentumStrategy(lookback=20, sl_percent=2.0, target_percent=3.0)
    engine = SanityBacktestEngine(
        initial_capital=100000,
        position_size_pct=10,
    )
    
    # Run
    results = await engine.run(
        strategy=strategy,
        instrument_ids=instrument_ids,
        symbols_map=symbols_map,
        start_date=start_date,
        end_date=end_date
    )
    
    # Print sample trades
    if engine.trades:
        print("\n📋 Sample Trades (last 5):")
        for trade in engine.trades[-5:]:
            pnl_sign = "+" if trade.pnl > 0 else ""
            print(f"   {trade.symbol}: {trade.entry_price:.2f} → {trade.exit_price:.2f} "
                  f"({pnl_sign}₹{trade.pnl:.2f}) [{trade.exit_reason}]")
    
    print("\n✅ Sanity backtest complete!")
    return results


if __name__ == "__main__":
    asyncio.run(main())
