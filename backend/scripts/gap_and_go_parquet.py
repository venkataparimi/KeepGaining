#!/usr/bin/env python3
"""
Gap-and-Go ULTRA FAST - Parquet Edition

Uses pre-computed indicator data from parquet files
Should complete in under 1 minute!
"""

import pandas as pd
import os
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from typing import List
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

PARQUET_DIR = 'data/strategy_dataset'

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
    'LAURUSLABS': 1700, 'NATIONALUM': 1700, 'IDEA': 10000, 'UNIONBANK': 3500
}
DEFAULT_LOT_SIZE = 500
ATM_DELTA = 0.55
BROKERAGE = 55


@dataclass
class TradeResult:
    date: date
    symbol: str
    gap_pct: float
    volume_ratio: float
    pnl_amount: float
    pnl_pct: float
    exit_reason: str


class ParquetGapAndGo:
    MIN_GAP_PCT = 1.0
    MIN_VOLUME_RATIO = 2.0
    TARGET_PCT = 30.0  # Realistic target
    STOPLOSS_PCT = 20.0  # Tighter stop
    
    def __init__(self):
        self.stock_data = {}
        
    def load_data(self):
        """Load all parquet files into memory once"""
        logger.info("Loading parquet files...")
        parquet_files = [f for f in os.listdir(PARQUET_DIR) if f.endswith('_EQUITY.parquet')]
        
        for file in parquet_files:
            symbol = file.replace('_EQUITY.parquet', '')
            try:
                df = pd.read_parquet(os.path.join(PARQUET_DIR, file))
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp')
                self.stock_data[symbol] = df
            except Exception as e:
                logger.warning(f"Failed to load {symbol}: {e}")
        
        logger.info(f"Loaded {len(self.stock_data)} stocks")
    
    def find_gaps(self, trade_date: date) -> List[dict]:
        """Find all gap ups on given date"""
        gaps = []
        
        for symbol, df in self.stock_data.items():
            try:
                # Get previous day close
                prev_date = pd.Timestamp(trade_date) - pd.Timedelta(days=1)
                while prev_date.weekday() >= 5:
                    prev_date -= pd.Timedelta(days=1)
                
                prev_day = df[df.index.date == prev_date.date()]
                if prev_day.empty:
                    continue
                prev_close = prev_day['close'].iloc[-1]
                
                # Get first candle at 9:15 AM (03:45 UTC)
                trade_day = df[df.index.date == pd.Timestamp(trade_date).date()]
                if trade_day.empty:
                    continue
                
                first_candle_time = pd.Timestamp(trade_date).replace(hour=9, minute=15)
                first_candle = trade_day[trade_day.index.time == pd.Timestamp('03:45:00').time()]
                
                if first_candle.empty:
                    continue
                
                first = first_candle.iloc[0]
                gap_pct = ((first['open'] - prev_close) / prev_close) * 100
                
                if gap_pct < self.MIN_GAP_PCT:
                    continue
                
                # Check if still bullish (closed above open)
                if first['close'] < first['open']:
                    continue
                
                # Check volume surge
                avg_volume = df['volume'].tail(375 * 5).mean() / 375  # 5 day avg per candle
                if avg_volume == 0:
                    continue
                
                volume_ratio = first['volume'] / avg_volume
                
                if volume_ratio < self.MIN_VOLUME_RATIO:
                    continue
                
                # Check above VWAP
                if first['vwap'] > 0 and first['close'] < first['vwap']:
                    continue
                
                gaps.append({
                    'symbol': symbol,
                    'gap_pct': gap_pct,
                    'volume_ratio': volume_ratio,
                    'entry_price': first['close'],
                    'vwap': first['vwap']
                })
                
            except Exception as e:
                continue
        
        # Sort by gap strength
        gaps.sort(key=lambda x: x['gap_pct'], reverse=True)
        return gaps[:2]  # Top 2
    
    def execute_trade(self, gap: dict, trade_date: date) -> TradeResult:
        """Execute trade using parquet data"""
        symbol = gap['symbol']
        df = self.stock_data[symbol]
        
        # Get intraday data
        trade_day = df[df.index.date == pd.Timestamp(trade_date).date()]
        
        # Filter from 9:15 to 2:30 PM (03:45 to 09:00 UTC)
        intraday = trade_day[
            (trade_day.index.time >= pd.Timestamp('03:45:00').time()) &
            (trade_day.index.time <= pd.Timestamp('09:00:00').time())
        ]
        
        if intraday.empty or len(intraday) < 2:
            return None
        
        entry_spot = gap['entry_price']
        exit_spot = intraday['close'].iloc[-1]
        exit_reason = 'EOD (2:30 PM)'
        
        # Check for target/stop during the day
        for idx, row in intraday.iloc[1:].iterrows():
            spot = row['close']
            spot_move = ((spot - entry_spot) / entry_spot) * 100
            option_pnl = spot_move * ATM_DELTA
            
            if option_pnl >= self.TARGET_PCT:
                exit_spot = spot
                exit_reason = 'Target (100%)'
                break
            
            if option_pnl <= -self.STOPLOSS_PCT:
                exit_spot = spot
                exit_reason = 'Stop (40%)'
                break
        
        # Final P&L
        final_move = ((exit_spot - entry_spot) / entry_spot) * 100
        option_pnl = final_move * ATM_DELTA
        
        lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
        premium = entry_spot * 0.025
        pnl_amount = premium * (option_pnl / 100) * lot_size
        
        return TradeResult(
            date=trade_date,
            symbol=symbol,
            gap_pct=gap['gap_pct'],
            volume_ratio=gap['volume_ratio'],
            pnl_amount=pnl_amount,
            pnl_pct=option_pnl,
            exit_reason=exit_reason
        )
    
    def backtest(self, start_date: date, end_date: date):
        logger.info("Starting backtest...")
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        all_results = []
        
        for trade_date in dates:
            gaps = self.find_gaps(trade_date)
            
            if gaps:
                logger.info(f"{trade_date}: Found {len(gaps)} gaps - " + 
                          ", ".join([f"{g['symbol']} ({g['gap_pct']:.1f}%, {g['volume_ratio']:.1f}x vol)" for g in gaps]))
            
            for gap in gaps:
                result = self.execute_trade(gap, trade_date)
                if result:
                    all_results.append(result)
        
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
        print("GAP-AND-GO PARQUET RESULTS")
        print("=" * 100)
        
        print(f"\nSTRATEGY:")
        print(f"  - Gap >{self.MIN_GAP_PCT}%, Volume >{self.MIN_VOLUME_RATIO}x avg")
        print(f"  - Price > VWAP at 9:15 AM")
        print(f"  - Top 2 gaps daily")
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
        
        print(f"\nTOP 5 TRADES:")
        top_trades = sorted(results, key=lambda x: x.pnl_amount, reverse=True)[:5]
        for r in top_trades:
            sign = "+" if r.pnl_amount > 0 else ""
            print(f"  {r.date} {r.symbol}: {r.gap_pct:.1f}% gap, {r.volume_ratio:.0f}x vol -> {sign}Rs {r.pnl_amount:,.0f} ({r.exit_reason})")
        
        print("=" * 100)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    strategy = ParquetGapAndGo()
    strategy.load_data()
    strategy.backtest(start, end)


if __name__ == "__main__":
    main()
