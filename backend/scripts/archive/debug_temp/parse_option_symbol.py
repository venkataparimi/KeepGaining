"""
Quick fix: Extract strike and expiry from trading_symbol
Example: NIFTY24DEC24000CE -> Strike: 24000, Expiry: 2024-12-26
"""
import re
from datetime import datetime

def parse_option_symbol(trading_symbol):
    """
    Parse option trading symbol to extract strike and expiry
    Format: SYMBOL[YY][MMM][STRIKE][CE/PE]
    Example: NIFTY24DEC24000CE
    """
    # Pattern: SYMBOL + YY + MMM + STRIKE + CE/PE
    pattern = r'([A-Z]+)(\d{2})([A-Z]{3})(\d+)(CE|PE)'
    match = re.match(pattern, trading_symbol)
    
    if not match:
        return None, None, None
    
    symbol, year, month, strike, opt_type = match.groups()
    
    # Convert to expiry date (last Thursday of month)
    month_map = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }
    
    year_full = 2000 + int(year)
    month_num = month_map.get(month)
    
    if not month_num:
        return None, None, None
    
    # Find last Thursday (simplified - just use last week)
    from calendar import monthrange
    last_day = monthrange(year_full, month_num)[1]
    expiry_date = datetime(year_full, month_num, last_day).date()
    
    # Adjust to last Thursday (weekday 3)
    while expiry_date.weekday() != 3:
        expiry_date = expiry_date.replace(day=expiry_date.day - 1)
    
    return int(strike), expiry_date, opt_type

# Test
if __name__ == "__main__":
    test_symbols = [
        "NIFTY24DEC24000CE",
        "BANKNIFTY25JAN50000PE",
        "RELIANCE24NOV2500CE"
    ]
    
    for symbol in test_symbols:
        strike, expiry, opt_type = parse_option_symbol(symbol)
        print(f"{symbol:30} -> Strike: {strike}, Expiry: {expiry}, Type: {opt_type}")
