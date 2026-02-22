"""
Analyze stock volatility and PE trade performance to build a filter.
Identify which stocks are suitable for PE trades based on:
1. Average True Range (ATR) - volatility measure
2. Historical PE trade performance
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from datetime import datetime, date, timedelta
from typing import List, Dict, Tuple
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create sync session
db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=engine)


@dataclass
class StockVolatility:
    symbol: str
    avg_daily_range_pct: float  # Average (High-Low)/Close %
    avg_atr_pct: float  # Average True Range %
    avg_body_pct: float  # Average candle body size %
    max_daily_move_pct: float  # Largest single day move
    down_days_pct: float  # % of days that closed lower
    pe_trades: int = 0
    pe_win_rate: float = 0.0
    pe_total_pnl: float = 0.0


def get_all_fo_symbols() -> List[str]:
    """Get all F&O symbols from database."""
    db = SessionLocal()
    try:
        query = text("""
            SELECT DISTINCT im.trading_symbol
            FROM instrument_master im
            WHERE im.instrument_type = 'EQUITY'
            AND im.exchange = 'NSE'
            AND EXISTS (
                SELECT 1 FROM candle_data cd 
                WHERE cd.instrument_id = im.instrument_id
            )
            ORDER BY im.trading_symbol
        """)
        result = db.execute(query)
        return [row[0] for row in result.fetchall()]
    finally:
        db.close()


def get_daily_data(symbol: str, days: int = 60) -> List[Dict]:
    """Get daily OHLC data (aggregated from 1-min candles)."""
    db = SessionLocal()
    try:
        start_date = date.today() - timedelta(days=days)
        
        query = text("""
            SELECT 
                DATE(cd.timestamp + INTERVAL '5 hours 30 minutes') as trade_date,
                MIN(cd.open) as day_open,
                MAX(cd.high) as day_high,
                MIN(cd.low) as day_low,
                MAX(cd.close) as day_close,
                SUM(cd.volume) as day_volume
            FROM candle_data cd
            JOIN instrument_master im ON cd.instrument_id = im.instrument_id
            WHERE im.trading_symbol = :symbol
            AND im.instrument_type = 'EQUITY'
            AND cd.timestamp >= :start_date
            GROUP BY DATE(cd.timestamp + INTERVAL '5 hours 30 minutes')
            ORDER BY trade_date ASC
        """)
        
        result = db.execute(query, {"symbol": symbol, "start_date": start_date})
        rows = result.fetchall()
        
        # Get proper day open/close from first/last candles
        daily_data = []
        for row in rows:
            # Simplified - just use the aggregated data
            daily_data.append({
                'date': row[0],
                'open': float(row[1]) if row[1] else 0,
                'high': float(row[2]) if row[2] else 0,
                'low': float(row[3]) if row[3] else 0,
                'close': float(row[4]) if row[4] else 0,
                'volume': int(row[5]) if row[5] else 0
            })
        
        return daily_data
    finally:
        db.close()


def calculate_volatility(symbol: str, days: int = 60) -> StockVolatility:
    """Calculate volatility metrics for a stock."""
    daily_data = get_daily_data(symbol, days)
    
    if len(daily_data) < 10:
        return StockVolatility(
            symbol=symbol,
            avg_daily_range_pct=0,
            avg_atr_pct=0,
            avg_body_pct=0,
            max_daily_move_pct=0,
            down_days_pct=0
        )
    
    ranges = []
    bodies = []
    atrs = []
    down_days = 0
    prev_close = None
    
    for day in daily_data:
        if day['close'] <= 0:
            continue
            
        # Daily range %
        daily_range = (day['high'] - day['low']) / day['close'] * 100
        ranges.append(daily_range)
        
        # Body size %
        body = abs(day['close'] - day['open']) / day['close'] * 100
        bodies.append(body)
        
        # ATR calculation
        if prev_close:
            true_range = max(
                day['high'] - day['low'],
                abs(day['high'] - prev_close),
                abs(day['low'] - prev_close)
            )
            atr_pct = true_range / day['close'] * 100
            atrs.append(atr_pct)
        
        # Down days
        if prev_close and day['close'] < prev_close:
            down_days += 1
        
        prev_close = day['close']
    
    return StockVolatility(
        symbol=symbol,
        avg_daily_range_pct=sum(ranges) / len(ranges) if ranges else 0,
        avg_atr_pct=sum(atrs) / len(atrs) if atrs else 0,
        avg_body_pct=sum(bodies) / len(bodies) if bodies else 0,
        max_daily_move_pct=max(ranges) if ranges else 0,
        down_days_pct=down_days / len(daily_data) * 100 if daily_data else 0
    )


def main():
    parser = argparse.ArgumentParser(description='Analyze volatility for PE filtering')
    parser.add_argument('--days', type=int, default=60, help='Number of days')
    parser.add_argument('--top', type=int, default=30, help='Show top N volatile stocks')
    args = parser.parse_args()
    
    print("Fetching F&O symbols...")
    symbols = get_all_fo_symbols()
    print(f"Found {len(symbols)} symbols")
    
    # Calculate volatility for all
    volatilities = []
    for i, symbol in enumerate(symbols):
        if i % 20 == 0:
            print(f"  Processing {i}/{len(symbols)}...")
        vol = calculate_volatility(symbol, args.days)
        if vol.avg_atr_pct > 0:
            volatilities.append(vol)
    
    # Sort by ATR (volatility)
    volatilities.sort(key=lambda x: x.avg_atr_pct, reverse=True)
    
    print(f"\n{'='*80}")
    print(f"TOP {args.top} MOST VOLATILE STOCKS (by ATR %)")
    print(f"{'='*80}")
    print(f"{'Symbol':<15} {'ATR%':>8} {'Range%':>8} {'Body%':>8} {'MaxMove%':>10} {'Down%':>8}")
    print(f"{'-'*60}")
    
    top_volatile = []
    for vol in volatilities[:args.top]:
        print(f"{vol.symbol:<15} {vol.avg_atr_pct:>7.2f}% {vol.avg_daily_range_pct:>7.2f}% {vol.avg_body_pct:>7.2f}% {vol.max_daily_move_pct:>9.2f}% {vol.down_days_pct:>7.1f}%")
        top_volatile.append(vol.symbol)
    
    # Now test PE on these volatile stocks only
    print(f"\n{'='*80}")
    print("RECOMMENDED PE-ELIGIBLE STOCKS (ATR > 2%)")
    print(f"{'='*80}")
    
    pe_eligible = [v for v in volatilities if v.avg_atr_pct >= 2.0]
    print(f"\nFound {len(pe_eligible)} stocks with ATR >= 2%:")
    for vol in pe_eligible:
        print(f"  - {vol.symbol} (ATR: {vol.avg_atr_pct:.2f}%, Down days: {vol.down_days_pct:.1f}%)")
    
    # Generate config
    print(f"\n{'='*80}")
    print("CONFIGURATION FOR STRATEGY")
    print(f"{'='*80}")
    print("\n# Add this to IntradayMomentumConfig:")
    print("pe_eligible_symbols: List[str] = field(default_factory=lambda: [")
    for vol in pe_eligible[:20]:  # Top 20
        print(f'    "{vol.symbol}",')
    print("])")
    
    print("\n# Or use minimum ATR threshold:")
    print("min_atr_pct_for_pe: float = 2.0  # Only PE on stocks with ATR >= 2%")


if __name__ == "__main__":
    main()
