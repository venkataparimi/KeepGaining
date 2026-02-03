#!/usr/bin/env python3
"""
Intraday R2 Breakout Scanner

Monitors stocks throughout the day for R2 breakouts
Not limited to gap-ups - catches breakouts anytime during market hours
"""

import asyncio
import asyncpg
from datetime import datetime, date, timedelta
from typing import List, Dict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

SCAN_STOCKS = [
    'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'BAJFINANCE',
    'AXISBANK', 'KOTAKBANK', 'HINDUNILVR', 'ITC', 'LT', 'ASIANPAINT', 'MARUTI',
    'TITAN', 'BHARTIARTL', 'WIPRO', 'HCLTECH', 'TECHM', 'ULTRACEMCO', 'SUNPHARMA',
    'TATAMOTORS', 'TATASTEEL', 'HINDALCO', 'ADANIENT', 'ADANIPORTS', 'BAJAJ-AUTO',
    'INDUSINDBK', 'POWERGRID', 'NTPC', 'ONGC', 'COALINDIA', 'JSWSTEEL', 'GRASIM',
    'DRREDDY', 'CIPLA', 'DIVISLAB', 'EICHERMOT', 'HEROMOTOCO', 'BRITANNIA',
    'VEDL', 'HINDZINC', 'CANBK', 'BPCL', 'NATIONALUM'
]

class IntradayR2Scanner:
    MIN_VOLUME_RATIO = 2.0  # Lower threshold for intraday
    
    def __init__(self):
        self.pool = None
        self.alerted_stocks = {}  # Track {symbol: timestamp} of alerts
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    def calculate_fib_r2(self, prev_high: float, prev_low: float, prev_close: float) -> float:
        pivot = (prev_high + prev_low + prev_close) / 3
        r2 = pivot + 0.618 * (prev_high - prev_low)
        return r2
    
    async def get_previous_day_data(self, symbol: str, current_date: date) -> Dict:
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
    
    async def check_intraday_breakout(self, symbol: str, current_date: date) -> Dict:
        """Check if stock has broken R2 during the day"""
        
        # Get previous day data
        prev_data = await self.get_previous_day_data(symbol, current_date)
        if not prev_data:
            return None
        
        # Calculate R2
        fib_r2 = self.calculate_fib_r2(
            prev_data['prev_high'],
            prev_data['prev_low'],
            prev_data['prev_close']
        )
        
        # Get today's candles
        async with self.pool.acquire() as conn:
            candles = await conn.fetch("""
                SELECT 
                    c.timestamp,
                    c.high,
                    c.close,
                    c.volume
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp::time >= '03:45:00'  -- 9:15 AM IST onwards
                ORDER BY c.timestamp
            """, symbol, current_date)
            
            if not candles:
                return None
            
            # Check each candle for R2 breakout
            for candle in candles:
                high = float(candle['high'])
                close = float(candle['close'])
                timestamp = candle['timestamp']
                
                # Check if high crossed R2 and close is above R2
                if high > fib_r2 and close > fib_r2:
                    # Check if already alerted for this stock
                    if symbol in self.alerted_stocks:
                        # Only alert again if it's been more than 30 minutes
                        last_alert = self.alerted_stocks[symbol]
                        if (timestamp - last_alert).total_seconds() < 1800:
                            continue
                    
                    # Calculate volume (need average)
                    avg_vol_result = await conn.fetchval("""
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
                    
                    if not avg_vol_result:
                        continue
                    
                    avg_vol_per_candle = float(avg_vol_result) / 375
                    volume_ratio = float(candle['volume']) / avg_vol_per_candle
                    
                    if volume_ratio >= self.MIN_VOLUME_RATIO:
                        # Mark as alerted
                        self.alerted_stocks[symbol] = timestamp
                        
                        return {
                            'symbol': symbol,
                            'timestamp': timestamp,
                            'current_price': close,
                            'fib_r2': fib_r2,
                            'breakout_pct': ((close - fib_r2) / fib_r2) * 100,
                            'volume_ratio': volume_ratio,
                            'prev_close': prev_data['prev_close']
                        }
        
        return None
    
    async def scan_all_stocks(self, current_date: date) -> List[Dict]:
        tasks = [self.check_intraday_breakout(symbol, current_date) for symbol in SCAN_STOCKS]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]
    
    async def run_continuous_scan(self, scan_date: date = None):
        if scan_date is None:
            scan_date = date.today()
        
        logger.info(f"Starting INTRADAY R2 Scanner for {scan_date}")
        logger.info(f"Monitoring {len(SCAN_STOCKS)} stocks for R2 breakouts")
        logger.info(f"Criteria: Price breaks above Fib R2, Volume > {self.MIN_VOLUME_RATIO}x avg")
        logger.info("=" * 100)
        
        scan_count = 0
        
        while True:
            scan_count += 1
            current_time = datetime.now().strftime('%H:%M:%S')
            logger.info(f"Scan #{scan_count} at {current_time}")
            
            breakouts = await self.scan_all_stocks(scan_date)
            
            if breakouts:
                for b in breakouts:
                    print("\n" + "=" * 100)
                    print(f"INTRADAY R2 BREAKOUT: {b['symbol']}")
                    print("=" * 100)
                    print(f"Time: {b['timestamp'].strftime('%H:%M:%S')}")
                    print(f"Price: Rs {b['current_price']:.2f}")
                    print(f"R2 Level: Rs {b['fib_r2']:.2f}")
                    print(f"Breakout: {b['breakout_pct']:+.2f}% above R2")
                    print(f"Volume: {b['volume_ratio']:.1f}x average")
                    print(f"Prev Close: Rs {b['prev_close']:.2f}")
                    print("=" * 100 + "\n")
            else:
                logger.info("No new breakouts")
            
            await asyncio.sleep(60)  # Scan every minute
    
    async def run_historical_scan(self, scan_date: date):
        logger.info(f"Historical Intraday R2 Scan for {scan_date}")
        logger.info("=" * 100)
        
        breakouts = await self.scan_all_stocks(scan_date)
        
        if not breakouts:
            print("\nNo intraday R2 breakouts found")
            return
        
        print(f"\nFound {len(breakouts)} intraday R2 breakouts:\n")
        print(f"{'Symbol':<12} {'Time':<10} {'Price':<10} {'R2':<10} {'Breakout':<10} {'Volume':<10}")
        print("=" * 100)
        
        for b in sorted(breakouts, key=lambda x: x['timestamp']):
            print(f"{b['symbol']:<12} "
                  f"{b['timestamp'].strftime('%H:%M'):<10} "
                  f"Rs {b['current_price']:<8.2f} "
                  f"Rs {b['fib_r2']:<8.2f} "
                  f"{b['breakout_pct']:+6.2f}% "
                  f"{b['volume_ratio']:>6.1f}x")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Intraday R2 Breakout Scanner')
    parser.add_argument('--mode', choices=['live', 'historical'], default='historical')
    parser.add_argument('--date', type=str, help='Date for historical scan (YYYY-MM-DD)')
    args = parser.parse_args()
    
    scanner = IntradayR2Scanner()
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
