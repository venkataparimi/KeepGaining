"""
Strategy Comparison Tool - Compare performance of different strategies on same trade
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from loguru import logger

DB_PATH = "keepgaining.db"
OPTIONS_DIR = Path("options_data")

def compare_strategies(stock, option_type, strike, trade_date):
    """Compare all strategies for a given trade"""
    
    # Map stock names
    stock_mapping = {
        'Federal': 'FEDERALBNK',
        'HDFC': 'HDFCBANK',
        'ICICI': 'ICICIBANK',
        'Axis': 'AXISBANK',
        'Kotak': 'KOTAKBANK'
    }
    stock = stock_mapping.get(stock, stock.upper())
    
    logger.info("="*100)
    logger.info(f"STRATEGY COMPARISON: {stock} {strike}{option_type} on {trade_date}")
    logger.info("="*100)
    
    # Parse date
    if '-' in trade_date and len(trade_date.split('-')[0]) <= 2:
        trade_dt = pd.to_datetime(trade_date, format='%d-%b-%y')
    else:
        trade_dt = pd.to_datetime(trade_date)
    
    # Load options data
    options_file = OPTIONS_DIR / "25NOV" / f"{stock}.csv"
    if not options_file.exists():
        options_file = OPTIONS_DIR / f"{stock}_25NOV.csv"
    
    if not options_file.exists():
        logger.error(f"❌ No options data for {stock}")
        return
    
    options_df = pd.read_csv(options_file)
    options_df['timestamp'] = pd.to_datetime(options_df['timestamp'])
    
    # Filter for specific option and day
    option_symbol = f"NSE:{stock}25NOV{int(strike)}{option_type}"
    day_data = options_df[
        (options_df['symbol'] == option_symbol) & 
        (options_df['timestamp'].dt.date == trade_dt.date())
    ].copy()
    
    if len(day_data) == 0:
        logger.error(f"❌ No data for {trade_dt.date()}")
        return
    
    # Load stock data
    stock_symbol = f"NSE:{stock}-EQ"
    conn = sqlite3.connect(DB_PATH)
    stock_df = pd.read_sql_query(
        "SELECT * FROM candle_data WHERE symbol = ? ORDER BY timestamp",
        conn, params=(stock_symbol,)
    )
    conn.close()
    
    if len(stock_df) == 0:
        logger.error(f"❌ No stock data for {stock_symbol}")
        return
    
    stock_df['timestamp'] = pd.to_datetime(stock_df['timestamp'])
    
    # Filter stock data for the trade day
    stock_day = stock_df[stock_df['timestamp'].dt.date == trade_dt.date()].copy()
    
    if len(stock_day) == 0:
        logger.warning("⚠ No stock data for this day, using previous day")
        stock_day = stock_df[stock_df['timestamp'] <= trade_dt].tail(375).copy()
    
    # Merge stock and option data by timestamp
    merged = pd.merge_asof(
        day_data.sort_values('timestamp'),
        stock_day[['timestamp', 'close', 'vwap', 'vwma_20', 'vwma_22', 'vwma_31', 'vwma_50', 
                   'bb_lower', 'bb_upper', 'rsi_14', 'ema_9', 'ema_21']],
        on='timestamp',
        direction='backward',
        suffixes=('_opt', '_stock')
    )
    
    # Define strategies
    strategies = []
    
    # 1. VWAP Reversion
    if option_type == 'CE':
        vwap_signals = merged[merged['close_stock'] < merged['vwap']]
    else:
        vwap_signals = merged[merged['close_stock'] > merged['vwap']]
    
    if len(vwap_signals) > 0:
        entry = vwap_signals.iloc[0]
        exit_candle = day_data.iloc[-1]
        pnl = ((exit_candle['close'] - entry['close_opt']) / entry['close_opt']) * 100
        strategies.append({
            'name': 'VWAP Reversion',
            'entry_time': entry['timestamp'],
            'entry_price': entry['close_opt'],
            'exit_price': exit_candle['close'],
            'pnl': pnl,
            'stock_price': entry['close_stock'],
            'signal': f"Price {entry['close_stock']:.2f} vs VWAP {entry['vwap']:.2f}"
        })
    
    # 2-5. VWMA Reversion (20, 22, 31, 50)
    for period in [20, 22, 31, 50]:
        vwma_col = f'vwma_{period}'
        if option_type == 'CE':
            vwma_signals = merged[merged['close_stock'] < merged[vwma_col]]
        else:
            vwma_signals = merged[merged['close_stock'] > merged[vwma_col]]
        
        if len(vwma_signals) > 0:
            entry = vwma_signals.iloc[0]
            exit_candle = day_data.iloc[-1]
            pnl = ((exit_candle['close'] - entry['close_opt']) / entry['close_opt']) * 100
            strategies.append({
                'name': f'VWMA{period} Reversion',
                'entry_time': entry['timestamp'],
                'entry_price': entry['close_opt'],
                'exit_price': exit_candle['close'],
                'pnl': pnl,
                'stock_price': entry['close_stock'],
                'signal': f"Price {entry['close_stock']:.2f} vs VWMA{period} {entry[vwma_col]:.2f}"
            })
    
    # 6. Bollinger Bands
    if option_type == 'CE':
        bb_signals = merged[merged['close_stock'] <= merged['bb_lower']]
    else:
        bb_signals = merged[merged['close_stock'] >= merged['bb_upper']]
    
    if len(bb_signals) > 0:
        entry = bb_signals.iloc[0]
        exit_candle = day_data.iloc[-1]
        pnl = ((exit_candle['close'] - entry['close_opt']) / entry['close_opt']) * 100
        strategies.append({
            'name': 'Bollinger Bands',
            'entry_time': entry['timestamp'],
            'entry_price': entry['close_opt'],
            'exit_price': exit_candle['close'],
            'pnl': pnl,
            'stock_price': entry['close_stock'],
            'signal': f"Price at {'lower' if option_type == 'CE' else 'upper'} band"
        })
    
    # 7. RSI Mean Reversion
    if option_type == 'CE':
        rsi_signals = merged[merged['rsi_14'] < 30]
    else:
        rsi_signals = merged[merged['rsi_14'] > 70]
    
    if len(rsi_signals) > 0:
        entry = rsi_signals.iloc[0]
        exit_candle = day_data.iloc[-1]
        pnl = ((exit_candle['close'] - entry['close_opt']) / entry['close_opt']) * 100
        strategies.append({
            'name': 'RSI Mean Reversion',
            'entry_time': entry['timestamp'],
            'entry_price': entry['close_opt'],
            'exit_price': exit_candle['close'],
            'pnl': pnl,
            'stock_price': entry['close_stock'],
            'signal': f"RSI {entry['rsi_14']:.2f}"
        })
    
    # Sort by P&L (best first)
    strategies.sort(key=lambda x: x['pnl'], reverse=True)
    
    # Create DataFrame for tabular display
    df = pd.DataFrame(strategies)
    df['entry_time'] = df['entry_time'].dt.strftime('%H:%M')
    df['entry_price'] = df['entry_price'].apply(lambda x: f"Rs.{x:.2f}")
    df['exit_price'] = df['exit_price'].apply(lambda x: f"Rs.{x:.2f}")
    df['pnl'] = df['pnl'].apply(lambda x: f"+{x:.2f}%" if x > 0 else f"{x:.2f}%")
    
    # Rename columns for display
    df_display = df[['name', 'entry_time', 'entry_price', 'exit_price', 'pnl', 'signal']].copy()
    df_display.columns = ['Strategy', 'Entry Time', 'Entry Price', 'Exit Price', 'P&L', 'Signal']
    df_display.insert(0, 'Rank', range(1, len(df_display) + 1))
    
    # Display table
    logger.info(f"\n{'='*120}")
    logger.info(f"STRATEGY PERFORMANCE COMPARISON - SORTED BY P&L")
    logger.info(f"{'='*120}\n")
    
    print(df_display.to_string(index=False, max_colwidth=50))
    
    # Summary
    if strategies:
        best = strategies[0]  # Already sorted by P&L
        earliest_idx = min(range(len(strategies)), key=lambda i: pd.to_datetime(f"2025-11-17 {strategies[i]['entry_time']}"))
        earliest = strategies[earliest_idx]
        
        logger.info(f"\n{'='*120}")
        logger.success(f"🏆 BEST PERFORMER: {best['name']} with {best['pnl']} profit")
        logger.info(f"⏰ EARLIEST SIGNAL: {earliest['name']} at {earliest['entry_time']}")
        
        # Calculate time advantage
        if best['name'] != earliest['name']:
            logger.warning(f"⚠️  Note: Earliest signal ({earliest['name']}) may not be the most profitable!")
        
        logger.info(f"{'='*120}")


# Test with Hero Motors
compare_strategies(
    stock="HEROMOTOCO",
    option_type="CE",
    strike=5600,
    trade_date="17-Nov-25"
)
