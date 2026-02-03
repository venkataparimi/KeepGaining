#!/usr/bin/env python3
"""
Gap-and-Go FAST - Optimized Version

Top 50 liquid stocks only
Batched database queries
Should complete in 5-10 minutes
"""

import asyncio
import asyncpg
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from typing import List
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

# Top 50 most liquid F&O stocks only
TOP_STOCKS = [
    'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'BAJFINANCE',
    'AXISBANK', 'KOTAKBANK', 'HINDUNILVR', 'ITC', 'LT', 'ASIANPAINT', 'MARUTI',
    'TITAN', 'BHARTIARTL', 'WIPRO', 'HCLTECH', 'TECHM', 'ULTRACEMCO', 'SUNPHARMA',
    'TATAMOTORS', 'TATASTEEL', 'HINDALCO', 'ADANIENT', 'ADANIPORTS', 'BAJAJ-AUTO',
    'INDUSINDBK', 'POWERGRID', 'NTPC', 'ONGC', 'COALINDIA', 'JSWSTEEL', 'GRASIM',
    'DRREDDY', 'CIPLA', 'DIVISLAB', 'EICHERMOT', 'HEROMOTOCO', 'BRITANNIA',
    'NESTLEIND', 'DABUR', 'GODREJCP', 'VEDL', 'HINDZINC', 'CANBK', 'BPCL',
    'LAURUSLABS', 'NATIONALUM', 'IDEA'
]

LOT_SIZES = {
    'RELIANCE': 250, 'TCS': 150, 'INFY': 300, 'HDFCBANK': 550, 'ICICIBANK': 1375,
    'SBIN': 3000, 'BAJFINANCE': 125, 'AXISBANK': 1200, 'KOTAKBANK': 400,
    'HINDUNILVR': 300, 'ITC': 1600, 'LT': 300, 'ASIANPAINT': 400, 'MARUTI': 50,
    'TITAN': 575, 'BHARTIARTL': 1885, 'WIPRO': 1500, 'HCLTECH': 650, 'TECHM': 580,
    'ULTRACEMCO': 100, 'SUNPHARMA': 700, 'TATAMOTORS': 2400, 'TATASTEEL': 2400,
    'HINDALCO': 3250, 'ADANIENT': 500, 'ADANIPORTS': 1250, 'BAJAJ-AUTO': 125,
    'INDUSINDBK': 900, 'POWERGRID': 3200, 'NTPC': 4500, 'ONGC': 4500,
    'COALINDIA': 3500, 'JSWSTEEL': 1600, 'GRASIM': 400, 'DRREDDY': 125,
    'CIPLA': 700, 'DIVISLAB': 400, 'EICHERMOT': 250, 'HEROMOTOCO': 600,
    'BRITANNIA': 200, 'NESTLEIND': 50, 'DABUR': 1700, 'GODREJCP': 900,
    'VEDL': 3075, 'HINDZINC': 2400, 'CANBK': 6750, 'BPCL': 975,
    'LAURUSLABS': 1700, 'NATIONALUM': 1700, 'IDEA': 10000
}
DEFAULT_LOT_SIZE = 500
ATM_DELTA = 0.55
BROKERAGE = 55


@dataclass
class TradeResult:
    date: date
    symbol: str
    gap_pct: float
    pnl_amount: float
    pnl_pct: float
    exit_reason: str


