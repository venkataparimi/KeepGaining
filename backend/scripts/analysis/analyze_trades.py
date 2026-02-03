"""
Universal Trade Analyzer - Just provide trade details
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.analyze_option_trade import TradeAnalyzer

# List available stocks
print("\nAvailable stocks with Nov options data:")
files = sorted([f.stem.replace('_25NOV', '') for f in Path('options_data').glob('*_25NOV.csv')])
for i, stock in enumerate(files, 1):
    print(f"{i:3d}. {stock}")

print(f"\nTotal: {len(files)} stocks\n")

# Analyze trades
analyzer = TradeAnalyzer()

# Add your trades here:
trades = [
    {"stock": "HEROMOTOCO", "type": "CE", "strike": 5600, "date": "17-Nov-25", "price": 115.00},
]

if not trades:
    print("No trades to analyze. Add trades to the 'trades' list above.")
    print("\nExample:")
    print('{"stock": "RELIANCE", "type": "CE", "strike": 1300, "date": "20-Nov-25", "price": 25.00}')
else:
    for i, trade in enumerate(trades, 1):
        print(f"\n{'='*80}")
        print(f"TRADE {i}/{len(trades)}")
        print(f"{'='*80}\n")
        
        analyzer.analyze_trade(
            stock=trade["stock"],
            option_type=trade["type"],
            strike=trade["strike"],
            entry_date=trade["date"],
            entry_price=trade["price"]
        )
