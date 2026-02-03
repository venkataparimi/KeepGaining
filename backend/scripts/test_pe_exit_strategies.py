"""
Test different PE exit strategies to find the best one.

Strategies:
1. Current: Big green candle + Trailing SL
2. Trailing SL only (no big candle exit)
3. 2 consecutive green candles 
4. Big candle + EMA9 confirmation
5. Longer minimum hold (5 candles)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create sync session for this script - convert async URL to sync
db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=engine)


@dataclass
class TradeResult:
    """Result of a single trade."""
    symbol: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    exit_reason: str
    pnl_pct: float


def calculate_ema(prices: List[float], period: int = 9) -> List[float]:
    """Calculate EMA for a list of prices."""
    if len(prices) < period:
        return [None] * len(prices)
    
    ema = []
    multiplier = 2 / (period + 1)
    
    # Initial SMA
    sma = sum(prices[:period]) / period
    ema = [None] * (period - 1) + [sma]
    
    # Calculate EMA
    for i in range(period, len(prices)):
        ema_value = (prices[i] * multiplier) + (ema[-1] * (1 - multiplier))
        ema.append(ema_value)
    
    return ema


def get_candle_data(symbol: str, days: int = 60) -> List[Dict]:
    """Fetch candle data from database."""
    db = SessionLocal()
    try:
        start_date = date.today() - timedelta(days=days)
        
        query = text("""
            SELECT cd.timestamp, cd.open, cd.high, cd.low, cd.close, cd.volume
            FROM candle_data cd
            JOIN instrument_master im ON cd.instrument_id = im.instrument_id
            WHERE im.trading_symbol = :symbol
            AND im.instrument_type = 'EQUITY'
            AND cd.timestamp >= :start_date
            ORDER BY cd.timestamp ASC
        """)
        
        result = db.execute(query, {"symbol": symbol, "start_date": start_date})
        rows = result.fetchall()
        
        candles = []
        for row in rows:
            candles.append({
                'timestamp': row[0],
                'open': float(row[1]),
                'high': float(row[2]),
                'low': float(row[3]),
                'close': float(row[4]),
                'volume': int(row[5])
            })
        
        return candles
    finally:
        db.close()


class PEExitTester:
    """Test different PE exit strategies."""
    
    def __init__(self, candles: List[Dict], symbol: str):
        self.candles = candles
        self.symbol = symbol
        self.IST_OFFSET = timedelta(hours=5, minutes=30)
        
        # Calculate indicators
        closes = [c['close'] for c in candles]
        self.ema9 = calculate_ema(closes, 9)
        
        # Group candles by day
        self.days = defaultdict(list)
        for i, c in enumerate(candles):
            day = c['timestamp'].date()
            self.days[day].append((i, c))
    
    def _get_previous_day_levels(self, current_date: date) -> Tuple[float, float, float]:
        """Get PDH, PDL, PDC for the given date."""
        sorted_days = sorted(self.days.keys())
        day_idx = sorted_days.index(current_date) if current_date in sorted_days else -1
        
        if day_idx <= 0:
            return 0, 0, 0
        
        prev_date = sorted_days[day_idx - 1]
        prev_candles = [c for _, c in self.days[prev_date]]
        
        pdh = max(c['high'] for c in prev_candles)
        pdl = min(c['low'] for c in prev_candles)
        pdc = prev_candles[-1]['close']
        
        return pdh, pdl, pdc
    
    def _get_avg_candle_size(self, idx: int, lookback: int = 20) -> float:
        """Get average candle body size."""
        start = max(0, idx - lookback)
        bodies = []
        for i in range(start, idx):
            body = abs(self.candles[i]['close'] - self.candles[i]['open'])
            bodies.append(body)
        return sum(bodies) / len(bodies) if bodies else 1
    
    def _is_big_green_candle(self, candle: Dict, avg_size: float, multiplier: float = 2.5) -> bool:
        """Check if candle is a big green candle."""
        if candle['close'] <= candle['open']:
            return False
        body = candle['close'] - candle['open']
        return body >= avg_size * multiplier
    
    def _find_pe_entries(self) -> List[Tuple[int, Dict]]:
        """Find all PE entry points (simplified criteria)."""
        entries = []
        
        for day, day_candles in self.days.items():
            pdh, pdl, pdc = self._get_previous_day_levels(day)
            if pdl <= 0:
                continue
            
            day_low = float('inf')
            first_candle = None
            consecutive_below = 0
            entry_taken = False
            
            for idx, candle in day_candles:
                ts = candle['timestamp']
                if ts.tzinfo:
                    ist = ts + self.IST_OFFSET
                else:
                    ist = ts
                ist_time = ist.time()
                
                # Track day stats
                if first_candle is None:
                    first_candle = candle
                day_low = min(day_low, candle['low'])
                
                # Skip pre-market and late hours
                if ist_time.hour < 9 or ist_time.hour >= 15:
                    continue
                if ist_time.hour == 9 and ist_time.minute < 15:
                    continue
                
                # Check for bearish market control (first candle high = day high)
                if first_candle['high'] < max(c['high'] for _, c in day_candles[:day_candles.index((idx, candle))+1]):
                    if day_candles.index((idx, candle)) > 5:  # Give some time
                        bearish_control = False
                    else:
                        bearish_control = True
                else:
                    bearish_control = True
                
                # Track consecutive closes below PDL
                if candle['close'] < pdl:
                    consecutive_below += 1
                else:
                    consecutive_below = 0
                
                # Entry conditions
                if entry_taken:
                    continue
                
                # Need at least 2 candles below PDL
                if consecutive_below < 2:
                    continue
                
                # Need breakdown of at least 0.3%
                breakdown_pct = (pdl - candle['close']) / pdl * 100
                if breakdown_pct < 0.3:
                    continue
                
                # Entry window (9:15 - 12:00)
                if ist_time.hour >= 12:
                    continue
                
                # Strong red candle for entry
                if candle['close'] >= candle['open']:
                    continue
                
                # Valid entry
                entries.append((idx, candle))
                entry_taken = True
        
        return entries
    
    def test_strategy_current(self) -> List[TradeResult]:
        """
        Current strategy: Big green candle (2.5x) + Trailing SL
        Min hold: 3 candles
        """
        results = []
        entries = self._find_pe_entries()
        
        for entry_idx, entry_candle in entries:
            entry_price = entry_candle['close']
            lowest_since_entry = entry_price
            trailing_sl = entry_price * 1.007  # 0.7% above
            max_profit_pct = 0
            candles_since_entry = 0
            
            for i in range(entry_idx + 1, min(entry_idx + 200, len(self.candles))):
                candle = self.candles[i]
                
                # Check if same day
                if candle['timestamp'].date() != entry_candle['timestamp'].date():
                    # EOD exit
                    exit_price = self.candles[i-1]['close']
                    pnl = (entry_price - exit_price) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        self.candles[i-1]['timestamp'], exit_price, "EOD", pnl
                    ))
                    break
                
                candles_since_entry += 1
                lowest_since_entry = min(lowest_since_entry, candle['low'])
                current_profit_pct = (entry_price - candle['close']) / entry_price * 100
                max_profit_pct = max(max_profit_pct, current_profit_pct)
                
                # Update trailing SL after profit
                if max_profit_pct >= 0.2:
                    new_sl = lowest_since_entry * 1.005  # 0.5% above lowest
                    trailing_sl = min(trailing_sl, new_sl)
                
                # Exit: Trailing SL hit
                if candle['high'] >= trailing_sl:
                    pnl = (entry_price - trailing_sl) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        candle['timestamp'], trailing_sl, "Trailing SL", pnl
                    ))
                    break
                
                # Exit: Big green candle (after min hold)
                if candles_since_entry >= 3:
                    avg_size = self._get_avg_candle_size(i)
                    if self._is_big_green_candle(candle, avg_size, 2.5):
                        exit_price = candle['close']
                        pnl = (entry_price - exit_price) / entry_price * 100
                        results.append(TradeResult(
                            self.symbol, entry_candle['timestamp'], entry_price,
                            candle['timestamp'], exit_price, "Big Green", pnl
                        ))
                        break
        
        return results
    
    def test_strategy_trailing_only(self) -> List[TradeResult]:
        """
        Strategy 1: Only trailing SL, no big candle exit
        """
        results = []
        entries = self._find_pe_entries()
        
        for entry_idx, entry_candle in entries:
            entry_price = entry_candle['close']
            lowest_since_entry = entry_price
            trailing_sl = entry_price * 1.007  # 0.7% above
            max_profit_pct = 0
            
            for i in range(entry_idx + 1, min(entry_idx + 200, len(self.candles))):
                candle = self.candles[i]
                
                # Check if same day
                if candle['timestamp'].date() != entry_candle['timestamp'].date():
                    exit_price = self.candles[i-1]['close']
                    pnl = (entry_price - exit_price) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        self.candles[i-1]['timestamp'], exit_price, "EOD", pnl
                    ))
                    break
                
                lowest_since_entry = min(lowest_since_entry, candle['low'])
                current_profit_pct = (entry_price - candle['close']) / entry_price * 100
                max_profit_pct = max(max_profit_pct, current_profit_pct)
                
                # Trail after profit
                if max_profit_pct >= 0.2:
                    new_sl = lowest_since_entry * 1.005
                    trailing_sl = min(trailing_sl, new_sl)
                
                # Exit: Trailing SL only
                if candle['high'] >= trailing_sl:
                    pnl = (entry_price - trailing_sl) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        candle['timestamp'], trailing_sl, "Trailing SL", pnl
                    ))
                    break
        
        return results
    
    def test_strategy_two_green_candles(self) -> List[TradeResult]:
        """
        Strategy 2: Exit on 2 consecutive green candles (not just big one)
        """
        results = []
        entries = self._find_pe_entries()
        
        for entry_idx, entry_candle in entries:
            entry_price = entry_candle['close']
            lowest_since_entry = entry_price
            trailing_sl = entry_price * 1.007
            max_profit_pct = 0
            consecutive_green = 0
            candles_since_entry = 0
            
            for i in range(entry_idx + 1, min(entry_idx + 200, len(self.candles))):
                candle = self.candles[i]
                
                if candle['timestamp'].date() != entry_candle['timestamp'].date():
                    exit_price = self.candles[i-1]['close']
                    pnl = (entry_price - exit_price) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        self.candles[i-1]['timestamp'], exit_price, "EOD", pnl
                    ))
                    break
                
                candles_since_entry += 1
                lowest_since_entry = min(lowest_since_entry, candle['low'])
                current_profit_pct = (entry_price - candle['close']) / entry_price * 100
                max_profit_pct = max(max_profit_pct, current_profit_pct)
                
                # Track consecutive green
                if candle['close'] > candle['open']:
                    consecutive_green += 1
                else:
                    consecutive_green = 0
                
                # Trail after profit
                if max_profit_pct >= 0.2:
                    new_sl = lowest_since_entry * 1.005
                    trailing_sl = min(trailing_sl, new_sl)
                
                # Exit: Trailing SL
                if candle['high'] >= trailing_sl:
                    pnl = (entry_price - trailing_sl) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        candle['timestamp'], trailing_sl, "Trailing SL", pnl
                    ))
                    break
                
                # Exit: 2 consecutive green candles (after min hold)
                if candles_since_entry >= 3 and consecutive_green >= 2:
                    exit_price = candle['close']
                    pnl = (entry_price - exit_price) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        candle['timestamp'], exit_price, "2 Green", pnl
                    ))
                    break
        
        return results
    
    def test_strategy_ema_confirmation(self) -> List[TradeResult]:
        """
        Strategy 3: Exit on big green candle ONLY if price > EMA9
        """
        results = []
        entries = self._find_pe_entries()
        
        for entry_idx, entry_candle in entries:
            entry_price = entry_candle['close']
            lowest_since_entry = entry_price
            trailing_sl = entry_price * 1.007
            max_profit_pct = 0
            candles_since_entry = 0
            
            for i in range(entry_idx + 1, min(entry_idx + 200, len(self.candles))):
                candle = self.candles[i]
                
                if candle['timestamp'].date() != entry_candle['timestamp'].date():
                    exit_price = self.candles[i-1]['close']
                    pnl = (entry_price - exit_price) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        self.candles[i-1]['timestamp'], exit_price, "EOD", pnl
                    ))
                    break
                
                candles_since_entry += 1
                lowest_since_entry = min(lowest_since_entry, candle['low'])
                current_profit_pct = (entry_price - candle['close']) / entry_price * 100
                max_profit_pct = max(max_profit_pct, current_profit_pct)
                
                # Trail after profit
                if max_profit_pct >= 0.2:
                    new_sl = lowest_since_entry * 1.005
                    trailing_sl = min(trailing_sl, new_sl)
                
                # Exit: Trailing SL
                if candle['high'] >= trailing_sl:
                    pnl = (entry_price - trailing_sl) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        candle['timestamp'], trailing_sl, "Trailing SL", pnl
                    ))
                    break
                
                # Exit: Big green candle + EMA confirmation (after min hold)
                if candles_since_entry >= 3:
                    avg_size = self._get_avg_candle_size(i)
                    ema = self.ema9[i] if i < len(self.ema9) else None
                    
                    if self._is_big_green_candle(candle, avg_size, 2.5):
                        # Only exit if price is ABOVE EMA9 (confirmed reversal)
                        if ema and candle['close'] > ema:
                            exit_price = candle['close']
                            pnl = (entry_price - exit_price) / entry_price * 100
                            results.append(TradeResult(
                                self.symbol, entry_candle['timestamp'], entry_price,
                                candle['timestamp'], exit_price, "BigGreen+EMA", pnl
                            ))
                            break
        
        return results
    
    def test_strategy_longer_hold(self) -> List[TradeResult]:
        """
        Strategy 4: Minimum hold 5 candles before any momentum exit
        """
        results = []
        entries = self._find_pe_entries()
        
        for entry_idx, entry_candle in entries:
            entry_price = entry_candle['close']
            lowest_since_entry = entry_price
            trailing_sl = entry_price * 1.007
            max_profit_pct = 0
            candles_since_entry = 0
            
            for i in range(entry_idx + 1, min(entry_idx + 200, len(self.candles))):
                candle = self.candles[i]
                
                if candle['timestamp'].date() != entry_candle['timestamp'].date():
                    exit_price = self.candles[i-1]['close']
                    pnl = (entry_price - exit_price) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        self.candles[i-1]['timestamp'], exit_price, "EOD", pnl
                    ))
                    break
                
                candles_since_entry += 1
                lowest_since_entry = min(lowest_since_entry, candle['low'])
                current_profit_pct = (entry_price - candle['close']) / entry_price * 100
                max_profit_pct = max(max_profit_pct, current_profit_pct)
                
                # Trail after profit
                if max_profit_pct >= 0.2:
                    new_sl = lowest_since_entry * 1.005
                    trailing_sl = min(trailing_sl, new_sl)
                
                # Exit: Trailing SL
                if candle['high'] >= trailing_sl:
                    pnl = (entry_price - trailing_sl) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        candle['timestamp'], trailing_sl, "Trailing SL", pnl
                    ))
                    break
                
                # Exit: Big green candle (after 5 candles min hold)
                if candles_since_entry >= 5:  # Changed from 3 to 5
                    avg_size = self._get_avg_candle_size(i)
                    if self._is_big_green_candle(candle, avg_size, 2.5):
                        exit_price = candle['close']
                        pnl = (entry_price - exit_price) / entry_price * 100
                        results.append(TradeResult(
                            self.symbol, entry_candle['timestamp'], entry_price,
                            candle['timestamp'], exit_price, "Big Green (5)", pnl
                        ))
                        break
        
        return results
    
    def test_strategy_ema_cross_only(self) -> List[TradeResult]:
        """
        Strategy 5: Exit ONLY when price crosses above EMA9 (no big candle check)
        """
        results = []
        entries = self._find_pe_entries()
        
        for entry_idx, entry_candle in entries:
            entry_price = entry_candle['close']
            lowest_since_entry = entry_price
            trailing_sl = entry_price * 1.007
            max_profit_pct = 0
            candles_since_entry = 0
            was_below_ema = False
            
            for i in range(entry_idx + 1, min(entry_idx + 200, len(self.candles))):
                candle = self.candles[i]
                
                if candle['timestamp'].date() != entry_candle['timestamp'].date():
                    exit_price = self.candles[i-1]['close']
                    pnl = (entry_price - exit_price) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        self.candles[i-1]['timestamp'], exit_price, "EOD", pnl
                    ))
                    break
                
                candles_since_entry += 1
                lowest_since_entry = min(lowest_since_entry, candle['low'])
                current_profit_pct = (entry_price - candle['close']) / entry_price * 100
                max_profit_pct = max(max_profit_pct, current_profit_pct)
                
                ema = self.ema9[i] if i < len(self.ema9) else None
                
                # Check if price was below EMA (confirmation we're in downtrend)
                if ema and candle['close'] < ema:
                    was_below_ema = True
                
                # Trail after profit
                if max_profit_pct >= 0.2:
                    new_sl = lowest_since_entry * 1.005
                    trailing_sl = min(trailing_sl, new_sl)
                
                # Exit: Trailing SL
                if candle['high'] >= trailing_sl:
                    pnl = (entry_price - trailing_sl) / entry_price * 100
                    results.append(TradeResult(
                        self.symbol, entry_candle['timestamp'], entry_price,
                        candle['timestamp'], trailing_sl, "Trailing SL", pnl
                    ))
                    break
                
                # Exit: EMA cross (after we were below it)
                if candles_since_entry >= 3 and was_below_ema and ema:
                    if candle['close'] > ema:
                        exit_price = candle['close']
                        pnl = (entry_price - exit_price) / entry_price * 100
                        results.append(TradeResult(
                            self.symbol, entry_candle['timestamp'], entry_price,
                            candle['timestamp'], exit_price, "EMA Cross", pnl
                        ))
                        break
        
        return results


def summarize_results(results: List[TradeResult], strategy_name: str) -> Dict:
    """Summarize trade results."""
    if not results:
        return {
            'strategy': strategy_name,
            'trades': 0,
            'wins': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_pnl': 0
        }
    
    wins = len([r for r in results if r.pnl_pct > 0])
    total_pnl = sum(r.pnl_pct for r in results)
    
    return {
        'strategy': strategy_name,
        'trades': len(results),
        'wins': wins,
        'win_rate': wins / len(results) * 100,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / len(results)
    }


def main():
    parser = argparse.ArgumentParser(description='Test PE exit strategies')
    parser.add_argument('--symbols', type=str, 
                        default='SBIN,TCS,NHPC,ETERNAL,PNB,ICICIBANK,HDFCBANK,INFY',
                        help='Comma-separated symbols')
    parser.add_argument('--days', type=int, default=60, help='Number of days')
    args = parser.parse_args()
    
    symbols = [s.strip() for s in args.symbols.split(',')]
    
    # Aggregate results by strategy
    all_results = {
        'Current (BigGreen+Trail)': [],
        'Trailing SL Only': [],
        '2 Consecutive Green': [],
        'BigGreen + EMA Confirm': [],
        'Longer Hold (5 candles)': [],
        'EMA Cross Only': []
    }
    
    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Testing {symbol}")
        print('='*60)
        
        candles = get_candle_data(symbol, args.days)
        if not candles:
            print(f"  No data for {symbol}")
            continue
        
        print(f"  Loaded {len(candles)} candles")
        
        tester = PEExitTester(candles, symbol)
        
        # Run all strategies
        r1 = tester.test_strategy_current()
        r2 = tester.test_strategy_trailing_only()
        r3 = tester.test_strategy_two_green_candles()
        r4 = tester.test_strategy_ema_confirmation()
        r5 = tester.test_strategy_longer_hold()
        r6 = tester.test_strategy_ema_cross_only()
        
        all_results['Current (BigGreen+Trail)'].extend(r1)
        all_results['Trailing SL Only'].extend(r2)
        all_results['2 Consecutive Green'].extend(r3)
        all_results['BigGreen + EMA Confirm'].extend(r4)
        all_results['Longer Hold (5 candles)'].extend(r5)
        all_results['EMA Cross Only'].extend(r6)
        
        # Print per-symbol summary
        s1 = summarize_results(r1, 'Current')
        s2 = summarize_results(r2, 'Trail Only')
        s3 = summarize_results(r3, '2 Green')
        s4 = summarize_results(r4, 'BigG+EMA')
        s5 = summarize_results(r5, 'Hold 5')
        s6 = summarize_results(r6, 'EMA Cross')
        
        print(f"\n  {symbol} Results:")
        print(f"    {'Strategy':<25} {'Trades':>7} {'Win%':>8} {'P&L':>10}")
        print(f"    {'-'*50}")
        for s in [s1, s2, s3, s4, s5, s6]:
            print(f"    {s['strategy']:<25} {s['trades']:>7} {s['win_rate']:>7.1f}% {s['total_pnl']:>+9.2f}%")
    
    # Final summary
    print("\n" + "="*70)
    print("OVERALL SUMMARY - ALL SYMBOLS COMBINED")
    print("="*70)
    print(f"\n{'Strategy':<30} {'Trades':>8} {'Wins':>6} {'Win%':>8} {'Total P&L':>12} {'Avg P&L':>10}")
    print("-"*75)
    
    best_strategy = None
    best_pnl = float('-inf')
    
    for name, results in all_results.items():
        summary = summarize_results(results, name)
        print(f"{name:<30} {summary['trades']:>8} {summary['wins']:>6} {summary['win_rate']:>7.1f}% {summary['total_pnl']:>+11.2f}% {summary['avg_pnl']:>+9.2f}%")
        
        if summary['total_pnl'] > best_pnl:
            best_pnl = summary['total_pnl']
            best_strategy = name
    
    print("-"*75)
    print(f"\n🏆 BEST STRATEGY: {best_strategy} with {best_pnl:+.2f}% total P&L")
    
    # Detailed exit reason breakdown for best strategy
    print(f"\n📊 Exit Reason Breakdown for '{best_strategy}':")
    exit_reasons = defaultdict(list)
    for r in all_results[best_strategy]:
        exit_reasons[r.exit_reason].append(r.pnl_pct)
    
    for reason, pnls in sorted(exit_reasons.items(), key=lambda x: sum(x[1]), reverse=True):
        wins = len([p for p in pnls if p > 0])
        total = sum(pnls)
        print(f"  {reason}: {len(pnls)} trades, {wins/len(pnls)*100:.1f}% win, {total:+.2f}% P&L")


if __name__ == "__main__":
    main()
