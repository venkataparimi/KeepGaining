"""Analyze Adani Ent trade"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.analyze_option_trade import TradeAnalyzer

analyzer = TradeAnalyzer()

analyzer.analyze_trade(
    stock="ADANIENT",
    option_type="CE",
    strike=2460,
    entry_date="20-Nov-25",
    entry_price=40.00
)
