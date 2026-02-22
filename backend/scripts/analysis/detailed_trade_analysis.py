#!/usr/bin/env python3
"""
Generate detailed trade-by-trade analysis for Fibonacci R1 Gap Strategy
"""

import pandas as pd
import os
from datetime import datetime, date, timedelta

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
    'LAURUSLABS': 1700, 'NATIONALUM': 1700, 'IDEA': 10000, 'LTTS': 1000,
    'ESCORTS': 1500, 'UNIONBANK': 3500, 'BIOCON': 2000, 'PETRONET': 2000,
    'IEX': 3000, 'DEEPAKNTR': 300, 'IRB': 5000, 'AUBANK': 2000, 'GAIL': 3000,
    'KEC': 2000, 'PVRINOX': 500
}
DEFAULT_LOT_SIZE = 500
ATM_DELTA = 0.55

def calculate_fib_r1(prev_high, prev_low, prev_close):
    pivot = (prev_high + prev_low + prev_close) / 3
    r1 = pivot + 0.382 * (prev_high - prev_low)
    return r1

def analyze_trade(symbol, trade_date, stock_data):
    """Detailed analysis of single trade"""
    df = stock_data[symbol]
    
    # Get previous day
    prev_date = pd.Timestamp(trade_date) - pd.Timedelta(days=1)
    while prev_date.weekday() >= 5:
        prev_date -= pd.Timedelta(days=1)
    
    prev_day = df[df.index.date == prev_date.date()]
    if prev_day.empty:
        return None
    
    prev_high = prev_day['high'].max()
    prev_low = prev_day['low'].min()
    prev_close = prev_day['close'].iloc[-1]
    fib_r1 = calculate_fib_r1(prev_high, prev_low, prev_close)
    
    # Get trade day
    trade_day = df[df.index.date == pd.Timestamp(trade_date).date()]
    if trade_day.empty:
        return None
    
    first_candle = trade_day[trade_day.index.time == pd.Timestamp('03:45:00').time()]
    if first_candle.empty:
        return None
    
    first = first_candle.iloc[0]
    
    # Entry details
    gap_pct = ((first['open'] - prev_close) / prev_close) * 100
    avg_volume = df['volume'].tail(375 * 5).mean() / 375
    volume_ratio = first['volume'] / avg_volume if avg_volume > 0 else 0
    entry_price = first['close']
    
    # Get intraday movement
    intraday = trade_day[
        (trade_day.index.time >= pd.Timestamp('03:45:00').time()) &
        (trade_day.index.time <= pd.Timestamp('09:00:00').time())
    ]
    
    if intraday.empty:
        return None
    
    # Track max gain during day
    max_spot_gain = 0
    max_option_gain = 0
    
    for idx, row in intraday.iterrows():
        spot = row['close']
        spot_move = ((spot - entry_price) / entry_price) * 100
        option_pnl = spot_move * ATM_DELTA
        
        if option_pnl > max_option_gain:
            max_option_gain = option_pnl
            max_spot_gain = spot_move
    
    # Final exit
    exit_price = intraday['close'].iloc[-1]
    final_spot_move = ((exit_price - entry_price) / entry_price) * 100
    final_option_pnl = final_spot_move * ATM_DELTA
    
    lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
    premium = entry_price * 0.025
    pnl_amount = premium * (final_option_pnl / 100) * lot_size
    
    return {
        'date': trade_date,
        'symbol': symbol,
        'prev_close': prev_close,
        'fib_r1': fib_r1,
        'gap_pct': gap_pct,
        'volume_ratio': volume_ratio,
        'entry_price': entry_price,
        'exit_price': exit_price,
        'max_spot_gain': max_spot_gain,
        'max_option_gain': max_option_gain,
        'final_spot_move': final_spot_move,
        'final_option_pnl': final_option_pnl,
        'pnl_amount': pnl_amount,
        'lot_size': lot_size,
        'premium_estimate': premium
    }

