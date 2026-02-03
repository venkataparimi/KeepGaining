"""
Zerodha Kite Connect Integration

Full implementation of Zerodha broker using Kite Connect API:
- Authentication with OAuth 2.0
- Order placement, modification, cancellation
- Position and holdings management
- Historical and real-time data
- WebSocket streaming for live quotes

Requires: pip install kiteconnect
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


class ZerodhaBroker(BaseBroker):
    """
    Zerodha Kite Connect Implementation.
    
    Provides full trading functionality through Zerodha's Kite Connect API.
    Supports equities, F&O, currency, and commodity trading.
    """
    
    # Zerodha exchange codes
    EXCHANGE_MAP = {
        "NSE": "NSE",
        "BSE": "BSE",
        "NFO": "NFO",  # NSE F&O
        "BFO": "BFO",  # BSE F&O
        "CDS": "CDS",  # Currency
        "MCX": "MCX",  # Commodity
    }
    
    # Order type mapping
    ORDER_TYPE_MAP = {
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT: "LIMIT",
        OrderType.SL: "SL",
        OrderType.SL_M: "SL-M",
    }
    
    # Product type mapping
    PRODUCT_MAP = {
        ProductType.MIS: "MIS",      # Intraday
        ProductType.CNC: "CNC",      # Delivery
        ProductType.NRML: "NRML",    # Normal (F&O)
    }
    
    # Validity mapping
    VALIDITY_MAP = {
        "DAY": "DAY",
        "IOC": "IOC",  # Immediate or Cancel
        "TTL": "TTL",  # Time to Live
    }
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: Optional[str] = None,
        redirect_url: str = "http://localhost:8000/api/zerodha/callback"
    ):
        """
        Initialize Zerodha broker.
        
        Args:
            api_key: Kite Connect API key
            api_secret: Kite Connect API secret
            access_token: Pre-existing access token (optional)
            redirect_url: OAuth redirect URL
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.redirect_url = redirect_url
        
        self.kite = None
        self.kite_ws = None
        self.is_authenticated = False
        self.user_id: Optional[str] = None
        self.user_name: Optional[str] = None
        
        # WebSocket state
        self._ws_connected = False
        self._subscribed_tokens: List[int] = []
        self._tick_callbacks: List[callable] = []
        
        # Initialize if access token provided
        if access_token:
            self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize Kite Connect client."""
        try:
            from kiteconnect import KiteConnect
            
            self.kite = KiteConnect(api_key=self.api_key)
            if self.access_token:
                self.kite.set_access_token(self.access_token)
                self.is_authenticated = True
                logger.info("Zerodha client initialized with access token")
        except ImportError:
            logger.warning("kiteconnect not installed. Run: pip install kiteconnect")
            self.kite = None
        except Exception as e:
            logger.error(f"Failed to initialize Zerodha client: {e}")
            self.kite = None
    
    def get_login_url(self) -> str:
        """
        Get OAuth login URL for Zerodha.
        
        Returns:
            URL to redirect user for authentication
        """
        if not self.kite:
            self._initialize_client()
        
        if self.kite:
            return self.kite.login_url()
        
        # Fallback manual URL construction
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={self.api_key}"
    
    async def authenticate(self, request_token: Optional[str] = None) -> bool:
        """
        Authenticate with Zerodha.
        
        Args:
            request_token: OAuth request token from callback
            
        Returns:
            True if authentication successful
        """
        if not self.kite:
            self._initialize_client()
        
        if not self.kite:
            logger.error("Kite client not available")
            return False
        
        try:
            if request_token:
                # Exchange request token for access token
                data = self.kite.generate_session(
                    request_token=request_token,
                    api_secret=self.api_secret
                )
                
                self.access_token = data["access_token"]
                self.kite.set_access_token(self.access_token)
                self.user_id = data.get("user_id")
                self.user_name = data.get("user_name")
                
                logger.info(f"Zerodha authenticated for user: {self.user_id}")
            
            # Verify authentication by fetching profile
            profile = self.kite.profile()
            self.user_id = profile.get("user_id")
            self.user_name = profile.get("user_name")
            self.is_authenticated = True
            
            return True
            
        except Exception as e:
            logger.error(f"Zerodha authentication failed: {e}")
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
            positions = self.kite.positions()
            result = []
            
            # Day positions
            for pos in positions.get("day", []):
                if pos["quantity"] != 0:
                    result.append(self._convert_position(pos, "day"))
            
            # Net positions
            for pos in positions.get("net", []):
                if pos["quantity"] != 0:
                    result.append(self._convert_position(pos, "net"))
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []
    
    def _convert_position(self, pos: Dict, position_type: str) -> Position:
        """Convert Kite position to internal Position object."""
        return Position(
            symbol=pos["tradingsymbol"],
            exchange=pos["exchange"],
            quantity=pos["quantity"],
            average_price=pos["average_price"],
            last_price=pos.get("last_price", 0),
            pnl=pos.get("pnl", 0),
            unrealized_pnl=pos.get("unrealised", 0),
            realized_pnl=pos.get("realised", 0),
            product=pos["product"],
            overnight_quantity=pos.get("overnight_quantity", 0),
            multiplier=pos.get("multiplier", 1),
            value=pos.get("value", 0),
        )
    
    async def get_holdings(self) -> List[Dict[str, Any]]:
        """
        Fetch portfolio holdings (delivery positions).
        
        Returns:
            List of holdings
        """
        if not self._check_auth():
            return []
        
        try:
            holdings = self.kite.holdings()
            return [
                {
                    "symbol": h["tradingsymbol"],
                    "exchange": h["exchange"],
                    "isin": h.get("isin"),
                    "quantity": h["quantity"],
                    "average_price": h["average_price"],
                    "last_price": h.get("last_price", 0),
                    "pnl": h.get("pnl", 0),
                    "day_change": h.get("day_change", 0),
                    "day_change_pct": h.get("day_change_percentage", 0),
                }
                for h in holdings
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
            # Convert to Kite order format
            order_params = {
                "tradingsymbol": order.symbol,
                "exchange": self.EXCHANGE_MAP.get(order.exchange, order.exchange),
                "transaction_type": "BUY" if order.side == OrderSide.BUY else "SELL",
                "quantity": order.quantity,
                "product": self.PRODUCT_MAP.get(order.product, "MIS"),
                "order_type": self.ORDER_TYPE_MAP.get(order.order_type, "MARKET"),
                "validity": self.VALIDITY_MAP.get(order.validity, "DAY"),
            }
            
            # Add price for limit orders
            if order.order_type in [OrderType.LIMIT, OrderType.SL]:
                order_params["price"] = order.price
            
            # Add trigger price for SL orders
            if order.order_type in [OrderType.SL, OrderType.SL_M]:
                order_params["trigger_price"] = order.trigger_price
            
            # Add tag for tracking
            if order.tag:
                order_params["tag"] = order.tag[:20]  # Max 20 chars
            
            # Place order
            order_id = self.kite.place_order(
                variety="regular",
                **order_params
            )
            
            logger.info(f"Zerodha order placed: {order_id} for {order.symbol}")
            
            return OrderResponse(
                order_id=str(order_id),
                status=OrderStatus.PENDING,
                message="Order placed successfully"
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
        
        Args:
            order_id: Order ID to modify
            price: New price (optional)
            quantity: New quantity (optional)
            trigger_price: New trigger price (optional)
            order_type: New order type (optional)
            
        Returns:
            OrderResponse with status
        """
        if not self._check_auth():
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        try:
            modify_params = {}
            
            if price is not None:
                modify_params["price"] = price
            if quantity is not None:
                modify_params["quantity"] = quantity
            if trigger_price is not None:
                modify_params["trigger_price"] = trigger_price
            if order_type is not None:
                modify_params["order_type"] = self.ORDER_TYPE_MAP.get(order_type, "LIMIT")
            
            self.kite.modify_order(
                variety="regular",
                order_id=order_id,
                **modify_params
            )
            
            logger.info(f"Zerodha order modified: {order_id}")
            
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.PENDING,
                message="Order modified successfully"
            )
            
        except Exception as e:
            logger.error(f"Failed to modify order {order_id}: {e}")
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
            OrderResponse with status
        """
        if not self._check_auth():
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        try:
            self.kite.cancel_order(
                variety="regular",
                order_id=order_id
            )
            
            logger.info(f"Zerodha order cancelled: {order_id}")
            
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.CANCELLED,
                message="Order cancelled successfully"
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
        
        Args:
            order_id: Order ID to check
            
        Returns:
            OrderResponse with current status
        """
        if not self._check_auth():
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        try:
            orders = self.kite.orders()
            
            for order in orders:
                if str(order["order_id"]) == order_id:
                    status = self._map_order_status(order["status"])
                    return OrderResponse(
                        order_id=order_id,
                        status=status,
                        filled_quantity=order.get("filled_quantity", 0),
                        average_price=order.get("average_price", 0),
                        message=order.get("status_message", "")
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
    
    def _map_order_status(self, kite_status: str) -> OrderStatus:
        """Map Kite order status to internal status."""
        status_map = {
            "COMPLETE": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "OPEN": OrderStatus.OPEN,
            "PENDING": OrderStatus.PENDING,
            "TRIGGER PENDING": OrderStatus.PENDING,
            "VALIDATION PENDING": OrderStatus.PENDING,
            "PUT ORDER REQ RECEIVED": OrderStatus.PENDING,
            "MODIFY PENDING": OrderStatus.PENDING,
            "CANCEL PENDING": OrderStatus.PENDING,
        }
        return status_map.get(kite_status.upper(), OrderStatus.PENDING)
    
    async def get_orders(self) -> List[Dict[str, Any]]:
        """
        Get all orders for the day.
        
        Returns:
            List of order details
        """
        if not self._check_auth():
            return []
        
        try:
            orders = self.kite.orders()
            return [
                {
                    "order_id": str(o["order_id"]),
                    "symbol": o["tradingsymbol"],
                    "exchange": o["exchange"],
                    "transaction_type": o["transaction_type"],
                    "quantity": o["quantity"],
                    "filled_quantity": o.get("filled_quantity", 0),
                    "pending_quantity": o.get("pending_quantity", 0),
                    "price": o.get("price", 0),
                    "average_price": o.get("average_price", 0),
                    "trigger_price": o.get("trigger_price", 0),
                    "order_type": o["order_type"],
                    "product": o["product"],
                    "status": o["status"],
                    "status_message": o.get("status_message", ""),
                    "placed_at": o.get("order_timestamp"),
                    "tag": o.get("tag"),
                }
                for o in orders
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
            timeframe: Candle interval (minute, 3minute, 5minute, 15minute, 30minute, 60minute, day)
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            exchange: Exchange (NSE, BSE, NFO, etc.)
            
        Returns:
            List of candle data
        """
        if not self._check_auth():
            return []
        
        try:
            # Get instrument token
            instruments = self.kite.instruments(exchange)
            instrument_token = None
            
            for inst in instruments:
                if inst["tradingsymbol"] == symbol:
                    instrument_token = inst["instrument_token"]
                    break
            
            if not instrument_token:
                logger.error(f"Instrument not found: {symbol}")
                return []
            
            # Fetch historical data
            data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=timeframe,
                continuous=False,
                oi=True if exchange in ["NFO", "MCX", "CDS"] else False
            )
            
            return [
                {
                    "timestamp": d["date"].isoformat(),
                    "open": d["open"],
                    "high": d["high"],
                    "low": d["low"],
                    "close": d["close"],
                    "volume": d["volume"],
                    "oi": d.get("oi", 0),
                }
                for d in data
            ]
            
        except Exception as e:
            logger.error(f"Failed to fetch historical data: {e}")
            return []
    
    async def get_quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """
        Get real-time quote for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange
            
        Returns:
            Quote object
        """
        if not self._check_auth():
            return Quote(symbol=symbol, last_price=0, volume=0, timestamp=None)
        
        try:
            instrument_key = f"{exchange}:{symbol}"
            quotes = self.kite.quote([instrument_key])
            
            if instrument_key in quotes:
                q = quotes[instrument_key]
                return Quote(
                    symbol=symbol,
                    last_price=q.get("last_price", 0),
                    volume=q.get("volume", 0),
                    timestamp=datetime.now(),
                    open=q.get("ohlc", {}).get("open", 0),
                    high=q.get("ohlc", {}).get("high", 0),
                    low=q.get("ohlc", {}).get("low", 0),
                    close=q.get("ohlc", {}).get("close", 0),
                    bid=q.get("depth", {}).get("buy", [{}])[0].get("price", 0),
                    ask=q.get("depth", {}).get("sell", [{}])[0].get("price", 0),
                    change=q.get("change", 0),
                    change_percent=q.get("change", 0) / q.get("ohlc", {}).get("close", 1) * 100 if q.get("ohlc", {}).get("close") else 0,
                )
            
            return Quote(symbol=symbol, last_price=0, volume=0, timestamp=None)
            
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            return Quote(symbol=symbol, last_price=0, volume=0, timestamp=None)
    
    async def get_ltp(self, symbols: List[str], exchange: str = "NSE") -> Dict[str, float]:
        """
        Get last traded price for multiple symbols.
        
        Args:
            symbols: List of trading symbols
            exchange: Exchange
            
        Returns:
            Dict of symbol -> LTP
        """
        if not self._check_auth():
            return {}
        
        try:
            instrument_keys = [f"{exchange}:{s}" for s in symbols]
            ltp_data = self.kite.ltp(instrument_keys)
            
            return {
                key.split(":")[1]: data.get("last_price", 0)
                for key, data in ltp_data.items()
            }
            
        except Exception as e:
            logger.error(f"Failed to get LTP: {e}")
            return {}
    
    async def get_instruments(self, exchange: str = "NSE") -> List[Dict[str, Any]]:
        """
        Get all instruments for an exchange.
        
        Args:
            exchange: Exchange code
            
        Returns:
            List of instrument details
        """
        if not self._check_auth():
            return []
        
        try:
            instruments = self.kite.instruments(exchange)
            return [
                {
                    "instrument_token": i["instrument_token"],
                    "exchange_token": i["exchange_token"],
                    "tradingsymbol": i["tradingsymbol"],
                    "name": i.get("name", ""),
                    "last_price": i.get("last_price", 0),
                    "expiry": i.get("expiry"),
                    "strike": i.get("strike", 0),
                    "tick_size": i.get("tick_size", 0.05),
                    "lot_size": i.get("lot_size", 1),
                    "instrument_type": i.get("instrument_type", ""),
                    "segment": i.get("segment", ""),
                }
                for i in instruments
            ]
        except Exception as e:
            logger.error(f"Failed to fetch instruments: {e}")
            return []
    
    async def get_order_activity_summary(self) -> Dict[str, int]:
        """
        Get today's order activity summary.
        
        Returns:
            Order counts by status
        """
        if not self._check_auth():
            return {
                "orders_placed": 0,
                "orders_executed": 0,
                "orders_rejected": 0,
                "orders_pending": 0,
                "orders_cancelled": 0,
            }
        
        try:
            orders = self.kite.orders()
            
            summary = {
                "orders_placed": len(orders),
                "orders_executed": 0,
                "orders_rejected": 0,
                "orders_pending": 0,
                "orders_cancelled": 0,
            }
            
            for order in orders:
                status = order.get("status", "").upper()
                if status == "COMPLETE":
                    summary["orders_executed"] += 1
                elif status == "REJECTED":
                    summary["orders_rejected"] += 1
                elif status == "CANCELLED":
                    summary["orders_cancelled"] += 1
                elif status in ["OPEN", "PENDING", "TRIGGER PENDING"]:
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
        """
        Get account margins.
        
        Returns:
            Margin details for equity and commodity segments
        """
        if not self._check_auth():
            return {}
        
        try:
            margins = self.kite.margins()
            return {
                "equity": {
                    "available": margins.get("equity", {}).get("available", {}).get("cash", 0),
                    "used": margins.get("equity", {}).get("utilised", {}).get("debits", 0),
                    "collateral": margins.get("equity", {}).get("available", {}).get("collateral", 0),
                },
                "commodity": {
                    "available": margins.get("commodity", {}).get("available", {}).get("cash", 0),
                    "used": margins.get("commodity", {}).get("utilised", {}).get("debits", 0),
                }
            }
        except Exception as e:
            logger.error(f"Failed to get margins: {e}")
            return {}
    
    def _check_auth(self) -> bool:
        """Check if authenticated."""
        if not self.is_authenticated or not self.kite:
            logger.warning("Zerodha not authenticated")
            return False
        return True
    
    # WebSocket methods for streaming
    
    async def connect_websocket(self) -> bool:
        """
        Connect to Zerodha WebSocket for live data.
        
        Returns:
            True if connected
        """
        if not self._check_auth():
            return False
        
        try:
            from kiteconnect import KiteTicker
            
            self.kite_ws = KiteTicker(self.api_key, self.access_token)
            
            def on_ticks(ws, ticks):
                for callback in self._tick_callbacks:
                    try:
                        callback(ticks)
                    except Exception as e:
                        logger.error(f"Tick callback error: {e}")
            
            def on_connect(ws, response):
                logger.info("Zerodha WebSocket connected")
                self._ws_connected = True
                if self._subscribed_tokens:
                    ws.subscribe(self._subscribed_tokens)
                    ws.set_mode(ws.MODE_FULL, self._subscribed_tokens)
            
            def on_close(ws, code, reason):
                logger.warning(f"Zerodha WebSocket closed: {code} - {reason}")
                self._ws_connected = False
            
            def on_error(ws, code, reason):
                logger.error(f"Zerodha WebSocket error: {code} - {reason}")
            
            self.kite_ws.on_ticks = on_ticks
            self.kite_ws.on_connect = on_connect
            self.kite_ws.on_close = on_close
            self.kite_ws.on_error = on_error
            
            # Connect in a thread
            self.kite_ws.connect(threaded=True)
            
            return True
            
        except ImportError:
            logger.error("kiteconnect not installed")
            return False
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
            return False
    
    def subscribe(self, instrument_tokens: List[int], mode: str = "full") -> None:
        """
        Subscribe to instrument tokens for live data.
        
        Args:
            instrument_tokens: List of instrument tokens
            mode: 'ltp', 'quote', or 'full'
        """
        self._subscribed_tokens.extend(instrument_tokens)
        
        if self.kite_ws and self._ws_connected:
            self.kite_ws.subscribe(instrument_tokens)
            
            mode_map = {
                "ltp": self.kite_ws.MODE_LTP,
                "quote": self.kite_ws.MODE_QUOTE,
                "full": self.kite_ws.MODE_FULL,
            }
            self.kite_ws.set_mode(mode_map.get(mode, self.kite_ws.MODE_FULL), instrument_tokens)
    
    def unsubscribe(self, instrument_tokens: List[int]) -> None:
        """Unsubscribe from instrument tokens."""
        for token in instrument_tokens:
            if token in self._subscribed_tokens:
                self._subscribed_tokens.remove(token)
        
        if self.kite_ws and self._ws_connected:
            self.kite_ws.unsubscribe(instrument_tokens)
    
    def add_tick_callback(self, callback: callable) -> None:
        """Add callback for tick data."""
        self._tick_callbacks.append(callback)
    
    async def disconnect_websocket(self) -> None:
        """Disconnect WebSocket."""
        if self.kite_ws:
            self.kite_ws.close()
            self._ws_connected = False
            self._subscribed_tokens = []
            logger.info("Zerodha WebSocket disconnected")
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status."""
        return {
            "broker": "zerodha",
            "authenticated": self.is_authenticated,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "websocket_connected": self._ws_connected,
            "subscribed_tokens": len(self._subscribed_tokens),
        }
