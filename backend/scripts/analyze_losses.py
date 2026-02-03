#!/usr/bin/env python3
"""
Analyze losing trades to identify improvement opportunities
"""

import asyncio
import asyncpg
from datetime import datetime, date, time as dt_time, timedelta
from collections import defaultdict
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
}
DEFAULT_LOT_SIZE = 500
ATM_DELTA = 0.55

# Sector mapping
SECTORS = {
    'BANKING': ['HDFCBANK', 'ICICIBANK', 'SBIN', 'AXISBANK', 'KOTAKBANK', 'INDUSINDBK', 'CANBK'],
    'IT': ['TCS', 'INFY', 'WIPRO', 'HCLTECH', 'TECHM'],
    'AUTO': ['MARUTI', 'TATAMOTORS', 'BAJAJ-AUTO', 'HEROMOTOCO', 'EICHERMOT'],
    'PHARMA': ['SUNPHARMA', 'DRREDDY', 'CIPLA', 'DIVISLAB', 'LAURUSLABS'],
    'ENERGY': ['RELIANCE', 'ONGC', 'NTPC', 'POWERGRID', 'BPCL', 'HINDPETRO'],
    'FMCG': ['HINDUNILVR', 'ITC', 'BRITANNIA', 'NESTLEIND', 'DABUR', 'GODREJCP'],
}

def get_sector(symbol):
    for sector, stocks in SECTORS.items():
        if symbol in stocks:
            return sector
    return 'OTHER'


