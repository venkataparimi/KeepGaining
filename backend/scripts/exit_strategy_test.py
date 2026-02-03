#!/usr/bin/env python3
"""
Compare Exit Strategies:
1. FIXED 15%: Exit immediately at +15%
2. TRAIL FROM 15%: Lock 15%, then trail with 10% stop from peak
"""

import asyncio
import asyncpg
from datetime import datetime, date, time as dt_time, timedelta
from dataclasses import dataclass
from typing import List, Optional
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s', datefmt='%H:%M:%S')
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
    'VEDL': 3075, 'HINDZINC': 2400, 'ZEEL': 3900, 'PVR': 1125,
    'CANBK': 6750, 'HINDPETRO': 1575, 'BPCL': 975, 'ABCAPITAL': 5400,
    'LAURUSLABS': 1700, 'SIEMENS': 275, 'POLYCAB': 300, 'IREDA': 3075,
    'SBILIFE': 900, 'SHREECEM': 50, 'ADANIGREEN': 1925, 'ADANIPOWER': 7700,
}
DEFAULT_LOT_SIZE = 500
ATM_DELTA = 0.55


@dataclass
class TradeResult:
    pnl_amount: float
    pnl_pct: float
    exit_reason: str
    max_profit_reached: float


class ExitStrategyComparison:
    STOP_PCT = 15.0
    ACTIVATION_PCT = 15.0
    TRAIL_PCT = 10.0
    MAX_HOLD_MINUTES = 15
    
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
                  AND EXISTS (
                      SELECT 1 FROM instrument_master im2
                      WHERE im2.underlying = im.trading_symbol
                        AND im2.instrument_type IN ('CE', 'PE')
                  )
                ORDER BY im.trading_symbol
            """)
            return [row['trading_symbol'] for row in rows]
    
    async def get_pdh_pdl(self, symbol: str, current_date: date) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            prev_date = current_date - timedelta(days=1)
            while prev_date.weekday() >= 5:
                prev_date -= timedelta(days=1)
            
            result = await conn.fetchrow("""
                SELECT MAX(c.high) as pdh, MIN(c.low) as pdl
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
            """, symbol, prev_date)
            
            if result and result['pdh']:
                return {'pdh': float(result['pdh']), 'pdl': float(result['pdl'])}
            return None
    
    async def scan_entries(self, symbol: str, trade_date: date) -> List[dict]:
        async with self.pool.acquire() as conn:
            candles = await conn.fetch("""
                SELECT c.timestamp, c.open, c.high, c.low, c.close
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp::time >= '03:50:00'
                  AND c.timestamp::time <= '05:00:00'
                ORDER BY c.timestamp
            """, symbol, trade_date)
            
            if not candles or len(candles) < 5:
                return []
            
            pdh_pdl = await self.get_pdh_pdl(symbol, trade_date)
            if not pdh_pdl:
                return []
            
            entries = []
            
            for i, candle in enumerate(candles):
                if i < 3:
                    continue
                
                high = float(candle['high'])
                low = float(candle['low'])
                current_price = float(candle['close'])
                
                if high > pdh_pdl['pdh'] and not any(e['signal'] == 'PDH_BREAK' for e in entries):
                    entries.append({
                        'time': candle['timestamp'],
                        'signal': 'PDH_BREAK',
                        'option_type': 'CE',
                        'spot_price': current_price
                    })
                
                if low < pdh_pdl['pdl'] and not any(e['signal'] == 'PDL_BREAK' for e in entries):
                    entries.append({
                        'time': candle['timestamp'],
                        'signal': 'PDL_BREAK',
                        'option_type': 'PE',
                        'spot_price': current_price
                    })
            
            return entries
    
    async def execute_fixed_exit(self, symbol: str, entry: dict, trade_date: date) -> Optional[TradeResult]:
        """Strategy 1: Exit immediately at +15%"""
        async with self.pool.acquire() as conn:
            spot_candles = await conn.fetch("""
                SELECT c.timestamp, c.close
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp >= $3
                ORDER BY c.timestamp
                LIMIT 30
            """, symbol, trade_date, entry['time'])
            
            if not spot_candles or len(spot_candles) < 2:
                return None
            
            entry_spot = float(spot_candles[0]['close'])
            entry_time = spot_candles[0]['timestamp']
            
            max_profit = 0.0
            
            for candle in spot_candles[1:]:
                minutes_elapsed = (candle['timestamp'] - entry_time).total_seconds() / 60
                current_spot = float(candle['close'])
                
                spot_move_pct = ((current_spot - entry_spot) / entry_spot) * 100
                
                if entry['option_type'] == 'CE':
                    estimated_pnl_pct = spot_move_pct * ATM_DELTA
                else:
                    estimated_pnl_pct = -spot_move_pct * ATM_DELTA
                
                if estimated_pnl_pct > max_profit:
                    max_profit = estimated_pnl_pct
                
                # FIXED EXIT: Immediately exit at +15%
                if estimated_pnl_pct >= self.ACTIVATION_PCT:
                    lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
                    estimated_premium = entry_spot * 0.025
                    pnl_amount = estimated_premium * (estimated_pnl_pct / 100) * lot_size
                    
                    return TradeResult(
                        pnl_amount=pnl_amount,
                        pnl_pct=estimated_pnl_pct,
                        exit_reason='Fixed 15% Target',
                        max_profit_reached=max_profit
                    )
                
                # Stop loss
                if estimated_pnl_pct <= -self.STOP_PCT:
                    lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
                    estimated_premium = entry_spot * 0.025
                    pnl_amount = estimated_premium * (estimated_pnl_pct / 100) * lot_size
                    
                    return TradeResult(
                        pnl_amount=pnl_amount,
                        pnl_pct=estimated_pnl_pct,
                        exit_reason='Stop Loss',
                        max_profit_reached=max_profit
                    )
                
                # Time limit
                if minutes_elapsed >= self.MAX_HOLD_MINUTES:
                    lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
                    estimated_premium = entry_spot * 0.025
                    pnl_amount = estimated_premium * (estimated_pnl_pct / 100) * lot_size
                    
                    return TradeResult(
                        pnl_amount=pnl_amount,
                        pnl_pct=estimated_pnl_pct,
                        exit_reason='Time Stop',
                        max_profit_reached=max_profit
                    )
            
            return None
    
    async def execute_trailing_exit(self, symbol: str, entry: dict, trade_date: date) -> Optional[TradeResult]:
        """Strategy 2: Lock 15%, then trail from peak with 10% stop"""
        async with self.pool.acquire() as conn:
            spot_candles = await conn.fetch("""
                SELECT c.timestamp, c.close
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp >= $3
                ORDER BY c.timestamp
                LIMIT 30
            """, symbol, trade_date, entry['time'])
            
            if not spot_candles or len(spot_candles) < 2:
                return None
            
            entry_spot = float(spot_candles[0]['close'])
            entry_time = spot_candles[0]['timestamp']
            
            trailing_active = False
            trailing_stop_pct = None
            max_profit = 0.0
            
            for candle in spot_candles[1:]:
                minutes_elapsed = (candle['timestamp'] - entry_time).total_seconds() / 60
                current_spot = float(candle['close'])
                
                spot_move_pct = ((current_spot - entry_spot) / entry_spot) * 100
                
                if entry['option_type'] == 'CE':
                    estimated_pnl_pct = spot_move_pct * ATM_DELTA
                else:
                    estimated_pnl_pct = -spot_move_pct * ATM_DELTA
                
                if estimated_pnl_pct > max_profit:
                    max_profit = estimated_pnl_pct
                
                # Activate trailing once we hit +15%
                if not trailing_active and estimated_pnl_pct >= self.ACTIVATION_PCT:
                    trailing_active = True
                    trailing_stop_pct = estimated_pnl_pct - self.TRAIL_PCT
                
                # Update trailing stop as we make new highs
                if trailing_active:
                    if estimated_pnl_pct > (trailing_stop_pct + self.TRAIL_PCT):
                        trailing_stop_pct = estimated_pnl_pct - self.TRAIL_PCT
                    
                    # Hit trailing stop?
                    if estimated_pnl_pct <= trailing_stop_pct:
                        lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
                        estimated_premium = entry_spot * 0.025
                        pnl_amount = estimated_premium * (estimated_pnl_pct / 100) * lot_size
                        
                        return TradeResult(
                            pnl_amount=pnl_amount,
                            pnl_pct=estimated_pnl_pct,
                            exit_reason=f'Trail ({estimated_pnl_pct:.1f}%)',
                            max_profit_reached=max_profit
                        )
                
                # Stop loss
                if estimated_pnl_pct <= -self.STOP_PCT:
                    lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
                    estimated_premium = entry_spot * 0.025
                    pnl_amount = estimated_premium * (estimated_pnl_pct / 100) * lot_size
                    
                    return TradeResult(
                        pnl_amount=pnl_amount,
                        pnl_pct=estimated_pnl_pct,
                        exit_reason='Stop Loss',
                        max_profit_reached=max_profit
                    )
                
                # Time limit
                if minutes_elapsed >= self.MAX_HOLD_MINUTES:
                    lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
                    estimated_premium = entry_spot * 0.025
                    pnl_amount = estimated_premium * (estimated_pnl_pct / 100) * lot_size
                    
                    return TradeResult(
                        pnl_amount=pnl_amount,
                        pnl_pct=estimated_pnl_pct,
                        exit_reason='Time Stop',
                        max_profit_reached=max_profit
                    )
            
            return None
    
    async def run_comparison(self, start_date: date, end_date: date):
        stocks = await self.get_fno_stocks()
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        logger.info(f"Testing {len(stocks)} stocks on {len(dates)} days")
        
        fixed_results = []
        trailing_results = []
        
        for trade_date in dates:
            for symbol in stocks:
                entries = await self.scan_entries(symbol, trade_date)
                
                for entry in entries:
                    # Test both strategies on same entry
                    fixed = await self.execute_fixed_exit(symbol, entry, trade_date)
                    trailing = await self.execute_trailing_exit(symbol, entry, trade_date)
                    
                    if fixed:
                        fixed_results.append(fixed)
                    if trailing:
                        trailing_results.append(trailing)
        
        self.print_comparison(fixed_results, trailing_results)
    
    def print_comparison(self, fixed: List[TradeResult], trailing: List[TradeResult]):
        print("\n" + "=" * 100)
        print("EXIT STRATEGY COMPARISON")
        print("=" * 100)
        
        # Strategy 1: Fixed 15%
        if fixed:
            fixed_winners = [r for r in fixed if r.pnl_pct > 0]
            fixed_pnl = sum(r.pnl_amount for r in fixed)
            fixed_avg_profit = sum(r.max_profit_reached for r in fixed) / len(fixed)
            
            print(f"\n1. FIXED 15% EXIT:")
            print(f"   Trades: {len(fixed)}")
            print(f"   Win Rate: {len(fixed_winners)/len(fixed)*100:.1f}%")
            print(f"   Total P&L: Rs {fixed_pnl:,.0f}")
            print(f"   Avg per Trade: Rs {fixed_pnl/len(fixed):,.0f}")
            print(f"   Avg Max Profit Reached: {fixed_avg_profit:.1f}% (but exited at 15%)")
        
        # Strategy 2: Trail from 15%
        if trailing:
            trailing_winners = [r for r in trailing if r.pnl_pct > 0]
            trailing_pnl = sum(r.pnl_amount for r in trailing)
            trailing_avg_profit = sum(r.max_profit_reached for r in trailing) / len(trailing)
            trail_exits = [r for r in trailing if 'Trail' in r.exit_reason]
            
            print(f"\n2. TRAIL FROM 15% (10% trail):")
            print(f"   Trades: {len(trailing)}")
            print(f"   Win Rate: {len(trailing_winners)/len(trailing)*100:.1f}%")
            print(f"   Total P&L: Rs {trailing_pnl:,.0f}")
            print(f"   Avg per Trade: Rs {trailing_pnl/len(trailing):,.0f}")
            print(f"   Avg Max Profit Reached: {trailing_avg_profit:.1f}%")
            print(f"   Trailing Exits: {len(trail_exits)} ({len(trail_exits)/len(trailing)*100:.1f}%)")
        
        # Winner
        if fixed and trailing:
            print("\n" + "=" * 100)
            diff = trailing_pnl - fixed_pnl
            if diff > 0:
                print(f"WINNER: TRAIL FROM 15% (+Rs {diff:,.0f})")
            else:
                print(f"WINNER: FIXED 15% (+Rs {-diff:,.0f})")
            print("=" * 100)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    tester = ExitStrategyComparison()
    await tester.connect()
    
    try:
        await tester.run_comparison(start, end)
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
