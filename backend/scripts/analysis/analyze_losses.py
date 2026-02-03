"""
Risk Analysis: Volume Rocket Strategy
Deep dive into the losing trades from the historical backtest.
"""
import pandas as pd
import numpy as np
from loguru import logger

def analyze_losses():
    logger.info("Analyzing Losses from 'historical_backtest_results.csv'...")
    
    try:
        df = pd.read_csv("historical_backtest_results.csv")
    except FileNotFoundError:
        logger.error("File not found. Please run backtest_historical.py first.")
        return

    # Filter for Losers
    losers = df[df['Stock Gain %'] <= 0].copy()
    winners = df[df['Stock Gain %'] > 0].copy()
    
    total_trades = len(df)
    total_losses = len(losers)
    loss_rate = (total_losses / total_trades) * 100
    
    # 1. Average & Max Loss
    avg_loss_stock = losers['Stock Gain %'].mean()
    max_loss_stock = losers['Stock Gain %'].min()
    
    avg_loss_opt = losers['Est Option %'].mean()
    max_loss_opt = losers['Est Option %'].min()
    
    # 2. Loss Distribution
    # Group losses into buckets: >2%, 1-2%, 0.5-1%, 0-0.5%
    # Bins must be increasing: [-100, -2, -1, -0.5, 0]
    bins = [-100, -2.0, -1.0, -0.5, 0.00001] # Added small epsilon to include 0
    labels = ['Huge (>-2%)', 'Large (-1% to -2%)', 'Medium (-0.5% to -1%)', 'Small (-0% to -0.5%)']
    losers['Loss Category'] = pd.cut(losers['Stock Gain %'], bins=bins, labels=labels)
    dist = losers['Loss Category'].value_counts().sort_index()
    
    # 3. Worst Stocks (Highest Failure Rate)
    stock_stats = df.groupby('Stock').agg(
        Total=('Stock', 'count'),
        Losses=('Stock Gain %', lambda x: (x <= 0).sum()),
        Avg_Loss=('Stock Gain %', lambda x: x[x <= 0].mean())
    )
    stock_stats['Failure Rate'] = (stock_stats['Losses'] / stock_stats['Total']) * 100
    worst_stocks = stock_stats[stock_stats['Total'] > 50].sort_values('Failure Rate', ascending=False).head(10)
    
    # 4. Streak Analysis (Max Consecutive Losses)
    # We need to sort by time to check streaks
    df['Entry Time'] = pd.to_datetime(df['Entry Time'])
    df = df.sort_values('Entry Time')
    
    df['Is Loss'] = df['Stock Gain %'] <= 0
    # Group consecutive True values
    df['Streak Group'] = (df['Is Loss'] != df['Is Loss'].shift()).cumsum()
    streaks = df[df['Is Loss']].groupby('Streak Group').size()
    max_losing_streak = streaks.max() if not streaks.empty else 0
    
    # Print Report
    logger.info(f"\n{'='*80}")
    logger.info("RISK PROFILE: LOSING TRADES ANALYSIS")
    logger.info(f"{'='*80}")
    
    print(f"Total Losing Trades:      {total_losses} ({loss_rate:.2f}%)")
    print(f"Average Loss (Stock):     {avg_loss_stock:.2f}%")
    print(f"Average Loss (Option):    {avg_loss_opt:.2f}% (Est. 10x)")
    print(f"Max Loss (Stock):         {max_loss_stock:.2f}%")
    print(f"Max Loss (Option):        {max_loss_opt:.2f}% (Est. 10x)")
    print(f"Max Losing Streak:        {max_losing_streak} trades (in a row)")
    
    logger.info(f"\n{'='*80}")
    logger.info("LOSS DISTRIBUTION (Stock %)")
    logger.info(f"{'='*80}")
    print(dist.to_string())
    
    logger.info(f"\n{'='*80}")
    logger.info("WORST STOCKS (Highest Failure Rate > 50 trades)")
    logger.info(f"{'='*80}")
    print(worst_stocks[['Failure Rate', 'Avg_Loss']].apply(lambda x: round(x, 2)).to_string())
    
    # Risk/Reward Ratio
    avg_win = winners['Stock Gain %'].mean()
    rr_ratio = abs(avg_win / avg_loss_stock)
    
    logger.info(f"\n{'='*80}")
    logger.info(f"RISK/REWARD METRICS")
    logger.info(f"{'='*80}")
    print(f"Avg Win:  +{avg_win:.2f}%")
    print(f"Avg Loss: {avg_loss_stock:.2f}%")
    print(f"R/R Ratio: 1:{rr_ratio:.2f}")
    
    if rr_ratio > 2:
        logger.success("✅ Excellent Risk/Reward (> 1:2)")
    elif rr_ratio > 1.5:
        logger.info("✅ Good Risk/Reward (> 1:1.5)")
    else:
        logger.warning("⚠️ Poor Risk/Reward (< 1:1.5) - Needs higher win rate")

if __name__ == "__main__":
    analyze_losses()
