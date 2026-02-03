from abc import ABC, abstractmethod
from typing import List, Dict, Any
from app.schemas.broker import OrderRequest, OrderResponse, Position, Quote

class BaseBroker(ABC):
    """
    Abstract Base Class for all Broker implementations.
    Ensures a unified interface for the Strategy Engine.
    """

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the broker API."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Fetch current open positions."""
        pass

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """Place a new order."""
        pass

    @abstractmethod
    async def modify_order(self, order_id: str, price: float = None, quantity: int = None) -> OrderResponse:
        """Modify an existing pending order."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel a pending order."""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderResponse:
        """Get the status of a specific order."""
        pass

    @abstractmethod
    async def get_historical_data(self, symbol: str, timeframe: str, from_date: str, to_date: str) -> Any:
        """Fetch historical OHLC data."""
        pass
    
    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Get real-time quote."""
        pass

    @abstractmethod
    async def get_order_activity_summary(self) -> Dict[str, int]:
        """
        Get today's order activity summary with standardized status counts.
        Returns:
            {
                "orders_placed": int,
                "orders_executed": int,
                "orders_rejected": int,
                "orders_pending": int,
                "orders_cancelled": int
            }
        This method should normalize broker-specific status codes to standard categories.
        """
        pass
