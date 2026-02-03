import asyncio
import random
from app.brokers.mock import MockBroker
from app.schemas.broker import OrderRequest, OrderResponse, OrderStatus

class PaperBroker(MockBroker):
    """
    Enhanced Mock Broker for Paper Trading.
    Simulates slippage, latency, and partial fills.
    """
    def __init__(self, slippage_std_dev: float = 0.05, latency_ms: int = 100):
        super().__init__()
        self.slippage_std_dev = slippage_std_dev
        self.latency_ms = latency_ms

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        # Simulate Network Latency
        await asyncio.sleep(self.latency_ms / 1000.0)
        
        # Simulate Slippage for Market Orders
        executed_price = order.price
        if order.order_type == "MARKET":
            # Assume last price is 100 for simulation if not available
            base_price = 100.0 
            slippage = random.gauss(0, self.slippage_std_dev)
            executed_price = base_price + slippage

        response = await super().place_order(order)
        
        # In a real paper broker, we would update the trade with the executed price
        # For now, we just return the response from MockBroker but with simulated delay
        
        return response
