"""
Update strategy_trades with correct P&L amounts based on actual lot sizes.
"""
import asyncio
import asyncpg

# F&O Stock Lot Sizes (as of 2024-2025)
LOT_SIZES = {
    'ABB': 250, 'ABCAPITAL': 5400, 'ABFRL': 2600, 'ACC': 300, 'ADANIENT': 500,
    'ADANIGREEN': 250, 'ADANIPORTS': 1250, 'ALKEM': 125, 'AMBUJACEM': 1100,
    'APOLLOHOSP': 125, 'APOLLOTYRE': 1700, 'ASHOKLEY': 4500, 'ASIANPAINT': 300,
    'ASTRAL': 275, 'ATUL': 75, 'AUBANK': 1000, 'AUROPHARMA': 500,
    'AXISBANK': 625, 'BAJAJ-AUTO': 125, 'BAJAJFINSV': 500, 'BAJFINANCE': 125,
    'BALKRISIND': 300, 'BALRAMCHIN': 1600, 'BANDHANBNK': 2700, 'BANKBARODA': 2925,
    'BATAINDIA': 313, 'BEL': 3500, 'BERGEPAINT': 1100, 'BHARATFORG': 500,
    'BHARTIARTL': 475, 'BHEL': 2850, 'BIOCON': 2700, 'BPCL': 900,
    'BRITANNIA': 200, 'BSOFT': 1350, 'CANBK': 6750, 'CANFINHOME': 975,
    'CHAMBLFERT': 1500, 'CHOLAFIN': 625, 'CIPLA': 650, 'COALINDIA': 1050,
    'COFORGE': 150, 'COLPAL': 175, 'CONCOR': 625, 'COROMANDEL': 575,
    'CROMPTON': 1375, 'CUB': 4000, 'CUMMINSIND': 375, 'DABUR': 1100,
    'DALBHARAT': 425, 'DEEPAKNTR': 400, 'DELTACORP': 2800, 'DIVISLAB': 175,
    'DIXON': 125, 'DLF': 825, 'DRREDDY': 125, 'EICHERMOT': 225,
    'ESCORTS': 250, 'EXIDEIND': 1600, 'FEDERALBNK': 5000, 'FSL': 4600,
    'GAIL': 3075, 'GLENMARK': 1225, 'GMRINFRA': 11250, 'GNFC': 1600,
    'GODREJCP': 500, 'GODREJPROP': 325, 'GRANULES': 1600, 'GRASIM': 475,
    'GUJGASLTD': 1000, 'HAL': 175, 'HAVELLS': 475, 'HCLTECH': 350,
    'HDFC': 300, 'HDFCAMC': 300, 'HDFCBANK': 550, 'HDFCLIFE': 1100,
    'HEROMOTOCO': 300, 'HINDALCO': 1075, 'HINDCOPPER': 2950, 'HINDPETRO': 1575,
    'HINDUNILVR': 300, 'ICICIBANK': 700, 'ICICIGI': 325, 'ICICIPRULI': 1500,
    'IDEA': 50000, 'IDFC': 7500, 'IDFCFIRSTB': 7500, 'IEX': 3750,
    'IGL': 1375, 'INDHOTEL': 1375, 'INDIACEM': 3000, 'INDIAMART': 200,
    'INDIGO': 300, 'INDUSINDBK': 300, 'INDUSTOWER': 3150, 'INFY': 400,
    'IOC': 3250, 'IPCALAB': 725, 'IRCTC': 875, 'ITC': 1600,
    'JINDALSTEL': 500, 'JKCEMENT': 175, 'JSWSTEEL': 550, 'JUBLFOOD': 375,
    'KOTAKBANK': 400, 'L&TFH': 5836, 'LALPATHLAB': 375, 'LAURUSLABS': 1700,
    'LICHSGFIN': 1000, 'LT': 150, 'LTIM': 150, 'LTTS': 100,
    'LUPIN': 425, 'M&M': 700, 'M&MFIN': 2500, 'MANAPPURAM': 4000,
    'MARICO': 800, 'MARUTI': 100, 'MCDOWELL-N': 625, 'MCX': 400,
    'METROPOLIS': 450, 'MFSL': 650, 'MGL': 600, 'MOTHERSON': 5000,
    'MPHASIS': 275, 'MRF': 10, 'MUTHOOTFIN': 375, 'NAM-INDIA': 1500,
    'NATIONALUM': 4500, 'NAUKRI': 125, 'NAVINFLUOR': 150, 'NCC': 4000,
    'NESTLEIND': 50, 'NMDC': 4000, 'NTPC': 2700, 'OBEROIRLTY': 525,
    'OFSS': 100, 'ONGC': 2925, 'PAGEIND': 15, 'PEL': 1000,
    'PERSISTENT': 150, 'PETRONET': 3000, 'PFC': 3200, 'PIDILITIND': 350,
    'PIIND': 200, 'PNB': 8000, 'POLYCAB': 175, 'POWERGRID': 2700,
    'PVRINOX': 500, 'RAIN': 2800, 'RAMCOCEM': 700, 'RBLBANK': 3800,
    'RECLTD': 3000, 'RELIANCE': 250, 'SAIL': 4750, 'SBICARD': 800,
    'SBILIFE': 750, 'SBIN': 750, 'SHREECEM': 25, 'SHRIRAMFIN': 300,
    'SIEMENS': 225, 'SRF': 375, 'STAR': 550, 'SUNPHARMA': 350,
    'SUNTV': 1250, 'SYNGENE': 1000, 'TATACHEM': 400, 'TATACOMM': 500,
    'TATACONSUM': 500, 'TATAELXSI': 125, 'TATAMOTORS': 550, 'TATAPOWER': 2025,
    'TATASTEEL': 550, 'TCS': 175, 'TECHM': 600, 'TITAN': 375,
    'TORNTPHARM': 200, 'TORNTPOWER': 1150, 'TRENT': 125, 'TVSMOTOR': 350,
    'UBL': 400, 'ULTRACEMCO': 100, 'UNIONBANK': 6000, 'UPL': 1200,
    'VEDL': 1550, 'VOLTAS': 500, 'WHIRLPOOL': 400, 'WIPRO': 1500,
    'ZEEL': 2750, 'ZYDUSLIFE': 625,
}

