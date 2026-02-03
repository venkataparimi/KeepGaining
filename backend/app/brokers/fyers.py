from typing import Dict, Any, List, Optional
from app.brokers.base import BaseBroker
from app.brokers.fyers_client import FyersClient
from app.core.config import settings
from app.schemas.broker import OrderRequest, OrderResponse, Position, Quote, OrderStatus
from loguru import logger
import pandas as pd
from datetime import datetime

class FyersBroker(BaseBroker):
    """
    Fyers Broker Adapter using the advanced FyersClient.
    """
    def __init__(self):
        self.client = FyersClient(
            client_id=settings.FYERS_CLIENT_ID,
            secret_key=settings.FYERS_SECRET_KEY,
            redirect_uri=settings.FYERS_REDIRECT_URI,
            username=settings.FYERS_USER_ID,
            pin=settings.FYERS_PIN,
            totp_key=settings.FYERS_TOTP_KEY
        )

    async def authenticate(self) -> bool:
        # FyersClient handles auth internally in __init__
        # Check if access_token is present and try a simple API call
        if not self.client.access_token:
            logger.warning("Fyers Broker: No access token available")
            return False
        
        try:
            # Try to get profile to verify connectivity
            response = self.client.get_profile()
            if response.get("s") == "ok":
                logger.info("Fyers Broker Authenticated and verified via API call")
                return True
            else:
                logger.warning(f"Fyers Broker: API returned error: {response.get('message')}")
                return False
        except Exception as e:
            logger.error(f"Fyers Broker: Authentication verification failed: {e}")
            return False

    async def get_positions(self) -> List[Position]:
        response = self.client.get_positions()
        if response.get("s") != "ok":
            logger.error(f"Failed to fetch positions: {response.get('message')}")
            return []

        # Exchange code mapping for Fyers
        exchange_map = {
            10: "NSE",
            11: "MCX", 
            12: "BSE",
            "NSE": "NSE",
            "MCX": "MCX",
            "BSE": "BSE"
        }

        positions = []
        for p in response.get("netPositions", []):
            exchange_val = p.get("exchange", "NSE")
            exchange_str = exchange_map.get(exchange_val, str(exchange_val))
            
            # Use netAvg for average price (Fyers uses netAvg for net positions)
            avg_price = p.get("netAvg") or p.get("avgPrice") or p.get("buyAvg") or 0.0
            
            positions.append(Position(
                symbol=p.get("symbol", ""),
                quantity=p.get("netQty") or p.get("qty", 0),
                average_price=avg_price,
                last_price=p.get("ltp") or 0.0,
                pnl=p.get("pl") or p.get("unrealized_profit") or 0.0,
                product_type=p.get("productType", "INTRADAY"),
                exchange=exchange_str
            ))
        return positions

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        data = {
            "symbol": order.symbol,
            "qty": order.quantity,
            "type": 1 if order.order_type == "LIMIT" else 2, # 1=Limit, 2=Market
            "side": 1 if order.side == "BUY" else -1,
            "productType": "INTRADAY", # Defaulting to Intraday
            "limitPrice": order.price if order.price else 0,
            "stopPrice": 0,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
        }

        response = self.client.place_order(data=data)
        
        if response.get("s") == "ok":
            return OrderResponse(
                order_id=response.get("id"),
                status=OrderStatus.PENDING,
                message="Order placed successfully"
            )
        else:
            return OrderResponse(
                order_id="",
                status=OrderStatus.REJECTED,
                message=response.get("message", "Unknown error")
            )

    async def modify_order(self, order_id: str, order: OrderRequest) -> OrderResponse:
        data = {
            "id": order_id,
            "qty": order.quantity,
            "type": 1 if order.order_type == "LIMIT" else 2,
            "limitPrice": order.price if order.price else 0,
        }
        
        response = self.client.modify_order(data=data)
        
        if response.get("s") == "ok":
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.PENDING,
                message="Order modified successfully"
            )
        else:
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message=response.get("message", "Unknown error")
            )

    async def cancel_order(self, order_id: str) -> OrderResponse:
        data = {"id": order_id}
        response = self.client.cancel_order(data=data)
        
        if response.get("s") == "ok":
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.CANCELLED,
                message="Order cancelled successfully"
            )
        else:
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message=response.get("message", "Unknown error")
            )

    async def get_order_status(self, order_id: str) -> OrderResponse:
        # Fetch all orders and find the one
        response = self.client.get_orders()
        if response.get("s") != "ok":
            return OrderResponse(order_id=order_id, status=OrderStatus.UNKNOWN, message="Failed to fetch orders")
        
        orders = response.get("orderBook", [])
        for o in orders:
            if o.get("id") == order_id:
                status_map = {
                    1: OrderStatus.CANCELLED,
                    2: OrderStatus.FILLED,
                    3: OrderStatus.REJECTED, # Check Fyers status codes
                    4: OrderStatus.PENDING,
                    5: OrderStatus.REJECTED,
                    6: OrderStatus.PENDING
                }
                # Fyers Status Codes: 1: Cancelled, 2: Traded/Filled, 3: For Future Use, 4: Transit, 5: Rejected, 6: Pending
                fyers_status = o.get("status")
                return OrderResponse(
                    order_id=order_id,
                    status=status_map.get(fyers_status, OrderStatus.UNKNOWN),
                    message=o.get("message", "")
                )
        
        return OrderResponse(order_id=order_id, status=OrderStatus.UNKNOWN, message="Order not found")

    async def get_quote(self, symbol: str) -> Quote:
        response = self.client.get_quotes(symbols=[symbol])
        if response.get("s") != "ok":
            logger.error(f"Failed to fetch quote: {response.get('message')}")
            return Quote(symbol=symbol, price=0.0, volume=0, timestamp=datetime.now())
        
        d = response.get("d", [])
        if d:
            data = d[0].get("v", {})
            return Quote(
                symbol=symbol,
                price=data.get("lp", 0.0), # Last Traded Price
                volume=data.get("volume", 0),
                timestamp=datetime.fromtimestamp(data.get("tt", datetime.now().timestamp()))
            )
        
        return Quote(symbol=symbol, price=0.0, volume=0, timestamp=datetime.now())

    async def get_quotes_batch(self, symbols: List[str]) -> Dict[str, Any]:
        """Fetch quotes for multiple symbols in one call."""
        # Fyers allows max 50 symbols per call usually, need to chunk if large
        # For now assuming list is reasonable size or client handles it (client just joins with comma)
        response = self.client.get_quotes(symbols=symbols)
        if response.get("s") != "ok":
            logger.error(f"Failed to fetch batch quotes: {response.get('message')}")
            return {}
        
        # Map response to symbol -> data
        result = {}
        for item in response.get("d", []):
            # item['n'] is the symbol name
            symbol = item.get("n")
            data = item.get("v", {})
            result[symbol] = {
                "price": data.get("lp", 0.0),
                "change_percent": data.get("chp", 0.0),
                "volume": data.get("volume", 0),
                "oi": data.get("oi", 0), # Open Interest
                "prev_close": data.get("prev_close_price", 0.0)
            }
        return result

    async def get_historical_data(self, symbol: str, resolution: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        return self.client.fetch_historical_data_chunked(
            symbol=symbol,
            resolution=resolution,
            range_from=start_date.strftime("%Y-%m-%d"),
            range_to=end_date.strftime("%Y-%m-%d")
        )

    async def get_order_activity_summary(self) -> Dict[str, int]:
        """
        Get today's order activity with Fyers-specific status code mapping.
        
        Fyers Order Status Codes:
        - 1: Cancelled
        - 2: Traded/Filled (Executed)
        - 3: For Future Use
        - 4: Transit (Pending)
        - 5: Rejected
        - 6: Pending
        """
        response = self.client.get_orders()
        
        summary = {
            "orders_placed": 0,
            "orders_executed": 0,
            "orders_rejected": 0,
            "orders_pending": 0,
            "orders_cancelled": 0
        }
        
        if response.get("s") != "ok":
            logger.error(f"Failed to fetch orders: {response.get('message')}")
            return summary
        
        order_book = response.get("orderBook", [])
        
        for order in order_book:
            summary["orders_placed"] += 1
            status = order.get("status")
            
            if status == 2:  # Traded/Filled
                summary["orders_executed"] += 1
            elif status == 5:  # Rejected
                summary["orders_rejected"] += 1
            elif status == 1:  # Cancelled
                summary["orders_cancelled"] += 1
            elif status in [4, 6]:  # Transit or Pending
                summary["orders_pending"] += 1
        
        return summary
