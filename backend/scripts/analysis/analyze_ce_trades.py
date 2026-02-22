"""
CE Trade Analysis Script
Analyzes CE trade patterns to identify improvement opportunities.

Key areas to analyze:
1. Exit timing - are we exiting too early?
2. Score correlation - do higher scores perform better?
3. Hold duration - optimal hold time
4. Time of day patterns
5. What happens after exit - missed profits?
"""

import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from app.core.config import settings

# IST offset
IST_OFFSET = timedelta(hours=5, minutes=30)

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
    
    # Convert decimal to float
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    return df

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate technical indicators."""
    # EMA
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    
    # VWAP (simplified - reset daily)
    df['ist_time'] = df['timestamp'] + IST_OFFSET
    df['date'] = df['ist_time'].dt.date
    df['cum_vol'] = df.groupby('date')['volume'].cumsum()
    df['cum_vol_price'] = df.groupby('date').apply(
        lambda x: (x['close'] * x['volume']).cumsum()
    ).reset_index(level=0, drop=True)
    df['vwap'] = df['cum_vol_price'] / df['cum_vol']
    
    # ATR
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(14).mean()
    
    # Candle properties
    df['body'] = abs(df['close'] - df['open'])
    df['range'] = df['high'] - df['low']
    df['body_pct'] = df['body'] / df['open'] * 100
    df['is_green'] = df['close'] > df['open']
    df['is_red'] = df['close'] < df['open']
    
    return df

def identify_ce_entries(df: pd.DataFrame) -> List[Dict]:
    """Identify potential CE entry points."""
    entries = []
    
    df = df.copy()
    df['ist_hour'] = (df['timestamp'] + IST_OFFSET).dt.hour
    df['ist_minute'] = (df['timestamp'] + IST_OFFSET).dt.minute
    
    # Entry window: 9:15 to 12:00 IST
    entry_mask = (
        (df['ist_hour'] >= 9) & 
        ((df['ist_hour'] < 12) | ((df['ist_hour'] == 9) & (df['ist_minute'] >= 15)))
    )
    
    prev_close = None
    
    for idx in range(20, len(df)):
        row = df.iloc[idx]
        
        if not entry_mask.iloc[idx]:
            continue
        
        # Basic CE entry conditions
        if not row['is_green']:
            continue
        
        if row['body_pct'] < 0.3:  # Significant green candle
            continue
            
        if row['close'] <= row['ema9']:
            continue
            
        if row['close'] <= row['vwap']:
            continue
        
        # Score calculation (simplified)
        score = 50
        if row['close'] > row['ema20']:
            score += 15
        if row['body_pct'] > 0.5:
            score += 15
        if row['volume'] > df['volume'].iloc[idx-5:idx].mean() * 1.2:
            score += 20
        
        entries.append({
            'entry_idx': idx,
            'entry_time': row['timestamp'],
            'entry_price': row['close'],
            'score': score,
            'ema9': row['ema9'],
            'vwap': row['vwap'],
            'atr': row['atr']
        })
    
    return entries

def analyze_ce_trade(df: pd.DataFrame, entry: Dict) -> Dict:
    """Analyze what happened after CE entry."""
    entry_idx = entry['entry_idx']
    entry_price = entry['entry_price']
    entry_time = entry['entry_time']
    
    # Look at next 60 candles (1 hour)
    trade_data = df.iloc[entry_idx:entry_idx + 60].copy()
    
    if len(trade_data) < 5:
        return None
    
    # Track exit scenarios
    exit_scenarios = {}
    
    # 1. Big red candle exit (current strategy)
    big_red_exit_idx = None
    for i in range(3, len(trade_data)):  # Min hold 3 candles
        row = trade_data.iloc[i]
        if row['is_red'] and row['body_pct'] > 0.3:
            big_red_exit_idx = i
            break
    
    if big_red_exit_idx:
        exit_price = trade_data.iloc[big_red_exit_idx]['close']
        exit_scenarios['big_red'] = {
            'exit_idx': big_red_exit_idx,
            'exit_price': exit_price,
            'pnl_pct': (exit_price - entry_price) / entry_price * 100,
            'duration_min': big_red_exit_idx
        }
    
    # 2. Trailing SL only (0.3% from high)
    max_high = entry_price
    trail_sl_exit_idx = None
    for i in range(1, len(trade_data)):
        row = trade_data.iloc[i]
        max_high = max(max_high, row['high'])
        trail_sl = max_high * 0.997  # 0.3% trailing
        if row['low'] <= trail_sl:
            trail_sl_exit_idx = i
            break
    
    if trail_sl_exit_idx:
        exit_price = max_high * 0.997
        exit_scenarios['trail_only'] = {
            'exit_idx': trail_sl_exit_idx,
            'exit_price': exit_price,
            'pnl_pct': (exit_price - entry_price) / entry_price * 100,
            'duration_min': trail_sl_exit_idx
        }
    
    # 3. Fixed time exits (5, 10, 15, 20, 30 candles)
    for hold_time in [5, 10, 15, 20, 30]:
        if len(trade_data) > hold_time:
            exit_price = trade_data.iloc[hold_time]['close']
            exit_scenarios[f'hold_{hold_time}'] = {
                'exit_idx': hold_time,
                'exit_price': exit_price,
                'pnl_pct': (exit_price - entry_price) / entry_price * 100,
                'duration_min': hold_time
            }
    
    # 4. EMA cross exit
    ema_cross_exit_idx = None
    for i in range(3, len(trade_data)):
        row = trade_data.iloc[i]
        if row['close'] < row['ema9']:
            ema_cross_exit_idx = i
            break
    
    if ema_cross_exit_idx:
        exit_price = trade_data.iloc[ema_cross_exit_idx]['close']
        exit_scenarios['ema_cross'] = {
            'exit_idx': ema_cross_exit_idx,
            'exit_price': exit_price,
            'pnl_pct': (exit_price - entry_price) / entry_price * 100,
            'duration_min': ema_cross_exit_idx
        }
    
    # 5. Big red + confirmation (2 red candles)
    confirmed_red_exit_idx = None
    for i in range(3, len(trade_data) - 1):
        row = trade_data.iloc[i]
        next_row = trade_data.iloc[i + 1]
        if row['is_red'] and next_row['is_red']:
            confirmed_red_exit_idx = i + 1
            break
    
    if confirmed_red_exit_idx:
        exit_price = trade_data.iloc[confirmed_red_exit_idx]['close']
        exit_scenarios['2_red_confirm'] = {
            'exit_idx': confirmed_red_exit_idx,
            'exit_price': exit_price,
            'pnl_pct': (exit_price - entry_price) / entry_price * 100,
            'duration_min': confirmed_red_exit_idx
        }
    
    # 6. Wait for green close below entry (trend broken)
    trend_break_exit_idx = None
    for i in range(3, len(trade_data)):
        row = trade_data.iloc[i]
        if row['close'] < entry_price and row['is_green']:
            trend_break_exit_idx = i
            break
    
    if trend_break_exit_idx:
        exit_price = trade_data.iloc[trend_break_exit_idx]['close']
        exit_scenarios['trend_break'] = {
            'exit_idx': trend_break_exit_idx,
            'exit_price': exit_price,
            'pnl_pct': (exit_price - entry_price) / entry_price * 100,
            'duration_min': trend_break_exit_idx
        }
    
    # Calculate max profit/drawdown during trade
    max_price = trade_data['high'].max()
    min_price = trade_data['low'].min()
    max_profit_pct = (max_price - entry_price) / entry_price * 100
    max_drawdown_pct = (entry_price - min_price) / entry_price * 100
    
    return {
        'entry': entry,
        'exit_scenarios': exit_scenarios,
        'max_profit_pct': max_profit_pct,
        'max_drawdown_pct': max_drawdown_pct,
        'candles_analyzed': len(trade_data)
    }

def main():
    print("=" * 80)
    print("CE TRADE ANALYSIS - IDENTIFYING IMPROVEMENT OPPORTUNITIES")
    print("=" * 80)
    
    engine = get_db_connection()
    
    # Test on multiple stocks
    symbols = [
        "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY",
        "SBIN", "AXISBANK", "BHARTIARTL", "LT", "KOTAKBANK",
        "HCLTECH", "BAJFINANCE", "ADANIENT", "HINDALCO", "TITAN"
    ]
    
    all_trades = []
    
    for symbol in symbols:
        print(f"\nAnalyzing {symbol}...")
        
        df = get_candle_data(engine, symbol, days=60)
        if len(df) < 100:
            print(f"  Skipping - insufficient data ({len(df)} candles)")
            continue
        
        df = calculate_indicators(df)
        entries = identify_ce_entries(df)
        
        print(f"  Found {len(entries)} potential CE entries")
        
        for entry in entries:
            trade_analysis = analyze_ce_trade(df, entry)
            if trade_analysis:
                trade_analysis['symbol'] = symbol
                all_trades.append(trade_analysis)
    
    print(f"\n{'=' * 80}")
    print(f"ANALYZED {len(all_trades)} CE TRADES")
    print("=" * 80)
    
    # Aggregate results by exit strategy
    exit_strategies = ['big_red', 'trail_only', 'ema_cross', '2_red_confirm', 
                       'trend_break', 'hold_5', 'hold_10', 'hold_15', 'hold_20', 'hold_30']
    
    print("\n" + "-" * 60)
    print("EXIT STRATEGY COMPARISON")
    print("-" * 60)
    
    for strategy in exit_strategies:
        pnls = []
        durations = []
        for trade in all_trades:
            if strategy in trade['exit_scenarios']:
                pnls.append(trade['exit_scenarios'][strategy]['pnl_pct'])
                durations.append(trade['exit_scenarios'][strategy]['duration_min'])
        
        if pnls:
            wins = sum(1 for p in pnls if p > 0)
            total_pnl = sum(pnls)
            avg_pnl = np.mean(pnls)
            avg_duration = np.mean(durations)
            win_rate = wins / len(pnls) * 100
            
            print(f"\n{strategy.upper():20} ({len(pnls)} trades)")
            print(f"  Win Rate: {win_rate:.1f}%")
            print(f"  Total P&L: {total_pnl:+.2f}%")
            print(f"  Avg P&L: {avg_pnl:+.3f}%")
            print(f"  Avg Duration: {avg_duration:.1f} candles")
    
    # Analyze by score buckets
    print("\n" + "-" * 60)
    print("PERFORMANCE BY ENTRY SCORE")
    print("-" * 60)
    
    score_buckets = [(50, 60), (60, 70), (70, 80), (80, 90), (90, 100)]
    for low, high in score_buckets:
        bucket_trades = [t for t in all_trades if low <= t['entry']['score'] < high]
        if bucket_trades:
            big_red_pnls = [t['exit_scenarios']['big_red']['pnl_pct'] 
                           for t in bucket_trades if 'big_red' in t['exit_scenarios']]
            if big_red_pnls:
                wins = sum(1 for p in big_red_pnls if p > 0)
                print(f"\nScore {low}-{high}: {len(big_red_pnls)} trades")
                print(f"  Win Rate: {wins/len(big_red_pnls)*100:.1f}%")
                print(f"  Total P&L: {sum(big_red_pnls):+.2f}%")
                print(f"  Avg P&L: {np.mean(big_red_pnls):+.3f}%")
    
    # Analyze max profit potential
    print("\n" + "-" * 60)
    print("MAX PROFIT POTENTIAL ANALYSIS")
    print("-" * 60)
    
    max_profits = [t['max_profit_pct'] for t in all_trades]
    max_drawdowns = [t['max_drawdown_pct'] for t in all_trades]
    
    if 'big_red' in all_trades[0]['exit_scenarios']:
        big_red_pnls = [t['exit_scenarios']['big_red']['pnl_pct'] 
                       for t in all_trades if 'big_red' in t['exit_scenarios']]
        captured = [t['exit_scenarios']['big_red']['pnl_pct'] / t['max_profit_pct'] * 100 
                   if t['max_profit_pct'] > 0 else 0
                   for t in all_trades if 'big_red' in t['exit_scenarios'] and t['max_profit_pct'] > 0]
        
        print(f"\nAvg Max Profit Available: {np.mean(max_profits):.2f}%")
        print(f"Avg Max Drawdown: {np.mean(max_drawdowns):.2f}%")
        print(f"Avg P&L Captured (Big Red Exit): {np.mean(big_red_pnls):.3f}%")
        if captured:
            print(f"Avg % of Max Profit Captured: {np.mean(captured):.1f}%")
    
    # Missed profit analysis - what happens after big red exit
    print("\n" + "-" * 60)
    print("POST-EXIT ANALYSIS (After Big Red Candle)")
    print("-" * 60)
    
    continued_up = 0
    continued_down = 0
    
    for trade in all_trades:
        if 'big_red' in trade['exit_scenarios'] and 'hold_30' in trade['exit_scenarios']:
            big_red_pnl = trade['exit_scenarios']['big_red']['pnl_pct']
            hold_30_pnl = trade['exit_scenarios']['hold_30']['pnl_pct']
            
            if hold_30_pnl > big_red_pnl + 0.1:  # Price went higher after exit
                continued_up += 1
            elif hold_30_pnl < big_red_pnl - 0.1:  # Price went lower after exit
                continued_down += 1
    
    total_analyzed = continued_up + continued_down
    if total_analyzed > 0:
        print(f"\nAfter Big Red Exit:")
        print(f"  Price continued UP: {continued_up} ({continued_up/total_analyzed*100:.1f}%)")
        print(f"  Price continued DOWN: {continued_down} ({continued_down/total_analyzed*100:.1f}%)")
    
    # Best performing stocks for CE
    print("\n" + "-" * 60)
    print("BEST CE STOCKS")
    print("-" * 60)
    
    stock_performance = {}
    for trade in all_trades:
        symbol = trade['symbol']
        if symbol not in stock_performance:
            stock_performance[symbol] = {'pnls': [], 'wins': 0}
        
        if 'big_red' in trade['exit_scenarios']:
            pnl = trade['exit_scenarios']['big_red']['pnl_pct']
            stock_performance[symbol]['pnls'].append(pnl)
            if pnl > 0:
                stock_performance[symbol]['wins'] += 1
    
    sorted_stocks = sorted(stock_performance.items(), 
                          key=lambda x: sum(x[1]['pnls']), 
                          reverse=True)
    
    for symbol, data in sorted_stocks:
        if data['pnls']:
            total_pnl = sum(data['pnls'])
            win_rate = data['wins'] / len(data['pnls']) * 100
            print(f"{symbol:12} | {len(data['pnls']):3} trades | {win_rate:5.1f}% win | {total_pnl:+6.2f}% P&L")

if __name__ == "__main__":
    main()
