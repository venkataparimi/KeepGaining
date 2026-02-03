#!/usr/bin/env python3
"""
Real-time Fibonacci R2 Breakout Scanner

Scans all F&O stocks during market hours for R2 breakouts
Alerts when price crosses above Fibonacci R2 with volume confirmation
"""

import asyncio
import asyncpg
from datetime import datetime, date, time as dt_time, timedelta
import pandas as pd
from typing import List, Dict
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

# Top liquid F&O stocks for scanning
SCAN_STOCKS = [
    'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'BAJFINANCE',
    'AXISBANK', 'KOTAKBANK', 'HINDUNILVR', 'ITC', 'LT', 'ASIANPAINT', 'MARUTI',
    'TITAN', 'BHARTIARTL', 'WIPRO', 'HCLTECH', 'TECHM', 'ULTRACEMCO', 'SUNPHARMA',
    'TATAMOTORS', 'TATASTEEL', 'HINDALCO', 'ADANIENT', 'ADANIPORTS', 'BAJAJ-AUTO',
    'INDUSINDBK', 'POWERGRID', 'NTPC', 'ONGC', 'COALINDIA', 'JSWSTEEL', 'GRASIM',
    'DRREDDY', 'CIPLA', 'DIVISLAB', 'EICHERMOT', 'HEROMOTOCO', 'BRITANNIA',
    'VEDL', 'HINDZINC', 'CANBK', 'BPCL', 'NATIONALUM'
]

