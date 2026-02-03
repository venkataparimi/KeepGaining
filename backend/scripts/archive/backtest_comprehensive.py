"""
Comprehensive Strategy Backtester - Tests ALL signals to identify noise and accuracy
Tests multiple timeframes and calculates win rate
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from loguru import logger
from datetime import datetime, timedelta

DB_PATH = "keepgaining.db"

def backtest_strategy_comprehensive(stock, start_date, end_date, timeframe='1min', min_profit_target=10):
    """
    Comprehensive backtest - finds ALL signals and tests them
    
    Args:
        stock: Stock symbol (e.g., 'HEROMOTOCO')
        start_date: Start date for backtest
        end_date: End date for backtest
        timeframe: '1min', '3min', '5min', or '15min'
        min_profit_target: Minimum profit % to consider a trade successful
    """
    
    logger.info("="*120)
    logger.info(f"COMPREHENSIVE BACKTEST: {stock} | Timeframe: {timeframe} | Period: {start_date} to {end_date}")
    logger.info("="*120)
    
    # Load stock data
    stock_symbol = f"NSE:{stock}-EQ"
    conn = sqlite3.connect(DB_PATH)
    
    query = """
        SELECT * FROM candle_data 
        WHERE symbol = ? 
        AND timestamp BETWEEN ? AND ?
        ORDER BY timestamp
    """
    
    stock_df = pd.read_sql_query(
        query, conn, 
        params=(stock_symbol, start_date, end_date)
    )
    conn.close()
    
    if len(stock_df) == 0:
        logger.error(f"❌ No data for {stock_symbol}")
        return
    
    stock_df['timestamp'] = pd.to_datetime(stock_df['timestamp'])
    logger.success(f"✓ Loaded {len(stock_df):,} candles")
    
    # Define strategies with entry conditions
    strategies = {
        'VWAP Reversion': {
            'long': lambda row: row['close'] < row['vwap'] * 0.997,  # 0.3% below VWAP
            'short': lambda row: row['close'] > row['vwap'] * 1.003,  # 0.3% above VWAP
        },
        'VWMA20 Reversion': {
            'long': lambda row: row['close'] < row['vwma_20'] * 0.997,
            'short': lambda row: row['close'] > row['vwma_20'] * 1.003,
        },
        'VWMA22 Reversion': {
            'long': lambda row: row['close'] < row['vwma_22'] * 0.997,
            'short': lambda row: row['close'] > row['vwma_22'] * 1.003,
        },
        'Bollinger Bands': {
            'long': lambda row: row['close'] <= row['bb_lower'],
            'short': lambda row: row['close'] >= row['bb_upper'],
        },
        'RSI Mean Reversion': {
            'long': lambda row: row['rsi_14'] < 30,
            'short': lambda row: row['rsi_14'] > 70,
        },
    }
    
    results = {}
    
    for strategy_name, conditions in strategies.items():
        logger.info(f"\n{'='*120}")
        logger.info(f"Testing: {strategy_name}")
        logger.info(f"{'='*120}")
        
        trades = []
        
        # Find all signals
        for i in range(len(stock_df) - 1):
            row = stock_df.iloc[i]
            
            # Check for long signal
            if conditions['long'](row):
                entry_price = row['close']
                entry_time = row['timestamp']
                
                # Exit at end of day or after X candles
                exit_idx = min(i + 30, len(stock_df) - 1)  # Max 30 candles (30 min for 1-min TF)
                
                # Find day end
                day_end_idx = i
                for j in range(i + 1, len(stock_df)):
                    if stock_df.iloc[j]['timestamp'].date() != entry_time.date():
                        break
                    day_end_idx = j
                
                exit_idx = min(exit_idx, day_end_idx)
                exit_row = stock_df.iloc[exit_idx]
                
                # Calculate P&L
                exit_price = exit_row['close']
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                
                trades.append({
                    'direction': 'LONG',
                    'entry_time': entry_time,
                    'entry_price': entry_price,
                    'exit_time': exit_row['timestamp'],
                    'exit_price': exit_price,
                    'pnl': pnl_pct,
                    'duration_candles': exit_idx - i,
                    'success': pnl_pct >= min_profit_target
                })
            
            # Check for short signal
            elif conditions['short'](row):
                entry_price = row['close']
                entry_time = row['timestamp']
                
                exit_idx = min(i + 30, len(stock_df) - 1)
                
                # Find day end
                day_end_idx = i
                for j in range(i + 1, len(stock_df)):
                    if stock_df.iloc[j]['timestamp'].date() != entry_time.date():
                        break
                    day_end_idx = j
                
                exit_idx = min(exit_idx, day_end_idx)
                exit_row = stock_df.iloc[exit_idx]
                
                # Calculate P&L (inverse for short)
                exit_price = exit_row['close']
                pnl_pct = ((entry_price - exit_price) / entry_price) * 100
                
                trades.append({
                    'direction': 'SHORT',
                    'entry_time': entry_time,
                    'entry_price': entry_price,
                    'exit_time': exit_row['timestamp'],
                    'exit_price': exit_price,
                    'pnl': pnl_pct,
                    'duration_candles': exit_idx - i,
                    'success': pnl_pct >= min_profit_target
                })
        
        # Calculate statistics
        if len(trades) > 0:
            df_trades = pd.DataFrame(trades)
            
            total_trades = len(trades)
            winning_trades = len(df_trades[df_trades['success']])
            losing_trades = total_trades - winning_trades
            win_rate = (winning_trades / total_trades) * 100
            
            avg_win = df_trades[df_trades['pnl'] > 0]['pnl'].mean() if len(df_trades[df_trades['pnl'] > 0]) > 0 else 0
            avg_loss = df_trades[df_trades['pnl'] < 0]['pnl'].mean() if len(df_trades[df_trades['pnl'] < 0]) > 0 else 0
            
            total_pnl = df_trades['pnl'].sum()
            avg_pnl = df_trades['pnl'].mean()
            
            results[strategy_name] = {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'total_pnl': total_pnl,
                'avg_pnl': avg_pnl,
                'trades': df_trades
            }
            
            logger.info(f"Total Signals:    {total_trades}")
            logger.info(f"Winning Trades:   {winning_trades} ({win_rate:.2f}%)")
            logger.info(f"Losing Trades:    {losing_trades}")
            logger.info(f"Avg Win:          +{avg_win:.2f}%")
            logger.info(f"Avg Loss:         {avg_loss:.2f}%")
            logger.info(f"Total P&L:        {total_pnl:.2f}%")
            logger.info(f"Avg P&L/Trade:    {avg_pnl:.2f}%")
            
            if win_rate >= 50:
                logger.success(f"✓ Good win rate!")
            else:
                logger.warning(f"⚠ Low win rate - high noise!")
        else:
            logger.warning(f"No signals found for {strategy_name}")
    
    # Summary comparison
    if results:
        logger.info(f"\n{'='*120}")
        logger.info("STRATEGY COMPARISON SUMMARY")
        logger.info(f"{'='*120}\n")
        
        summary_data = []
        for name, stats in results.items():
            summary_data.append({
                'Strategy': name,
                'Signals': stats['total_trades'],
                'Win Rate': f"{stats['win_rate']:.1f}%",
                'Avg Win': f"+{stats['avg_win']:.2f}%",
                'Avg Loss': f"{stats['avg_loss']:.2f}%",
                'Total P&L': f"{stats['total_pnl']:.2f}%",
                'Avg P&L': f"{stats['avg_pnl']:.2f}%"
            })
        
        df_summary = pd.DataFrame(summary_data)
        print(df_summary.to_string(index=False))
        
        # Best strategy
        best = max(results.items(), key=lambda x: x[1]['win_rate'])
        logger.info(f"\n{'='*120}")
        logger.success(f"🏆 BEST WIN RATE: {best[0]} with {best[1]['win_rate']:.2f}% accuracy")
        logger.info(f"{'='*120}")
    
    return results

# Test on Hero Motors
backtest_strategy_comprehensive(
    stock="HEROMOTOCO",
    start_date="2025-11-01",
    end_date="2025-11-25",
    timeframe="1min",
    min_profit_target=0.5  # Lower target for stock scalping (0.5% is good for 1-min)
)
