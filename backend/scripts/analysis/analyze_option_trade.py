"""
Options Trade Analyzer
Analyzes historical options trades and identifies which strategy triggered them
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger

DB_PATH = "keepgaining.db"
OPTIONS_DIR = Path("options_data")

class TradeAnalyzer:
    def __init__(self):
        self.strategies = {
            'Volume Rocket': self._check_volume_rocket_signal,
            'Bollinger Bands': self._check_bb_signal,
            'RSI Mean Reversion': self._check_rsi_signal,
            'VWAP Reversion': self._check_vwap_signal,
            'VWMA Reversion (20)': self._check_vwma_reversion,
            'VWMA Crossover (20/50)': self._check_vwma_crossover,
            'MACD Crossover': self._check_macd_signal,
            'EMA Crossover': self._check_ema_signal,
            'Supertrend': self._check_supertrend_signal
        }

    def _check_volume_rocket_signal(self, row, option_type):
        """Check Volume Rocket signal (Momentum Breakout)"""
        # Ensure vol_ma_20 exists (handled in analyze_trade)
        if 'vol_ma_20' not in row.index or pd.isna(row['vol_ma_20']):
            return None
            
        if option_type == 'CE':
            # Bullish Rocket: Vol > 3x, Price > Upper BB, RSI > 70, Uptrend
            if (row['volume'] > row['vol_ma_20'] * 3) and \
               (row['close'] > row['bb_upper']) and \
               (row['rsi_14'] > 70) and \
               (row['close'] > row['ema_200']):
                return f"Bullish: Volume Rocket! Vol {row['volume']} (>3x Avg), RSI {row['rsi_14']:.1f}"
        else: # PE
            # Bearish Rocket: Vol > 3x, Price < Lower BB, RSI < 30, Downtrend
            if (row['volume'] > row['vol_ma_20'] * 3) and \
               (row['close'] < row['bb_lower']) and \
               (row['rsi_14'] < 30) and \
               (row['close'] < row['ema_200']):
                return f"Bearish: Volume Rocket! Vol {row['volume']} (>3x Avg), RSI {row['rsi_14']:.1f}"
        return None
    
    def analyze_trade(self, stock, option_type, strike, entry_date, entry_price):
        """
        Analyze a potential options trade
        
        Args:
            stock: Stock name (e.g., 'RELIANCE', 'SBIN', 'Federal' for FEDERALBNK)
            option_type: 'CE' or 'PE'
            strike: Strike price (e.g., 250)
            entry_date: Entry date as string 'DD-MMM-YY' (e.g., '25-Nov-25')
            entry_price: Entry price (e.g., 7.50)
        """
        # Map common names to actual symbols
        stock_mapping = {
            'Federal': 'FEDERALBNK',
            'HDFC': 'HDFCBANK',
            'ICICI': 'ICICIBANK',
            'Axis': 'AXISBANK',
            'Kotak': 'KOTAKBANK'
        }
        
        stock = stock_mapping.get(stock, stock.upper())
        
        logger.info("="*80)
        logger.info(f"ANALYZING TRADE: {stock} {strike}{option_type} on {entry_date}")
        logger.info(f"Entry Price: ₹{entry_price}")
        logger.info("="*80)
        
        # Parse date
        try:
            if '-' in entry_date and len(entry_date.split('-')[0]) <= 2:
                entry_dt = pd.to_datetime(entry_date, format='%d-%b-%y')
            else:
                entry_dt = pd.to_datetime(entry_date)
        except:
            logger.error(f"❌ Invalid date format: {entry_date}")
            return None
        
        # Check if options data exists (try both folder structures)
        options_file = OPTIONS_DIR / "25NOV" / f"{stock}.csv"
        if not options_file.exists():
            # Try old format: STOCK_25NOV.csv in root
            options_file = OPTIONS_DIR / f"{stock}_25NOV.csv"
        
        if not options_file.exists():
            logger.error(f"❌ DATA UNAVAILABLE: No Nov options data for {stock}")
            logger.info(f"   Tried: options_data/25NOV/{stock}.csv")
            logger.info(f"   Tried: options_data/{stock}_25NOV.csv")
            return None
        
        # Load options data
        logger.info(f"\n✓ Options data found")
        options_df = pd.read_csv(options_file)
        options_df['timestamp'] = pd.to_datetime(options_df['timestamp'])
        
        # Filter for specific option
        option_symbol = f"NSE:{stock}25NOV{int(strike)}{option_type}"
        option_data = options_df[options_df['symbol'] == option_symbol].copy()
        
        if len(option_data) == 0:
            logger.error(f"❌ Option not found: {option_symbol}")
            logger.info(f"   Available strikes: {sorted(options_df['strike'].unique())}")
            return None
        
        # Filter for the specific day
        day_data = option_data[option_data['timestamp'].dt.date == entry_dt.date()]
        
        if len(day_data) == 0:
            logger.error(f"❌ No data for {entry_dt.date()}")
            available_dates = option_data['timestamp'].dt.date.unique()
            logger.info(f"   Available dates: {sorted(available_dates)}")
            return None
        
        logger.success(f"✓ Found {len(day_data)} candles for {entry_dt.date()}")
        
        # Find entry candle (closest to entry price)
        day_data['price_diff'] = abs(day_data['close'] - entry_price)
        entry_candle = day_data.loc[day_data['price_diff'].idxmin()]
        entry_time = entry_candle['timestamp']
        actual_entry_price = entry_candle['close']
        
        # Exit at market close (last candle of the day)
        exit_candle = day_data.iloc[-1]
        exit_price = exit_candle['close']
        exit_time = exit_candle['timestamp']
        
        pnl_pct = ((exit_price - actual_entry_price) / actual_entry_price) * 100
        
        logger.info(f"\n{'='*80}")
        logger.info("TRADE DETAILS")
        logger.info(f"{'='*80}")
        logger.info(f"Entry Time:      {entry_time}")
        logger.info(f"Entry Price:     ₹{actual_entry_price:.2f} (target: ₹{entry_price})")
        logger.info(f"Exit Time:       {exit_time}")
        logger.info(f"Exit Price:      ₹{exit_price:.2f}")
        logger.info(f"Day High:        ₹{day_data['high'].max():.2f}")
        logger.info(f"Day Low:         ₹{day_data['low'].min():.2f}")
        
        if pnl_pct > 0:
            logger.success(f"\nP&L: +{pnl_pct:.2f}% ✓")
        else:
            logger.error(f"\nP&L: {pnl_pct:.2f}% ✗")
        
        # Analyze stock signals at entry time
        logger.info(f"\n{'='*80}")
        logger.info("STRATEGY ANALYSIS")
        logger.info(f"{'='*80}")
        
        # Load stock data
        stock_symbol = f"NSE:{stock}-EQ"
        conn = sqlite3.connect(DB_PATH)
        stock_df = pd.read_sql_query(
            "SELECT * FROM candle_data WHERE symbol = ? ORDER BY timestamp",
            conn, params=(stock_symbol,)
        )
        conn.close()
        
        if len(stock_df) == 0:
            logger.warning(f"⚠ No stock data for {stock_symbol} - cannot analyze strategies")
            return {
                'stock': stock,
                'option': option_symbol,
                'entry_time': entry_time,
                'exit_time': exit_time,
                'entry_price': actual_entry_price,
                'exit_price': exit_price,
                'pnl_pct': pnl_pct,
                'triggered_strategies': []
            }
        
        stock_df['timestamp'] = pd.to_datetime(stock_df['timestamp'])
        
        # Calculate Volume MA for Volume Rocket strategy
        stock_df['vol_ma_20'] = stock_df['volume'].rolling(window=20).mean()
        
        # Find stock candle at entry time
        stock_entry = stock_df[stock_df['timestamp'] <= entry_dt].iloc[-1] if len(stock_df[stock_df['timestamp'] <= entry_dt]) > 0 else None
        
        if stock_entry is None:
            logger.warning("⚠ No stock data at entry time")
            return None
        
        logger.info(f"\nStock price at entry: ₹{stock_entry['close']:.2f}")
        logger.info(f"Stock timestamp: {stock_entry['timestamp']}")
        
        # Check all strategies
        triggered_strategies = []
        for strategy_name, check_func in self.strategies.items():
            signal = check_func(stock_entry, option_type)
            if signal:
                triggered_strategies.append(strategy_name)
                logger.success(f"✓ {strategy_name}: TRIGGERED")
                logger.info(f"  Signal: {signal}")
            else:
                logger.info(f"  {strategy_name}: No signal")
        
        if triggered_strategies:
            logger.info(f"\n{'='*80}")
            logger.success(f"🎯 STRATEGIES THAT TRIGGERED: {', '.join(triggered_strategies)}")
            logger.info(f"{'='*80}")
        else:
            logger.warning(f"\n⚠ No strategy triggered this trade")
        
        return {
            'stock': stock,
            'option': option_symbol,
            'entry_time': entry_candle['timestamp'],
            'exit_time': exit_candle['timestamp'],
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'triggered_strategies': triggered_strategies
        }
    
    def _check_bb_signal(self, row, option_type):
        """Check Bollinger Bands signal"""
        if option_type == 'CE':
            if row['close'] <= row['bb_lower']:
                return f"Bullish: Price ({row['close']:.2f}) at lower band ({row['bb_lower']:.2f})"
        else:  # PE
            if row['close'] >= row['bb_upper']:
                return f"Bearish: Price ({row['close']:.2f}) at upper band ({row['bb_upper']:.2f})"
        return None
    
    def _check_rsi_signal(self, row, option_type):
        """Check RSI signal"""
        if option_type == 'CE':
            if row['rsi_14'] < 30:
                return f"Bullish: RSI ({row['rsi_14']:.2f}) oversold"
        else:  # PE
            if row['rsi_14'] > 70:
                return f"Bearish: RSI ({row['rsi_14']:.2f}) overbought"
        return None
    
    def _check_vwap_signal(self, row, option_type):
        """Check VWAP signal"""
        if option_type == 'CE':
            if row['close'] < row['vwap']:
                return f"Bullish: Price ({row['close']:.2f}) below VWAP ({row['vwap']:.2f})"
        else:  # PE
            if row['close'] > row['vwap']:
                return f"Bearish: Price ({row['close']:.2f}) above VWAP ({row['vwap']:.2f})"
        return None
    
    def _check_macd_signal(self, row, option_type):
        """Check MACD signal"""
        if option_type == 'CE':
            if row['macd'] > row['macd_signal'] and row['macd_histogram'] > 0:
                return f"Bullish: MACD crossover"
        else:  # PE
            if row['macd'] < row['macd_signal'] and row['macd_histogram'] < 0:
                return f"Bearish: MACD crossover"
        return None
    
    def _check_ema_signal(self, row, option_type):
        """Check EMA signal"""
        if option_type == 'CE':
            if row['ema_9'] > row['ema_21']:
                return f"Bullish: EMA 9 ({row['ema_9']:.2f}) > EMA 21 ({row['ema_21']:.2f})"
        else:  # PE
            if row['ema_9'] < row['ema_21']:
                return f"Bearish: EMA 9 ({row['ema_9']:.2f}) < EMA 21 ({row['ema_21']:.2f})"
        return None
    
    
    def _check_vwma_reversion(self, row, option_type):
        """Check VWMA Reversion signal (similar to VWAP)"""
        if option_type == 'CE':
            if row['close'] < row['vwma_20']:
                deviation_pct = ((row['vwma_20'] - row['close']) / row['vwma_20']) * 100
                if deviation_pct > 0.3:  # At least 0.3% below VWMA
                    return f"Bullish: Price (₹{row['close']:.2f}) below VWMA20 (₹{row['vwma_20']:.2f}) by {deviation_pct:.2f}%"
        else:  # PE
            if row['close'] > row['vwma_20']:
                deviation_pct = ((row['close'] - row['vwma_20']) / row['vwma_20']) * 100
                if deviation_pct > 0.3:  # At least 0.3% above VWMA
                    return f"Bearish: Price (₹{row['close']:.2f}) above VWMA20 (₹{row['vwma_20']:.2f}) by {deviation_pct:.2f}%"
        return None
    
    def _check_vwma_crossover(self, row, option_type):
        """Check VWMA Crossover signal (VWMA20 vs VWMA50)"""
        if option_type == 'CE':
            if row['vwma_20'] > row['vwma_50']:
                return f"Bullish: VWMA20 (₹{row['vwma_20']:.2f}) > VWMA50 (₹{row['vwma_50']:.2f})"
        else:  # PE
            if row['vwma_20'] < row['vwma_50']:
                return f"Bearish: VWMA20 (₹{row['vwma_20']:.2f}) < VWMA50 (₹{row['vwma_50']:.2f})"
        return None
    
    def _check_supertrend_signal(self, row, option_type):
        """Check Supertrend signal"""
        if option_type == 'CE':
            if row['supertrend_direction'] == 1:
                return f"Bullish: Supertrend uptrend"
        else:  # PE
            if row['supertrend_direction'] == -1:
                return f"Bearish: Supertrend downtrend"
        return None


def main():
    """Example usage"""
    analyzer = TradeAnalyzer()
    
    # Example trade
    logger.info("EXAMPLE: Analyzing a sample trade\n")
    
    result = analyzer.analyze_trade(
        stock="RELIANCE",
        option_type="CE",
        strike=1300,
        entry_date="2025-11-20 10:00:00",
        exit_date="2025-11-20 15:00:00"
    )

if __name__ == "__main__":
    main()
