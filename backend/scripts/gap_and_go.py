#!/usr/bin/env python3
"""
Gap-and-Go Strategy - First Minute Volume Surge

Entry (9:15 AM - First Candle):
1. Gap Up >1% (Open vs Previous Close)
2. Volume >2x average
3. Price > VWAP
4. Price > VWMA (Volume-weighted MA)

Take top 1-2 strongest gaps daily
100% target, 40% stop, hold till 2:30 PM
"""

import asyncio
import asyncpg
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from typing import List, Optional
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

LOT_SIZES = {
    'RELIANCE': 250, 'TCS': 150, 'INFY': 300, 'HDFCBANK': 550, 'ICICIBANK': 1375,
    'SBIN': 3000, 'BAJFINANCE': 125, 'AXISBANK': 1200, 'KOTAKBANK': 400,
    'HINDUNILVR': 300, 'ITC': 1600, 'LT': 300, 'ASIANPAINT': 400,
    'MARUTI': 50, 'TITAN': 575, 'BHARTIARTL': 1885, 'WIPRO': 1500,
    'HCLTECH': 650, 'TECHM': 580, 'ULTRACEMCO': 100, 'SUNPHARMA': 700,
    'TATAMOTORS': 2400, 'TATASTEEL': 2400, 'HINDALCO': 3250, 'ADANIENT': 500,
    'ADANIPORTS': 1250, 'BAJAJ-AUTO': 125, 'INDUSINDBK': 900, 'POWERGRID': 3200,
    'NTPC': 4500, 'ONGC': 4500, 'COALINDIA': 3500, 'JSWSTEEL': 1600,
    'GRASIM': 400, 'DRREDDY': 125, 'CIPLA': 700, 'DIVISLAB': 400,
    'EICHERMOT': 250, 'HEROMOTOCO': 600, 'BRITANNIA': 200, 'NESTLEIND': 50,
    'DABUR': 1700, 'GODREJCP': 900, 'MARICO': 3600, 'COLPAL': 1200,
    'VEDL': 3075, 'HINDZINC': 2400, 'CANBK': 6750, 'HINDPETRO': 1575,
    'BPCL': 975, 'ABCAPITAL': 5400, 'LAURUSLABS': 1700, 'SIEMENS': 275,
}
DEFAULT_LOT_SIZE = 500
ATM_DELTA = 0.55
BROKERAGE = 55


@dataclass
class GapSetup:
    symbol: str
    gap_pct: float
    first_candle_volume: float
    avg_volume: float
    volume_ratio: float
    open_price: float
    vwap: float
    vwma: float
    score: float


@dataclass
class TradeResult:
    symbol: str
    gap_pct: float
    volume_ratio: float
    pnl_amount: float
    pnl_pct: float
    exit_reason: str


