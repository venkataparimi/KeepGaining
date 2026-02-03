import asyncio
from app.execution.oms import OrderManagementSystem
from app.brokers.paper import PaperBroker
from app.schemas.broker import OrderRequest, OrderSide
from loguru import logger

async def verify_oms_flow():
    logger.info("Verifying OMS & Risk Flow...")
    
    # 1. Setup
    broker = PaperBroker(latency_ms=10)
    oms = OrderManagementSystem(broker)
    
    # 2. Place Valid Order
    valid_order = OrderRequest(
        symbol="INFY",
        quantity=10,
        side=OrderSide.BUY,
        price=1500.0,
        order_type="LIMIT"
    )
    response = await oms.place_order(valid_order, strategy_id=1)
    logger.info(f"Valid Order Response: {response}")
    
    # 3. Place Risky Order (Exceeds Value)
    risky_order = OrderRequest(
        symbol="INFY",
        quantity=100000, # Huge quantity
        side=OrderSide.BUY,
        price=1500.0,
        order_type="LIMIT"
    )
    response_risky = await oms.place_order(risky_order, strategy_id=1)
    logger.info(f"Risky Order Response: {response_risky}")
    
    # 4. Place Restricted Symbol Order
    restricted_order = OrderRequest(
        symbol="SCAM_CO",
        quantity=1,
        side=OrderSide.BUY,
        order_type="MARKET"
    )
    response_restricted = await oms.place_order(restricted_order, strategy_id=1)
    logger.info(f"Restricted Order Response: {response_restricted}")

if __name__ == "__main__":
    # Note: This script requires a running Database for OMS to persist trades.
    asyncio.run(verify_oms_flow())
