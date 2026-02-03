"""
Parse trading symbols to extract strike and expiry
Format: "NIFTY 27000 CE 30 DEC 25"
"""
from datetime import datetime
import re

def parse_trading_symbol(trading_symbol):
    """
    Parse trading symbol to extract components
    Format: SYMBOL STRIKE TYPE DD MMM YY
    Example: "NIFTY 27000 CE 30 DEC 25"
    
    Returns: (strike, expiry_date, option_type)
    """
    try:
        parts = trading_symbol.strip().split()
        
        if len(parts) < 6:
            return None, None, None
        
        # Extract components
        # Format: SYMBOL STRIKE TYPE DD MMM YY
        strike = int(parts[1])
        option_type = parts[2]  # CE or PE
        day = int(parts[3])
        month_str = parts[4]
        year = int(parts[5])
        
        # Convert month
        month_map = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
            'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
            'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        
        month = month_map.get(month_str.upper())
        if not month:
            return None, None, None
        
        # Full year
        year_full = 2000 + year if year < 100 else year
        
        # Create date
        expiry_date = datetime(year_full, month, day).date()
        
        return strike, expiry_date, option_type
        
    except (ValueError, IndexError) as e:
        return None, None, None

# Test
if __name__ == "__main__":
    test_symbols = [
        "NIFTY 27000 CE 30 DEC 25",
        "BANKNIFTY 51200 PE 30 DEC 25",
        "NIFTY 24000 CE 26 DEC 24"
    ]
    
    for symbol in test_symbols:
        strike, expiry, opt_type = parse_trading_symbol(symbol)
        print(f"{symbol:40} -> Strike: {strike:6}, Expiry: {expiry}, Type: {opt_type}")