def main():
    print("Loading data...")
    stock_data = {}
    parquet_files = [f for f in os.listdir(PARQUET_DIR) if f.endswith('_EQUITY.parquet')]
    
    for file in parquet_files:
        symbol = file.replace('_EQUITY.parquet', '')
        try:
            df = pd.read_parquet(os.path.join(PARQUET_DIR, file))
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp')
            stock_data[symbol] = df
        except:
            continue
    
    # Trades from backtest
    trades = [
        ('LTTS', date(2025, 12, 1)),
        ('ESCORTS', date(2025, 12, 1)),
        ('IDEA', date(2025, 12, 2)),
        ('UNIONBANK', date(2025, 12, 2)),
        ('DRREDDY', date(2025, 12, 3)),
        ('BIOCON', date(2025, 12, 3)),
        ('PETRONET', date(2025, 12, 4)),
        ('IEX', date(2025, 12, 4)),
        ('DEEPAKNTR', date(2025, 12, 5)),
        ('INFY', date(2025, 12, 5)),
        ('IRB', date(2025, 12, 10)),
        ('AUBANK', date(2025, 12, 10)),
        ('TATASTEEL', date(2025, 12, 11)),
        ('HINDZINC', date(2025, 12, 11)),
        ('LT', date(2025, 12, 12)),
        ('GAIL', date(2025, 12, 12)),
        ('KEC', date(2025, 12, 15)),
        ('PVRINOX', date(2025, 12, 15)),
    ]
    
    results = []
    for symbol, trade_date in trades:
        if symbol in stock_data:
            result = analyze_trade(symbol, trade_date, stock_data)
            if result:
                results.append(result)
    
    # Print detailed report
    print("\n" + "="*120)
    print("DETAILED TRADE-BY-TRADE ANALYSIS - FIBONACCI R1 GAP STRATEGY")
    print("="*120)
    
    total_pnl = 0
    for i, trade in enumerate(results, 1):
        print(f"\nTRADE #{i}: {trade['date']} - {trade['symbol']}")
        print("-" * 120)
        print(f"ENTRY CONDITIONS:")
        print(f"  Previous Close: Rs {trade['prev_close']:.2f}")
        print(f"  Fibonacci R1: Rs {trade['fib_r1']:.2f}")
        print(f"  Gap: {trade['gap_pct']:.2f}% (opened above prev close)")
        print(f"  Volume Ratio: {trade['volume_ratio']:.1f}x average")
        print(f"  Entry Price (9:15 AM close): Rs {trade['entry_price']:.2f}")
        print(f"  Entry above R1: {'YES' if trade['entry_price'] > trade['fib_r1'] else 'NO'}")
        
        print(f"\nINTRADAY MOVEMENT:")
        print(f"  Max Spot Gain: {trade['max_spot_gain']:.2f}%")
        print(f"  Max Option Gain: {trade['max_option_gain']:.2f}% (with 0.55 delta)")
        print(f"  Reached 10% target: {'YES' if trade['max_option_gain'] >= 10 else 'NO'}")
        
        print(f"\nEXIT (2:30 PM):")
        print(f"  Exit Price: Rs {trade['exit_price']:.2f}")
        print(f"  Final Spot Move: {trade['final_spot_move']:.2f}%")
        print(f"  Final Option P&L: {trade['final_option_pnl']:.2f}%")
        
        print(f"\nP&L CALCULATION:")
        print(f"  Lot Size: {trade['lot_size']}")
        print(f"  Estimated Premium: Rs {trade['premium_estimate']:.2f}")
        print(f"  P&L per lot: Rs {trade['premium_estimate'] * (trade['final_option_pnl']/100):.2f}")
        print(f"  Total P&L: Rs {trade['pnl_amount']:.2f}")
        print(f"  After Brokerage (Rs 55): Rs {trade['pnl_amount'] - 55:.2f}")
        
        total_pnl += trade['pnl_amount']
    
    print("\n" + "="*120)
    print("SUMMARY")
    print("="*120)
    print(f"Total Trades: {len(results)}")
    print(f"Gross P&L: Rs {total_pnl:.2f}")
    print(f"Brokerage: Rs {len(results) * 55}")
    print(f"NET P&L: Rs {total_pnl - (len(results) * 55):.2f}")
    print(f"\nTrades that reached 10% option target: {sum(1 for t in results if t['max_option_gain'] >= 10)}")
    print(f"Trades that reached 5% option target: {sum(1 for t in results if t['max_option_gain'] >= 5)}")
    print(f"Average max option gain: {sum(t['max_option_gain'] for t in results)/len(results):.2f}%")
    print("="*120)

if __name__ == "__main__":
    main()
