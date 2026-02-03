"""Quick trade analysis"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.analyze_option_trade import TradeAnalyzer

analyzer = TradeAnalyzer()

# Federal Bank trade from image
analyzer.analyze_trade(
    stock="Federal",
    option_type="CE",
    strike=250,
    entry_date="25-Nov-25",
    entry_price=7.50
)
