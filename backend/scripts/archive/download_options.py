"""
Download options data for current and recent expiries
Checks for all available expiries in the last 60 days
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime, timedelta
import pandas as pd
from app.brokers.fyers import FyersBroker
from loguru import logger

# Major indices for options
OPTION_UNDERLYINGS = [
    "NSE:NIFTY50-INDEX",
    "NSE:NIFTYBANK-INDEX",
]

OUTPUT_DIR = Path("options_data")


async def get_expiry_dates(broker: FyersBroker, underlying: str):
    """Get all expiry dates for an underlying"""
    try:
        # Fyers doesn't have direct expiry API, we'll need to construct
        # For now, get current weekly and monthly expiries
        
        # Weekly expiries (Thursdays)
        expiries = []
        today = datetime.now()
        
        # Get next 8 weeks (covers 60 days)
        for i in range(8):
            # Find next Thursday
            days_ahead = (3 - today.weekday()) % 7  # Thursday is 3
            if days_ahead == 0 and today.hour >= 15:  # After 3 PM
                days_ahead = 7
            next_thursday = today + timedelta(days=days_ahead + (i * 7))
            expiries.append(next_thursday.strftime("%y%b%d").upper())
        
        # Monthly expiry (last Thursday)
        # Simplified: add end of month
        for i in range(3):  # Next 3 months
            month_date = today + timedelta(days=30 * i)
            # Last Thursday of month (simplified)
            expiries.append(month_date.strftime("%y%b").upper() + "MONTH")
        
        logger.info(f"Generated expiries for {underlying}: {expiries[:5]}...")
        return expiries[:5]  # Return first 5 expiries
        
    except Exception as e:
        logger.error(f"Error getting expiries: {e}")
        return []


async def get_atm_strike(broker: FyersBroker, underlying: str):
    """Get ATM strike for underlying"""
    try:
        quote = await broker.get_quote(underlying)
        if quote and 'lp' in quote:
            price = quote['lp']
            # Round to nearest 50 for Nifty, 100 for Bank Nifty
            if "BANK" in underlying:
                atm = round(price / 100) * 100
            else:
                atm = round(price / 50) * 50
            logger.info(f"{underlying} price: {price}, ATM: {atm}")
            return atm
    except Exception as e:
        logger.error(f"Error getting ATM: {e}")
        # Fallback defaults
        if "BANK" in underlying:
            return 51000
        return 24000


def generate_option_symbols(underlying: str, expiry: str, atm_strike: float, num_strikes: int = 10):
    """Generate option symbols around ATM"""
    symbols = []
    
    # Determine strike interval
    if "BANK" in underlying:
        interval = 100
        base_symbol = "BANKNIFTY"
    else:
        interval = 50
        base_symbol = "NIFTY"
    
    # Generate strikes around ATM
    for i in range(-num_strikes, num_strikes + 1):
        strike = atm_strike + (i * interval)
        
        # CE symbol: NSE:BANKNIFTY2432551000CE
        ce_symbol = f"NSE:{base_symbol}{expiry}{int(strike)}CE"
        pe_symbol = f"NSE:{base_symbol}{expiry}{int(strike)}PE"
        
        symbols.append({"symbol": ce_symbol, "strike": strike, "type": "CE", "expiry": expiry})
        symbols.append({"symbol": pe_symbol, "strike": strike, "type": "PE", "expiry": expiry})
    
    return symbols


async def download_option_data(broker: FyersBroker, symbol_info: dict):
    """Download historical data for one option"""
    symbol = symbol_info['symbol']
    
    try:
        # Download last 60 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)
        
        df = await broker.get_historical_data(
            symbol=symbol,
            resolution="1",
            start_date=start_date,
            end_date=end_date
        )
        
        if df.empty:
            logger.warning(f"No data for {symbol}")
            return None
        
        # Add metadata
        df['symbol'] = symbol
        df['strike'] = symbol_info['strike']
        df['option_type'] = symbol_info['type']
        df['expiry'] = symbol_info['expiry']
        df['underlying'] = symbol_info.get('underlying', '')
        
        logger.success(f"✓ {symbol}: {len(df)} candles")
        return df
        
    except Exception as e:
        logger.error(f"Error downloading {symbol}: {e}")
        return None


async def main():
    """Main options download function"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    logger.info("=" * 80)
    logger.info("OPTIONS DATA DOWNLOAD - Last 60 Days")
    logger.info("=" * 80)
    
    broker = FyersBroker()
    
    for underlying in OPTION_UNDERLYINGS:
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing: {underlying}")
        logger.info(f"{'='*80}")
        
        # Get expiries
        expiries = await get_expiry_dates(broker, underlying)
        if not expiries:
            logger.warning(f"No expiries found for {underlying}")
            continue
        
        # Get ATM strike
        atm_strike = await get_atm_strike(broker, underlying)
        
        # Process each expiry
        for expiry in expiries:
            logger.info(f"\nExpiry: {expiry}")
            
            # Generate option symbols
            option_symbols = generate_option_symbols(underlying, expiry, atm_strike, num_strikes=5)
            logger.info(f"Generated {len(option_symbols)} option symbols")
            
            # Download data for each option
            all_data = []
            for idx, symbol_info in enumerate(option_symbols, 1):
                symbol_info['underlying'] = underlying
                
                logger.info(f"[{idx}/{len(option_symbols)}] {symbol_info['symbol']}")
                df = await download_option_data(broker, symbol_info)
                
                if df is not None:
                    all_data.append(df)
                
                await asyncio.sleep(0.3)  # Rate limiting
            
            # Save to CSV
            if all_data:
                combined_df = pd.concat(all_data, ignore_index=True)
                filename = OUTPUT_DIR / f"{underlying.replace(':', '_')}_{expiry}.csv"
                combined_df.to_csv(filename, index=False)
                logger.success(f"✓ Saved {len(combined_df)} candles to {filename}")
    
    logger.info("\n" + "=" * 80)
    logger.success("OPTIONS DOWNLOAD COMPLETE!")
    logger.info(f"Data saved to {OUTPUT_DIR}/")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
