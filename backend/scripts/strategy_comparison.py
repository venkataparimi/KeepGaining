#!/usr/bin/env python3
"""
Multi-Strategy Scalping Comparison

Tests 4 variations:
1. BASE: Current (PDH/PDL + Momentum, 15% target/stop, 15min)
2. PDH_PDL_ONLY: Remove momentum signals
3. SMART_EXIT: 10% stop, 15% partial, 25% trail
4. VOLUME_FILTER: Add volume confirmation
5. OPTIMIZED: PDH/PDL only + Smart Exit + Volume
"""

import asyncio
import asyncpg
from datetime import datetime, date, time as dt_time, timedelta
from dataclasses import dataclass
from typing import List, Optional, Dict
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


@dataclass
class StrategyConfig:
    name: str
    use_pdh_pdl: bool = True
    use_momentum: bool = True
    require_volume: bool = False
    volume_multiplier: float = 1.5
    stop_loss_pct: float = 15.0
    first_target_pct: float = 15.0
    final_target_pct: float = 15.0
    use_trailing: bool = False
    trailing_activation_pct: float = 15.0
    trailing_stop_pct: float = 10.0
    max_hold_minutes: int = 15


@dataclass  
class ScalpResult:
    pnl_amount: float
    pnl_pct: float
    exit_reason: str
    hold_minutes: int


