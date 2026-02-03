#!/usr/bin/env python3
"""
PDH/PDL Scalping with Technical Indicators + Brokerage Costs

Entry Filters:
1. PDH/PDL Breakout (>0.3%)
2. RSI alignment (>55 for CE, <45 for PE)
3. Price vs VWAP (above for CE, below for PE)
4. EMA trend (rising for CE, falling for PE)

Exit: 15% target, 15% stop, 15 minutes
Costs: Rs 55 per trade (realistic brokerage)
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
BROKERAGE_PER_TRADE = 55  # Rs per trade (realistic for options)


@dataclass
class TradeResult:
    pnl_amount: float
    pnl_pct: float
    exit_reason: str
    hold_minutes: int
    rsi: float
    vwap: float
    ema: float


class TechnicalScalper:
    # Entry filters
    MIN_BREAKOUT_PCT = 0.3
    RSI_BULLISH = 55
    RSI_BEARISH = 45
    RSI_PERIOD = 14
    EMA_PERIOD = 20
    
    # Exit rules
    TARGET_PCT = 15.0
    STOPLOSS_PCT = 15.0
    MAX_HOLD_MINUTES = 15
    
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
        self.pool = None
        self.filtered_out = {
            'weak_breakout': 0,
            'rsi_fail': 0,
            'vwap_fail': 0,
            'ema_fail': 0
        }
        
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
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate RSI indicator"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_vwap(self, candles: List[dict]) -> float:
        """Calculate VWAP (Volume Weighted Average Price)"""
        if not candles:
            return 0.0
        
        total_pv = sum(((c['high'] + c['low'] + c['close']) / 3) * c['volume'] for c in candles)
        total_volume = sum(c['volume'] for c in candles)
        
        if total_volume == 0:
            return 0.0
        
        return total_pv / total_volume
    
    def calculate_ema(self, prices: List[float], period: int = 20) -> float:
        """Calculate EMA (Exponential Moving Average)"""
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0.0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    async def scan_entries(self, symbol: str, trade_date: date) -> List[dict]:
        """Scan with technical indicator filters"""
        async with self.pool.acquire() as conn:
            candles = await conn.fetch("""
                SELECT c.timestamp, c.open, c.high, c.low, c.close, c.volume
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp::time >= '03:50:00'  -- 9:20 IST
                  AND c.timestamp::time <= '05:00:00'  -- 10:30 IST
                ORDER BY c.timestamp
            """, symbol, trade_date)
            
            if not candles or len(candles) < 25:  # Need history for indicators
                return []
            
            pdh_pdl = await self.get_pdh_pdl(symbol, trade_date)
            if not pdh_pdl:
                return []
            
            # Convert to list of dicts for easier processing
            candle_list = [dict(c) for c in candles]
            entries = []
            
            for i in range(20, len(candle_list)):  # Start after indicator warmup
                candle = candle_list[i]
                high = float(candle['high'])
                low = float(candle['low'])
                close_price = float(candle['close'])
                
                # Calculate indicators using historical data
                historical_candles = candle_list[:i+1]
                prices = [float(c['close']) for c in historical_candles]
                
                rsi = self.calculate_rsi(prices, self.RSI_PERIOD)
                vwap = self.calculate_vwap(historical_candles)
                ema = self.calculate_ema(prices, self.EMA_PERIOD)
                ema_prev = self.calculate_ema(prices[:-1], self.EMA_PERIOD)
                ema_trend = ema - ema_prev
                
                # PDH Break (Bullish)
                if high > pdh_pdl['pdh']:
                    breakout_strength = ((high - pdh_pdl['pdh']) / pdh_pdl['pdh']) * 100
                    
                    # FILTER 1: Breakout strength
                    if breakout_strength < self.MIN_BREAKOUT_PCT:
                        self.filtered_out['weak_breakout'] += 1
                        continue
                    
                    # FILTER 2: RSI bullish
                    if rsi < self.RSI_BULLISH:
                        self.filtered_out['rsi_fail'] += 1
                        continue
                    
                    # FILTER 3: Price above VWAP
                    if close_price < vwap:
                        self.filtered_out['vwap_fail'] += 1
                        continue
                    
                    # FILTER 4: EMA trending up
                    if ema_trend <= 0:
                        self.filtered_out['ema_fail'] += 1
                        continue
                    
                    # ALL FILTERS PASSED
                    if not any(e['signal'] == 'PDH_BREAK' for e in entries):
                        entries.append({
                            'time': candle['timestamp'],
                            'signal': 'PDH_BREAK',
                            'option_type': 'CE',
                            'spot_price': close_price,
                            'rsi': rsi,
                            'vwap': vwap,
                            'ema': ema
                        })
                
                # PDL Break (Bearish)
                if low < pdh_pdl['pdl']:
                    breakout_strength = ((pdh_pdl['pdl'] - low) / pdh_pdl['pdl']) * 100
                    
                    # FILTER 1: Breakout strength
                    if breakout_strength < self.MIN_BREAKOUT_PCT:
                        self.filtered_out['weak_breakout'] += 1
                        continue
                    
                    # FILTER 2: RSI bearish
                    if rsi > self.RSI_BEARISH:
                        self.filtered_out['rsi_fail'] += 1
                        continue
                    
                    # FILTER 3: Price below VWAP
                    if close_price > vwap:
                        self.filtered_out['vwap_fail'] += 1
                        continue
                    
                    # FILTER 4: EMA trending down
                    if ema_trend >= 0:
                        self.filtered_out['ema_fail'] += 1
                        continue
                    
                    # ALL FILTERS PASSED
                    if not any(e['signal'] == 'PDL_BREAK' for e in entries):
                        entries.append({
                            'time': candle['timestamp'],
                            'signal': 'PDL_BREAK',
                            'option_type': 'PE',
                            'spot_price': close_price,
                            'rsi': rsi,
                            'vwap': vwap,
                            'ema': ema
                        })
            
            return entries
    
    async def execute_trade(self, symbol: str, entry: dict, trade_date: date) -> Optional[TradeResult]:
        """Execute trade with spot-based estimation"""
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
            
            for candle in spot_candles[1:]:
                minutes = (candle['timestamp'] - entry_time).total_seconds() / 60
                spot = float(candle['close'])
                
                spot_move = ((spot - entry_spot) / entry_spot) * 100
                option_pnl = spot_move * ATM_DELTA if entry['option_type'] == 'CE' else -spot_move * ATM_DELTA
                
                if option_pnl >= self.TARGET_PCT:
                    lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
                    premium = entry_spot * 0.025
                    pnl_amount = premium * (option_pnl / 100) * lot_size
                    
                    return TradeResult(
                        pnl_amount=pnl_amount,
                        pnl_pct=option_pnl,
                        exit_reason='Target',
                        hold_minutes=int(minutes),
                        rsi=entry['rsi'],
                        vwap=entry['vwap'],
                        ema=entry['ema']
                    )
                
                if option_pnl <= -self.STOPLOSS_PCT:
                    lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
                    premium = entry_spot * 0.025
                    pnl_amount = premium * (option_pnl / 100) * lot_size
                    
                    return TradeResult(
                        pnl_amount=pnl_amount,
                        pnl_pct=option_pnl,
                        exit_reason='Stop',
                        hold_minutes=int(minutes),
                        rsi=entry['rsi'],
                        vwap=entry['vwap'],
                        ema=entry['ema']
                    )
                
                if minutes >= self.MAX_HOLD_MINUTES:
                    lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
                    premium = entry_spot * 0.025
                    pnl_amount = premium * (option_pnl / 100) * lot_size
                    
                    return TradeResult(
                        pnl_amount=pnl_amount,
                        pnl_pct=option_pnl,
                        exit_reason='Time',
                        hold_minutes=int(minutes),
                        rsi=entry['rsi'],
                        vwap=entry['vwap'],
                        ema=entry['ema']
                    )
            
            return None
    
    async def backtest(self, start_date: date, end_date: date):
        stocks = await self.get_fno_stocks()
        logger.info(f"Scanning {len(stocks)} stocks with TECHNICAL INDICATORS")
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        results = []
        
        for trade_date in dates:
            day_trades = 0
            for symbol in stocks:
                entries = await self.scan_entries(symbol, trade_date)
                
                for entry in entries:
                    result = await self.execute_trade(symbol, entry, trade_date)
                    if result:
                        results.append(result)
                        day_trades += 1
            
            if day_trades > 0:
                logger.info(f"{trade_date}: {day_trades} trades")
        
        self.print_results(results)
    
    def print_results(self, results: List[TradeResult]):
        if not results:
            print("\nNo trades found")
            return
        
        winners = [r for r in results if r.pnl_pct > 0]
        gross_pnl = sum(r.pnl_amount for r in results)
        brokerage = len(results) * BROKERAGE_PER_TRADE
        net_pnl = gross_pnl - brokerage
        
        print("\n" + "=" * 100)
        print("TECHNICAL SCALPING RESULTS (RSI + VWAP + EMA)")
        print("=" * 100)
        print(f"\nFILTERS:")
        print(f"  1. PDH/PDL Breakout: >{self.MIN_BREAKOUT_PCT}%")
        print(f"  2. RSI: >55 (CE), <45 (PE)")
        print(f"  3. VWAP: Price above (CE), below (PE)")
        print(f"  4. EMA({self.EMA_PERIOD}): Trending up (CE), down (PE)")
        
        print(f"\nFILTERED OUT:")
        for reason, count in self.filtered_out.items():
            print(f"  - {reason}: {count}")
        print(f"  - TOTAL REJECTED: {sum(self.filtered_out.values())}")
        
        print(f"\n" + "=" * 100)
        print(f"PERFORMANCE:")
        print(f"  Total Trades: {len(results)}")
        print(f"  Winners: {len(winners)} ({len(winners)/len(results)*100:.1f}%)")
        print(f"  Gross P&L: Rs {gross_pnl:,.0f}")
        print(f"  Brokerage: Rs {brokerage:,.0f} ({len(results)} trades @ Rs {BROKERAGE_PER_TRADE})")
        print(f"  NET P&L: Rs {net_pnl:,.0f}")
        print(f"  Avg per Trade: Rs {net_pnl/len(results):,.0f}")
        print(f"  Avg Hold: {sum(r.hold_minutes for r in results)/len(results):.1f} min")
        print("=" * 100)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    scalper = TechnicalScalper()
    await scalper.connect()
    
    try:
        await scalper.backtest(start, end)
    finally:
        await scalper.close()


if __name__ == "__main__":
    asyncio.run(main())
