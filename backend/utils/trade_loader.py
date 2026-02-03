"""
Load backtest trade data from CSV and serve via API
"""
import pandas as pd
import glob
from pathlib import Path

def load_latest_trades():
    """Load trades from the most recent backtest CSV file"""
    # Find all backtest CSV files
    csv_files = glob.glob('backtest_exit_*.csv')
    
    if not csv_files:
        print("No backtest CSV files found")
        return []
    
    # Get the most recent file
    latest_file = max(csv_files, key=lambda x: Path(x).stat().st_mtime)
    print(f"Loading trades from: {latest_file}")
    
    # Load CSV
    df = pd.read_csv(latest_file)
    
    # Convert to list of dictionaries
    trades = df.to_dict('records')
    
    print(f"Loaded {len(trades)} trades")
    return trades

def get_trades_by_month(month: str):
    """Get trades for a specific month (format: YYYY-MM)"""
    all_trades = load_latest_trades()
    
    if month == "all":
        return all_trades
    
    filtered = [t for t in all_trades if t['date'].startswith(month)]
    return filtered

def get_trades_by_type(trade_type: str):
    """Get trades by type (backtest, paper, live)"""
    all_trades = load_latest_trades()
    
    if trade_type == "all":
        return all_trades
    
    # For now, all loaded trades are backtest
    # In future, this will filter from database
    return [t for t in all_trades if t.get('trade_type', 'backtest') == trade_type]

if __name__ == "__main__":
    trades = load_latest_trades()
    print(f"\nSample trade:")
    if trades:
        print(trades[0])
