"""
Multi-Strategy Backtester - With Time Period Analysis
Tests strategies on different time periods
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger

DB_PATH = "keepgaining.db"
SYMBOL = "NSE:RELIANCE-EQ"
INITIAL_CAPITAL = 100000

class Strategy:
    def __init__(self, name):
        self.name = name
    
    def generate_signals(self, df):
        raise NotImplementedError

def load_data(symbol, days=None):
    """Load candle data with indicators"""
    conn = sqlite3.connect(DB_PATH)
    
    if days:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        query = f"SELECT * FROM candle_data WHERE symbol = ? AND timestamp >= ? ORDER BY timestamp"
        df = pd.read_sql_query(query, conn, params=(symbol, cutoff_date))
    else:
        query = "SELECT * FROM candle_data WHERE symbol = ? ORDER BY timestamp"
        df = pd.read_sql_query(query, conn, params=(symbol,))
    
    conn.close()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

# Strategy implementations
class RSIMeanReversion(Strategy):
    def generate_signals(self, df):
        df['signal'] = 0
        df.loc[df['rsi_14'] < 30, 'signal'] = 1
        df.loc[df['rsi_14'] > 70, 'signal'] = -1
        return df

class BollingerBands(Strategy):
    def generate_signals(self, df):
        df['signal'] = 0
        df.loc[(df['close'] <= df['bb_lower']) & (df['close'].shift(-1) > df['close']), 'signal'] = 1
        df.loc[df['close'] >= df['bb_upper'], 'signal'] = -1
        return df

class VWAPReversion(Strategy):
    def generate_signals(self, df):
        df['signal'] = 0
        df.loc[(df['close'] < df['vwap']) & (df['volume'] > df['volume'].rolling(20).mean()), 'signal'] = 1
        df.loc[df['close'] > df['vwap'] * 1.01, 'signal'] = -1
        return df

def backtest_strategy(strategy, df):
    """Simple backtest engine"""
    df = strategy.generate_signals(df.copy())
    
    position = 0
    entry_price = 0
    trades = []
    capital = INITIAL_CAPITAL
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        if row['signal'] == 1 and position == 0:
            position = capital / row['close']
            entry_price = row['close']
            
        elif row['signal'] == -1 and position > 0:
            exit_price = row['close']
            pnl = (exit_price - entry_price) * position
            capital += pnl
            
            trades.append({
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl': pnl,
                'return_pct': (exit_price - entry_price) / entry_price * 100
            })
            
            position = 0
    
    if len(trades) > 0:
        trades_df = pd.DataFrame(trades)
        win_rate = len(trades_df[trades_df['pnl'] > 0]) / len(trades_df) * 100
        total_return = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
        
        return {
            'strategy': strategy.name,
            'total_trades': len(trades),
            'win_rate': win_rate,
            'total_return': total_return,
            'final_capital': capital
        }
    else:
        return {
            'strategy': strategy.name,
            'total_trades': 0,
            'win_rate': 0,
            'total_return': 0,
            'final_capital': INITIAL_CAPITAL
        }

def main():
    logger.info("="*80)
    logger.info(f"STRATEGY BACKTEST: {SYMBOL}")
    logger.info("="*80)
    
    strategies = [
        RSIMeanReversion("RSI Mean Reversion"),
        BollingerBands("Bollinger Bands"),
        VWAPReversion("VWAP Reversion")
    ]
    
    # Test on different time periods
    periods = [
        ("Last 1 Month", 30),
        ("Last 3 Months", 90),
        ("All Data (6 Months)", None)
    ]
    
    for period_name, days in periods:
        logger.info(f"\n{'='*80}")
        logger.info(f"{period_name.upper()}")
        logger.info(f"{'='*80}")
        
        df = load_data(SYMBOL, days)
        logger.info(f"Data: {len(df):,} candles from {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        results = []
        for strategy in strategies:
            result = backtest_strategy(strategy, df)
            results.append(result)
        
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('total_return', ascending=False)
        
        print("\n" + results_df[['strategy', 'total_trades', 'win_rate', 'total_return']].to_string(index=False))
        
        # Show top strategy
        top = results_df.iloc[0]
        logger.success(f"\n🏆 Best: {top['strategy']} - {top['total_return']:.2f}% return ({top['total_trades']} trades)")

if __name__ == "__main__":
    main()
