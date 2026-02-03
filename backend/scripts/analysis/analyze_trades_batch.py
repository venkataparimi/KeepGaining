"""Analyze multiple trades"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.analyze_option_trade import TradeAnalyzer

analyzer = TradeAnalyzer()

print("\n" + "="*80)
print("TRADE 1: DELHIVERY")
print("="*80)
analyzer.analyze_trade(
    stock="DELHIVERY",
    option_type="PE",
    strike=420,
    entry_date="24-Nov-25",
    entry_price=18.00
)

print("\n\n" + "="*80)
print("TRADE 2: AB CAPITAL")
print("="*80)
analyzer.analyze_trade(
    stock="ABCAPITAL",
    option_type="CE",
    strike=330,
    entry_date="25-Nov-25",
    entry_price=15.00
)
