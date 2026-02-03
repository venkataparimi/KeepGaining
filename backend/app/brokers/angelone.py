"""
Angel One (Angel Broking) SmartAPI Integration

Full implementation of Angel One broker using SmartAPI:
- Authentication with OAuth 2.0 + TOTP
- Order placement, modification, cancellation
- Position and holdings management
- Historical and real-time data
- WebSocket streaming for live quotes

Requires: pip install smartapi-python pyotp
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from decimal import Decimal

from app.brokers.base import BaseBroker
from app.schemas.broker import (
    OrderRequest, OrderResponse, Position, Quote,
    OrderType, OrderSide, ProductType
)
from app.db.models import OrderStatus

logger = logging.getLogger(__name__)


class AngelOneBroker(BaseBroker):
    """
    Angel One SmartAPI Implementation.
    
    Provides full trading functionality through Angel One's SmartAPI.
    Supports equities, F&O, currency, and commodity trading.
    """
    
    # Exchange codes
    EXCHANGE_MAP = {
        "NSE": "NSE",
        "BSE": "BSE",
        "NFO": "NFO",
        "BFO": "BFO",
        "CDS": "CDS",
        "MCX": "MCX",
    }
    
    # Order type mapping
    ORDER_TYPE_MAP = {
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT: "LIMIT",
        OrderType.SL: "STOPLOSS_LIMIT",
        OrderType.SL_M: "STOPLOSS_MARKET",
    }
    
    # Product type mapping
    PRODUCT_MAP = {
        ProductType.MIS: "INTRADAY",
        ProductType.CNC: "DELIVERY",
        ProductType.NRML: "CARRYFORWARD",
    }
    
    # Variety mapping
    VARIETY_MAP = {
        "regular": "NORMAL",
        "amo": "AMO",        # After Market Order
        "stoploss": "STOPLOSS",
        "robo": "ROBO",      # Bracket/Cover Order
    }
    
    def __init__(
        self,
        api_key: str,
        client_id: str,
        password: str,
        totp_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None
    ):
        """
        Initialize Angel One broker.
        
        Args:
            api_key: SmartAPI API key
            client_id: Angel One client ID
            password: Trading password or PIN
            totp_secret: TOTP secret for 2FA (optional)
            access_token: Pre-existing access token (optional)
            refresh_token: Refresh token (optional)
        """
        self.api_key = api_key
        self.client_id = client_id
        self.password = password
        self.totp_secret = totp_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        
        self.smart_api = None
        self.is_authenticated = False
        self.user_name: Optional[str] = None
        self.user_email: Optional[str] = None
        
        # WebSocket state
        self._ws = None
        self._ws_connected = False
        self._subscribed_tokens: List[Dict] = []
        self._tick_callbacks: List[callable] = []
        
        # Initialize if access token provided
        if access_token:
            self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize SmartAPI client."""
        try:
            from SmartApi import SmartConnect
            
            self.smart_api = SmartConnect(api_key=self.api_key)
            
            if self.access_token:
                self.smart_api.setAccessToken(self.access_token)
                if self.refresh_token:
                    self.smart_api.setRefreshToken(self.refresh_token)
                self.is_authenticated = True
                logger.info("Angel One client initialized with access token")
                
        except ImportError:
            logger.warning("smartapi-python not installed. Run: pip install smartapi-python")
            self.smart_api = None
        except Exception as e:
            logger.error(f"Failed to initialize Angel One client: {e}")
            self.smart_api = None
    
    async def authenticate(self, totp: Optional[str] = None) -> bool:
        """
        Authenticate with Angel One.
        
        Args:
            totp: TOTP code for 2FA (optional if totp_secret provided)
            
        Returns:
            True if authentication successful
        """
        try:
            from SmartApi import SmartConnect
            
            self.smart_api = SmartConnect(api_key=self.api_key)
            
            # Generate TOTP if secret provided
            if not totp and self.totp_secret:
                try:
                    import pyotp
                    totp_obj = pyotp.TOTP(self.totp_secret)
                    totp = totp_obj.now()
                except ImportError:
                    logger.error("pyotp not installed for TOTP generation")
                    return False
            
            # Login
            data = self.smart_api.generateSession(
                clientCode=self.client_id,
                password=self.password,
                totp=totp
            )
            
            if data and data.get("status"):
                self.access_token = data["data"]["jwtToken"]
                self.refresh_token = data["data"]["refreshToken"]
                self.user_name = data["data"].get("name", "")
                self.user_email = data["data"].get("email", "")
                self.is_authenticated = True
                
                logger.info(f"Angel One authenticated for user: {self.client_id}")
                return True
            else:
                logger.error(f"Angel One authentication failed: {data}")
                return False
                
        except ImportError:
            logger.error("smartapi-python not installed")
            return False
        except Exception as e:
            logger.error(f"Angel One authentication failed: {e}")
            self.is_authenticated = False
            return False
    
    async def get_positions(self) -> List[Position]:
        """
        Fetch current open positions.
        
        Returns:
            List of Position objects
        """
        if not self._check_auth():
            return []
        
        try:
            position_data = self.smart_api.position()
            
            if not position_data or not position_data.get("data"):
                return []
            
            result = []
            for pos in position_data["data"]:
                if int(pos.get("netqty", 0)) != 0:
                    result.append(Position(
                        symbol=pos["tradingsymbol"],
                        exchange=pos["exchange"],
                        quantity=int(pos["netqty"]),
                        average_price=float(pos.get("averageprice", 0)),
                        last_price=float(pos.get("ltp", 0)),
                        pnl=float(pos.get("pnl", 0)),
                        unrealized_pnl=float(pos.get("unrealised", 0)),
                        realized_pnl=float(pos.get("realised", 0)),
                        product=pos.get("producttype", ""),
                        overnight_quantity=int(pos.get("cfbuyqty", 0)) - int(pos.get("cfsellqty", 0)),
                        multiplier=int(pos.get("multiplier", 1)),
                        value=float(pos.get("netqty", 0)) * float(pos.get("ltp", 0)),
                    ))
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []
    
    async def get_holdings(self) -> List[Dict[str, Any]]:
        """
        Fetch portfolio holdings (delivery positions).
        
        Returns:
            List of holdings
        """
        if not self._check_auth():
            return []
        
        try:
            holding_data = self.smart_api.holding()
            
            if not holding_data or not holding_data.get("data"):
                return []
            
            return [
                {
                    "symbol": h["tradingsymbol"],
                    "exchange": h["exchange"],
                    "isin": h.get("isin", ""),
                    "quantity": int(h.get("quantity", 0)),
                    "average_price": float(h.get("averageprice", 0)),
                    "last_price": float(h.get("ltp", 0)),
                    "pnl": float(h.get("profitandloss", 0)),
                    "day_change": float(h.get("close", 0)) - float(h.get("averageprice", 0)),
                    "day_change_pct": (
                        (float(h.get("ltp", 0)) - float(h.get("averageprice", 0))) /
                        float(h.get("averageprice", 1)) * 100
                    ) if float(h.get("averageprice", 0)) > 0 else 0,
                }
                for h in holding_data["data"]
            ]
            
        except Exception as e:
            logger.error(f"Failed to fetch holdings: {e}")
            return []
    
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """
        Place a new order.
        
        Args:
            order: OrderRequest with order details
            
        Returns:
            OrderResponse with order ID and status
        """
        if not self._check_auth():
            return OrderResponse(
                order_id="",
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        try:
            # Get symbol token
            symbol_token = await self._get_symbol_token(order.symbol, order.exchange)
            
            if not symbol_token:
                return OrderResponse(
                    order_id="",
                    status=OrderStatus.REJECTED,
                    message=f"Symbol not found: {order.symbol}"
                )
            
            # Build order params
            order_params = {
                "tradingsymbol": order.symbol,
                "symboltoken": symbol_token,
                "exchange": self.EXCHANGE_MAP.get(order.exchange, order.exchange),
                "transactiontype": "BUY" if order.side == OrderSide.BUY else "SELL",
                "quantity": order.quantity,
                "producttype": self.PRODUCT_MAP.get(order.product, "INTRADAY"),
                "ordertype": self.ORDER_TYPE_MAP.get(order.order_type, "MARKET"),
                "variety": self.VARIETY_MAP.get(order.variety, "NORMAL"),
                "duration": "DAY",
            }
            
            # Add price for limit orders
            if order.order_type in [OrderType.LIMIT, OrderType.SL]:
                order_params["price"] = str(order.price)
            else:
                order_params["price"] = "0"
            
            # Add trigger price for SL orders
            if order.order_type in [OrderType.SL, OrderType.SL_M]:
                order_params["triggerprice"] = str(order.trigger_price)
            else:
                order_params["triggerprice"] = "0"
            
            # Place order
            result = self.smart_api.placeOrder(order_params)
            
            if result and result.get("status"):
                order_id = result["data"]["orderid"]
                logger.info(f"Angel One order placed: {order_id} for {order.symbol}")
                
                return OrderResponse(
                    order_id=str(order_id),
                    status=OrderStatus.PENDING,
                    message="Order placed successfully"
                )
            else:
                return OrderResponse(
                    order_id="",
                    status=OrderStatus.REJECTED,
                    message=result.get("message", "Order placement failed")
                )
                
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
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
        order_type: OrderType = None
    ) -> OrderResponse:
        """
        Modify an existing pending order.
        """
        if not self._check_auth():
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        try:
            # Get existing order details first
            orders = await self.get_orders()
            existing_order = None
            for o in orders:
                if o["order_id"] == order_id:
                    existing_order = o
                    break
            
            if not existing_order:
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.REJECTED,
                    message="Order not found"
                )
            
            # Build modify params
            modify_params = {
                "orderid": order_id,
                "variety": existing_order.get("variety", "NORMAL"),
                "tradingsymbol": existing_order["symbol"],
                "symboltoken": existing_order.get("symbol_token", ""),
                "exchange": existing_order["exchange"],
                "transactiontype": existing_order["transaction_type"],
                "producttype": existing_order["product"],
                "ordertype": self.ORDER_TYPE_MAP.get(order_type, existing_order["order_type"]) if order_type else existing_order["order_type"],
                "duration": "DAY",
                "quantity": str(quantity) if quantity else str(existing_order["quantity"]),
                "price": str(price) if price else str(existing_order.get("price", 0)),
                "triggerprice": str(trigger_price) if trigger_price else str(existing_order.get("trigger_price", 0)),
            }
            
            result = self.smart_api.modifyOrder(modify_params)
            
            if result and result.get("status"):
                logger.info(f"Angel One order modified: {order_id}")
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.PENDING,
                    message="Order modified successfully"
                )
            else:
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.REJECTED,
                    message=result.get("message", "Modification failed")
                )
                
        except Exception as e:
            logger.error(f"Failed to modify order {order_id}: {e}")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message=str(e)
            )
    
    async def cancel_order(self, order_id: str, variety: str = "NORMAL") -> OrderResponse:
        """
        Cancel a pending order.
        """
        if not self._check_auth():
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        try:
            result = self.smart_api.cancelOrder(order_id, variety)
            
            if result and result.get("status"):
                logger.info(f"Angel One order cancelled: {order_id}")
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.CANCELLED,
                    message="Order cancelled successfully"
                )
            else:
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.REJECTED,
                    message=result.get("message", "Cancellation failed")
                )
                
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message=str(e)
            )
    
    async def get_order_status(self, order_id: str) -> OrderResponse:
        """
        Get the status of a specific order.
        """
        if not self._check_auth():
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        try:
            order_book = self.smart_api.orderBook()
            
            if order_book and order_book.get("data"):
                for order in order_book["data"]:
                    if str(order["orderid"]) == order_id:
                        status = self._map_order_status(order["status"])
                        return OrderResponse(
                            order_id=order_id,
                            status=status,
                            filled_quantity=int(order.get("filledshares", 0)),
                            average_price=float(order.get("averageprice", 0)),
                            message=order.get("text", "")
                        )
            
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="Order not found"
            )
            
        except Exception as e:
            logger.error(f"Failed to get order status {order_id}: {e}")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message=str(e)
            )
    
    def _map_order_status(self, angel_status: str) -> OrderStatus:
        """Map Angel One order status to internal status."""
        status_map = {
            "complete": OrderStatus.FILLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "open": OrderStatus.OPEN,
            "pending": OrderStatus.PENDING,
            "trigger pending": OrderStatus.PENDING,
            "open pending": OrderStatus.PENDING,
            "validation pending": OrderStatus.PENDING,
            "put order req received": OrderStatus.PENDING,
            "modify pending": OrderStatus.PENDING,
            "cancel pending": OrderStatus.PENDING,
            "after market order req received": OrderStatus.PENDING,
        }
        return status_map.get(angel_status.lower(), OrderStatus.PENDING)
    
    async def get_orders(self) -> List[Dict[str, Any]]:
        """Get all orders for the day."""
        if not self._check_auth():
            return []
        
        try:
            order_book = self.smart_api.orderBook()
            
            if not order_book or not order_book.get("data"):
                return []
            
            return [
                {
                    "order_id": str(o["orderid"]),
                    "symbol": o["tradingsymbol"],
                    "symbol_token": o.get("symboltoken", ""),
                    "exchange": o["exchange"],
                    "transaction_type": o["transactiontype"],
                    "quantity": int(o["quantity"]),
                    "filled_quantity": int(o.get("filledshares", 0)),
                    "pending_quantity": int(o["quantity"]) - int(o.get("filledshares", 0)),
                    "price": float(o.get("price", 0)),
                    "average_price": float(o.get("averageprice", 0)),
                    "trigger_price": float(o.get("triggerprice", 0)),
                    "order_type": o["ordertype"],
                    "product": o["producttype"],
                    "variety": o.get("variety", "NORMAL"),
                    "status": o["status"],
                    "status_message": o.get("text", ""),
                    "placed_at": o.get("updatetime"),
                }
                for o in order_book["data"]
            ]
            
        except Exception as e:
            logger.error(f"Failed to fetch orders: {e}")
            return []
    
    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        from_date: str,
        to_date: str,
        exchange: str = "NSE"
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical OHLC data.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle interval (ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, THIRTY_MINUTE, ONE_HOUR, ONE_DAY)
            from_date: Start date (YYYY-MM-DD HH:MM)
            to_date: End date (YYYY-MM-DD HH:MM)
            exchange: Exchange
            
        Returns:
            List of candle data
        """
        if not self._check_auth():
            return []
        
        try:
            # Get symbol token
            symbol_token = await self._get_symbol_token(symbol, exchange)
            
            if not symbol_token:
                logger.error(f"Symbol not found: {symbol}")
                return []
            
            # Map timeframe
            interval_map = {
                "1m": "ONE_MINUTE",
                "1minute": "ONE_MINUTE",
                "5m": "FIVE_MINUTE",
                "5minute": "FIVE_MINUTE",
                "15m": "FIFTEEN_MINUTE",
                "15minute": "FIFTEEN_MINUTE",
                "30m": "THIRTY_MINUTE",
                "30minute": "THIRTY_MINUTE",
                "60m": "ONE_HOUR",
                "60minute": "ONE_HOUR",
                "1h": "ONE_HOUR",
                "1d": "ONE_DAY",
                "day": "ONE_DAY",
            }
            interval = interval_map.get(timeframe.lower(), "ONE_DAY")
            
            params = {
                "exchange": exchange,
                "symboltoken": symbol_token,
                "interval": interval,
                "fromdate": from_date,
                "todate": to_date,
            }
            
            data = self.smart_api.getCandleData(params)
            
            if data and data.get("data"):
                return [
                    {
                        "timestamp": candle[0],
                        "open": candle[1],
                        "high": candle[2],
                        "low": candle[3],
                        "close": candle[4],
                        "volume": candle[5],
                    }
                    for candle in data["data"]
                ]
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to fetch historical data: {e}")
            return []
    
    async def get_quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Get real-time quote for a symbol."""
        if not self._check_auth():
            return Quote(symbol=symbol, last_price=0, volume=0, timestamp=None)
        
        try:
            symbol_token = await self._get_symbol_token(symbol, exchange)
            
            if not symbol_token:
                return Quote(symbol=symbol, last_price=0, volume=0, timestamp=None)
            
            data = self.smart_api.ltpData(exchange, symbol, symbol_token)
            
            if data and data.get("data"):
                ltp_data = data["data"]
                return Quote(
                    symbol=symbol,
                    last_price=float(ltp_data.get("ltp", 0)),
                    volume=0,  # LTP call doesn't include volume
                    timestamp=datetime.now(),
                    open=float(ltp_data.get("open", 0)),
                    high=float(ltp_data.get("high", 0)),
                    low=float(ltp_data.get("low", 0)),
                    close=float(ltp_data.get("close", 0)),
                )
            
            return Quote(symbol=symbol, last_price=0, volume=0, timestamp=None)
            
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            return Quote(symbol=symbol, last_price=0, volume=0, timestamp=None)
    
    async def get_order_activity_summary(self) -> Dict[str, int]:
        """Get today's order activity summary."""
        if not self._check_auth():
            return {
                "orders_placed": 0,
                "orders_executed": 0,
                "orders_rejected": 0,
                "orders_pending": 0,
                "orders_cancelled": 0,
            }
        
        try:
            orders = await self.get_orders()
            
            summary = {
                "orders_placed": len(orders),
                "orders_executed": 0,
                "orders_rejected": 0,
                "orders_pending": 0,
                "orders_cancelled": 0,
            }
            
            for order in orders:
                status = order.get("status", "").lower()
                if status == "complete":
                    summary["orders_executed"] += 1
                elif status == "rejected":
                    summary["orders_rejected"] += 1
                elif status == "cancelled":
                    summary["orders_cancelled"] += 1
                elif status in ["open", "pending", "trigger pending", "open pending"]:
                    summary["orders_pending"] += 1
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get order summary: {e}")
            return {
                "orders_placed": 0,
                "orders_executed": 0,
                "orders_rejected": 0,
                "orders_pending": 0,
                "orders_cancelled": 0,
            }
    
    async def get_margins(self) -> Dict[str, Any]:
        """Get account margins."""
        if not self._check_auth():
            return {}
        
        try:
            rms_data = self.smart_api.rmsLimit()
            
            if rms_data and rms_data.get("data"):
                data = rms_data["data"]
                return {
                    "available_cash": float(data.get("availablecash", 0)),
                    "available_margin": float(data.get("availableintradaypayin", 0)),
                    "used_margin": float(data.get("utiliseddebits", 0)),
                    "collateral": float(data.get("collateral", 0)),
                    "net": float(data.get("net", 0)),
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get margins: {e}")
            return {}
    
    async def _get_symbol_token(self, symbol: str, exchange: str) -> Optional[str]:
        """Get symbol token for trading."""
        try:
            # Search in instrument list
            # Note: In production, cache the instrument list
            search_result = self.smart_api.searchScrip(exchange, symbol)
            
            if search_result and search_result.get("data"):
                for scrip in search_result["data"]:
                    if scrip["tradingsymbol"] == symbol:
                        return scrip["symboltoken"]
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get symbol token: {e}")
            return None
    
    def _check_auth(self) -> bool:
        """Check if authenticated."""
        if not self.is_authenticated or not self.smart_api:
            logger.warning("Angel One not authenticated")
            return False
        return True
    
    # WebSocket methods
    
    async def connect_websocket(self) -> bool:
        """Connect to Angel One WebSocket for live data."""
        if not self._check_auth():
            return False
        
        try:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2
            
            def on_data(wsapp, message):
                for callback in self._tick_callbacks:
                    try:
                        callback(message)
                    except Exception as e:
                        logger.error(f"Tick callback error: {e}")
            
            def on_open(wsapp):
                logger.info("Angel One WebSocket connected")
                self._ws_connected = True
            
            def on_close(wsapp):
                logger.warning("Angel One WebSocket closed")
                self._ws_connected = False
            
            def on_error(wsapp, error):
                logger.error(f"Angel One WebSocket error: {error}")
            
            self._ws = SmartWebSocketV2(
                self.access_token,
                self.api_key,
                self.client_id,
                self.smart_api.FEED_TOKEN
            )
            
            self._ws.on_data = on_data
            self._ws.on_open = on_open
            self._ws.on_close = on_close
            self._ws.on_error = on_error
            
            self._ws.connect()
            
            return True
            
        except ImportError:
            logger.error("smartapi-python not installed")
            return False
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
            return False
    
    def subscribe(
        self,
        tokens: List[Dict[str, str]],
        mode: int = 1
    ) -> None:
        """
        Subscribe to tokens for live data.
        
        Args:
            tokens: List of {"exchange": "NSE", "token": "1234"}
            mode: 1 = LTP, 2 = Quote, 3 = Snap Quote
        """
        self._subscribed_tokens.extend(tokens)
        
        if self._ws and self._ws_connected:
            correlation_id = "stream_1"
            self._ws.subscribe(correlation_id, mode, tokens)
    
    def unsubscribe(self, tokens: List[Dict[str, str]]) -> None:
        """Unsubscribe from tokens."""
        for token in tokens:
            if token in self._subscribed_tokens:
                self._subscribed_tokens.remove(token)
        
        if self._ws and self._ws_connected:
            correlation_id = "stream_1"
            self._ws.unsubscribe(correlation_id, 1, tokens)
    
    def add_tick_callback(self, callback: callable) -> None:
        """Add callback for tick data."""
        self._tick_callbacks.append(callback)
    
    async def disconnect_websocket(self) -> None:
        """Disconnect WebSocket."""
        if self._ws:
            self._ws.close_connection()
            self._ws_connected = False
            self._subscribed_tokens = []
            logger.info("Angel One WebSocket disconnected")
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status."""
        return {
            "broker": "angelone",
            "authenticated": self.is_authenticated,
            "client_id": self.client_id,
            "user_name": self.user_name,
            "websocket_connected": self._ws_connected,
            "subscribed_tokens": len(self._subscribed_tokens),
        }
    
    async def logout(self) -> bool:
        """Logout and invalidate session."""
        if not self._check_auth():
            return True
        
        try:
            result = self.smart_api.terminateSession(self.client_id)
            self.is_authenticated = False
            self.access_token = None
            self.refresh_token = None
            logger.info("Angel One session terminated")
            return True
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            return False