class GapAndGo:
    MIN_GAP_PCT = 1.0
    MIN_VOLUME_RATIO = 2.0
    TARGET_PCT = 100.0  # 100% on options!
    STOPLOSS_PCT = 40.0
    TRADES_PER_DAY = 2
    
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
        self.pool = None
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
        
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def get_fno_stocks(self) -> List[str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT im.trading_symbol
                FROM instrument_master im
                WHERE im.instrument_type = 'EQUITY'
                  AND im.segment = 'EQ'
                  AND EXISTS (SELECT 1 FROM candle_data cd WHERE cd.instrument_id = im.instrument_id)
                ORDER BY im.trading_symbol
            """)
            return [row['trading_symbol'] for row in rows]
    
    async def scan_gap(self, symbol: str, trade_date: date) -> Optional[GapSetup]:
        """Check for gap up at market open (9:15 AM)"""
        async with self.pool.acquire() as conn:
            # Get previous close
            prev_date = trade_date - timedelta(days=1)
            while prev_date.weekday() >= 5:
                prev_date -= timedelta(days=1)
            
            prev_close = await conn.fetchval("""
                SELECT c.close
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                ORDER BY c.timestamp DESC
                LIMIT 1
            """, symbol, prev_date)
            
            if not prev_close:
                return None
            
            prev_close = float(prev_close)
            
            # Get average volume (last 5 days)
            avg_volume = await conn.fetchval("""
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
            """, symbol, trade_date)
            
            if not avg_volume:
                return None
            
            avg_volume = float(avg_volume)
            
            # Get first candle (9:15 AM)
            first_candle = await conn.fetchrow("""
                SELECT c.timestamp, c.open, c.high, c.low, c.close, c.volume
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp::time = '03:45:00'  -- 9:15 IST
            """, symbol, trade_date)
            
            if not first_candle:
                return None
            
            open_price = float(first_candle['open'])
            close_price = float(first_candle['close'])
            volume = float(first_candle['volume'])
            
            # Calculate gap
            gap_pct = ((open_price - prev_close) / prev_close) * 100
            
            if gap_pct < self.MIN_GAP_PCT:
                return None
            
            # Calculate volume ratio
            volume_ratio = volume / (avg_volume / 375) if avg_volume > 0 else 0  # 375 candles per day
            
            if volume_ratio < self.MIN_VOLUME_RATIO:
                return None
            
            # Get first 5 candles for VWAP/VWMA
            candles = await conn.fetch("""
                SELECT c.high, c.low, c.close, c.volume
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp::time >= '03:45:00'
                  AND c.timestamp::time <= '03:49:00'  -- First 5 minutes
                ORDER BY c.timestamp
            """, symbol, trade_date)
            
            if not candles:
                return None
            
            # Calculate VWAP
            total_pv = sum(((float(c['high']) + float(c['low']) + float(c['close'])) / 3) * float(c['volume']) for c in candles)
            total_volume = sum(float(c['volume']) for c in candles)
            vwap = total_pv / total_volume if total_volume > 0 else 0
            
            # Calculate VWMA (simple volume-weighted average)
            vwma = sum(float(c['close']) * float(c['volume']) for c in candles) / total_volume if total_volume > 0 else 0
            
            # Check if price above VWAP and VWMA
            if close_price < vwap or close_price < vwma:
                return None
            
            # Score the setup
            score = 0
            score += min(gap_pct * 10, 30)  # Gap strength (max 30)
            score += min(volume_ratio * 10, 40)  # Volume surge (max 40)
            score += 15 if close_price > vwap else 0  # Above VWAP
            score += 15 if close_price > vwma else 0  # Above VWMA
            
            return GapSetup(
                symbol=symbol,
                gap_pct=gap_pct,
                first_candle_volume=volume,
                avg_volume=avg_volume,
                volume_ratio=volume_ratio,
                open_price=open_price,
                vwap=vwap,
                vwma=vwma,
                score=score
            )
    
    async def execute_trade(self, setup: GapSetup, trade_date: date) -> Optional[TradeResult]:
        """Execute gap trade with 100% target"""
        async with self.pool.acquire() as conn:
            # Get candles from 9:15 onwards
            candles = await conn.fetch("""
                SELECT c.timestamp, c.close
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp::time >= '03:45:00'  -- 9:15 IST
                  AND c.timestamp::time <= '09:00:00'  -- 2:30 PM IST
                ORDER BY c.timestamp
            """, setup.symbol, trade_date)
            
            if not candles or len(candles) < 2:
                return None
            
            entry_spot = float(candles[0]['close'])
            entry_time = candles[0]['timestamp']
            
            for candle in candles[1:]:
                spot = float(candle['close'])
                spot_move = ((spot - entry_spot) / entry_spot) * 100
                option_pnl = spot_move * ATM_DELTA  # CE only for gap ups
                
                # Check 100% target!
                if option_pnl >= self.TARGET_PCT:
                    lot_size = LOT_SIZES.get(setup.symbol, DEFAULT_LOT_SIZE)
                    premium = entry_spot * 0.025
                    pnl_amount = premium * (option_pnl / 100) * lot_size
                    
                    return TradeResult(
                        symbol=setup.symbol,
                        gap_pct=setup.gap_pct,
                        volume_ratio=setup.volume_ratio,
                        pnl_amount=pnl_amount,
                        pnl_pct=option_pnl,
                        exit_reason='Target (100%)'
                    )
                
                # Check stop
                if option_pnl <= -self.STOPLOSS_PCT:
                    lot_size = LOT_SIZES.get(setup.symbol, DEFAULT_LOT_SIZE)
                    premium = entry_spot * 0.025
                    pnl_amount = premium * (option_pnl / 100) * lot_size
                    
                    return TradeResult(
                        symbol=setup.symbol,
                        gap_pct=setup.gap_pct,
                        volume_ratio=setup.volume_ratio,
                        pnl_amount=pnl_amount,
                        pnl_pct=option_pnl,
                        exit_reason='Stop (40%)'
                    )
            
            # EOD exit (2:30 PM)
            final_spot = float(candles[-1]['close'])
            spot_move = ((final_spot - entry_spot) / entry_spot) * 100
            option_pnl = spot_move * ATM_DELTA
            
            lot_size = LOT_SIZES.get(setup.symbol, DEFAULT_LOT_SIZE)
            premium = entry_spot * 0.025
            pnl_amount = premium * (option_pnl / 100) * lot_size
            
            return TradeResult(
                symbol=setup.symbol,
                gap_pct=setup.gap_pct,
                volume_ratio=setup.volume_ratio,
                pnl_amount=pnl_amount,
                pnl_pct=option_pnl,
                exit_reason='EOD (2:30 PM)'
            )
    
    async def backtest(self, start_date: date, end_date: date):
        stocks = await self.get_fno_stocks()
        logger.info(f"GAP-AND-GO: Scanning {len(stocks)} stocks for gap ups")
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        all_results = []
        
        for trade_date in dates:
            # Scan all stocks for gaps
            day_gaps = []
            for symbol in stocks:
                gap = await self.scan_gap(symbol, trade_date)
                if gap:
                    day_gaps.append(gap)
            
            # Take top 2 strongest gaps
            day_gaps.sort(key=lambda x: x.score, reverse=True)
            top_gaps = day_gaps[:self.TRADES_PER_DAY]
            
            # Execute trades
            for gap in top_gaps:
                result = await self.execute_trade(gap, trade_date)
                if result:
                    all_results.append(result)
            
            if top_gaps:
                logger.info(f"{trade_date}: {len(top_gaps)} gaps - " + 
                          ", ".join([f"{g.symbol} ({g.gap_pct:.1f}%, {g.volume_ratio:.1f}x vol)" for g in top_gaps]))
        
        self.print_results(all_results)
    
    def print_results(self, results: List[TradeResult]):
        if not results:
            print("\nNo gap trades found")
            return
        
        winners = [r for r in results if r.pnl_pct > 0]
        gross_pnl = sum(r.pnl_amount for r in results)
        brokerage = len(results) * BROKERAGE
        net_pnl = gross_pnl - brokerage
        
        print("\n" + "=" * 100)
        print("GAP-AND-GO RESULTS")
        print("=" * 100)
        print(f"\nSTRATEGY:")
        print(f"  - Gap Up >{self.MIN_GAP_PCT}% at open")
        print(f"  - Volume >{self.MIN_VOLUME_RATIO}x average (first candle)")
        print(f"  - Price > VWAP & VWMA")
        print(f"  - Top {self.TRADES_PER_DAY} gaps daily")
        print(f"  - {self.TARGET_PCT}% target, {self.STOPLOSS_PCT}% stop")
        
        print(f"\n" + "=" * 100)
        print(f"PERFORMANCE:")
        print(f"  Total Trades: {len(results)}")
        print(f"  Winners: {len(winners)} ({len(winners)/len(results)*100:.1f}%)")
        print(f"  Gross P&L: Rs {gross_pnl:,.0f}")
        print(f"  Brokerage: Rs -{brokerage:,.0f}")
        print(f"  NET P&L: Rs {net_pnl:,.0f}")
        print(f"  Avg per Trade (NET): Rs {net_pnl/len(results):,.0f}")
        print(f"  Avg Gap: {sum(r.gap_pct for r in results)/len(results):.1f}%")
        print(f"  Avg Volume Ratio: {sum(r.volume_ratio for r in results)/len(results):.1f}x")
        
        if winners:
            print(f"  Avg Win: Rs {sum(r.pnl_amount for r in winners)/len(winners):,.0f}")
        if len(results) > len(winners):
            losers = [r for r in results if r.pnl_pct <= 0]
            print(f"  Avg Loss: Rs {sum(r.pnl_amount for r in losers)/len(losers):,.0f}")
        
        # Exit breakdown
        targets = len([r for r in results if 'Target' in r.exit_reason])
        stops = len([r for r in results if 'Stop' in r.exit_reason])
        eods = len([r for r in results if 'EOD' in r.exit_reason])
        print(f"\n  Exits: {targets} targets, {stops} stops, {eods} EOD")
        print("=" * 100)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    strategy = GapAndGo()
    await strategy.connect()
    
    try:
        await strategy.backtest(start, end)
    finally:
        await strategy.close()


if __name__ == "__main__":
    asyncio.run(main())
