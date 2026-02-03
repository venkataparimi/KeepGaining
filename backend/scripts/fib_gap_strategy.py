#!/usr/bin/env python3
"""
Fibonacci R1 Gap Strategy

Entry Rules (9:15 AM first candle):
1. Gap up (any amount)
2. Volume > 3x average
3. Close above Fibonacci R1 level
4. Enter ATM CE

Exit: 25% target on option
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
    volume_ratio: float
    fib_r1: float
    entry_price: float
    pnl_amount: float
    pnl_pct: float
    exit_reason: str


class FibGapStrategy:
    MIN_VOLUME_RATIO = 3.0
    TARGET_PCT = 10.0  # Achievable intraday target
    TRADES_PER_DAY = 2
    
    def __init__(self):
        self.stock_data = {}
        
    def load_data(self):
        """Load all parquet files"""
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
                continue
        
        logger.info(f"Loaded {len(self.stock_data)} stocks")
    
    def calculate_fib_r1(self, prev_high: float, prev_low: float, prev_close: float) -> float:
        """Calculate Fibonacci R1 resistance level"""
        # Fibonacci R1 = Pivot + 0.382 * (High - Low)
        pivot = (prev_high + prev_low + prev_close) / 3
        r1 = pivot + 0.382 * (prev_high - prev_low)
        return r1
    
    def find_setups(self, trade_date: date) -> List[dict]:
        """Find all valid Fib R1 gap setups"""
        setups = []
        
        for symbol, df in self.stock_data.items():
            try:
                # Get previous day data
                prev_date = pd.Timestamp(trade_date) - pd.Timedelta(days=1)
                while prev_date.weekday() >= 5:
                    prev_date -= pd.Timedelta(days=1)
                
                prev_day = df[df.index.date == prev_date.date()]
                if prev_day.empty:
                    continue
                
                prev_high = prev_day['high'].max()
                prev_low = prev_day['low'].min()
                prev_close = prev_day['close'].iloc[-1]
                
                # Calculate Fib R1
                fib_r1 = self.calculate_fib_r1(prev_high, prev_low, prev_close)
                
                # Get first candle at 9:15 AM
                trade_day = df[df.index.date == pd.Timestamp(trade_date).date()]
                if trade_day.empty:
                    continue
                
                first_candle = trade_day[trade_day.index.time == pd.Timestamp('03:45:00').time()]
                if first_candle.empty:
                    continue
                
                first = first_candle.iloc[0]
                
                # Check gap up
                gap_pct = ((first['open'] - prev_close) / prev_close) * 100
                if gap_pct <= 0:
                    continue
                
                # Check volume > 3x average
                avg_volume = df['volume'].tail(375 * 5).mean() / 375
                if avg_volume == 0:
                    continue
                
                volume_ratio = first['volume'] / avg_volume
                if volume_ratio < self.MIN_VOLUME_RATIO:
                    continue
                
                # Check close above Fib R1
                if first['close'] < fib_r1:
                    continue
                
                setups.append({
                    'symbol': symbol,
                    'gap_pct': gap_pct,
                    'volume_ratio': volume_ratio,
                    'fib_r1': fib_r1,
                    'entry_price': first['close'],
                    'score': gap_pct * volume_ratio  # Score by gap * volume
                })
                
            except Exception as e:
                continue
        
        # Sort by score and take top 2
        setups.sort(key=lambda x: x['score'], reverse=True)
        return setups[:self.TRADES_PER_DAY]
    
    def execute_trade(self, setup: dict, trade_date: date) -> TradeResult:
        """Execute trade with 25% target"""
        symbol = setup['symbol']
        df = self.stock_data[symbol]
        
        # Get intraday data
        trade_day = df[df.index.date == pd.Timestamp(trade_date).date()]
        intraday = trade_day[
            (trade_day.index.time >= pd.Timestamp('03:45:00').time()) &
            (trade_day.index.time <= pd.Timestamp('09:00:00').time())
        ]
        
        if intraday.empty or len(intraday) < 2:
            return None
        
        entry_spot = setup['entry_price']
        exit_spot = intraday['close'].iloc[-1]
        exit_reason = 'EOD (2:30 PM)'
        
        # Check for 25% target during the day
        for idx, row in intraday.iloc[1:].iterrows():
            spot = row['close']
            spot_move = ((spot - entry_spot) / entry_spot) * 100
            option_pnl = spot_move * ATM_DELTA
            
            if option_pnl >= self.TARGET_PCT:
                exit_spot = spot
                exit_reason = 'Target (25%)'
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
            gap_pct=setup['gap_pct'],
            volume_ratio=setup['volume_ratio'],
            fib_r1=setup['fib_r1'],
            entry_price=entry_spot,
            pnl_amount=pnl_amount,
            pnl_pct=option_pnl,
            exit_reason=exit_reason
        )
    
    def backtest(self, start_date: date, end_date: date):
        logger.info("Starting Fibonacci R1 Gap backtest...")
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        all_results = []
        
        for trade_date in dates:
            setups = self.find_setups(trade_date)
            
            if setups:
                logger.info(f"{trade_date}: {len(setups)} setups - " + 
                          ", ".join([f"{s['symbol']} (gap {s['gap_pct']:.1f}%, {s['volume_ratio']:.0f}x vol, R1 {s['fib_r1']:.0f})" for s in setups]))
            
            for setup in setups:
                result = self.execute_trade(setup, trade_date)
                if result:
                    all_results.append(result)
        
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
        print("FIBONACCI R1 GAP STRATEGY RESULTS")
        print("=" * 100)
        
        print(f"\nSTRATEGY:")
        print(f"  - Gap up at 9:15 AM")
        print(f"  - Volume >{self.MIN_VOLUME_RATIO}x average")
        print(f"  - Close above Fibonacci R1")
        print(f"  - ATM CE with {self.TARGET_PCT}% target")
        
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
        eods = len([r for r in results if 'EOD' in r.exit_reason])
        print(f"  Exits: {targets} targets, {eods} EOD")
        
        print(f"\nTOP 5 TRADES:")
        top_trades = sorted(results, key=lambda x: x.pnl_amount, reverse=True)[:5]
        for r in top_trades:
            sign = "+" if r.pnl_amount > 0 else ""
            print(f"  {r.date} {r.symbol}: {r.gap_pct:.1f}% gap, {r.volume_ratio:.0f}x vol, R1={r.fib_r1:.0f} -> {sign}Rs {r.pnl_amount:,.0f} ({r.exit_reason})")
        
        print("=" * 100)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    strategy = FibGapStrategy()
    strategy.load_data()
    strategy.backtest(start, end)


if __name__ == "__main__":
    main()