class MultiStrategyBacktest:
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
    
    async def get_avg_volume(self, symbol: str, current_date: date) -> float:
        """Get 5-day average volume."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT AVG(daily_vol) as avg_vol
                FROM (
                    SELECT DATE(c.timestamp) as day, SUM(c.volume) as daily_vol
                    FROM candle_data c
                    JOIN instrument_master im ON c.instrument_id = im.instrument_id
                    WHERE im.trading_symbol = $1
                      AND im.instrument_type = 'EQUITY'
                      AND DATE(c.timestamp) < $2
                      AND DATE(c.timestamp) >= $2 - INTERVAL '5 days'
                    GROUP BY DATE(c.timestamp)
                ) sub
            """, symbol, current_date)
            
            return float(result['avg_vol']) if result and result['avg_vol'] else 0
    
    async def scan_entries(self, symbol: str, trade_date: date, config: StrategyConfig) -> List[dict]:
        async with self.pool.acquire() as conn:
            candles = await conn.fetch("""
                SELECT c.timestamp, c.open, c.high, c.low, c.close, c.volume
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
            
            avg_volume = None
            if config.require_volume:
                avg_volume = await self.get_avg_volume(symbol, trade_date)
                if avg_volume == 0:
                    return []
            
            entries = []
            day_open = float(candles[0]['open'])
            
            for i, candle in enumerate(candles):
                if i < 3:
                    continue
                
                current_price = float(candle['close'])
                high = float(candle['high'])
                low = float(candle['low'])
                volume = float(candle['volume'])
                
                # Volume check
                volume_ok = True
                if config.require_volume and avg_volume > 0:
                    # Check if cumulative volume so far is above average
                    cum_volume = sum(float(c['volume']) for c in candles[:i+1])
                    expected_volume = (avg_volume / 375) * (i + 1)  # 375 = total candles in day
                    volume_ok = cum_volume >= expected_volume * config.volume_multiplier
                
                # PDH Break
                if config.use_pdh_pdl and high > pdh_pdl['pdh']:
                    if not any(e['signal'] == 'PDH_BREAK' for e in entries):
                        if volume_ok:
                            entries.append({
                                'time': candle['timestamp'],
                                'signal': 'PDH_BREAK',
                                'option_type': 'CE',
                                'spot_price': current_price
                            })
                
                # PDL Break
                if config.use_pdh_pdl and low < pdh_pdl['pdl']:
                    if not any(e['signal'] == 'PDL_BREAK' for e in entries):
                        if volume_ok:
                            entries.append({
                                'time': candle['timestamp'],
                                'signal': 'PDL_BREAK',
                                'option_type': 'PE',
                                'spot_price': current_price
                            })
                
                # Momentum
                if config.use_momentum and i >= 15 and i % 15 == 0:
                    momentum_start = float(candles[i-15]['close'])
                    momentum_pct = ((current_price - momentum_start) / momentum_start) * 100
                    
                    if abs(momentum_pct) >= 0.5:
                        signal_type = 'CE' if momentum_pct > 0 else 'PE'
                        if volume_ok:
                            entries.append({
                                'time': candle['timestamp'],
                                'signal': 'MOMENTUM',
                                'option_type': signal_type,
                                'spot_price': current_price
                            })
            
            return entries
    
    async def execute_scalp(self, symbol: str, entry: dict, trade_date: date, config: StrategyConfig) -> Optional[ScalpResult]:
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
                return None
            
            entry_premium = float(option_candles[0]['close'])
            if entry_premium <= 0:
                return None
            
            entry_time = option_candles[0]['timestamp']
            
            # Calculate levels
            stop_premium = entry_premium * (1 - config.stop_loss_pct / 100)
            first_target_premium = entry_premium * (1 + config.first_target_pct / 100)
            final_target_premium = entry_premium * (1 + config.final_target_pct / 100)
            
            exit_premium = None
            exit_reason = None
            trailing_stop = None
            highest_premium = entry_premium
            
            for candle in option_candles[1:]:
                minutes_elapsed = (candle['timestamp'] - entry_time).total_seconds() / 60
                current_premium = float(candle['close'])
                
                # Track highest for trailing
                if current_premium > highest_premium:
                    highest_premium = current_premium
                
                # Activate trailing stop
                if config.use_trailing and highest_premium >= entry_premium * (1 + config.trailing_activation_pct / 100):
                    trailing_stop = highest_premium * (1 - config.trailing_stop_pct / 100)
                
                # Check trailing stop
                if trailing_stop and current_premium <= trailing_stop:
                    exit_premium = current_premium
                    exit_reason = f'Trail ({config.trailing_stop_pct}%)'
                    break
                
                # Check stop loss
                if current_premium <= stop_premium:
                    exit_premium = current_premium
                    exit_reason = f'Stop ({config.stop_loss_pct}%)'
                    break
                
                # Check final target
                if current_premium >= final_target_premium:
                    exit_premium = current_premium
                    exit_reason = f'Target ({config.final_target_pct}%)'
                    break
                
                # Check time limit
                if minutes_elapsed >= config.max_hold_minutes:
                    exit_premium = current_premium
                    exit_reason = f'Time ({config.max_hold_minutes}min)'
                    break
            
            if not exit_premium:
                exit_premium = float(option_candles[-1]['close'])
                exit_reason = 'EOD'
            
            pnl_pct = ((exit_premium - entry_premium) / entry_premium) * 100
            lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
            pnl_amount = (exit_premium - entry_premium) * lot_size
            hold_minutes = int((candle['timestamp'] - entry_time).total_seconds() / 60)
            
            return ScalpResult(
                pnl_amount=pnl_amount,
                pnl_pct=pnl_pct,
                exit_reason=exit_reason,
                hold_minutes=hold_minutes
            )
    
    async def run_strategy(self, config: StrategyConfig, start_date: date, end_date: date) -> Dict:
        stocks = await self.get_fno_stocks()
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        all_results = []
        
        for trade_date in dates:
            for symbol in stocks:
                entries = await self.scan_entries(symbol, trade_date, config)
                
                for entry in entries:
                    result = await self.execute_scalp(symbol, entry, trade_date, config)
                    if result:
                        all_results.append(result)
        
        # Calculate stats
        if not all_results:
            return {'name': config.name, 'trades': 0}
        
        winners = [r for r in all_results if r.pnl_pct > 0]
        total_pnl = sum(r.pnl_amount for r in all_results)
        
        return {
            'name': config.name,
            'trades': len(all_results),
            'winners': len(winners),
            'win_rate': len(winners) / len(all_results) * 100,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / len(all_results),
            'avg_hold': sum(r.hold_minutes for r in all_results) / len(all_results)
        }


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    # Define strategies to test
    strategies = [
        StrategyConfig(
            name="BASE (Current)",
            use_pdh_pdl=True,
            use_momentum=True,
            stop_loss_pct=15.0,
            first_target_pct=15.0,
            final_target_pct=15.0
        ),
        StrategyConfig(
            name="PDH/PDL Only",
            use_pdh_pdl=True,
            use_momentum=False,
            stop_loss_pct=15.0,
            first_target_pct=15.0,
            final_target_pct=15.0
        ),
        StrategyConfig(
            name="Smart Exit (10% SL, 25% Target + Trail)",
            use_pdh_pdl=True,
            use_momentum=False,
            stop_loss_pct=10.0,
            first_target_pct=15.0,
            final_target_pct=25.0,
            use_trailing=True,
            trailing_activation_pct=15.0,
            trailing_stop_pct=10.0
        ),
        StrategyConfig(
            name="Volume Filter",
            use_pdh_pdl=True,
            use_momentum=False,
            require_volume=True,
            volume_multiplier=1.5,
            stop_loss_pct=15.0,
            first_target_pct=15.0,
            final_target_pct=15.0
        ),
        StrategyConfig(
            name="OPTIMIZED (All Improvements)",
            use_pdh_pdl=True,
            use_momentum=False,
            require_volume=True,
            volume_multiplier=1.5,
            stop_loss_pct=10.0,
            first_target_pct=15.0,
            final_target_pct=25.0,
            use_trailing=True,
            trailing_activation_pct=15.0,
            trailing_stop_pct=10.0
        )
    ]
    
    backtester = MultiStrategyBacktest()
    await backtester.connect()
    
    try:
        results = []
        for i, config in enumerate(strategies, 1):
            logger.info(f"Testing Strategy {i}/{len(strategies)}: {config.name}")
            result = await backtester.run_strategy(config, start, end)
            results.append(result)
        
        # Print comparison
        print("\n" + "=" * 100)
        print("STRATEGY COMPARISON")
        print("=" * 100)
        print(f"{'Strategy':<45} | {'Trades':>6} | {'Win%':>6} | {'Total P&L':>12} | {'Avg/Trade':>10}")
        print("-" * 100)
        
        for r in results:
            if r['trades'] > 0:
                print(f"{r['name']:<45} | {r['trades']:>6} | {r['win_rate']:>5.1f}% | Rs {r['total_pnl']:>9,.0f} | Rs {r['avg_pnl']:>7,.0f}")
        
        print("=" * 100)
        
        # Find best
        best = max(results, key=lambda x: x.get('total_pnl', float('-inf')))
        print(f"\n🏆 WINNER: {best['name']}")
        print(f"   Total P&L: Rs {best['total_pnl']:,.0f} | Win Rate: {best['win_rate']:.1f}%")
        
    finally:
        await backtester.close()


if __name__ == "__main__":
    asyncio.run(main())