class LossAnalyzer:
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
        self.pool = None
        
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)
        
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def get_fno_stocks(self):
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
    
    async def get_pdh_pdl(self, symbol: str, current_date: date):
        async with self.pool.acquire() as conn:
            prev_date = current_date - timedelta(days=1)
            while prev_date.weekday() >= 5:
                prev_date -= timedelta(days=1)
            
            result = await conn.fetchrow("""
                SELECT MAX(c.high) as pdh, MIN(c.low) as pdl,
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
    
    async def analyze(self, start_date: date, end_date: date):
        stocks = await self.get_fno_stocks()
        logger.info(f"Analyzing {len(stocks)} stocks")
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        # Track all trades
        by_time = defaultdict(lambda: {'wins': 0, 'losses': 0})
        by_sector = defaultdict(lambda: {'wins': 0, 'losses': 0})
        by_signal_strength = defaultdict(lambda: {'wins': 0, 'losses': 0})
        by_volume = defaultdict(lambda: {'wins': 0, 'losses': 0})
        
        total_trades = 0
        
        for trade_date in dates:
            for symbol in stocks:
                sector = get_sector(symbol)
                pdh_pdl = await self.get_pdh_pdl(symbol, trade_date)
                
                if not pdh_pdl:
                    continue
                
                # Get candles
                async with self.pool.acquire() as conn:
                    candles = await conn.fetch("""
                        SELECT c.timestamp, c.high, c.low, c.close, c.volume
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
                    continue
                
                for i, candle in enumerate(candles):
                    if i < 3:
                        continue
                    
                    high = float(candle['high'])
                    low = float(candle['low'])
                    close_price = float(candle['close'])
                    volume = float(candle['volume'])
                    candle_time = candle['timestamp'].time()
                    
                    # PDH break
                    if high > pdh_pdl['pdh']:
                        breakout_strength = ((high - pdh_pdl['pdh']) / pdh_pdl['pdh']) * 100
                        volume_ratio = volume / pdh_pdl['avg_volume'] if pdh_pdl['avg_volume'] > 0 else 0
                        
                        # Simulate trade outcome
                        is_winner = self.simulate_trade(candles[i:], close_price, 'CE')
                        
                        total_trades += 1
                        result = 'wins' if is_winner else 'losses'
                        
                        # Track by time
                        hour = (candle_time.hour + 5) + (candle_time.minute + 30) // 60
                        minute = (candle_time.minute + 30) % 60
                        time_bucket = f"{hour:02d}:{minute//15*15:02d}"
                        by_time[time_bucket][result] += 1
                        
                        # Track by sector
                        by_sector[sector][result] += 1
                        
                        # Track by breakout strength
                        if breakout_strength < 0.1:
                            strength_bucket = '<0.1%'
                        elif breakout_strength < 0.3:
                            strength_bucket = '0.1-0.3%'
                        elif breakout_strength < 0.5:
                            strength_bucket = '0.3-0.5%'
                        else:
                            strength_bucket = '>0.5%'
                        by_signal_strength[strength_bucket][result] += 1
                        
                        # Track by volume
                        if volume_ratio < 0.5:
                            vol_bucket = 'Low (<0.5x)'
                        elif volume_ratio < 1.0:
                            vol_bucket = 'Medium (0.5-1x)'
                        elif volume_ratio < 2.0:
                            vol_bucket = 'High (1-2x)'
                        else:
                            vol_bucket = 'Very High (>2x)'
                        by_volume[vol_bucket][result] += 1
                        
                        break  # One PDH break per stock per day
                    
                    # PDL break
                    if low < pdh_pdl['pdl']:
                        breakout_strength = ((pdh_pdl['pdl'] - low) / pdh_pdl['pdl']) * 100
                        volume_ratio = volume / pdh_pdl['avg_volume'] if pdh_pdl['avg_volume'] > 0 else 0
                        
                        is_winner = self.simulate_trade(candles[i:], close_price, 'PE')
                        
                        total_trades += 1
                        result = 'wins' if is_winner else 'losses'
                        
                        hour = (candle_time.hour + 5) + (candle_time.minute + 30) // 60
                        minute = (candle_time.minute + 30) % 60
                        time_bucket = f"{hour:02d}:{minute//15*15:02d}"
                        by_time[time_bucket][result] += 1
                        
                        by_sector[sector][result] += 1
                        
                        if breakout_strength < 0.1:
                            strength_bucket = '<0.1%'
                        elif breakout_strength < 0.3:
                            strength_bucket = '0.1-0.3%'
                        elif breakout_strength < 0.5:
                            strength_bucket = '0.3-0.5%'
                        else:
                            strength_bucket = '>0.5%'
                        by_signal_strength[strength_bucket][result] += 1
                        
                        if volume_ratio < 0.5:
                            vol_bucket = 'Low (<0.5x)'
                        elif volume_ratio < 1.0:
                            vol_bucket = 'Medium (0.5-1x)'
                        elif volume_ratio < 2.0:
                            vol_bucket = 'High (1-2x)'
                        else:
                            vol_bucket = 'Very High (>2x)'
                        by_volume[vol_bucket][result] += 1
                        
                        break
        
        self.print_analysis(total_trades, by_time, by_sector, by_signal_strength, by_volume)
    
    def simulate_trade(self, future_candles, entry_spot, option_type):
        """Simple simulation of trade outcome"""
        entry_time = future_candles[0]['timestamp']
        
        for candle in future_candles[1:]:
            minutes = (candle['timestamp'] - entry_time).total_seconds() / 60
            spot = float(candle['close'])
            
            spot_move = ((spot - entry_spot) / entry_spot) * 100
            option_pnl = spot_move * ATM_DELTA if option_type == 'CE' else -spot_move * ATM_DELTA
            
            if option_pnl >= 15:
                return True
            if option_pnl <= -15:
                return False
            if minutes >= 15:
                return option_pnl > 0
        
        return False
    
    def print_analysis(self, total, by_time, by_sector, by_strength, by_volume):
        print("\n" + "=" * 100)
        print(f"LOSS ANALYSIS - {total} TRADES")
        print("=" * 100)
        
        # By Time
        print("\n1. WIN RATE BY TIME OF DAY:")
        print("-" * 100)
        for time_slot in sorted(by_time.keys()):
            stats = by_time[time_slot]
            total_slot = stats['wins'] + stats['losses']
            win_rate = (stats['wins'] / total_slot * 100) if total_slot > 0 else 0
            marker = "✅" if win_rate >= 55 else "❌" if win_rate < 45 else "⚠️"
            print(f"{marker} {time_slot} IST | {total_slot:3} trades | Win Rate: {win_rate:5.1f}%")
        
        # By Sector
        print("\n2. WIN RATE BY SECTOR:")
        print("-" * 100)
        sector_list = sorted(by_sector.items(), key=lambda x: x[1]['wins']/(x[1]['wins']+x[1]['losses']) if (x[1]['wins']+x[1]['losses']) > 0 else 0, reverse=True)
        for sector, stats in sector_list:
            total_sector = stats['wins'] + stats['losses']
            win_rate = (stats['wins'] / total_sector * 100) if total_sector > 0 else 0
            marker = "✅" if win_rate >= 55 else "❌" if win_rate < 45 else "⚠️"
            print(f"{marker} {sector:12} | {total_sector:3} trades | Win Rate: {win_rate:5.1f}%")
        
        # By Signal Strength
        print("\n3. WIN RATE BY PDH/PDL BREAKOUT STRENGTH:")
        print("-" * 100)
        for strength in ['<0.1%', '0.1-0.3%', '0.3-0.5%', '>0.5%']:
            if strength in by_strength:
                stats = by_strength[strength]
                total_str = stats['wins'] + stats['losses']
                win_rate = (stats['wins'] / total_str * 100) if total_str > 0 else 0
                marker = "✅" if win_rate >= 55 else "❌" if win_rate < 45 else "⚠️"
                print(f"{marker} {strength:12} | {total_str:3} trades | Win Rate: {win_rate:5.1f}%")
        
        # By Volume
        print("\n4. WIN RATE BY VOLUME:")
        print("-" * 100)
        for vol in ['Low (<0.5x)', 'Medium (0.5-1x)', 'High (1-2x)', 'Very High (>2x)']:
            if vol in by_volume:
                stats = by_volume[vol]
                total_vol = stats['wins'] + stats['losses']
                win_rate = (stats['wins'] / total_vol * 100) if total_vol > 0 else 0
                marker = "✅" if win_rate >= 55 else "❌" if win_rate < 45 else "⚠️"
                print(f"{marker} {vol:20} | {total_vol:3} trades | Win Rate: {win_rate:5.1f}%")
        
        print("\n" + "=" * 100)
        print("RECOMMENDATIONS:")
        print("=" * 100)
        
        # Find best sectors
        good_sectors = [s for s, st in by_sector.items() if (st['wins']/(st['wins']+st['losses'])*100 if (st['wins']+st['losses']) > 10 else 0) >= 55]
        if good_sectors:
            print(f"✅ TRADE ONLY: {', '.join(good_sectors)}")
        
        # Find best times
        good_times = [t for t, st in by_time.items() if (st['wins']/(st['wins']+st['losses'])*100 if (st['wins']+st['losses']) > 5 else 0) >= 55]
        if good_times:
            print(f"✅ BEST TIMES: {', '.join(good_times)}")
        
        # Signal strength
        print(f"✅ MINIMUM BREAKOUT: >0.3% (avoid weak breaks <0.3%)")
        
        # Volume
        print(f"✅ VOLUME FILTER: Require >1x average volume")
        
        print("=" * 100)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    analyzer = LossAnalyzer()
    await analyzer.connect()
    
    try:
        await analyzer.analyze(start, end)
    finally:
        await analyzer.close()


if __name__ == "__main__":
    asyncio.run(main())
