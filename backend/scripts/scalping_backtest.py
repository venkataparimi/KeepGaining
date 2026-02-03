#!/usr/bin/env python3
"""
Scalping Strategy Backtest - Quick In/Out with PDH/PDL Breakout

Entry Signals:
- PDH Break: Buy CE when price breaks previous day high
- PDL Break: Buy PE when price breaks previous day low
- Momentum: >0.5% move in 15 minutes (fallback)

Entry Window: 9:20 AM - 10:30 AM
Exit: 15% Target OR 15% Stop OR 15 Minutes (whichever first)
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

# F&O Lot Sizes (for P&L calculation)
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


@dataclass
class ScalpTrade:
    symbol: str
    option_type: str
    strike_price: int
    trade_date: date
    entry_time: datetime
    exit_time: datetime
    entry_premium: float
    exit_premium: float
    entry_signal: str  # 'PDH_BREAK', 'PDL_BREAK', 'MOMENTUM'
    exit_reason: str
    hold_minutes: int
    pnl_pct: float
    pnl_amount: float
    spot_at_entry: float
    spot_at_exit: float


class ScalpingBacktest:
    # Scalping parameters
    TARGET_PCT = 15.0
    STOPLOSS_PCT = 15.0
    MAX_HOLD_MINUTES = 15
    MOMENTUM_THRESHOLD = 0.5
    
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
        self.pool = None
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
        logger.info("Connected to database")
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def get_fno_stocks(self) -> List[str]:
        """Get F&O stocks with available data."""
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
                  AND EXISTS (
                      SELECT 1 FROM candle_data cd 
                      WHERE cd.instrument_id = im.instrument_id
                  )
                ORDER BY im.trading_symbol
            """)
            return [row['trading_symbol'] for row in rows]
    
    async def get_previous_day_levels(self, symbol: str, current_date: date) -> Optional[dict]:
        """Get PDH/PDL from previous trading day."""
        async with self.pool.acquire() as conn:
            # Find previous trading day (not weekend)
            prev_date = current_date - timedelta(days=1)
            while prev_date.weekday() >= 5:  # Skip weekends
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
    
    async def scan_for_entries(self, symbol: str, trade_date: date) -> List[dict]:
        """Scan for scalping entry opportunities between 9:20 AM and 10:30 AM."""
        async with self.pool.acquire() as conn:
            # Get equity candles
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
            
            pdh_pdl = await self.get_previous_day_levels(symbol, trade_date)
            if not pdh_pdl:
                return []
            
            day_open = float(candles[0]['open'])
            entries = []
            
            for i, candle in enumerate(candles):
                if i < 3:  # Need at least 3 candles for momentum check
                    continue
                
                current_price = float(candle['close'])
                high = float(candle['high'])
                low = float(candle['low'])
                
                # Check PDH breakout (bullish)
                if high > pdh_pdl['pdh'] and not any(e['signal'] == 'PDH_BREAK' for e in entries):
                    entries.append({
                        'time': candle['timestamp'],
                        'signal': 'PDH_BREAK',
                        'option_type': 'CE',
                        'spot_price': current_price,
                        'reason': f"Broke PDH {pdh_pdl['pdh']:.2f}"
                    })
                
                # Check PDL breakout (bearish)
                if low < pdh_pdl['pdl'] and not any(e['signal'] == 'PDL_BREAK' for e in entries):
                    entries.append({
                        'time': candle['timestamp'],
                        'signal': 'PDL_BREAK',
                        'option_type': 'PE',
                        'spot_price': current_price,
                        'reason': f"Broke PDL {pdh_pdl['pdl']:.2f}"
                    })
                
                # Check momentum (every 15 minutes max 1 signal)
                if i >= 15 and i % 15 == 0:  # Every 15 candles (15 min)
                    momentum_start = float(candles[i-15]['close'])
                    momentum_pct = ((current_price - momentum_start) / momentum_start) * 100
                    
                    if abs(momentum_pct) >= self.MOMENTUM_THRESHOLD:
                        signal_type = 'CE' if momentum_pct > 0 else 'PE'
                        entries.append({
                            'time': candle['timestamp'],
                            'signal': 'MOMENTUM',
                            'option_type': signal_type,
                            'spot_price': current_price,
                            'reason': f"Momentum {momentum_pct:+.2f}%"
                        })
            
            return entries
    
    async def execute_scalp(self, symbol: str, entry_signal: dict, trade_date: date) -> Optional[ScalpTrade]:
        """Execute a scalping trade with 15% target/stop and 15-minute timer."""
        async with self.pool.acquire() as conn:
            # Find ATM option
            spot_price = entry_signal['spot_price']
            option_type = entry_signal['option_type']
            
            if spot_price < 500:
                strike_step = 10
            elif spot_price < 1000:
                strike_step = 50
            elif spot_price < 5000:
                strike_step = 100
            else:
                strike_step = 500
            
            atm_strike = round(spot_price / strike_step) * strike_step
            
            # Get option candles from entry time onwards
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
                LIMIT 30  -- Max 30 minutes of data
            """, symbol, option_type, atm_strike, trade_date, entry_signal['time'])
            
            if not option_candles or len(option_candles) < 2:
                return None
            
            entry_premium = float(option_candles[0]['close'])
            if entry_premium <= 0:
                return None
            
            entry_time = option_candles[0]['timestamp']
            target_premium = entry_premium * (1 + self.TARGET_PCT / 100)
            stop_premium = entry_premium * (1 - self.STOPLOSS_PCT / 100)
            
            # Scan for exit
            exit_premium = None
            exit_time = None
            exit_reason = None
            
            for candle in option_candles[1:]:
                minutes_elapsed = (candle['timestamp'] - entry_time).total_seconds() / 60
                current_premium = float(candle['close'])
                
                # Check target
                if current_premium >= target_premium:
                    exit_premium = current_premium
                    exit_time = candle['timestamp']
                    exit_reason = f'Target ({self.TARGET_PCT}%)'
                    break
                
                # Check stop
                if current_premium <= stop_premium:
                    exit_premium = current_premium
                    exit_time = candle['timestamp']
                    exit_reason = f'Stop ({self.STOPLOSS_PCT}%)'
                    break
                
                # Check time limit
                if minutes_elapsed >= self.MAX_HOLD_MINUTES:
                    exit_premium = current_premium
                    exit_time = candle['timestamp']
                    exit_reason = f'Time Stop ({self.MAX_HOLD_MINUTES}min)'
                    break
            
            # If no exit, use last candle
            if not exit_premium:
                exit_premium = float(option_candles[-1]['close'])
                exit_time = option_candles[-1]['timestamp']
                exit_reason = 'End of Data'
            
            # Calculate P&L
            pnl_pct = ((exit_premium - entry_premium) / entry_premium) * 100
            lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
            pnl_amount = (exit_premium - entry_premium) * lot_size
            hold_minutes = int((exit_time - entry_time).total_seconds() / 60)
            
            return ScalpTrade(
                symbol=symbol,
                option_type=option_type,
                strike_price=atm_strike,
                trade_date=trade_date,
                entry_time=entry_time,
                exit_time=exit_time,
                entry_premium=entry_premium,
                exit_premium=exit_premium,
                entry_signal=entry_signal['signal'],
                exit_reason=exit_reason,
                hold_minutes=hold_minutes,
                pnl_pct=pnl_pct,
                pnl_amount=pnl_amount,
                spot_at_entry=spot_price,
                spot_at_exit=spot_price  # Simplified
            )
    
    async def backtest(self, start_date: date, end_date: date):
        """Run scalping backtest."""
        stocks = await self.get_fno_stocks()
        logger.info(f"Scanning {len(stocks)} F&O stocks")
        
        # Get trading days
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        logger.info(f"Backtesting {len(dates)} trading days")
        
        all_trades = []
        
        for trade_date in dates:
            day_trades = 0
            for symbol in stocks:
                entries = await self.scan_for_entries(symbol, trade_date)
                
                for entry in entries:
                    trade = await self.execute_scalp(symbol, entry, trade_date)
                    if trade:
                        all_trades.append(trade)
                        day_trades += 1
            
            if day_trades > 0:
                logger.info(f"{trade_date}: {day_trades} scalps")
        
        # Print results
        self.print_results(all_trades)
    
    def print_results(self, trades: List[ScalpTrade]):
        """Print backtest results."""
        if not trades:
            print("\n❌ No trades found")
            return
        
        winners = [t for t in trades if t.pnl_pct > 0]
        total_pnl = sum(t.pnl_amount for t in trades)
        total_pnl_pct = sum(t.pnl_pct for t in trades)
        avg_hold = sum(t.hold_minutes for t in trades) / len(trades)
        
        print("\n" + "=" * 80)
        print("SCALPING BACKTEST RESULTS")
        print("=" * 80)
        print(f"Total Trades: {len(trades)}")
        print(f"Winners: {len(winners)} ({len(winners)/len(trades)*100:.1f}%)")
        print(f"Total P&L: Rs {total_pnl:,.0f}")
        print(f"Total P&L %: {total_pnl_pct:+.1f}%")
        print(f"Avg Trade: {total_pnl_pct/len(trades):+.1f}%")
        print(f"Avg Hold Time: {avg_hold:.1f} minutes")
        
        # Breakdown by entry signal
        print("\n" + "=" * 80)
        print("BY ENTRY SIGNAL:")
        for signal_type in ['PDH_BREAK', 'PDL_BREAK', 'MOMENTUM']:
            signal_trades = [t for t in trades if t.entry_signal == signal_type]
            if signal_trades:
                signal_winners = [t for t in signal_trades if t.pnl_pct > 0]
                signal_pnl = sum(t.pnl_amount for t in signal_trades)
                print(f"  {signal_type:12} | {len(signal_trades):3} trades | {len(signal_winners)/len(signal_trades)*100:5.1f}% win | Rs {signal_pnl:+10,.0f}")
        
        # Breakdown by exit reason
        print("\n" + "=" * 80)
        print("BY EXIT REASON:")
        for exit_type in [f'Target ({self.TARGET_PCT}%)', f'Stop ({self.STOPLOSS_PCT}%)', f'Time Stop ({self.MAX_HOLD_MINUTES}min)']:
            exit_trades = [t for t in trades if t.exit_reason == exit_type]
            if exit_trades:
                exit_pnl = sum(t.pnl_amount for t in exit_trades)
                print(f"  {exit_type:20} | {len(exit_trades):3} trades | Rs {exit_pnl:+10,.0f}")
        print("=" * 80)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end', type=str, required=True, help='End date YYYY-MM-DD')
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    backtester = ScalpingBacktest()
    await backtester.connect()
    
    try:
        await backtester.backtest(start, end)
    finally:
        await backtester.close()


if __name__ == "__main__":
    asyncio.run(main())
