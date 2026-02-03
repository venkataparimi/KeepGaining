import uuid
from datetime import datetime
from typing import List, Dict, Any
from app.brokers.base import BaseBroker
from app.schemas.broker import OrderRequest, OrderResponse, Position, Quote
from app.db.models import OrderStatus

class MockBroker(BaseBroker):
    """
    Mock Broker for Paper Trading and Testing.
    Simulates order fills and maintains local state.
    """
    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, OrderRequest] = {}
        self.is_authenticated = False

    async def authenticate(self) -> bool:
        self.is_authenticated = True
        return True

    async def get_positions(self) -> List[Position]:
        return list(self.positions.values())

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        order_id = str(uuid.uuid4())
        self.orders[order_id] = order
        
        # Simulate immediate fill for Market orders
        if order.order_type == "MARKET":
            # Logic to update positions would go here (simplified for now)
            pass
            
        return OrderResponse(order_id=order_id, status=OrderStatus.OPEN, message="Order placed successfully")

    async def modify_order(self, order_id: str, price: float = None, quantity: int = None) -> OrderResponse:
        if order_id in self.orders:
            return OrderResponse(order_id=order_id, status=OrderStatus.PENDING, message="Order modified")
        return OrderResponse(order_id=order_id, status=OrderStatus.REJECTED, message="Order not found")

    async def cancel_order(self, order_id: str) -> OrderResponse:
        if order_id in self.orders:
            return OrderResponse(order_id=order_id, status=OrderStatus.CANCELLED, message="Order cancelled")
        return OrderResponse(order_id=order_id, status=OrderStatus.REJECTED, message="Order not found")

    async def get_order_status(self, order_id: str) -> OrderResponse:
        if order_id in self.orders:
            return OrderResponse(order_id=order_id, status=OrderStatus.OPEN)
        return OrderResponse(order_id=order_id, status=OrderStatus.REJECTED, message="Order not found")

    async def get_historical_data(self, symbol: str, timeframe: str, from_date: str, to_date: str) -> Any:
        # Return dummy data
        return []

    async def get_quote(self, symbol: str) -> Quote:
        return Quote(
            symbol=symbol,
            last_price=100.0,
            volume=1000,
            timestamp=datetime.now()
        )

    async def get_order_activity_summary(self) -> Dict[str, int]:
        """
        Get today's order activity for mock broker.
        Returns counts based on internal order state.
        """
        summary = {
            "orders_placed": len(self.orders),
            "orders_executed": 0,
            "orders_rejected": 0,
            "orders_pending": 0,
            "orders_cancelled": 0
        }
        
        # For mock, assume all orders are executed
        summary["orders_executed"] = len(self.orders)
        
        return summary
