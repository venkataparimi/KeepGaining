#!/usr/bin/env python3
"""
Intraday R2 Breakout Strategy Backtest

Tests profitability of trading R2 breakouts anytime during the day
Not limited to gap-ups at 9:15 AM
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
    entry_time: str
    entry_price: float
    fib_r2: float
    pnl_amount: float
    pnl_pct: float
    exit_reason: str


class IntradayR2Backtest:
    MIN_VOLUME_RATIO = 2.0
    TARGET_PCT = 10.0
    MAX_TRADES_PER_DAY = 5  # Limit to avoid overtrading
    
    def __init__(self):
        self.stock_data = {}
        
    def load_data(self):
        logger.info("Loading parquet files...")
        parquet_files = [f for f in os.listdir(PARQUET_DIR) if f.endswith('_EQUITY.parquet')]
        
        for file in parquet_files:
            symbol = file.replace('_EQUITY.parquet', '')
            try:
                df = pd.read_parquet(os.path.join(PARQUET_DIR, file))
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp')
                self.stock_data[symbol] = df
            except:
                continue
        
        logger.info(f"Loaded {len(self.stock_data)} stocks")
    
    def calculate_fib_r2(self, prev_high: float, prev_low: float, prev_close: float) -> float:
        pivot = (prev_high + prev_low + prev_close) / 3
        r2 = pivot + 0.618 * (prev_high - prev_low)
        return r2
    
    def find_intraday_breakouts(self, trade_date: date) -> List[dict]:
        """Find all R2 breakouts during the day"""
        breakouts = []
        
        for symbol, df in self.stock_data.items():
            try:
                # Get previous day
                prev_date = pd.Timestamp(trade_date) - pd.Timedelta(days=1)
                while prev_date.weekday() >= 5:
                    prev_date -= pd.Timedelta(days=1)
                
                prev_day = df[df.index.date == prev_date.date()]
                if prev_day.empty:
                    continue
                
                prev_high = prev_day['high'].max()
                prev_low = prev_day['low'].min()
                prev_close = prev_day['close'].iloc[-1]
                
                fib_r2 = self.calculate_fib_r2(prev_high, prev_low, prev_close)
                
                # Get today's candles
                trade_day = df[df.index.date == pd.Timestamp(trade_date).date()]
                if trade_day.empty:
                    continue
                
                # Check volume
                avg_volume = df['volume'].tail(375 * 5).mean() / 375
                if avg_volume == 0:
                    continue
                
                # Find first candle that breaks R2
                for idx, row in trade_day.iterrows():
                    if row['high'] > fib_r2 and row['close'] > fib_r2:
                        volume_ratio = row['volume'] / avg_volume
                        
                        if volume_ratio >= self.MIN_VOLUME_RATIO:
                            breakouts.append({
                                'symbol': symbol,
                                'entry_time': idx,
                                'entry_price': row['close'],
                                'fib_r2': fib_r2,
                                'breakout_pct': ((row['close'] - fib_r2) / fib_r2) * 100
                            })
                            break  # Only first breakout per stock per day
                
            except:
                continue
        
        # Sort by entry time and take top N
        breakouts.sort(key=lambda x: x['entry_time'])
        return breakouts[:self.MAX_TRADES_PER_DAY]
    
    def execute_trade(self, setup: dict, trade_date: date) -> TradeResult:
        """Execute trade from breakout point till EOD"""
        symbol = setup['symbol']
        df = self.stock_data[symbol]
        
        trade_day = df[df.index.date == pd.Timestamp(trade_date).date()]
        
        # Get candles from entry time onwards
        entry_time = setup['entry_time']
        remaining_candles = trade_day[trade_day.index >= entry_time]
        
        if remaining_candles.empty or len(remaining_candles) < 2:
            return None
        
        entry_spot = setup['entry_price']
        exit_spot = remaining_candles['close'].iloc[-1]
        exit_reason = 'EOD (2:30 PM)'
        
        # Check for 10% target
        for idx, row in remaining_candles.iloc[1:].iterrows():
            spot = row['close']
            spot_move = ((spot - entry_spot) / entry_spot) * 100
            option_pnl = spot_move * ATM_DELTA
            
            if option_pnl >= self.TARGET_PCT:
                exit_spot = spot
                exit_reason = 'Target (10%)'
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
            entry_time=entry_time.strftime('%H:%M'),
            entry_price=entry_spot,
            fib_r2=setup['fib_r2'],
            pnl_amount=pnl_amount,
            pnl_pct=option_pnl,
            exit_reason=exit_reason
        )
    
    def backtest(self, start_date: date, end_date: date):
        logger.info("Starting Intraday R2 backtest...")
        
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        all_results = []
        
        for trade_date in dates:
            breakouts = self.find_intraday_breakouts(trade_date)
            
            if breakouts:
                logger.info(f"{trade_date}: {len(breakouts)} breakouts - " + 
                          ", ".join([f"{b['symbol']} ({b['entry_time'].strftime('%H:%M')})" for b in breakouts]))
            
            for breakout in breakouts:
                result = self.execute_trade(breakout, trade_date)
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
        print("INTRADAY R2 BREAKOUT STRATEGY RESULTS")
        print("=" * 100)
        
        print(f"\nSTRATEGY:")
        print(f"  - R2 breakout anytime during the day")
        print(f"  - Volume >{self.MIN_VOLUME_RATIO}x average")
        print(f"  - Max {self.MAX_TRADES_PER_DAY} trades per day")
        print(f"  - {self.TARGET_PCT}% target, hold till EOD")
        
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
        
        print(f"\nCOMPARISON TO GAP-UP R2:")
        print(f"  Gap-up R2: 16 trades, Rs 5,363 net, Rs 335/trade")
        print(f"  Intraday R2: {len(results)} trades, Rs {net_pnl:,.0f} net, Rs {net_pnl/len(results):,.0f}/trade")
        
        # Show entry time distribution
        morning = len([r for r in results if int(r.entry_time.split(':')[0]) < 11])
        midday = len([r for r in results if 11 <= int(r.entry_time.split(':')[0]) < 13])
        afternoon = len([r for r in results if int(r.entry_time.split(':')[0]) >= 13])
        
        print(f"\nENTRY TIME DISTRIBUTION:")
        print(f"  Morning (9:15-11:00): {morning} trades")
        print(f"  Midday (11:00-13:00): {midday} trades")
        print(f"  Afternoon (13:00-15:30): {afternoon} trades")
        
        print("=" * 100)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, required=True)
    parser.add_argument('--end', type=str, required=True)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    strategy = IntradayR2Backtest()
    strategy.load_data()
    strategy.backtest(start, end)


if __name__ == "__main__":
    main()
