#!/usr/bin/env python3
"""
Daily Sniper Strategy - Top 2 Setups Only

Multi-Indicator Scoring System:
- RSI, MACD, VWAP, EMA, ATR, Bollinger Bands, ADX, Stochastic, Supertrend
- Score each setup 0-100
- Trade ONLY top 2 highest scores per day
- 50% target, 30% stop, hold till EOD
- Aim: 70%+ win rate, Rs 500+ net per trade
"""

import asyncio
import asyncpg
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from typing import List, Optional
import logging
import math

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
    'VEDL': 3075, 'HINDZINC': 2400, 'CANBK': 6750, 'HINDPETRO': 1575,
    'BPCL': 975, 'ABCAPITAL': 5400, 'LAURUSLABS': 1700, 'SIEMENS': 275,
}
DEFAULT_LOT_SIZE = 500
ATM_DELTA = 0.55
BROKERAGE = 55


@dataclass
class ScoredSetup:
    symbol: str
    signal_type: str
    option_type: str
    spot_price: float
    breakout_pct: float
    score: float
    score_breakdown: dict
    entry_time: datetime


@dataclass
class TradeResult:
    symbol: str
    score: float
    pnl_amount: float
    pnl_pct: float
    exit_reason: str
    hold_minutes: int


class DailySniper:
    TARGET_PCT = 50.0
    STOPLOSS_PCT = 30.0
    TRADES_PER_DAY = 2
    MIN_SCORE = 40  # Lowered from 70 to find trades
    
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
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
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
        return 100 - (100 / (1 + rs))
    
    def calculate_macd(self, prices: List[float]) -> tuple:
        if len(prices) < 26:
            return 0, 0, 0
        ema12 = self.calculate_ema(prices, 12)
        ema26 = self.calculate_ema(prices, 26)
        macd_line = ema12 - ema26
        # Signal line would need more history, simplified
        signal_line = macd_line * 0.9
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0.0
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def calculate_vwap(self, candles: List[dict]) -> float:
        if not candles:
            return 0.0
        total_pv = sum(((float(c['high']) + float(c['low']) + float(c['close'])) / 3) * float(c['volume']) for c in candles)
        total_volume = sum(float(c['volume']) for c in candles)
        return float(total_pv / total_volume) if total_volume > 0 else 0.0
    
    def calculate_atr(self, candles: List[dict], period: int = 14) -> float:
        if len(candles) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(candles)):
            high = float(candles[i]['high'])
            low = float(candles[i]['low'])
            prev_close = float(candles[i-1]['close'])
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        return sum(trs[-period:]) / period if trs else 0.0
    
    def calculate_bollinger_bands(self, prices: List[float], period: int = 20) -> tuple:
        if len(prices) < period:
            return 0, 0, 0
        sma = sum(prices[-period:]) / period
        variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
        std = math.sqrt(variance)
        upper = sma + (2 * std)
        lower = sma - (2 * std)
        return upper, sma, lower
    
    def calculate_adx(self, candles: List[dict], period: int = 14) -> float:
        if len(candles) < period + 1:
            return 0.0
        dx_values = []
        for i in range(1, len(candles)):
            high_diff = float(candles[i]['high']) - float(candles[i-1]['high'])
            low_diff = float(candles[i-1]['low']) - float(candles[i]['low'])
            if high_diff > low_diff and high_diff > 0:
                dx_values.append(abs(high_diff))
            elif low_diff > high_diff and low_diff > 0:
                dx_values.append(abs(low_diff))
            else:
                dx_values.append(0)
        return float(sum(dx_values[-period:]) / period) if dx_values else 0.0
    
    def calculate_stochastic(self, candles: List[dict], period: int = 14) -> float:
        if len(candles) < period:
            return 50.0
        recent = candles[-period:]
        high = max(float(c['high']) for c in recent)
        low = min(float(c['low']) for c in recent)
        close = float(candles[-1]['close'])
        if high == low:
            return 50.0
        return float(((close - low) / (high - low)) * 100)
    
    def calculate_supertrend(self, candles: List[dict], atr_period: int = 10, multiplier: float = 3.0) -> str:
        if len(candles) < atr_period:
            return 'NEUTRAL'
        atr = self.calculate_atr(candles, atr_period)
        basic_ub = ((float(candles[-1]['high']) + float(candles[-1]['low'])) / 2) + (multiplier * atr)
        basic_lb = ((float(candles[-1]['high']) + float(candles[-1]['low'])) / 2) - (multiplier * atr)
        close = float(candles[-1]['close'])
        return 'BUY' if close > basic_lb else 'SELL' if close < basic_ub else 'NEUTRAL'
    
    async def score_setup(self, symbol: str, trade_date: date, pdh: float, pdl: float) -> Optional[ScoredSetup]:
        """Score a potential setup using all indicators"""
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
            
            if not candles or len(candles) < 30:
                return None
            
            candle_list = [dict(c) for c in candles]
            prices = [float(c['close']) for c in candle_list]
            current = candle_list[-1]
            
            # Check for breakout
            high = float(current['high'])
            low = float(current['low'])
            close = float(current['close'])
            
            breakout_type = None
            breakout_pct = 0
            option_type = None
            
            if high > pdh:
                breakout_pct = ((high - pdh) / pdh) * 100
                breakout_type = 'PDH_BREAK'
                option_type = 'CE'
            elif low < pdl:
                breakout_pct = ((pdl - low) / pdl) * 100
                breakout_type = 'PDL_BREAK'
                option_type = 'PE'
            else:
                return None
            
            if breakout_pct < 0.3:  # Minimum breakout
                return None
            
            # Calculate all indicators
            rsi = self.calculate_rsi(prices)
            macd, signal, histogram = self.calculate_macd(prices)
            vwap = self.calculate_vwap(candle_list)
            ema20 = self.calculate_ema(prices, 20)
            atr = self.calculate_atr(candle_list)
            bb_upper, bb_mid, bb_lower = self.calculate_bollinger_bands(prices)
            adx = self.calculate_adx(candle_list)
            stoch = self.calculate_stochastic(candle_list)
            supertrend = self.calculate_supertrend(candle_list)
            
            # SCORING (0-100)
            score_breakdown = {}
            total_score = 0
            
            # 1. Breakout Strength (0-15)
            breakout_score = min(breakout_pct * 5, 15)
            score_breakdown['breakout'] = breakout_score
            total_score += breakout_score
            
            # 2. RSI Alignment (0-10)
            if option_type == 'CE':
                rsi_score = min((rsi - 50) / 5, 10) if rsi > 50 else 0
            else:
                rsi_score = min((50 - rsi) / 5, 10) if rsi < 50 else 0
            score_breakdown['rsi'] = rsi_score
            total_score += rsi_score
            
            # 3. MACD Signal (0-15)
            if option_type == 'CE':
                macd_score = 15 if histogram > 0 and macd > signal else 0
            else:
                macd_score = 15 if histogram < 0 and macd < signal else 0
            score_breakdown['macd'] = macd_score
            total_score += macd_score
            
            # 4. VWAP Position (0-10)
            vwap_diff_pct = abs(((close - vwap) / vwap) * 100)
            if option_type == 'CE':
                vwap_score = 10 if close > vwap else 0
            else:
                vwap_score = 10 if close < vwap else 0
            score_breakdown['vwap'] = vwap_score
            total_score += vwap_score
            
            # 5. EMA Trend (0-10)
            ema_slope = ((prices[-1] - prices[-5]) / prices[-5]) * 100 if len(prices) >= 5 else 0
            if option_type == 'CE':
                ema_score = min(abs(ema_slope) * 5, 10) if ema_slope > 0 else 0
            else:
                ema_score = min(abs(ema_slope) * 5, 10) if ema_slope < 0 else 0
            score_breakdown['ema'] = ema_score
            total_score += ema_score
            
            # 6. ATR (High Volatility) (0-10)
            atr_pct = (atr / close) * 100
            atr_score = min(atr_pct * 2, 10)
            score_breakdown['atr'] = atr_score
            total_score += atr_score
            
            # 7. Bollinger Bands (0-10)
            bb_width_pct = ((bb_upper - bb_lower) / bb_mid) * 100
            if option_type == 'CE':
                bb_score = 10 if close > bb_upper else 5 if close > bb_mid else 0
            else:
                bb_score = 10 if close < bb_lower else 5 if close < bb_mid else 0
            score_breakdown['bollinger'] = bb_score
            total_score += bb_score
            
            # 8. ADX (Trend Strength) (0-10)
            adx_score = min(adx / 3, 10)
            score_breakdown['adx'] = adx_score
            total_score += adx_score
            
            # 9. Stochastic (0-5)
            if option_type == 'CE':
                stoch_score = min((stoch - 50) / 10, 5) if stoch > 50 else 0
            else:
                stoch_score = min((50 - stoch) / 10, 5) if stoch < 50 else 0
            score_breakdown['stochastic'] = stoch_score
            total_score += stoch_score
            
            # 10. Supertrend (0-5)
            if (option_type == 'CE' and supertrend == 'BUY') or (option_type == 'PE' and supertrend == 'SELL'):
                supertrend_score = 5
            else:
                supertrend_score = 0
            score_breakdown['supertrend'] = supertrend_score
            total_score += supertrend_score
            
            return ScoredSetup(
                symbol=symbol,
                signal_type=breakout_type,
                option_type=option_type,
                spot_price=close,
                breakout_pct=breakout_pct,
                score=total_score,
                score_breakdown=score_breakdown,
                entry_time=current['timestamp']
            )
    
    async def execute_trade(self, setup: ScoredSetup, trade_date: date) -> Optional[TradeResult]:
        """Execute trade with 50% target, 30% stop"""
        async with self.pool.acquire() as conn:
            candles = await conn.fetch("""
                SELECT c.timestamp, c.close
                FROM candle_data c
                JOIN instrument_master im ON c.instrument_id = im.instrument_id
                WHERE im.trading_symbol = $1
                  AND im.instrument_type = 'EQUITY'
                  AND DATE(c.timestamp) = $2
                  AND c.timestamp >= $3
                ORDER BY c.timestamp
            """, setup.symbol, trade_date, setup.entry_time)
            
            if not candles or len(candles) < 2:
                return None
            
            entry_spot = float(candles[0]['close'])
            entry_time = candles[0]['timestamp']
            
            for candle in candles[1:]:
                spot = float(candle['close'])
                spot_move = ((spot - entry_spot) / entry_spot) * 100
                option_pnl = spot_move * ATM_DELTA if setup.option_type == 'CE' else -spot_move * ATM_DELTA
                
                minutes = (candle['timestamp'] - entry_time).total_seconds() / 60
                
                # Check target
                if option_pnl >= self.TARGET_PCT:
                    lot_size = LOT_SIZES.get(setup.symbol, DEFAULT_LOT_SIZE)
                    premium = entry_spot * 0.025
                    pnl_amount = premium * (option_pnl / 100) * lot_size
                    
                    return TradeResult(
                        symbol=setup.symbol,
                        score=setup.score,
                        pnl_amount=pnl_amount,
                        pnl_pct=option_pnl,
                        exit_reason='Target (50%)',
                        hold_minutes=int(minutes)
                    )
                
                # Check stop
                if option_pnl <= -self.STOPLOSS_PCT:
                    lot_size = LOT_SIZES.get(setup.symbol, DEFAULT_LOT_SIZE)
                    premium = entry_spot * 0.025
                    pnl_amount = premium * (option_pnl / 100) * lot_size
                    
                    return TradeResult(
                        symbol=setup.symbol,
                        score=setup.score,
                        pnl_amount=pnl_amount,
                        pnl_pct=option_pnl,
                        exit_reason='Stop (30%)',
                        hold_minutes=int(minutes)
                    )
            
            # EOD exit
            final_spot = float(candles[-1]['close'])
            spot_move = ((final_spot - entry_spot) / entry_spot) * 100
            option_pnl = spot_move * ATM_DELTA if setup.option_type == 'CE' else -spot_move * ATM_DELTA
            
            lot_size = LOT_SIZES.get(setup.symbol, DEFAULT_LOT_SIZE)
            premium = entry_spot * 0.025
            pnl_amount = premium * (option_pnl / 100) * lot_size
            
            return TradeResult(
                symbol=setup.symbol,
                score=setup.score,
                pnl_amount=pnl_amount,
                pnl_pct=option_pnl,
                exit_reason='EOD',
                hold_minutes=int((candles[-1]['timestamp'] - entry_time).total_seconds() / 60)
            )
    
    async def backtest(self, start_date: date, end_date: date):
        stocks = await self.get_fno_stocks()
        logger.info(f"DAILY SNIPER: Scanning {len(stocks)} stocks, taking top {self.TRADES_PER_DAY} daily")
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        all_results = []
        
        for trade_date in dates:
            # Get PDH/PDL for all stocks
            async with self.pool.acquire() as conn:
                prev_date = trade_date - timedelta(days=1)
                while prev_date.weekday() >= 5:
                    prev_date -= timedelta(days=1)
            
            # Score all setups for this day
            day_setups = []
            for symbol in stocks:
                async with self.pool.acquire() as conn:
                    pdh_pdl = await conn.fetchrow("""
                        SELECT MAX(c.high) as pdh, MIN(c.low) as pdl
                        FROM candle_data c
                        JOIN instrument_master im ON c.instrument_id = im.instrument_id
                        WHERE im.trading_symbol = $1
                          AND im.instrument_type = 'EQUITY'
                          AND DATE(c.timestamp) = $2
                    """, symbol, prev_date)
                    
                    if pdh_pdl and pdh_pdl['pdh']:
                        setup = await self.score_setup(symbol, trade_date, float(pdh_pdl['pdh']), float(pdh_pdl['pdl']))
                        if setup and setup.score >= self.MIN_SCORE:
                            day_setups.append(setup)
            
            # Take top 2
            day_setups.sort(key=lambda x: x.score, reverse=True)
            top_setups = day_setups[:self.TRADES_PER_DAY]
            
            # Execute trades
            for setup in top_setups:
                result = await self.execute_trade(setup, trade_date)
                if result:
                    all_results.append(result)
            
            if top_setups:
                logger.info(f"{trade_date}: {len(top_setups)} trades (scores: {[f'{s.score:.0f}' for s in top_setups]})")
        
        self.print_results(all_results)
    
    def print_results(self, results: List[TradeResult]):
        if not results:
            print("\nNo trades found")
            return
        
        winners = [r for r in results if r.pnl_pct > 0]
        gross_pnl = sum(r.pnl_amount for r in results)
        brokerage = len(results) * BROKERAGE
        net_pnl = gross_pnl - brokerage
        
        print("\n" + "=" * 100)
        print("DAILY SNIPER RESULTS - TOP 2 SETUPS PER DAY")
        print("=" * 100)
        print(f"\nSTRATEGY:")
        print(f"  - Multi-indicator scoring (RSI, MACD, VWAP, EMA, ATR, BB, ADX, Stoch, Supertrend)")
        print(f"  - Trade ONLY top {self.TRADES_PER_DAY} highest scores per day")
        print(f"  - 50% target, 30% stop, hold till EOD")
        print(f"  - Minimum score: {self.MIN_SCORE}/100")
        
        print(f"\n" + "=" * 100)
        print(f"PERFORMANCE:")
        print(f"  Total Trades: {len(results)}")
        print(f"  Winners: {len(winners)} ({len(winners)/len(results)*100:.1f}%)")
        print(f"  Gross P&L: Rs {gross_pnl:,.0f}")
        print(f"  Brokerage: Rs -{brokerage:,.0f}")
        print(f"  NET P&L: Rs {net_pnl:,.0f}")
        print(f"  Avg per Trade (NET): Rs {net_pnl/len(results):,.0f}")
        print(f"  Avg Score: {sum(r.score for r in results)/len(results):.1f}/100")
        print(f"  Avg Hold: {sum(r.hold_minutes for r in results)/len(results):.0f} min")
        
        if len(winners) > 0:
            avg_win = sum(r.pnl_amount for r in winners) / len(winners)
            print(f"  Avg Win: Rs {avg_win:,.0f}")
        
        if len(results) > len(winners):
            losers = [r for r in results if r.pnl_pct <= 0]
            avg_loss = sum(r.pnl_amount for r in losers) / len(losers)
            print(f"  Avg Loss: Rs {avg_loss:,.0f}")
        
        print("=" * 100)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    sniper = DailySniper()
    await sniper.connect()
    
    try:
        await sniper.backtest(start, end)
    finally:
        await sniper.close()


if __name__ == "__main__":
    asyncio.run(main())