class FastGapAndGo:
    MIN_GAP_PCT = 1.0
    TARGET_PCT = 100.0
    STOPLOSS_PCT = 40.0
    TRADES_PER_DAY = 2
    
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
        self.pool = None
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url, min_size=5, max_size=10)
        
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def scan_day(self, trade_date: date) -> List[TradeResult]:
        """Scan all stocks for ONE day and execute trades"""
        prev_date = trade_date - timedelta(days=1)
        while prev_date.weekday() >= 5:
            prev_date -= timedelta(days=1)
        
        async with self.pool.acquire() as conn:
            # Single query to get all data needed
            gaps = await conn.fetch("""
                WITH prev_close AS (
                    SELECT 
                        im.trading_symbol,
                        c.close as prev_close
                    FROM candle_data c
                    JOIN instrument_master im ON c.instrument_id = im.instrument_id
                    WHERE im.trading_symbol = ANY($1::text[])
                      AND im.instrument_type = 'EQUITY'
                      AND DATE(c.timestamp) = $2
                      AND c.timestamp::time = (
                          SELECT MAX(c2.timestamp::time)
                          FROM candle_data c2
                          JOIN instrument_master im2 ON c2.instrument_id = im2.instrument_id
                          WHERE im2.trading_symbol = im.trading_symbol
                            AND im2.instrument_type = 'EQUITY'
                            AND DATE(c2.timestamp) = $2
                      )
                ),
                first_candle AS (
                    SELECT 
                        im.trading_symbol,
                        c.open,
                        c.close,
                        c.volume
                    FROM candle_data c
                    JOIN instrument_master im ON c.instrument_id = im.instrument_id
                    WHERE im.trading_symbol = ANY($1::text[])
                      AND im.instrument_type = 'EQUITY'
                      AND DATE(c.timestamp) = $3
                      AND c.timestamp::time = '03:45:00'
                )
                SELECT 
                    fc.trading_symbol,
                    fc.open,
                    fc.close,
                    fc.volume,
                    pc.prev_close,
                    ((fc.open - pc.prev_close) / pc.prev_close * 100) as gap_pct
                FROM first_candle fc
                JOIN prev_close pc ON fc.trading_symbol = pc.trading_symbol
                WHERE ((fc.open - pc.prev_close) / pc.prev_close * 100) >= $4
                  AND fc.close > fc.open  -- Still above open (bullish)
                ORDER BY gap_pct DESC
                LIMIT $5
            """, TOP_STOCKS, prev_date, trade_date, self.MIN_GAP_PCT, self.TRADES_PER_DAY)
            
            if not gaps:
                return []
            
            results = []
            for gap in gaps:
                symbol = gap['trading_symbol']
                gap_pct = float(gap['gap_pct'])
                entry_spot = float(gap['close'])
                
                logger.info(f"{trade_date}: {symbol} gap {gap_pct:.1f}%")
                
                # Execute trade
                result = await self.execute_trade(conn, symbol, entry_spot, gap_pct, trade_date)
                if result:
                    results.append(result)
            
            return results
    
    async def execute_trade(self, conn, symbol: str, entry_spot: float, gap_pct: float, trade_date: date) -> TradeResult:
        """Execute single trade with simple spot-based P&L"""
        # Get intraday candles
        candles = await conn.fetch("""
            SELECT c.timestamp, c.close
            FROM candle_data c
            JOIN instrument_master im ON c.instrument_id = im.instrument_id  
            WHERE im.trading_symbol = $1
              AND im.instrument_type = 'EQUITY'
              AND DATE(c.timestamp) = $2
              AND c.timestamp::time >= '03:45:00'
              AND c.timestamp::time <= '09:00:00'
            ORDER BY c.timestamp
        """, symbol, trade_date)
        
        if not candles or len(candles) < 2:
            return None
        
        # Track movement
        max_gain_pct = 0
        exit_spot = float(candles[-1]['close'])
        exit_reason = 'EOD (2:30 PM)'
        
        for candle in candles[1:]:
            spot = float(candle['close'])
            spot_move = ((spot - entry_spot) / entry_spot) * 100
            option_pnl = spot_move * ATM_DELTA
            
            if option_pnl > max_gain_pct:
                max_gain_pct = option_pnl
            
            if option_pnl >= self.TARGET_PCT:
                exit_spot = spot
                exit_reason = 'Target (100%)'
                break
            
            if option_pnl <= -self.STOPLOSS_PCT:
                exit_spot = spot
                exit_reason = 'Stop (40%)'
                break
        
        # Calculate final P&L
        final_move = ((exit_spot - entry_spot) / entry_spot) * 100
        option_pnl = final_move * ATM_DELTA
        
        lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
        premium = entry_spot * 0.025
        pnl_amount = premium * (option_pnl / 100) * lot_size
        
        return TradeResult(
            date=trade_date,
            symbol=symbol,
            gap_pct=gap_pct,
            pnl_amount=pnl_amount,
            pnl_pct=option_pnl,
            exit_reason=exit_reason
        )
    
    async def backtest(self, start_date: date, end_date: date):
        logger.info(f"FAST GAP-AND-GO: Top {len(TOP_STOCKS)} stocks only")
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        all_results = []
        for trade_date in dates:
            day_results = await self.scan_day(trade_date)
            all_results.extend(day_results)
        
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
        print("FAST GAP-AND-GO RESULTS")
        print("=" * 100)
        
        print(f"\nSTRATEGY:")
        print(f"  - Top {len(TOP_STOCKS)} liquid stocks only")
        print(f"  - Gap >{self.MIN_GAP_PCT}%, still bullish at 9:15")
        print(f"  - Top {self.TRADES_PER_DAY} gaps daily")
        print(f"  - {self.TARGET_PCT}% target, {self.STOPLOSS_PCT}% stop")
        
        print(f"\n{'='*100}")
        print(f"PERFORMANCE:")
        print(f"  Total Trades: {len(results)}")
        print(f"  Winners: {len(winners)} ({len(winners)/len(results)*100:.1f}%)")
        print(f"  Gross P&L: Rs {gross_pnl:,.0f}")
        print(f"  Brokerage: Rs -{brokerage:,.0f}")
        print(f"  NET P&L: Rs {net_pnl:,.0f}")
        print(f"  Avg per Trade (NET): Rs {net_pnl/len(results):,.0f}")
        
        if winners:
            print(f"  Avg Win: Rs {sum(r.pnl_amount for r in winners)/len(winners):,.0f}")
        if len(results) > len(winners):
            losers = [r for r in results if r.pnl_pct <= 0]
            print(f"  Avg Loss: Rs {sum(r.pnl_amount for r in losers)/len(losers):,.0f}")
        
        targets = len([r for r in results if 'Target' in r.exit_reason])
        stops = len([r for r in results if 'Stop' in r.exit_reason])
        eods = len([r for r in results if 'EOD' in r.exit_reason])
        print(f"  Exits: {targets} targets, {stops} stops, {eods} EOD")
        
        print(f"\nTOP GAPS:")
        top_gaps = sorted(results, key=lambda x: x.gap_pct, reverse=True)[:5]
        for r in top_gaps:
            sign = "+" if r.pnl_amount > 0 else ""
            print(f"  {r.date} {r.symbol}: {r.gap_pct:.1f}% gap → {sign}Rs {r.pnl_amount:,.0f} ({r.exit_reason})")
        
        print("=" * 100)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    strategy = FastGapAndGo()
    await strategy.connect()
    
    try:
        await strategy.backtest(start, end)
    finally:
        await strategy.close()


if __name__ == "__main__":
    asyncio.run(main())
