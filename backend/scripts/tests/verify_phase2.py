import asyncio
from app.brokers.mock import MockBroker
from app.schemas.broker import OrderRequest, OrderSide
from app.services.data_feed import DataFeedService
from loguru import logger

async def verify_broker_flow():
    logger.info("Verifying Broker Flow...")
    
    # 1. Instantiate Mock Broker
    broker = MockBroker()
    authenticated = await broker.authenticate()
    logger.info(f"Authentication: {authenticated}")
    
    # 2. Place Order
    order = OrderRequest(
        symbol="INFY",
        quantity=10,
        side=OrderSide.BUY,
        order_type="MARKET"
    )
    response = await broker.place_order(order)
    logger.info(f"Order Placed: {response}")
    
    # 3. Check Status
    status = await broker.get_order_status(response.order_id)
    logger.info(f"Order Status: {status}")

async def verify_data_feed():
    logger.info("Verifying Data Feed...")
    broker = MockBroker()
    service = DataFeedService(broker)
    
    # 4. Fetch Historical Data (Mock)
    await service.fetch_and_store_historical_data(
        symbol="INFY",
        timeframe="1m",
        from_date="2023-01-01",
        to_date="2023-01-02"
    )

if __name__ == "__main__":
    asyncio.run(verify_broker_flow())
    asyncio.run(verify_data_feed())