# Default lot size if symbol not found
DEFAULT_LOT_SIZE = 500

async def update_pnl_amounts():
    pool = await asyncpg.create_pool('postgresql://user:password@127.0.0.1:5432/keepgaining')
    
    try:
        async with pool.acquire() as conn:
            # Get all trades
            trades = await conn.fetch('''
                SELECT trade_id, symbol, entry_premium, exit_premium
                FROM strategy_trades
                WHERE exit_premium IS NOT NULL
            ''')
            
            print(f"Updating P&L amounts for {len(trades)} trades...")
            
            updated = 0
            for trade in trades:
                symbol = trade['symbol']
                entry = float(trade['entry_premium'])
                exit_val = float(trade['exit_premium'])
                lot_size = LOT_SIZES.get(symbol, DEFAULT_LOT_SIZE)
                
                # P&L = (exit - entry) * lot_size
                pnl_amount = (exit_val - entry) * lot_size
                
                await conn.execute('''
                    UPDATE strategy_trades 
                    SET pnl_amount = $1, quantity = $2
                    WHERE trade_id = $3
                ''', round(pnl_amount, 2), lot_size, trade['trade_id'])
                
                updated += 1
            
            print(f"✅ Updated {updated} trades with correct P&L amounts")
            
            # Show some examples
            examples = await conn.fetch('''
                SELECT symbol, entry_premium, exit_premium, pnl_pct, pnl_amount, quantity
                FROM strategy_trades
                ORDER BY ABS(pnl_amount) DESC
                LIMIT 10
            ''')
            
            print("\nTop 10 trades by absolute P&L:")
            print("Symbol      | Entry   | Exit    | PnL%   | PnL Amt   | Lot Size")
            print("-" * 70)
            for t in examples:
                print(f"{t['symbol']:12}| {t['entry_premium']:7.2f} | {t['exit_premium']:7.2f} | {t['pnl_pct']:6.2f}% | ₹{t['pnl_amount']:>8,.0f} | {t['quantity']}")
            
            # Total P&L
            total = await conn.fetchval("SELECT SUM(pnl_amount) FROM strategy_trades")
            print(f"\n💰 Total P&L: ₹{total:,.0f}")
            
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(update_pnl_amounts())
