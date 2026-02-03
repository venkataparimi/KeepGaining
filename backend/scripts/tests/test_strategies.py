"""
Multi-Strategy Backtester - Test 6 Famous Strategies on RELIANCE
Compares performance of different strategies on the same stock
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from loguru import logger

DB_PATH = "keepgaining.db"
SYMBOL = "NSE:RELIANCE-EQ"
INITIAL_CAPITAL = 100000  # ₹1 Lakh

class Strategy:
    """Base strategy class"""
    def __init__(self, name):
        self.name = name
        self.positions = []
        self.capital = INITIAL_CAPITAL
        self.trades = []
    
    def generate_signals(self, df):
        """Override this method in each strategy"""
        raise NotImplementedError

def load_data(symbol):
    """Load candle data with indicators"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM candle_data WHERE symbol = ? ORDER BY timestamp",
        conn,
        params=(symbol,)
    )
    conn.close()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

# Strategy 1: RSI Mean Reversion
class RSIMeanReversion(Strategy):
    def generate_signals(self, df):
        df['signal'] = 0
        df.loc[df['rsi_14'] < 30, 'signal'] = 1  # Buy oversold
        df.loc[df['rsi_14'] > 70, 'signal'] = -1  # Sell overbought
        return df

# Strategy 2: MACD Crossover
class MACDCrossover(Strategy):
    def generate_signals(self, df):
        df['signal'] = 0
        df['macd_cross'] = np.where(df['macd'] > df['macd_signal'], 1, -1)
        df['signal'] = df['macd_cross'].diff()
        return df

# Strategy 3: Bollinger Band Breakout
class BollingerBands(Strategy):
    def generate_signals(self, df):
        df['signal'] = 0
        # Buy when price touches lower band
        df.loc[(df['close'] <= df['bb_lower']) & (df['close'].shift(-1) > df['close']), 'signal'] = 1
        # Sell when price touches upper band
        df.loc[df['close'] >= df['bb_upper'], 'signal'] = -1
        return df

# Strategy 4: EMA Crossover (9/21)
class EMACrossover(Strategy):
    def generate_signals(self, df):
        df['signal'] = 0
        df['ema_cross'] = np.where(df['ema_9'] > df['ema_21'], 1, -1)
        df['signal'] = df['ema_cross'].diff()
        return df

# Strategy 5: Supertrend
class SupertrendStrategy(Strategy):
    def generate_signals(self, df):
        df['signal'] = df['supertrend_direction'].diff()
        return df

# Strategy 6: VWAP Reversion
class VWAPReversion(Strategy):
    def generate_signals(self, df):
        df['signal'] = 0
        # Buy below VWAP with volume confirmation
        df.loc[(df['close'] < df['vwap']) & (df['volume'] > df['volume'].rolling(20).mean()), 'signal'] = 1
        # Sell above VWAP
        df.loc[df['close'] > df['vwap'] * 1.01, 'signal'] = -1
        return df

def backtest_strategy(strategy, df):
    """Simple backtest engine"""
    df = strategy.generate_signals(df.copy())
    
    position = 0
    entry_price = 0
    trades = []
    equity_curve = []
    capital = INITIAL_CAPITAL
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        # Entry signal
        if row['signal'] == 1 and position == 0:
            position = capital / row['close']
            entry_price = row['close']
            
        # Exit signal
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
        
        # Track equity
        current_value = capital + (position * row['close'] if position > 0 else 0)
        equity_curve.append(current_value)
    
    # Calculate metrics
    if len(trades) > 0:
        trades_df = pd.DataFrame(trades)
        win_rate = len(trades_df[trades_df['pnl'] > 0]) / len(trades_df) * 100
        avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if len(trades_df[trades_df['pnl'] > 0]) > 0 else 0
        avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if len(trades_df[trades_df['pnl'] < 0]) > 0 else 0
        total_return = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
        
        return {
            'strategy': strategy.name,
            'total_trades': len(trades),
            'win_rate': win_rate,
            'total_return': total_return,
            'final_capital': capital,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': abs(avg_win / avg_loss) if avg_loss != 0 else 0
        }
    else:
        return {
            'strategy': strategy.name,
            'total_trades': 0,
            'win_rate': 0,
            'total_return': 0,
            'final_capital': INITIAL_CAPITAL,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0
        }

def main():
    logger.info("="*80)
    logger.info(f"MULTI-STRATEGY BACKTEST: {SYMBOL}")
    logger.info("="*80)
    
    # Load data
    logger.info("\nLoading data...")
    df = load_data(SYMBOL)
    logger.info(f"Loaded {len(df):,} candles from {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    # Define strategies
    strategies = [
        RSIMeanReversion("RSI Mean Reversion"),
        MACDCrossover("MACD Crossover"),
        BollingerBands("Bollinger Bands"),
        EMACrossover("EMA 9/21 Crossover"),
        SupertrendStrategy("Supertrend"),
        VWAPReversion("VWAP Reversion")
    ]
    
    # Run backtests
    logger.info(f"\nRunning {len(strategies)} strategies...\n")
    results = []
    
    for strategy in strategies:
        logger.info(f"Testing {strategy.name}...")
        result = backtest_strategy(strategy, df)
        results.append(result)
    
    # Display results
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('total_return', ascending=False)
    
    logger.info("\n" + "="*80)
    logger.info("RESULTS SUMMARY")
    logger.info("="*80)
    
    print("\n" + results_df.to_string(index=False))
    
    logger.info("\n" + "="*80)
    logger.info("TOP 3 STRATEGIES:")
    logger.info("="*80)
    
    for idx, row in results_df.head(3).iterrows():
        logger.success(f"\n{idx+1}. {row['strategy']}")
        logger.info(f"   Return: {row['total_return']:.2f}%")
        logger.info(f"   Trades: {row['total_trades']}")
        logger.info(f"   Win Rate: {row['win_rate']:.1f}%")
        logger.info(f"   Profit Factor: {row['profit_factor']:.2f}")

if __name__ == "__main__":
    main()
