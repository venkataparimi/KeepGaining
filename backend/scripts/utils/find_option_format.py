"""
Download Fyers Symbol Master to find correct option symbol format
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from app.brokers.fyers import FyersBroker
from loguru import logger

async def get_symbol_master():
    """Get symbol master from Fyers"""
    broker = FyersBroker()
    
    # Try to get symbol master
    try:
        # Fyers provides symbol master via API
        response = broker.client.client.symbol_master()
        
        if response:
            logger.info(f"Symbol master response: {response}")
            
            # Save to file for inspection
            import json
            with open("fyers_symbol_master.json", "w") as f:
                json.dump(response, f, indent=2)
            
            logger.success("Symbol master saved to fyers_symbol_master.json")
        else:
            logger.error("No symbol master data received")
            
    except Exception as e:
        logger.error(f"Error getting symbol master: {e}")
        logger.info("Trying alternative method...")
        
        # Alternative: Try to get quotes for a known option symbol
        # Let's try different formats for a Nifty 24200 CE expiring Nov 27
        test_symbols = [
            "NSE:NIFTY24NOV24200CE",
            "NSE:NIFTY24N2724200CE", 
            "NSE:NIFTY2411N24200CE",
            "NSE:NIFTY24327CE24200",
            "NSE:NIFTY24NOV2724200CE",
        ]
        
        for symbol in test_symbols:
            try:
                quote = await broker.get_quote(symbol)
                if quote and quote.price > 0:
                    logger.success(f"✓ FOUND VALID FORMAT: {symbol}")
                    logger.success(f"  Price: {quote.price}")
                    return symbol
                else:
                    logger.info(f"✗ Invalid: {symbol}")
            except Exception as e:
                logger.info(f"✗ Invalid: {symbol} - {e}")
        
        logger.warning("Could not find valid option symbol format")

if __name__ == "__main__":
    asyncio.run(get_symbol_master())
