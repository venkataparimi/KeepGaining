"""
Update lot_sizes in option_master based on historical revisions.

Lot size changes:
- April 2023: NIFTY 50→75, BANKNIFTY 25→15
- Before April 2023: Use old lot sizes
"""
import asyncio
import asyncpg
from datetime import date
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

# Lot size revision date (April 2023 - exact date was April 3, 2023)
REVISION_DATE = date(2023, 4, 3)

# Lot sizes by period
LOT_SIZES_NEW = {  # After April 2023
    'NIFTY': 75,
    'BANKNIFTY': 15,
    'FINNIFTY': 40,
    'MIDCPNIFTY': 75,
    'SENSEX': 10,
    'BANKEX': 15,
}

LOT_SIZES_OLD = {  # Before April 2023
    'NIFTY': 50,
    'BANKNIFTY': 25,
    'FINNIFTY': 40,  # unchanged
    'MIDCPNIFTY': 75,  # unchanged
    'SENSEX': 10,  # unchanged
    'BANKEX': 15,  # unchanged
}


async def update_lot_sizes():
    conn = await asyncpg.connect(DB_URL)
    
    logger.info("=" * 80)
    logger.info("UPDATING LOT SIZES WITH HISTORICAL REVISIONS")
    logger.info(f"Revision date: {REVISION_DATE}")
    logger.info("=" * 80)
    
    # Get index instrument IDs for underlying lookup
    indices = await conn.fetch('''
        SELECT instrument_id, trading_symbol FROM instrument_master
        WHERE instrument_type = 'INDEX'
    ''')
    
    # Map trading_symbol to underlying name
    index_to_underlying = {}
    for row in indices:
        symbol = row['trading_symbol']
        if symbol == 'NIFTY 50':
            index_to_underlying[row['instrument_id']] = 'NIFTY'
        elif symbol == 'NIFTY BANK':
            index_to_underlying[row['instrument_id']] = 'BANKNIFTY'
        elif symbol == 'NIFTY FIN SERVICE':
            index_to_underlying[row['instrument_id']] = 'FINNIFTY'
        elif symbol == 'NIFTY MIDCAP 50':
            index_to_underlying[row['instrument_id']] = 'MIDCPNIFTY'
        elif symbol in ('SENSEX', 'BANKEX'):
            index_to_underlying[row['instrument_id']] = symbol
    
    # Update options before revision date (old lot sizes)
    logger.info(f"\nUpdating options BEFORE {REVISION_DATE} with old lot sizes...")
    for underlying, old_lot in LOT_SIZES_OLD.items():
        # Find underlying_instrument_id for this underlying
        underlying_id = None
        for idx_id, uname in index_to_underlying.items():
            if uname == underlying:
                underlying_id = idx_id
                break
        
        if not underlying_id:
            logger.warning(f"  No index found for {underlying}")
            continue
        
        result = await conn.execute('''
            UPDATE option_master
            SET lot_size = $1
            WHERE underlying_instrument_id = $2
            AND expiry_date < $3
        ''', old_lot, underlying_id, REVISION_DATE)
        
        count = result.split()[-1] if result else '0'
        logger.info(f"  {underlying}: {count} options updated to lot_size={old_lot}")
    
    # Update options after revision date (new lot sizes)
    logger.info(f"\nUpdating options AFTER {REVISION_DATE} with new lot sizes...")
    for underlying, new_lot in LOT_SIZES_NEW.items():
        underlying_id = None
        for idx_id, uname in index_to_underlying.items():
            if uname == underlying:
                underlying_id = idx_id
                break
        
        if not underlying_id:
            logger.warning(f"  No index found for {underlying}")
            continue
        
        result = await conn.execute('''
            UPDATE option_master
            SET lot_size = $1
            WHERE underlying_instrument_id = $2
            AND expiry_date >= $3
        ''', new_lot, underlying_id, REVISION_DATE)
        
        count = result.split()[-1] if result else '0'
        logger.info(f"  {underlying}: {count} options updated to lot_size={new_lot}")
    
    await conn.close()
    
    logger.info("\n" + "=" * 80)
    logger.info("LOT SIZE UPDATE COMPLETE")
    logger.info("=" * 80)


if __name__ == '__main__':
    asyncio.run(update_lot_sizes())
