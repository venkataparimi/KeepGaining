"""
Test different CE exit strategies on the actual backtest framework.
Based on analysis findings:
1. EMA Cross exit performs better than Big Red
2. Holding longer (15-30 candles) improves results
3. We're exiting too early - 83% of time price goes up after big red exit
"""

import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from app.core.config import settings

# IST offset
IST_OFFSET = timedelta(hours=5, minutes=30)

class CEExitStrategy(Enum):
    CURRENT = "current"  # Big red candle + trailing SL
    EMA_CROSS = "ema_cross"  # Exit when price closes below EMA9
    LONGER_HOLD = "longer_hold"  # Min hold 10 candles before any exit
    EMA_CONFIRM = "ema_confirm"  # Big red + price must close below EMA
    TWO_RED = "two_red"  # Wait for 2 consecutive red candles
    TRAIL_TIGHTER = "trail_tighter"  # 0.2% trailing SL only

@dataclass
class Trade:
    symbol: str
    direction: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    pnl_pct: float
    exit_reason: str
    score: float

def get_db_connection():
    """Get sync database connection."""
    db_url = str(settings.DATABASE_URL)
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return create_engine(db_url)

def get_candle_data(engine, symbol: str, days: int = 60) -> pd.DataFrame:
    """Fetch candle data for analysis."""
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
    
    with engine.connect() as conn:
        result = conn.execute(query, {"symbol": symbol, "start_date": start_date})
        rows = result.fetchall()
    
    if not rows:
        return pd.DataFrame()
    
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    return df

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate technical indicators."""
    df = df.copy()
    
    # EMA
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    
    # VWAP (simplified - reset daily)
    df['ist_time'] = df['timestamp'] + IST_OFFSET
    df['date'] = df['ist_time'].dt.date
    df['cum_vol'] = df.groupby('date')['volume'].cumsum()
    df['cum_vol_price'] = (df['close'] * df['volume']).groupby(df['date']).cumsum()
    df['vwap'] = df['cum_vol_price'] / df['cum_vol']
    
    # ATR
    df['prev_close'] = df['close'].shift(1)
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            np.abs(df['high'] - df['prev_close']),
            np.abs(df['low'] - df['prev_close'])
        )
    )
    df['atr'] = df['tr'].rolling(14).mean()
    
    # Candle properties
    df['body'] = np.abs(df['close'] - df['open'])
    df['range'] = df['high'] - df['low']
    df['body_pct'] = df['body'] / df['open'] * 100
    df['is_green'] = df['close'] > df['open']
    df['is_red'] = df['close'] < df['open']
    
    # Previous day high
    df['prev_day_high'] = df.groupby('date')['high'].transform('max').shift(1)
    
    return df

def check_ce_entry(df: pd.DataFrame, idx: int) -> Tuple[bool, float]:
    """Check if CE entry conditions are met."""
    if idx < 20:
        return False, 0
    
    row = df.iloc[idx]
    ist_time = row['timestamp'] + IST_OFFSET
    ist_hour = ist_time.hour
    ist_minute = ist_time.minute
    
    # Entry window: 9:15 to 12:00 IST
    if ist_hour < 9 or ist_hour >= 12:
        return False, 0
    if ist_hour == 9 and ist_minute < 15:
        return False, 0
    
    # Must be green candle with significant body
    if not row['is_green']:
        return False, 0
    if row['body_pct'] < 0.3:
        return False, 0
    
    # Price above EMA9 and VWAP
    if row['close'] <= row['ema9']:
        return False, 0
    if row['close'] <= row['vwap']:
        return False, 0
    
    # Volume above average
    vol_avg = df['volume'].iloc[max(0, idx-10):idx].mean()
    if row['volume'] < vol_avg * 0.8:
        return False, 0
    
    # Score calculation
    score = 50
    if row['close'] > row['ema20']:
        score += 15
    if row['body_pct'] > 0.5:
        score += 10
    if row['volume'] > vol_avg * 1.5:
        score += 15
    if pd.notna(row.get('prev_day_high')) and row['close'] > row['prev_day_high']:
        score += 10
    
    return True, score

def simulate_ce_trade(df: pd.DataFrame, entry_idx: int, entry_price: float, 
                      strategy: CEExitStrategy, score: float) -> Optional[Trade]:
    """Simulate a CE trade with specific exit strategy."""
    
    # Config
    min_hold = 3 if strategy != CEExitStrategy.LONGER_HOLD else 10
    stop_loss_pct = 0.005  # 0.5%
    trail_sl_pct = 0.003 if strategy != CEExitStrategy.TRAIL_TIGHTER else 0.002
    max_hold = 90  # ~1.5 hours
    
    entry_time = df.iloc[entry_idx]['timestamp']
    stop_loss = entry_price * (1 - stop_loss_pct)
    max_high = entry_price
    candles_held = 0
    exit_idx = None
    exit_price = None
    exit_reason = None
    
    consecutive_red = 0
    
    for i in range(entry_idx + 1, min(entry_idx + max_hold, len(df))):
        candle = df.iloc[i]
        candles_held += 1
        
        ist_time = candle['timestamp'] + IST_OFFSET
        ist_hour = ist_time.hour
        ist_minute = ist_time.minute
        
        # Check if we're in different day - close trade
        entry_ist = entry_time + IST_OFFSET
        if candle['ist_time'].date() != entry_ist.date():
            exit_idx = i
            exit_price = candle['open']
            exit_reason = "New day"
            break
        
        # EOD exit at 15:15 IST
        if ist_hour == 15 and ist_minute >= 15:
            exit_idx = i
            exit_price = candle['close']
            exit_reason = "EOD exit"
            break
        
        # Stop loss
        if candle['low'] <= stop_loss:
            exit_idx = i
            exit_price = stop_loss
            exit_reason = "Stop loss hit"
            break
        
        # Update trailing stop
        if candle['high'] > max_high:
            max_high = candle['high']
        
        # Trailing SL check
        trail_sl = max_high * (1 - trail_sl_pct)
        if candle['low'] <= trail_sl:
            exit_idx = i
            exit_price = trail_sl
            exit_reason = f"Trailing SL hit"
            break
        
        # Strategy-specific exits (after min hold)
        if candles_held >= min_hold:
            
            if strategy == CEExitStrategy.CURRENT:
                # Big red candle exit
                if candle['is_red'] and candle['body_pct'] > 0.3:
                    exit_idx = i
                    exit_price = candle['close']
                    exit_reason = "Big red candle"
                    break
            
            elif strategy == CEExitStrategy.EMA_CROSS:
                # Exit when close below EMA9
                if candle['close'] < candle['ema9']:
                    exit_idx = i
                    exit_price = candle['close']
                    exit_reason = "EMA9 cross down"
                    break
            
            elif strategy == CEExitStrategy.LONGER_HOLD:
                # Same as current but with longer min hold
                if candle['is_red'] and candle['body_pct'] > 0.3:
                    exit_idx = i
                    exit_price = candle['close']
                    exit_reason = "Big red candle (10-hold)"
                    break
            
            elif strategy == CEExitStrategy.EMA_CONFIRM:
                # Big red + close below EMA
                if candle['is_red'] and candle['body_pct'] > 0.3 and candle['close'] < candle['ema9']:
                    exit_idx = i
                    exit_price = candle['close']
                    exit_reason = "Big red + EMA confirm"
                    break
            
            elif strategy == CEExitStrategy.TWO_RED:
                # Two consecutive red candles
                if candle['is_red']:
                    consecutive_red += 1
                    if consecutive_red >= 2:
                        exit_idx = i
                        exit_price = candle['close']
                        exit_reason = "Two red candles"
                        break
                else:
                    consecutive_red = 0
            
            elif strategy == CEExitStrategy.TRAIL_TIGHTER:
                # Just trailing SL (handled above)
                pass
    
    if exit_idx is None:
        return None
    
    exit_time = df.iloc[exit_idx]['timestamp']
    if exit_price is None:
        exit_price = df.iloc[exit_idx]['close']
    
    pnl_pct = (exit_price - entry_price) / entry_price * 100
    
    return Trade(
        symbol="",  # Will be set later
        direction="CE",
        entry_time=entry_time,
        entry_price=entry_price,
        exit_time=exit_time,
        exit_price=exit_price,
        pnl_pct=pnl_pct,
        exit_reason=exit_reason,
        score=score
    )

def run_backtest(df: pd.DataFrame, symbol: str, strategy: CEExitStrategy) -> List[Trade]:
    """Run backtest for a symbol with specific exit strategy."""
    trades = []
    in_trade = False
    cooldown_until = None
    
    for idx in range(20, len(df)):
        if in_trade:
            continue
        
        if cooldown_until and df.iloc[idx]['timestamp'] < cooldown_until:
            continue
        
        # Check entry
        entry_ok, score = check_ce_entry(df, idx)
        if not entry_ok:
            continue
        
        entry_price = df.iloc[idx]['close']
        
        # Simulate trade
        trade = simulate_ce_trade(df, idx, entry_price, strategy, score)
        
        if trade:
            trade.symbol = symbol
            trades.append(trade)
            # Cooldown - no new trade for 15 candles
            cooldown_until = df.iloc[min(idx + 15, len(df) - 1)]['timestamp']
    
    return trades

def main():
    print("=" * 80)
    print("CE EXIT STRATEGY COMPARISON")
    print("=" * 80)
    
    engine = get_db_connection()
    
    symbols = [
        "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY",
        "SBIN", "AXISBANK", "BHARTIARTL", "LT", "KOTAKBANK",
        "HCLTECH", "BAJFINANCE", "ADANIENT", "HINDALCO", "TITAN",
        "WIPRO", "ULTRACEMCO", "SUNPHARMA", "MARUTI", "TATASTEEL"
    ]
    
    strategies = [
        CEExitStrategy.CURRENT,
        CEExitStrategy.EMA_CROSS,
        CEExitStrategy.LONGER_HOLD,
        CEExitStrategy.EMA_CONFIRM,
        CEExitStrategy.TWO_RED,
        CEExitStrategy.TRAIL_TIGHTER,
    ]
    
    results = {s: [] for s in strategies}
    
    for symbol in symbols:
        print(f"\nProcessing {symbol}...")
        
        df = get_candle_data(engine, symbol, days=60)
        if len(df) < 100:
            print(f"  Skipping - insufficient data")
            continue
        
        df = calculate_indicators(df)
        
        for strategy in strategies:
            trades = run_backtest(df, symbol, strategy)
            results[strategy].extend(trades)
        
        print(f"  Trades per strategy: {len(results[CEExitStrategy.CURRENT])} total so far")
    
    # Print results
    print("\n" + "=" * 80)
    print("STRATEGY COMPARISON RESULTS")
    print("=" * 80)
    
    for strategy in strategies:
        trades = results[strategy]
        if not trades:
            continue
        
        wins = sum(1 for t in trades if t.pnl_pct > 0)
        total_pnl = sum(t.pnl_pct for t in trades)
        avg_pnl = np.mean([t.pnl_pct for t in trades])
        
        win_pnls = [t.pnl_pct for t in trades if t.pnl_pct > 0]
        loss_pnls = [t.pnl_pct for t in trades if t.pnl_pct <= 0]
        
        avg_win = np.mean(win_pnls) if win_pnls else 0
        avg_loss = np.mean(loss_pnls) if loss_pnls else 0
        
        print(f"\n{'-' * 60}")
        print(f"{strategy.value.upper()}")
        print(f"{'-' * 60}")
        print(f"  Total Trades: {len(trades)}")
        print(f"  Win Rate: {wins/len(trades)*100:.1f}%")
        print(f"  Total P&L: {total_pnl:+.2f}%")
        print(f"  Avg P&L: {avg_pnl:+.3f}%")
        print(f"  Avg Win: {avg_win:+.3f}% | Avg Loss: {avg_loss:+.3f}%")
        
        # Exit reason breakdown
        exit_reasons = {}
        for t in trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1
        print(f"  Exit Reasons:")
        for reason, count in sorted(exit_reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count}")
    
    # Best strategy recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    best_strategy = max(strategies, key=lambda s: sum(t.pnl_pct for t in results[s]) if results[s] else -999)
    best_trades = results[best_strategy]
    best_pnl = sum(t.pnl_pct for t in best_trades)
    
    current_trades = results[CEExitStrategy.CURRENT]
    current_pnl = sum(t.pnl_pct for t in current_trades)
    
    print(f"\nBest Strategy: {best_strategy.value.upper()}")
    print(f"  Total P&L: {best_pnl:+.2f}%")
    print(f"\nCurrent Strategy P&L: {current_pnl:+.2f}%")
    print(f"Improvement: {best_pnl - current_pnl:+.2f}%")

if __name__ == "__main__":
    main()
