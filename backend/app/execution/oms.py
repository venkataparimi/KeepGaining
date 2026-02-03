from typing import Dict, Optional
from app.brokers.base import BaseBroker
from app.execution.risk import RiskManager
from app.schemas.broker import OrderRequest, OrderResponse, OrderStatus
from app.db.session import AsyncSessionLocal
from app.db.models import Trade
from loguru import logger
import uuid

class OrderManagementSystem:
    """
    Central system for routing and tracking orders.
    """
    def __init__(self, broker: BaseBroker):
        self.broker = broker
        self.risk_manager = RiskManager()

    async def place_order(self, order: OrderRequest, strategy_id: int) -> OrderResponse:
        """
        Validate and route order to broker.
        """
        # 1. Risk Check
        if not self.risk_manager.check_order(order):
            return OrderResponse(
                order_id=str(uuid.uuid4()),
                status=OrderStatus.REJECTED,
                message="Risk check failed"
            )

        # 2. Route to Broker
        try:
            response = await self.broker.place_order(order)
            
            # 3. Persist to DB
            async with AsyncSessionLocal() as session:
                trade = Trade(
                    strategy_id=strategy_id,
                    instrument_id=1, # TODO: Resolve actual instrument ID
                    order_id=response.order_id,
                    side=order.side,
                    quantity=order.quantity,
                    price=order.price or 0.0, # 0 for Market orders initially
                    status=response.status
                )
                session.add(trade)
                await session.commit()
            
            logger.info(f"OMS: Order placed {response.order_id}")
            return response

        except Exception as e:
            logger.error(f"OMS: Order placement failed: {e}")
            return OrderResponse(
                order_id=str(uuid.uuid4()),
                status=OrderStatus.REJECTED,
                message=str(e)
            )

    async def cancel_order(self, order_id: str) -> OrderResponse:
        return await self.broker.cancel_order(order_id)
