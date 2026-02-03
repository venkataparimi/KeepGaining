#!/usr/bin/env python3
"""
PDH/PDL Scalping with Spot Fallback

When option data is unavailable due to liquidity, estimate P&L using spot price movement.
ATM options typically have ~0.5-0.6 delta, so we can approximate option P&L.
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

# Delta approximation for ATM options (how much option moves per 1% stock move)
ATM_DELTA = 0.55  # 55% sensitivity


@dataclass
class ScalpResult:
    pnl_amount: float
    pnl_pct: float
    exit_reason: str
    hold_minutes: int
    data_source: str  # 'OPTION' or 'SPOT_ESTIMATE'


class PDHPDLScalper:
    TARGET_PCT = 15.0
    STOPLOSS_PCT = 15.0
    MAX_HOLD_MINUTES = 15
    
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
        self.pool = None
        self.option_trades = 0
        self.spot_fallback_trades = 0
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
        
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def get_fno_stocks(self) -> List[str]:
        """Get F&O stocks with available data - SAME QUERY AS generate_strategy_trades.py"""
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
                  AND c.timestamp::time >= '03:50:00'  -- 9:20 IST
                  AND c.timestamp::time <= '05:00:00'  -- 10:30 IST
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
                
                # PDH Break
                if high > pdh_pdl['pdh'] and not any(e['signal'] == 'PDH_BREAK' for e in entries):
                    entries.append({
                        'time': candle['timestamp'],
                        'signal': 'PDH_BREAK',
                        'option_type': 'CE',
                        'spot_price': current_price
                    })
                
                # PDL Break
                if low < pdh_pdl['pdl'] and not any(e['signal'] == 'PDL_BREAK' for e in entries):
                    entries.append({
                        'time': candle['timestamp'],
                        'signal': 'PDL_BREAK',
                        'option_type': 'PE',
                        'spot_price': current_price
                    })
            
            return entries
    
    async def execute_with_option_data(self, symbol: str, entry: dict, trade_date: date) -> Optional[ScalpResult]:
        """Try to execute using actual option data first."""
        async with self.pool.acquire() as conn:
            spot_price = entry['spot_price']
            option_type = entry['option_type']
            
            if spot_price < 500:
                strike_step = 10
            elif spot_price < 1000:
                strike_step = 50
            elif spot_price < 5000:
                strike_step = 100
            else:
                strike_step = 500
            
            atm_strike = round(spot_price / strike_step) * strike_step
            
            option_candles = await conn.fetch("""
                SELECT c.timestamp, c.close
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                JOIN option_master om ON im.instrument_id = om.instrument_id
                WHERE im.underlying = $1
                  AND im.instrument_type = $2
                  AND om.strike_price = $3
                  AND om.expiry_date >= $4
                  AND DATE(c.timestamp) = $4
                  AND c.timestamp >= $5
                ORDER BY om.expiry_date, c.timestamp
                LIMIT 30
            """, symbol, option_type, atm_strike, trade_date, entry['time'])
            
            if not option_candles or len(option_candles) < 2:
                return None  # Will fall back to spot
            
            entry_premium = float(option_candles[0]['close'])
            if entry_premium <= 0:
                return None
            
            entry_time = option_candles[0]['timestamp']
            target_premium = entry_premium * (1 + self.TARGET_PCT / 100)
            stop_premium = entry_premium * (1 - self.STOPLOSS_PCT / 100)
            
            exit_premium = None
            exit_reason = None
            exit_time = None
            
            for candle in option_candles[1:]:
                minutes_elapsed = (candle['timestamp'] - entry_time).total_seconds() / 60
                current_premium = float(candle['close'])
                
                if current_premium >= target_premium:
                    exit_premium = current_premium
                    exit_time = candle['timestamp']
                    exit_reason = f'Target ({self.TARGET_PCT}%)'
                    break
                
                if current_premium <= stop_premium:
                    exit_premium = current_premium
                    exit_time = candle['timestamp']
                    exit_reason = f'Stop ({self.STOPLOSS_PCT}%)'
                    break
                
                if minutes_elapsed >= self.MAX_HOLD_MINUTES:
                    exit_premium = current_premium
                    exit_time = candle['timestamp']
                    exit_reason = f'Time ({self.MAX_HOLD_MINUTES}min)'
                    break
            
            if not exit_premium:
                exit_premium = float(option_candles[-1]['close'])
                exit_time = option_candles[-1]['timestamp']
                exit_reason = 'EOD'
            
            pnl_pct = ((exit_premium - entry_premium) / entry_premium) * 100
            lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
            pnl_amount = (exit_premium - entry_premium) * lot_size
            hold_minutes = int((exit_time - entry_time).total_seconds() / 60)
            
            self.option_trades += 1
            
            return ScalpResult(
                pnl_amount=pnl_amount,
                pnl_pct=pnl_pct,
                exit_reason=exit_reason,
                hold_minutes=hold_minutes,
                data_source='OPTION'
            )
    
    async def execute_with_spot_fallback(self, symbol: str, entry: dict, trade_date: date) -> Optional[ScalpResult]:
        """Fallback: Use spot price movement to estimate option P&L."""
        async with self.pool.acquire() as conn:
            # Get spot candles from entry time
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
            
            # Track for exit
            exit_spot = None
            exit_reason = None
            exit_time = None
            
            for candle in spot_candles[1:]:
                minutes_elapsed = (candle['timestamp'] - entry_time).total_seconds() / 60
                current_spot = float(candle['close'])
                
                # Calculate spot movement %
                spot_move_pct = ((current_spot - entry_spot) / entry_spot) * 100
                
                # Estimate option movement using delta
                # For CE: positive stock move = positive option move
                # For PE: negative stock move = positive option move
                if entry['option_type'] == 'CE':
                    estimated_option_pnl_pct = spot_move_pct * ATM_DELTA
                else:  # PE
                    estimated_option_pnl_pct = -spot_move_pct * ATM_DELTA
                
                # Check target
                if estimated_option_pnl_pct >= self.TARGET_PCT:
                    exit_spot = current_spot
                    exit_time = candle['timestamp']
                    exit_reason = f'Target ({self.TARGET_PCT}% est.)'
                    break
                
                # Check stop
                if estimated_option_pnl_pct <= -self.STOPLOSS_PCT:
                    exit_spot = current_spot
                    exit_time = candle['timestamp']
                    exit_reason = f'Stop ({self.STOPLOSS_PCT}% est.)'
                    break
                
                # Check time
                if minutes_elapsed >= self.MAX_HOLD_MINUTES:
                    exit_spot = current_spot
                    exit_time = candle['timestamp']
                    exit_reason = f'Time ({self.MAX_HOLD_MINUTES}min est.)'
                    break
            
            if not exit_spot:
                exit_spot = float(spot_candles[-1]['close'])
                exit_time = spot_candles[-1]['timestamp']
                exit_reason = 'EOD est.'
            
            # Calculate final P&L
            spot_move_pct = ((exit_spot - entry_spot) / entry_spot) * 100
            
            if entry['option_type'] == 'CE':
                estimated_pnl_pct = spot_move_pct * ATM_DELTA
            else:
                estimated_pnl_pct = -spot_move_pct * ATM_DELTA
            
            # Estimate premium based on typical ATM option value (5-10% of spot)
            estimated_entry_premium = entry_spot * 0.025  # 2.5% of spot as baseline
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
                data_source='SPOT_ESTIMATE'
            )
    
    async def execute_scalp(self, symbol: str, entry: dict, trade_date: date) -> Optional[ScalpResult]:
        """Try option data first, fall back to spot if unavailable."""
        result = await self.execute_with_option_data(symbol, entry, trade_date)
        
        if result:
            return result
        
        # Fallback to spot-based estimation
        return await self.execute_with_spot_fallback(symbol, entry, trade_date)
    
    async def backtest(self, start_date: date, end_date: date):
        stocks = await self.get_fno_stocks()
        logger.info(f"Scanning {len(stocks)} F&O stocks")
        
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
                    result = await self.execute_scalp(symbol, entry, trade_date)
                    if result:
                        all_results.append(result)
                        day_trades += 1
            
            if day_trades > 0:
                logger.info(f"{trade_date}: {day_trades} scalps")
        
        self.print_results(all_results)
    
    def print_results(self, results: List[ScalpResult]):
        if not results:
            print("\nNo trades found")
            return
        
        winners = [r for r in results if r.pnl_pct > 0]
        option_data = [r for r in results if r.data_source == 'OPTION']
        spot_data = [r for r in results if r.data_source == 'SPOT_ESTIMATE']
        
        total_pnl = sum(r.pnl_amount for r in results)
        
        print("\n" + "=" * 80)
        print("PDH/PDL SCALPING WITH SPOT FALLBACK")
        print("=" * 80)
        print(f"Total Trades: {len(results)}")
        print(f"  - Option Data: {len(option_data)} ({len(option_data)/len(results)*100:.1f}%)")
        print(f"  - Spot Estimate: {len(spot_data)} ({len(spot_data)/len(results)*100:.1f}%)")
        print(f"\nWinners: {len(winners)} ({len(winners)/len(results)*100:.1f}%)")
        print(f"Total P&L: Rs {total_pnl:,.0f}")
        print(f"Avg per Trade: Rs {total_pnl/len(results):,.0f}")
        print(f"Avg Hold: {sum(r.hold_minutes for r in results)/len(results):.1f} minutes")
        
        print("\n" + "=" * 80)
        print("COMPARISON: Option Data vs Spot Estimate")
        print("=" * 80)
        
        if option_data:
            opt_pnl = sum(r.pnl_amount for r in option_data)
            opt_winners = len([r for r in option_data if r.pnl_pct > 0])
            print(f"Option Data  : {len(option_data):3} trades | {opt_winners/len(option_data)*100:5.1f}% win | Rs {opt_pnl:+10,.0f}")
        
        if spot_data:
            spot_pnl = sum(r.pnl_amount for r in spot_data)
            spot_winners = len([r for r in spot_data if r.pnl_pct > 0])
            print(f"Spot Estimate: {len(spot_data):3} trades | {spot_winners/len(spot_data)*100:5.1f}% win | Rs {spot_pnl:+10,.0f}")
        
        print("=" * 80)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    scalper = PDHPDLScalper()
    await scalper.connect()
    
    try:
        await scalper.backtest(start, end)
    finally:
        await scalper.close()


if __name__ == "__main__":
    asyncio.run(main())
