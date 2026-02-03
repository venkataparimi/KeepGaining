#!/usr/bin/env python3
"""
PDH/PDL Scalping with Quality Filters

Filters Applied:
1. Breakout Strength: >0.3% move to break PDH/PDL
2. Volume Confirmation: >1.5x average volume
3. Time Window: 9:30-10:30 AM (skip early noise)
4. Multiple Confirmations: All 3 must be true

Exit: 15% target, 15% stop, 15 minutes
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
class ScalpResult:
    pnl_amount: float
    pnl_pct: float
    exit_reason: str
    hold_minutes: int
    data_source: str
    breakout_strength: float
    volume_ratio: float


class FilteredScalper:
    # Quality Filters
    MIN_BREAKOUT_PCT = 0.3  # Minimum 0.3% break of PDH/PDL
    MIN_VOLUME_RATIO = 1.5  # Volume must be 1.5x average
    ENTRY_START = dt_time(4, 0)  # 9:30 AM IST (skip 9:20-9:30 noise)
    ENTRY_END = dt_time(5, 0)    # 10:30 AM IST
    
    # Exit Rules
    TARGET_PCT = 15.0
    STOPLOSS_PCT = 15.0
    MAX_HOLD_MINUTES = 15
    
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
        self.pool = None
        self.filtered_out = {'weak_breakout': 0, 'low_volume': 0, 'early_time': 0}
        self.option_trades = 0
        self.spot_fallback_trades = 0
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
        
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def get_fno_stocks(self) -> List[str]:
        """Get F&O stocks with available data"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT im.trading_symbol
                FROM instrument_master im
                WHERE im.instrument_type = 'EQUITY'
                  AND im.segment = 'EQ'
                  AND EXISTS (
                      SELECT 1 FROM candle_data cd 
                      WHERE cd.instrument_id = im.instrument_id
                  )
                ORDER BY im.trading_symbol
            """)
            return [row['trading_symbol'] for row in rows]
    
    async def get_pdh_pdl_with_stats(self, symbol: str, current_date: date) -> Optional[dict]:
        """Get PDH/PDL and volume statistics"""
        async with self.pool.acquire() as conn:
            prev_date = current_date - timedelta(days=1)
            while prev_date.weekday() >= 5:
                prev_date -= timedelta(days=1)
            
            result = await conn.fetchrow("""
                SELECT MAX(c.high) as pdh, 
                       MIN(c.low) as pdl,
                       AVG(c.volume) as avg_volume
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
            """, symbol, prev_date)
            
            if result and result['pdh']:
                return {
                    'pdh': float(result['pdh']), 
                    'pdl': float(result['pdl']),
                    'avg_volume': float(result['avg_volume']) if result['avg_volume'] else 0
                }
            return None
    
    async def scan_entries(self, symbol: str, trade_date: date) -> List[dict]:
        """Scan for HIGH-QUALITY breakout entries only"""
        async with self.pool.acquire() as conn:
            candles = await conn.fetch("""
                SELECT c.timestamp, c.open, c.high, c.low, c.close, c.volume
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp::time >= '04:00:00'  -- 9:30 IST (skip early noise)
                  AND c.timestamp::time <= '05:00:00'  -- 10:30 IST
                ORDER BY c.timestamp
            """, symbol, trade_date)
            
            if not candles or len(candles) < 5:
                return []
            
            pdh_pdl = await self.get_pdh_pdl_with_stats(symbol, trade_date)
            if not pdh_pdl:
                return []
            
            entries = []
            
            for i, candle in enumerate(candles):
                if i < 3:
                    continue
                
                high = float(candle['high'])
                low = float(candle['low'])
                current_price = float(candle['close'])
                volume = float(candle['volume'])
                candle_time = candle['timestamp'].time()
                
                # Calculate volume ratio
                volume_ratio = volume / pdh_pdl['avg_volume'] if pdh_pdl['avg_volume'] > 0 else 0
                
                # PDH Break
                if high > pdh_pdl['pdh']:
                    breakout_strength = ((high - pdh_pdl['pdh']) / pdh_pdl['pdh']) * 100
                    
                    # FILTERS
                    if breakout_strength < self.MIN_BREAKOUT_PCT:
                        self.filtered_out['weak_breakout'] += 1
                        continue
                    
                    if volume_ratio < self.MIN_VOLUME_RATIO:
                        self.filtered_out['low_volume'] += 1
                        continue
                    
                    if candle_time < self.ENTRY_START:
                        self.filtered_out['early_time'] += 1
                        continue
                    
                    # ALL FILTERS PASSED
                    if not any(e['signal'] == 'PDH_BREAK' for e in entries):
                        entries.append({
                            'time': candle['timestamp'],
                            'signal': 'PDH_BREAK',
                            'option_type': 'CE',
                            'spot_price': current_price,
                            'breakout_strength': breakout_strength,
                            'volume_ratio': volume_ratio
                        })
                
                # PDL Break
                if low < pdh_pdl['pdl']:
                    breakout_strength = ((pdh_pdl['pdl'] - low) / pdh_pdl['pdl']) * 100
                    
                    # FILTERS
                    if breakout_strength < self.MIN_BREAKOUT_PCT:
                        self.filtered_out['weak_breakout'] += 1
                        continue
                    
                    if volume_ratio < self.MIN_VOLUME_RATIO:
                        self.filtered_out['low_volume'] += 1
                        continue
                    
                    if candle_time < self.ENTRY_START:
                        self.filtered_out['early_time'] += 1
                        continue
                    
                    # ALL FILTERS PASSED
                    if not any(e['signal'] == 'PDL_BREAK' for e in entries):
                        entries.append({
                            'time': candle['timestamp'],
                            'signal': 'PDL_BREAK',
                            'option_type': 'PE',
                            'spot_price': current_price,
                            'breakout_strength': breakout_strength,
                            'volume_ratio': volume_ratio
                        })
            
            return entries
    
    async def execute_with_spot_fallback(self, symbol: str, entry: dict, trade_date: date) -> Optional[ScalpResult]:
        """Execute using spot price (most trades will use this)"""
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
            
            stop_premium = entry_spot * (1 - self.STOPLOSS_PCT / 100)
            target_premium = entry_spot * (1 + self.TARGET_PCT / 100)
            
            exit_spot = None
            exit_reason = None
            exit_time = None
            
            for candle in spot_candles[1:]:
                minutes_elapsed = (candle['timestamp'] - entry_time).total_seconds() / 60
                current_spot = float(candle['close'])
                
                # Estimate option P&L
                spot_move_pct = ((current_spot - entry_spot) / entry_spot) * 100
                
                if entry['option_type'] == 'CE':
                    estimated_pnl_pct = spot_move_pct * ATM_DELTA
                else:
                    estimated_pnl_pct = -spot_move_pct * ATM_DELTA
                
                # Check target
                if estimated_pnl_pct >= self.TARGET_PCT:
                    exit_spot = current_spot
                    exit_time = candle['timestamp']
                    exit_reason = f'Target ({self.TARGET_PCT}%)'
                    break
                
                # Check stop
                if estimated_pnl_pct <= -self.STOPLOSS_PCT:
                    exit_spot = current_spot
                    exit_time = candle['timestamp']
                    exit_reason = f'Stop ({self.STOPLOSS_PCT}%)'
                    break
                
                # Check time
                if minutes_elapsed >= self.MAX_HOLD_MINUTES:
                    exit_spot = current_spot
                    exit_time = candle['timestamp']
                    exit_reason = f'Time ({self.MAX_HOLD_MINUTES}min)'
                    break
            
            if not exit_spot:
                exit_spot = float(spot_candles[-1]['close'])
                exit_time = spot_candles[-1]['timestamp']
                exit_reason = 'EOD'
            
            # Calculate P&L
            spot_move_pct = ((exit_spot - entry_spot) / entry_spot) * 100
            
            if entry['option_type'] == 'CE':
                estimated_pnl_pct = spot_move_pct * ATM_DELTA
            else:
                estimated_pnl_pct = -spot_move_pct * ATM_DELTA
            
            estimated_entry_premium = entry_spot * 0.025
            estimated_pnl_per_lot = estimated_entry_premium * (estimated_pnl_pct / 100)
            
            lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
            pnl_amount = estimated_pnl_per_lot * lot_size
            hold_minutes = int((exit_time - entry_time).total_seconds() / 60)
            
            self.spot_fallback_trades += 1
            
            return ScalpResult(
                pnl_amount=pnl_amount,
                pnl_pct=estimated_pnl_pct,
                exit_reason=exit_reason,
                hold_minutes=hold_minutes,
                data_source='SPOT_ESTIMATE',
                breakout_strength=entry['breakout_strength'],
                volume_ratio=entry['volume_ratio']
            )
    
    async def backtest(self, start_date: date, end_date: date):
        """Run filtered backtest"""
        stocks = await self.get_fno_stocks()
        logger.info(f"Scanning {len(stocks)} F&O stocks with QUALITY FILTERS")
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        logger.info(f"Backtesting {len(dates)} trading days")
        
        all_results = []
        
        for trade_date in dates:
            day_trades = 0
            for symbol in stocks:
                entries = await self.scan_entries(symbol, trade_date)
                
                for entry in entries:
                    result = await self.execute_with_spot_fallback(symbol, entry, trade_date)
                    if result:
                        all_results.append(result)
                        day_trades += 1
            
            if day_trades > 0:
                logger.info(f"{trade_date}: {day_trades} quality scalps")
        
        self.print_results(all_results)
    
    def print_results(self, results: List[ScalpResult]):
        if not results:
            print("\nNo trades found")
            return
        
        winners = [r for r in results if r.pnl_pct > 0]
        total_pnl = sum(r.pnl_amount for r in results)
        
        print("\n" + "=" * 100)
        print("FILTERED PDH/PDL SCALPING RESULTS")
        print("=" * 100)
        print(f"\nFILTERS APPLIED:")
        print(f"  - Breakout Strength: >{self.MIN_BREAKOUT_PCT}%")
        print(f"  - Volume Ratio: >{self.MIN_VOLUME_RATIO}x average")
        print(f"  - Entry Window: 9:30 AM - 10:30 AM IST (no early noise)")
        print(f"\nFILTERED OUT:")
        print(f"  - Weak Breakouts (<{self.MIN_BREAKOUT_PCT}%): {self.filtered_out['weak_breakout']}")
        print(f"  - Low Volume (<{self.MIN_VOLUME_RATIO}x): {self.filtered_out['low_volume']}")
        print(f"  - Too Early (<9:30 AM): {self.filtered_out['early_time']}")
        print(f"  - Total Rejected: {sum(self.filtered_out.values())}")
        
        print(f"\n" + "=" * 100)
        print(f"PERFORMANCE:")
        print(f"  Total Trades: {len(results)}")
        print(f"  Winners: {len(winners)} ({len(winners)/len(results)*100:.1f}%)")
        print(f"  Total P&L: Rs {total_pnl:,.0f}")
        print(f"  Avg per Trade: Rs {total_pnl/len(results):,.0f}")
        print(f"  Avg Hold: {sum(r.hold_minutes for r in results)/len(results):.1f} minutes")
        print(f"  Avg Breakout Strength: {sum(r.breakout_strength for r in results)/len(results):.2f}%")
        print(f"  Avg Volume Ratio: {sum(r.volume_ratio for r in results)/len(results):.1f}x")
        print("=" * 100)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    scalper = FilteredScalper()
    await scalper.connect()
    
    try:
        await scalper.backtest(start, end)
    finally:
        await scalper.close()


if __name__ == "__main__":
    asyncio.run(main())
