"""
Download November 25, 2025 Weekly Expiry Options Data
Expiry Date: November 25, 2025 (Tuesday - TODAY)

Fyers Weekly Option Symbol Format: NSE:NIFTY25N2524200CE
Format: NSE:UNDERLYING + YY + M + DD + STRIKE + CE/PE
Where M is single character for month (N for November)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime, timedelta
import pandas as pd
from app.brokers.fyers import FyersBroker
from loguru import logger

# November 25, 2025 weekly expiry (Tuesday - TODAY)
# Fyers weekly format: YY + M + DD (e.g., 25N25)
NOV_EXPIRY = "25N25"  # Format: YY + M + DD (M = N for November)

# Underlyings
UNDERLYINGS = [
    {"symbol": "NSE:NIFTY50-INDEX", "name": "NIFTY", "interval": 50},
    {"symbol": "NSE:NIFTYBANK-INDEX", "name": "BANKNIFTY", "interval": 100},
]

OUTPUT_DIR = Path("options_data")


async def get_current_price(broker: FyersBroker, symbol: str):
    """Get current price of underlying"""
    try:
        quote = await broker.get_quote(symbol)
        if quote and quote.price > 0:
            logger.info(f"Got live price for {symbol}: {quote.price}")
            return quote.price
    except Exception as e:
        logger.warning(f"Could not get live price for {symbol}: {e}")
    
    # Fallback to approximate current prices (as of Nov 25, 2025)
    logger.info(f"Using fallback price for {symbol}")
    if "BANK" in symbol:
        return 51500.0  # Approximate Bank Nifty
    else:
        return 24200.0  # Approximate Nifty


def generate_option_chain(underlying_name: str, expiry: str, spot_price: float, interval: int, num_strikes: int = 20):
    """Generate option symbols around ATM
    
    Fyers Weekly Format: NSE:NIFTY25N2624200CE
    - NSE: Exchange
    - NIFTY/BANKNIFTY: Underlying
    - 25: Year (2025)
    - N: Month (N for November)
    - 26: Day (26th)
    - 24200: Strike
    - CE/PE: Call/Put
    """
    # Calculate ATM strike
    atm_strike = round(spot_price / interval) * interval
    
    options = []
    for i in range(-num_strikes, num_strikes + 1):
        strike = atm_strike + (i * interval)
        
        # Fyers weekly format: NSE:NIFTY25N2624200CE
        ce_symbol = f"NSE:{underlying_name}{expiry}{int(strike)}CE"
        pe_symbol = f"NSE:{underlying_name}{expiry}{int(strike)}PE"
        
        options.append({
            "symbol": ce_symbol,
            "strike": strike,
            "type": "CE",
            "expiry": expiry,
            "underlying": underlying_name,
            "atm_distance": i
        })
        options.append({
            "symbol": pe_symbol,
            "strike": strike,
            "type": "PE",
            "expiry": expiry,
            "underlying": underlying_name,
            "atm_distance": i
        })
    
    return options


async def download_option_historical(broker: FyersBroker, option_info: dict, days_back: int = 30):
    """Download historical data for one option"""
    symbol = option_info['symbol']
    
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        df = await broker.get_historical_data(
            symbol=symbol,
            resolution="1",  # 1-minute
            start_date=start_date,
            end_date=end_date
        )
        
        if df.empty:
            logger.warning(f"  No data for {symbol}")
            return None
        
        # Add metadata
        df['symbol'] = symbol
        df['strike'] = option_info['strike']
        df['option_type'] = option_info['type']
        df['expiry'] = option_info['expiry']
        df['underlying'] = option_info['underlying']
        df['atm_distance'] = option_info['atm_distance']
        
        logger.success(f"  Got {len(df):,} candles for {symbol}")
        return df
        
    except Exception as e:
        logger.error(f"  Error downloading {symbol}: {e}")
        return None


async def main():
    """Download November 26 weekly expiry options data"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    logger.info("="*80)
    logger.info("NOVEMBER 25, 2025 WEEKLY EXPIRY OPTIONS DATA DOWNLOAD")
    logger.info(f"Expiry Date: November 25, 2025 (Tuesday - TODAY) - Format: {NOV_EXPIRY}")
    logger.info("="*80)
    
    broker = FyersBroker()
    
    for underlying in UNDERLYINGS:
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing: {underlying['name']}")
        logger.info(f"{'='*80}")
        
        # Get current spot price
        spot_price = await get_current_price(broker, underlying['symbol'])
        
        logger.info(f"Spot Price: {spot_price:,.2f}")
        
        # Generate option chain (20 strikes above and below ATM = 41 strikes total)
        option_chain = generate_option_chain(
            underlying['name'],
            NOV_EXPIRY,
            spot_price,
            underlying['interval'],
            num_strikes=20
        )
        
        logger.info(f"Generated {len(option_chain)} option symbols (41 strikes × 2 types)")
        logger.info(f"Strike range: {option_chain[0]['strike']} to {option_chain[-1]['strike']}")
        logger.info(f"Sample symbols: {option_chain[40]['symbol']}, {option_chain[41]['symbol']}")
        
        # Download data for each option
        all_data = []
        total = len(option_chain)
        
        for idx, option_info in enumerate(option_chain, 1):
            logger.info(f"[{idx}/{total}] {option_info['symbol']}")
            
            df = await download_option_historical(broker, option_info, days_back=30)
            
            if df is not None:
                all_data.append(df)
            
            # Rate limiting
            await asyncio.sleep(0.5)
        
        # Save combined data
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            filename = OUTPUT_DIR / f"{underlying['name']}_{NOV_EXPIRY}.csv"
            combined_df.to_csv(filename, index=False)
            
            logger.success(f"\n{'='*60}")
            logger.success(f"Saved {len(combined_df):,} total candles to {filename}")
            logger.success(f"Options with data: {len(all_data)}/{total}")
            logger.success(f"{'='*60}")
        else:
            logger.warning(f"No data downloaded for {underlying['name']}")
    
    logger.info("\n" + "="*80)
    logger.success("NOVEMBER 25 WEEKLY EXPIRY OPTIONS DOWNLOAD COMPLETE!")
    logger.info(f"Data saved to: {OUTPUT_DIR}/")
    logger.info("="*80)


if __name__ == "__main__":
    asyncio.run(main())
