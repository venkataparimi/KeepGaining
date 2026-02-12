"""
Link Orphaned Option Instruments to option_master

Finds instruments that have candle data but are missing from option_master,
parses their trading_symbol to extract option details, and creates the missing
option_master entries with correct lot_size values.
"""
import asyncio
import asyncpg
import re
from datetime import datetime
from uuid import uuid4
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

# Lot sizes by underlying (as of 2024-2026)
LOT_SIZES = {
    'NIFTY': 75,        # Changed from 50 to 75 in April 2023
    'BANKNIFTY': 15,    # Changed from 25 to 15 in April 2023
    'FINNIFTY': 40,
    'MIDCPNIFTY': 75,
    'SENSEX': 10,
    'BANKEX': 15,
}

# Month name to number mapping
MONTH_MAP = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}


def parse_trading_symbol(symbol: str) -> dict:
    """
    Parse trading symbol like 'NIFTY 23200 CE 03 FEB 26' or 'BANKNIFTY 52000 PE 30 JAN 25'
    Returns: {underlying, strike_price, option_type, expiry_date}
    """
    # Pattern: UNDERLYING STRIKE OPTION_TYPE DD MMM YY
    pattern = r'^(\w+)\s+(\d+(?:\.\d+)?)\s+(CE|PE)\s+(\d{2})\s+(\w{3})\s+(\d{2})$'
    match = re.match(pattern, symbol.strip())
    
    if not match:
        return None
    
    underlying = match.group(1)
    strike_price = float(match.group(2))
    option_type = match.group(3)
    day = int(match.group(4))
    month_str = match.group(5).upper()
    year_short = int(match.group(6))
    
    # Convert 2-digit year to full year
    year = 2000 + year_short if year_short < 50 else 1900 + year_short
    month = MONTH_MAP.get(month_str)
    
    if not month:
        return None
    
    try:
        expiry_date = datetime(year, month, day).date()
    except ValueError:
        return None
    
    return {
        'underlying': underlying,
        'strike_price': strike_price,
        'option_type': option_type,
        'expiry_date': expiry_date
    }


async def get_underlying_instrument_ids(conn) -> dict:
    """Get instrument_ids for underlying indices."""
    result = await conn.fetch('''
        SELECT instrument_id, trading_symbol, underlying
        FROM instrument_master
        WHERE instrument_type = 'INDEX'
    ''')
    
    # Map option underlying names to instrument_ids
    # Option symbols use NIFTY, BANKNIFTY, FINNIFTY
    # DB INDEX symbols use NIFTY 50, NIFTY BANK, NIFTY FIN SERVICE
    mapping = {}
    for row in result:
        symbol = row['trading_symbol']
        inst_id = row['instrument_id']
        
        # Map DB names to option symbol names
        if symbol == 'NIFTY 50':
            mapping['NIFTY'] = inst_id
        elif symbol == 'NIFTY BANK':
            mapping['BANKNIFTY'] = inst_id
        elif symbol == 'NIFTY FIN SERVICE':
            mapping['FINNIFTY'] = inst_id
        elif symbol == 'NIFTY MIDCAP 50':
            mapping['MIDCPNIFTY'] = inst_id
        elif symbol in ('SENSEX', 'BANKEX'):
            mapping[symbol] = inst_id
    
    return mapping


async def link_orphaned_instruments():
    """Find and link orphaned instruments to option_master."""
    conn = await asyncpg.connect(DB_URL)
    
    logger.info("=" * 80)
    logger.info("LINKING ORPHANED OPTION INSTRUMENTS")
    logger.info("=" * 80)
    
    # Get underlying instrument IDs
    logger.info("Fetching underlying instrument IDs...")
    underlying_ids = await get_underlying_instrument_ids(conn)
    logger.info(f"Found {len(underlying_ids)} underlying instruments: {list(underlying_ids.keys())}")
    
    # Find all orphaned instruments
    logger.info("\nFinding orphaned instruments (have candles, no option_master)...")
    orphaned = await conn.fetch('''
        SELECT DISTINCT
            im.instrument_id,
            im.trading_symbol,
            im.underlying,
            im.instrument_type
        FROM instrument_master im
        JOIN candle_data cd ON im.instrument_id = cd.instrument_id
        LEFT JOIN option_master om ON im.instrument_id = om.instrument_id
        WHERE im.instrument_type IN ('CE', 'PE', 'OPTIDX')
        AND om.option_id IS NULL
    ''')
    
    logger.info(f"Found {len(orphaned)} orphaned instruments to process")
    
    if not orphaned:
        logger.info("No orphaned instruments found!")
        await conn.close()
        return
    
    # Process each orphaned instrument
    linked = 0
    failed = 0
    
    for i, row in enumerate(orphaned):
        instrument_id = row['instrument_id']
        trading_symbol = row['trading_symbol']
        underlying_from_db = row['underlying']
        
        # Parse the trading symbol
        parsed = parse_trading_symbol(trading_symbol)
        
        if not parsed:
            logger.warning(f"  [{i+1}] Could not parse: {trading_symbol}")
            failed += 1
            continue
        
        underlying = parsed['underlying']
        strike_price = parsed['strike_price']
        option_type = parsed['option_type']
        expiry_date = parsed['expiry_date']
        
        # Get lot size
        lot_size = LOT_SIZES.get(underlying, 1)
        
        # Get underlying instrument ID
        underlying_inst_id = underlying_ids.get(underlying)
        
        if not underlying_inst_id:
            logger.warning(f"  [{i+1}] No underlying ID for {underlying}: {trading_symbol}")
            failed += 1
            continue
        
        # Determine expiry type (Weekly if not last Thursday of month, else Monthly)
        # Simplified: if day <= 7, likely weekly
        expiry_type = 'Weekly' if expiry_date.day <= 7 or expiry_date.day >= 25 else 'Weekly'
        
        try:
            # Check if already exists
            exists = await conn.fetchval(
                'SELECT 1 FROM option_master WHERE instrument_id = $1',
                instrument_id
            )
            
            if exists:
                # Update lot_size if needed
                await conn.execute('''
                    UPDATE option_master SET lot_size = $1 WHERE instrument_id = $2
                ''', lot_size, instrument_id)
                linked += 1
            else:
                # Insert new record
                await conn.execute('''
                    INSERT INTO option_master (
                        option_id, instrument_id, underlying_instrument_id,
                        strike_price, option_type, expiry_date, expiry_type, lot_size
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ''', uuid4(), instrument_id, underlying_inst_id,
                    strike_price, option_type, expiry_date, expiry_type, lot_size)
                linked += 1
            
            if linked % 100 == 0:
                logger.info(f"  Progress: {linked} linked, {failed} failed ({i+1}/{len(orphaned)})")
                
        except Exception as e:
            logger.error(f"  [{i+1}] Error linking {trading_symbol}: {e}")
            failed += 1
    
    await conn.close()
    
    logger.info("\n" + "=" * 80)
    logger.info("COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Successfully linked: {linked}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Total processed: {len(orphaned)}")


if __name__ == '__main__':
    asyncio.run(link_orphaned_instruments())
