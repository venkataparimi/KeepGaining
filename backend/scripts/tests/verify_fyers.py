import asyncio
from app.brokers.fyers import FyersBroker
from loguru import logger
from datetime import datetime, timedelta

async def verify_fyers():
    logger.info("Verifying Fyers Integration...")
    
    # 1. Initialize Broker (Triggers Auto-Login)
    broker = FyersBroker()
    is_auth = await broker.authenticate()
    
    if not is_auth:
        logger.error("Authentication Failed!")
        return

    logger.success("Authentication Successful!")

    # 2. Fetch Profile/Funds
    try:
        funds = broker.client.get_funds()
        logger.info(f"Funds: {funds}")
    except Exception as e:
        logger.error(f"Failed to fetch funds: {e}")

    # 3. Fetch Historical Data (SBIN)
    logger.info("Fetching Historical Data for NSE:SBIN-EQ...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5)
    
    try:
        df = await broker.get_historical_data(
            symbol="NSE:SBIN-EQ",
            resolution="D",
            start_date=start_date,
            end_date=end_date
        )
        logger.info(f"Fetched {len(df)} candles.")
        print(df.head())
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")

    # 4. Fetch Option Chain (NIFTY)
    logger.info("Fetching Option Chain for NSE:NIFTY50-INDEX...")
    try:
        # Get nearest expiry
        expiries = broker.client.get_available_expiries("NSE:NIFTY50-INDEX")
        if expiries:
            nearest_expiry = expiries[0]
            logger.info(f"Nearest Expiry: {nearest_expiry['date']}")
            
            chain = broker.client.get_option_chain(
                symbol="NSE:NIFTY50-INDEX",
                expiry_timestamp=nearest_expiry['timestamp'],
                strike_count=2
            )
            logger.info("Option Chain Fetched Successfully")
        else:
            logger.warning("No expiries found.")
            
    except Exception as e:
        logger.error(f"Failed to fetch option chain: {e}")

if __name__ == "__main__":
    asyncio.run(verify_fyers())
