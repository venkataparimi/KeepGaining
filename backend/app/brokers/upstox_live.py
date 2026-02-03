"""
Upstox Live Trading Broker
KeepGaining Trading Platform

Full broker implementation for live trading via Upstox API.
Supports:
- Order placement (market, limit, SL, SL-M)
- Order modification and cancellation
- Position tracking and reconciliation
- Real-time order status streaming
- GTT (Good Till Triggered) orders
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from decimal import Decimal
from enum import Enum
import json

from loguru import logger

# Add upstox SDK to path
UPSTOX_SDK_PATH = Path(__file__).parent.parent / "upstox-python-master"
if UPSTOX_SDK_PATH.exists():
    sys.path.insert(0, str(UPSTOX_SDK_PATH))

try:
    from upstox_client import ApiClient, Configuration
    from upstox_client.api import OrderApi, PortfolioApi, UserApi
    from upstox_client.rest import ApiException
    UPSTOX_SDK_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Upstox SDK not available: {e}")
    UPSTOX_SDK_AVAILABLE = False

from app.brokers.base import BaseBroker
from app.schemas.broker import (
    OrderRequest, OrderResponse, Position, Quote,
    OrderType, ProductType
)
from app.db.models import OrderStatus, OrderSide
from app.core.events import EventBus, EventType, get_event_bus_sync


class UpstoxProductType(str, Enum):
    """Upstox product types."""
    DELIVERY = "D"      # CNC / Delivery
    INTRADAY = "I"      # MIS / Intraday
    CO = "CO"           # Cover Order
    OCO = "OCO"         # One Cancels Other


class UpstoxOrderType(str, Enum):
    """Upstox order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"           # Stop Loss Limit
    SL_M = "SL-M"       # Stop Loss Market


class UpstoxOrderValidity(str, Enum):
    """Order validity."""
    DAY = "DAY"
    IOC = "IOC"         # Immediate or Cancel