class R2BreakoutScanner:
    MIN_VOLUME_RATIO = 3.0
    
    def __init__(self):
        self.pool = None
        self.alerted_stocks = set()  # Track already alerted stocks
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(DB_URL, min_size=5, max_size=10)
        
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    def calculate_fib_r2(self, prev_high: float, prev_low: float, prev_close: float) -> float:
        """Calculate Fibonacci R2 resistance"""
        pivot = (prev_high + prev_low + prev_close) / 3
        r2 = pivot + 0.618 * (prev_high - prev_low)
        return r2
    
    async def get_previous_day_data(self, symbol: str, current_date: date) -> Dict:
        """Get previous day's high, low, close"""
        async with self.pool.acquire() as conn:
            prev_date = current_date - timedelta(days=1)
            while prev_date.weekday() >= 5:
                prev_date -= timedelta(days=1)
            
            result = await conn.fetchrow("""
                SELECT 
                    MAX(c.high) as prev_high,
                    MIN(c.low) as prev_low,
                    (SELECT c2.close 
                     FROM candle_data c2
                     JOIN instrument_master im2 ON c2.instrument_id = im2.instrument_id
                     WHERE im2.trading_symbol = $1
                       AND im2.instrument_type = 'EQUITY'
                       AND DATE(c2.timestamp) = $2
                     ORDER BY c2.timestamp DESC
                     LIMIT 1) as prev_close
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
            """, symbol, prev_date)
            
            if result and result['prev_high']:
                return {
                    'prev_high': float(result['prev_high']),
                    'prev_low': float(result['prev_low']),
                    'prev_close': float(result['prev_close'])
                }
            return None
    
    async def get_current_price_and_volume(self, symbol: str, current_date: date) -> Dict:
        """Get latest price and volume data"""
        async with self.pool.acquire() as conn:
            # Get latest candle
            latest = await conn.fetchrow("""
                SELECT 
                    c.timestamp,
                    c.close as current_price,
                    c.volume as current_volume,
                    c.high,
                    c.low
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                ORDER BY c.timestamp DESC
                LIMIT 1
            """, symbol, current_date)
            
            if not latest:
                return None
            
            # Get average volume (last 5 days)
            avg_vol = await conn.fetchval("""
                SELECT AVG(daily_vol)
                FROM (
                    SELECT SUM(c.volume) as daily_vol
                    FROM candle_data c
                    JOIN instrument_master im ON c.instrument_id = im.instrument_id
                    WHERE im.trading_symbol = $1
                      AND im.instrument_type = 'EQUITY'
                      AND DATE(c.timestamp) < $2
                      AND DATE(c.timestamp) >= $2 - INTERVAL '5 days'
                    GROUP BY DATE(c.timestamp)
                ) sub
            """, symbol, current_date)
            
            if not avg_vol:
                return None
            
            avg_vol_per_candle = float(avg_vol) / 375  # 375 candles per day
            
            return {
                'timestamp': latest['timestamp'],
                'current_price': float(latest['current_price']),
                'current_volume': float(latest['current_volume']),
                'high': float(latest['high']),
                'low': float(latest['low']),
                'avg_volume': avg_vol_per_candle
            }
    
    async def scan_stock(self, symbol: str, current_date: date) -> Dict:
        """Scan single stock for R2 breakout"""
        
        # Skip if already alerted
        if symbol in self.alerted_stocks:
            return None
        
        # Get previous day data
        prev_data = await self.get_previous_day_data(symbol, current_date)
        if not prev_data:
            return None
        
        # Calculate Fib R2
        fib_r2 = self.calculate_fib_r2(
            prev_data['prev_high'],
            prev_data['prev_low'],
            prev_data['prev_close']
        )
        
        # Get current price and volume
        current_data = await self.get_current_price_and_volume(symbol, current_date)
        if not current_data:
            return None
        
        current_price = current_data['current_price']
        volume_ratio = current_data['current_volume'] / current_data['avg_volume']
        
        # Check for R2 breakout
        if current_price > fib_r2 and volume_ratio >= self.MIN_VOLUME_RATIO:
            # Mark as alerted
            self.alerted_stocks.add(symbol)
            
            return {
                'symbol': symbol,
                'timestamp': current_data['timestamp'],
                'current_price': current_price,
                'fib_r2': fib_r2,
                'breakout_pct': ((current_price - fib_r2) / fib_r2) * 100,
                'volume_ratio': volume_ratio,
                'prev_close': prev_data['prev_close'],
                'gap_pct': ((current_price - prev_data['prev_close']) / prev_data['prev_close']) * 100
            }
        
        return None
    
    async def scan_all_stocks(self, current_date: date) -> List[Dict]:
        """Scan all stocks for R2 breakouts"""
        tasks = [self.scan_stock(symbol, current_date) for symbol in SCAN_STOCKS]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]
    
    async def run_continuous_scan(self, scan_date: date = None):
        """Run continuous scanning during market hours"""
        if scan_date is None:
            scan_date = date.today()
        
        logger.info(f"Starting R2 Breakout Scanner for {scan_date}")
        logger.info(f"Scanning {len(SCAN_STOCKS)} stocks")
        logger.info(f"Criteria: Price > Fib R2 (0.618), Volume > {self.MIN_VOLUME_RATIO}x avg")
        logger.info("=" * 100)
        
        scan_count = 0
        
        while True:
            scan_count += 1
            logger.info(f"Scan #{scan_count} at {datetime.now().strftime('%H:%M:%S')}")
            
            breakouts = await self.scan_all_stocks(scan_date)
            
            if breakouts:
                for breakout in breakouts:
                    print("\n" + "🚨 " * 20)
                    print(f"R2 BREAKOUT ALERT: {breakout['symbol']}")
                    print("=" * 100)
                    print(f"Time: {breakout['timestamp'].strftime('%H:%M:%S')}")
                    print(f"Current Price: Rs {breakout['current_price']:.2f}")
                    print(f"Fibonacci R2: Rs {breakout['fib_r2']:.2f}")
                    print(f"Breakout: {breakout['breakout_pct']:+.2f}% above R2")
                    print(f"Gap from Prev Close: {breakout['gap_pct']:+.2f}%")
                    print(f"Volume: {breakout['volume_ratio']:.1f}x average")
                    print("=" * 100)
                    print("🚨 " * 20 + "\n")
            else:
                logger.info("No new R2 breakouts detected")
            
            # Wait 1 minute before next scan
            await asyncio.sleep(60)
    
    async def run_historical_scan(self, scan_date: date):
        """Run scan on historical date (for testing)"""
        logger.info(f"Historical R2 Breakout Scan for {scan_date}")
        logger.info("=" * 100)
        
        breakouts = await self.scan_all_stocks(scan_date)
        
        if not breakouts:
            print("\nNo R2 breakouts found on this date")
            return
        
        print(f"\nFound {len(breakouts)} R2 breakouts:\n")
        print(f"{'Symbol':<12} {'Time':<10} {'Price':<10} {'R2':<10} {'Breakout':<10} {'Gap':<10} {'Volume':<10}")
        print("=" * 100)
        
        for b in sorted(breakouts, key=lambda x: x['breakout_pct'], reverse=True):
            print(f"{b['symbol']:<12} "
                  f"{b['timestamp'].strftime('%H:%M'):<10} "
                  f"Rs {b['current_price']:<8.2f} "
                  f"Rs {b['fib_r2']:<8.2f} "
                  f"{b['breakout_pct']:+6.2f}% "
                  f"{b['gap_pct']:+6.2f}% "
                  f"{b['volume_ratio']:>6.1f}x")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fibonacci R2 Breakout Scanner')
    parser.add_argument('--mode', choices=['live', 'historical'], default='historical',
                       help='Live scanning or historical date scan')
    parser.add_argument('--date', type=str, help='Date for historical scan (YYYY-MM-DD)')
    args = parser.parse_args()
    
    scanner = R2BreakoutScanner()
    await scanner.connect()
    
    try:
        if args.mode == 'live':
            await scanner.run_continuous_scan()
        else:
            if args.date:
                scan_date = datetime.strptime(args.date, '%Y-%m-%d').date()
            else:
                scan_date = date.today()
            await scanner.run_historical_scan(scan_date)
    finally:
        await scanner.close()


if __name__ == "__main__":
    asyncio.run(main())