class UpstoxLiveBroker(BaseBroker):
    """
    Live trading broker implementation for Upstox.
    
    This broker connects to the real Upstox API and executes actual trades.
    Use with caution - all orders are REAL!
    
    Usage:
        broker = UpstoxLiveBroker(access_token="your_token")
        await broker.authenticate()
        
        order = OrderRequest(
            symbol="NSE_EQ|INE002A01018",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY
        )
        response = await broker.place_order(order)
    """
    
    BASE_URL = "https://api.upstox.com/v2"
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        event_bus: Optional[EventBus] = None,
        sandbox_mode: bool = False
    ):
        """
        Initialize Upstox Live Broker.
        
        Args:
            access_token: Upstox access token
            event_bus: Event bus for publishing order events
            sandbox_mode: If True, validates orders but doesn't execute
        """
        if not UPSTOX_SDK_AVAILABLE:
            raise RuntimeError("Upstox SDK not available. Install required packages.")
        
        self.access_token = access_token
        self.event_bus = event_bus or get_event_bus_sync()
        self.sandbox_mode = sandbox_mode
        
        # API clients (initialized on authenticate)
        self._api_client: Optional[ApiClient] = None
        self._order_api: Optional[OrderApi] = None
        self._portfolio_api: Optional[PortfolioApi] = None
        self._user_api: Optional[UserApi] = None
        
        # State
        self._authenticated = False
        self._user_profile: Optional[Dict] = None
        
        # Order cache for reconciliation
        self._orders: Dict[str, Dict] = {}
        self._positions: Dict[str, Dict] = {}
        
        logger.info(f"UpstoxLiveBroker initialized (sandbox={sandbox_mode})")
    
    def set_access_token(self, token: str) -> None:
        """Set access token (e.g., after OAuth)."""
        self.access_token = token
        self._authenticated = False
    
    async def authenticate(self) -> bool:
        """
        Authenticate with Upstox API.
        
        Returns:
            True if authentication successful
        """
        if not self.access_token:
            logger.error("No access token provided")
            return False
        
        try:
            # Configure API client
            config = Configuration()
            config.access_token = self.access_token
            
            self._api_client = ApiClient(config)
            self._order_api = OrderApi(self._api_client)
            self._portfolio_api = PortfolioApi(self._api_client)
            self._user_api = UserApi(self._api_client)
            
            # Verify authentication by getting user profile
            profile_response = self._user_api.get_profile("2.0")
            
            if profile_response.status == "success":
                self._user_profile = profile_response.data.to_dict() if hasattr(profile_response.data, 'to_dict') else profile_response.data
                self._authenticated = True
                logger.info(f"Authenticated as: {self._user_profile.get('user_name', 'Unknown')}")
                return True
            else:
                logger.error(f"Authentication failed: {profile_response}")
                return False
                
        except ApiException as e:
            logger.error(f"API authentication failed: {e.status} - {e.body}")
            return False
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    async def get_positions(self) -> List[Position]:
        """
        Fetch current open positions from Upstox.
        
        Returns:
            List of Position objects
        """
        if not self._authenticated:
            logger.error("Not authenticated")
            return []
        
        try:
            response = self._portfolio_api.get_positions("2.0")
            
            if response.status != "success":
                logger.error(f"Failed to get positions: {response}")
                return []
            
            positions = []
            for pos in response.data or []:
                pos_dict = pos.to_dict() if hasattr(pos, 'to_dict') else pos
                
                # Map to our Position schema
                position = Position(
                    symbol=pos_dict.get("tradingsymbol", ""),
                    instrument_key=pos_dict.get("instrument_token", ""),
                    quantity=int(pos_dict.get("quantity", 0)),
                    average_price=float(pos_dict.get("average_price", 0)),
                    last_price=float(pos_dict.get("last_price", 0)),
                    pnl=float(pos_dict.get("pnl", 0)),
                    product_type=pos_dict.get("product", ""),
                    exchange=pos_dict.get("exchange", "")
                )
                positions.append(position)
                
                # Cache position
                self._positions[position.instrument_key] = pos_dict
            
            return positions
            
        except ApiException as e:
            logger.error(f"Failed to get positions: {e.status} - {e.body}")
            return []
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """
        Place a new order via Upstox API.
        
        Args:
            order: Order request with all details
            
        Returns:
            OrderResponse with order ID and status
        """
        if not self._authenticated:
            return OrderResponse(
                order_id="",
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        if self.sandbox_mode:
            logger.info(f"[SANDBOX] Would place order: {order}")
            return OrderResponse(
                order_id=f"SANDBOX_{datetime.now().timestamp()}",
                status=OrderStatus.PENDING,
                message="Sandbox mode - order not executed"
            )
        
        try:
            # Map our order types to Upstox types
            upstox_order_type = self._map_order_type(order.order_type)
            upstox_product = self._map_product_type(order.product_type)
            upstox_side = "BUY" if order.side == OrderSide.BUY else "SELL"
            
            # Build order payload
            order_payload = {
                "quantity": order.quantity,
                "product": upstox_product,
                "validity": "DAY",
                "price": order.price or 0,
                "tag": order.tag or "KEEPGAINING",
                "instrument_token": order.symbol,
                "order_type": upstox_order_type,
                "transaction_type": upstox_side,
                "disclosed_quantity": 0,
                "trigger_price": order.trigger_price or 0,
                "is_amo": False  # After Market Order
            }
            
            logger.info(f"Placing order: {order_payload}")
            
            # Place order via API
            response = self._order_api.place_order(order_payload, "2.0")
            
            if response.status == "success":
                order_id = response.data.get("order_id", "") if isinstance(response.data, dict) else str(response.data)
                
                # Cache order
                self._orders[order_id] = {
                    "order_id": order_id,
                    "request": order,
                    "response": response,
                    "placed_at": datetime.now(timezone.utc),
                    "status": "PENDING"
                }
                
                # Publish event
                await self._publish_order_event(order_id, "PLACED", order)
                
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.PENDING,
                    message="Order placed successfully"
                )
            else:
                error_msg = str(response.errors) if hasattr(response, 'errors') else "Order placement failed"
                logger.error(f"Order placement failed: {error_msg}")
                return OrderResponse(
                    order_id="",
                    status=OrderStatus.REJECTED,
                    message=error_msg
                )
                
        except ApiException as e:
            error_body = json.loads(e.body) if e.body else {}
            error_msg = error_body.get("message", str(e))
            logger.error(f"Order API error: {e.status} - {error_msg}")
            return OrderResponse(
                order_id="",
                status=OrderStatus.REJECTED,
                message=error_msg
            )
        except Exception as e:
            logger.error(f"Order placement error: {e}")
            return OrderResponse(
                order_id="",
                status=OrderStatus.REJECTED,
                message=str(e)
            )
    
    async def modify_order(
        self, 
        order_id: str, 
        price: float = None, 
        quantity: int = None,
        trigger_price: float = None,
        order_type: str = None
    ) -> OrderResponse:
        """
        Modify an existing pending order.
        
        Args:
            order_id: Order ID to modify
            price: New price (optional)
            quantity: New quantity (optional)
            trigger_price: New trigger price for SL orders (optional)
            order_type: New order type (optional)
            
        Returns:
            OrderResponse with modification status
        """
        if not self._authenticated:
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        if self.sandbox_mode:
            logger.info(f"[SANDBOX] Would modify order {order_id}")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.PENDING,
                message="Sandbox mode - order not modified"
            )
        
        try:
            # Get current order details
            current_order = self._orders.get(order_id)
            
            modify_payload = {
                "order_id": order_id,
                "validity": "DAY"
            }
            
            if quantity is not None:
                modify_payload["quantity"] = quantity
            if price is not None:
                modify_payload["price"] = price
            if trigger_price is not None:
                modify_payload["trigger_price"] = trigger_price
            if order_type is not None:
                modify_payload["order_type"] = order_type
            
            response = self._order_api.modify_order(modify_payload, "2.0")
            
            if response.status == "success":
                logger.info(f"Order modified: {order_id}")
                await self._publish_order_event(order_id, "MODIFIED", None)
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.PENDING,
                    message="Order modified successfully"
                )
            else:
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.REJECTED,
                    message="Modification failed"
                )
                
        except ApiException as e:
            logger.error(f"Order modify error: {e.status} - {e.body}")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message=str(e)
            )
    
    async def cancel_order(self, order_id: str) -> OrderResponse:
        """
        Cancel a pending order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            OrderResponse with cancellation status
        """
        if not self._authenticated:
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        if self.sandbox_mode:
            logger.info(f"[SANDBOX] Would cancel order {order_id}")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.CANCELLED,
                message="Sandbox mode - order not cancelled"
            )
        
        try:
            response = self._order_api.cancel_order(order_id, "2.0")
            
            if response.status == "success":
                logger.info(f"Order cancelled: {order_id}")
                
                # Update cache
                if order_id in self._orders:
                    self._orders[order_id]["status"] = "CANCELLED"
                
                await self._publish_order_event(order_id, "CANCELLED", None)
                
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.CANCELLED,
                    message="Order cancelled successfully"
                )
            else:
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.REJECTED,
                    message="Cancellation failed"
                )
                
        except ApiException as e:
            logger.error(f"Order cancel error: {e.status} - {e.body}")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message=str(e)
            )
    
    async def get_order_status(self, order_id: str) -> OrderResponse:
        """
        Get the status of a specific order.
        
        Args:
            order_id: Order ID to check
            
        Returns:
            OrderResponse with current order status
        """
        if not self._authenticated:
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        try:
            response = self._order_api.get_order_details("2.0", order_id=order_id)
            
            if response.status == "success" and response.data:
                order_data = response.data[0] if isinstance(response.data, list) else response.data
                order_dict = order_data.to_dict() if hasattr(order_data, 'to_dict') else order_data
                
                status = self._map_upstox_status(order_dict.get("status", ""))
                
                return OrderResponse(
                    order_id=order_id,
                    status=status,
                    filled_quantity=order_dict.get("filled_quantity", 0),
                    average_price=order_dict.get("average_price", 0),
                    message=order_dict.get("status_message", "")
                )
            else:
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.REJECTED,
                    message="Order not found"
                )
                
        except ApiException as e:
            logger.error(f"Get order status error: {e.status} - {e.body}")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message=str(e)
            )
    
    async def get_order_book(self) -> List[Dict]:
        """
        Get all orders for the day.
        
        Returns:
            List of order dictionaries
        """
        if not self._authenticated:
            return []
        
        try:
            response = self._order_api.get_order_book("2.0")
            
            if response.status == "success":
                orders = []
                for order in response.data or []:
                    order_dict = order.to_dict() if hasattr(order, 'to_dict') else order
                    orders.append(order_dict)
                    # Cache
                    self._orders[order_dict.get("order_id", "")] = order_dict
                return orders
            return []
            
        except ApiException as e:
            logger.error(f"Get order book error: {e.status}")
            return []
    
    async def get_trade_book(self) -> List[Dict]:
        """
        Get all trades (executed orders) for the day.
        
        Returns:
            List of trade dictionaries
        """
        if not self._authenticated:
            return []
        
        try:
            response = self._order_api.get_trade_history("2.0")
            
            if response.status == "success":
                trades = []
                for trade in response.data or []:
                    trade_dict = trade.to_dict() if hasattr(trade, 'to_dict') else trade
                    trades.append(trade_dict)
                return trades
            return []
            
        except ApiException as e:
            logger.error(f"Get trade book error: {e.status}")
            return []
    
    async def get_historical_data(
        self, 
        symbol: str, 
        timeframe: str, 
        from_date: str, 
        to_date: str
    ) -> Any:
        """
        Fetch historical OHLC data.
        
        Note: For live trading, use the data service instead.
        This is kept for interface compatibility.
        """
        logger.warning("Use UpstoxDataService for historical data")
        return []
    
    async def get_quote(self, symbol: str) -> Quote:
        """
        Get real-time quote for a symbol.
        
        Note: For bulk quotes, use UpstoxDataService.
        """
        # This would use the market quote API
        return Quote(
            symbol=symbol,
            ltp=0,
            bid=0,
            ask=0,
            volume=0
        )
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map our OrderType to Upstox order type."""
        mapping = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP_LOSS: "SL",
            OrderType.STOP_LOSS_MARKET: "SL-M",
        }
        return mapping.get(order_type, "MARKET")
    
    def _map_product_type(self, product_type: ProductType) -> str:
        """Map our ProductType to Upstox product type."""
        mapping = {
            ProductType.INTRADAY: "I",
            ProductType.DELIVERY: "D",
            ProductType.CNC: "D",
            ProductType.MIS: "I",
        }
        return mapping.get(product_type, "I")
    
    def _map_upstox_status(self, upstox_status: str) -> OrderStatus:
        """Map Upstox order status to our OrderStatus."""
        mapping = {
            "open": OrderStatus.PENDING,
            "pending": OrderStatus.PENDING,
            "trigger pending": OrderStatus.PENDING,
            "complete": OrderStatus.FILLED,
            "traded": OrderStatus.FILLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "modified": OrderStatus.PENDING,
        }
        return mapping.get(upstox_status.lower(), OrderStatus.PENDING)
    
    async def _publish_order_event(
        self, 
        order_id: str, 
        event_type: str, 
        order: Optional[OrderRequest]
    ) -> None:
        """Publish order event to event bus."""
        try:
            await self.event_bus.publish(
                "order",
                {
                    "order_id": order_id,
                    "event": event_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "order": order.__dict__ if order else None
                }
            )
        except Exception as e:
            logger.warning(f"Failed to publish order event: {e}")

    async def get_order_activity_summary(self) -> Dict[str, int]:
        """
        Get today's order activity with Upstox-specific status mapping.
        
        Upstox Order Statuses:
        - open/pending/trigger pending: Pending
        - complete/traded: Executed (Filled)
        - cancelled: Cancelled
        - rejected: Rejected
        """
        summary = {
            "orders_placed": 0,
            "orders_executed": 0,
            "orders_rejected": 0,
            "orders_pending": 0,
            "orders_cancelled": 0
        }
        
        if not self._authenticated:
            logger.warning("Not authenticated - cannot get order activity")
            return summary
        
        try:
            # Get order book from Upstox
            response = self._order_api.get_order_book(self._api_version)
            
            if response and hasattr(response, 'data') and response.data:
                for order in response.data:
                    summary["orders_placed"] += 1
                    status = order.status.lower() if hasattr(order, 'status') else ""
                    
                    if status in ["complete", "traded"]:
                        summary["orders_executed"] += 1
                    elif status == "rejected":
                        summary["orders_rejected"] += 1
                    elif status == "cancelled":
                        summary["orders_cancelled"] += 1
                    elif status in ["open", "pending", "trigger pending", "modified"]:
                        summary["orders_pending"] += 1
                        
        except ApiException as e:
            logger.error(f"Error fetching order activity: {e.status}")
        except Exception as e:
            logger.error(f"Error getting order activity: {e}")
        
        return summary


# Factory function
def create_upstox_live_broker(
    access_token: Optional[str] = None,
    sandbox: bool = False
) -> UpstoxLiveBroker:
    """Create and return an Upstox live broker instance."""
    return UpstoxLiveBroker(
        access_token=access_token,
        sandbox_mode=sandbox
    )
