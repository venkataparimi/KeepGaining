"""
Upstox Data Service
KeepGaining Trading Platform

Batch data service for market scanning via Upstox API.
Features:
- Notification-based authentication (semi-automated, official Upstox method)
- TOTP-based automatic authentication (fallback, uses third-party library)
- OAuth2 manual browser flow (fallback)
- High-throughput batch quote fetching (500 symbols per request)
- Historical data downloads with rate limiting
- Efficient symbol mapping
- Event bus integration for publishing scanned data

Authentication Modes:
- NOTIFICATION (default): Request token → Approve on phone → Token delivered to webhook
- TOTP: Fully automated using upstox-totp library (requires credentials in env)
- MANUAL: Browser-based OAuth flow
"""

import asyncio
import webbrowser
import os
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from enum import Enum
from urllib.parse import urlencode, urlparse, parse_qs
import time
import json
from pathlib import Path

import httpx
from loguru import logger

# Optional: upstox-totp for automatic authentication (fallback)
try:
    from upstox_totp import UpstoxTOTP
    UPSTOX_TOTP_AVAILABLE = True
except ImportError:
    UPSTOX_TOTP_AVAILABLE = False

from app.core.config import settings
from app.core.events import EventBus, TickEvent, EventType, get_event_bus


class UpstoxAuthMode(str, Enum):
    """Authentication modes for Upstox."""
    NOTIFICATION = "notification"  # Semi-automated: approve on phone (default, official)
    TOTP = "totp"                  # Fully automated: third-party library
    MANUAL = "manual"              # Browser-based OAuth


class UpstoxAuthState(str, Enum):
    """Authentication states."""
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    AUTHENTICATED = "AUTHENTICATED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    ERROR = "ERROR"


@dataclass
class UpstoxQuote:
    """Upstox quote data structure."""
    symbol: str
    instrument_key: str
    ltp: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    oi: int = 0
    change: float = 0.0
    change_percent: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "instrument_key": self.instrument_key,
            "ltp": self.ltp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "oi": self.oi,
            "change": self.change,
            "change_percent": self.change_percent,
            "bid": self.bid,
            "ask": self.ask,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class HistoricalCandle:
    """Historical candle data structure."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int = 0


class RateLimiter:
    """
    Token bucket rate limiter for API calls.
    
    Supports both per-second and per-minute limits.
    """
    
    def __init__(
        self,
        per_second: int = 25,
        per_minute: int = 2000,
    ):
        self.per_second = per_second
        self.per_minute = per_minute
        
        self._second_tokens = per_second
        self._minute_tokens = per_minute
        self._last_second_refill = time.monotonic()
        self._last_minute_refill = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, count: int = 1) -> None:
        """
        Acquire tokens, waiting if necessary.
        
        Args:
            count: Number of tokens to acquire.
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                
                # Refill second tokens
                elapsed_seconds = now - self._last_second_refill
                if elapsed_seconds >= 1.0:
                    self._second_tokens = self.per_second
                    self._last_second_refill = now
                
                # Refill minute tokens
                elapsed_minutes = now - self._last_minute_refill
                if elapsed_minutes >= 60.0:
                    self._minute_tokens = self.per_minute
                    self._last_minute_refill = now
                
                # Check if we have enough tokens
                if self._second_tokens >= count and self._minute_tokens >= count:
                    self._second_tokens -= count
                    self._minute_tokens -= count
                    return
                
                # Wait for next refill
                if self._second_tokens < count:
                    wait_time = 1.0 - (now - self._last_second_refill)
                else:
                    wait_time = 60.0 - (now - self._last_minute_refill)
                
                await asyncio.sleep(max(0.01, wait_time))


class UpstoxAuth:
    """
    Handles Upstox authentication with multiple modes.
    
    Authentication Modes:
    1. NOTIFICATION (default): Semi-automated, official Upstox method
       - Your app requests token via API
       - You approve on WhatsApp/Upstox app (one tap)
       - Token delivered to your webhook
       
    2. TOTP: Fully automated using third-party upstox-totp library
       - Requires username, password, PIN, TOTP secret in env
       - No manual intervention needed
       - Uses third-party library (security consideration)
       
    3. MANUAL: Browser-based OAuth flow
       - Opens browser for login
       - User completes login manually
    
    Mode Selection:
    - Set UPSTOX_AUTH_MODE env var: "notification", "totp", or "manual"
    - Default is "notification" (safest, official method)
    """
    
    AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
    TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
    TOKEN_REQUEST_URL = "https://api.upstox.com/v3/login/auth/token/request"
    TOKEN_FILE = Path("data/upstox_token.json")
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        auth_mode: Optional[UpstoxAuthMode] = None,
    ):
        """
        Initialize Upstox auth handler.
        
        Args:
            api_key: Upstox API key (client_id)
            api_secret: Upstox API secret (client_secret)
            redirect_uri: OAuth redirect URI
            auth_mode: Authentication mode (notification/totp/manual)
        """
        # Support both old and new env variable names
        self.api_key = api_key or os.getenv('UPSTOX_CLIENT_ID') or getattr(settings, 'UPSTOX_API_KEY', None)
        self.api_secret = api_secret or os.getenv('UPSTOX_CLIENT_SECRET') or getattr(settings, 'UPSTOX_API_SECRET', None)
        self.redirect_uri = redirect_uri or getattr(settings, 'UPSTOX_REDIRECT_URI', None)
        
        # Auth mode from parameter, env, or default to notification
        mode_str = os.getenv('UPSTOX_AUTH_MODE', 'notification').lower()
        self.auth_mode = auth_mode or UpstoxAuthMode(mode_str)
        
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._pending_token_request: bool = False
        
        # Check capabilities
        self._totp_available = UPSTOX_TOTP_AVAILABLE and self._check_totp_config()
        self._notifier_url = os.getenv('UPSTOX_NOTIFIER_URL')  # Webhook URL for notification mode
    
    def _check_totp_config(self) -> bool:
        """Check if TOTP configuration is available."""
        required = ['UPSTOX_USERNAME', 'UPSTOX_PASSWORD', 'UPSTOX_PIN_CODE', 'UPSTOX_TOTP_SECRET']
        return all(os.getenv(var) for var in required)
    
    # =========================================================================
    # NOTIFICATION MODE (Default, Official Upstox Method)
    # =========================================================================
    
    async def request_token_notification(self) -> Dict[str, Any]:
        """
        Request access token via notification mode.
        
        This triggers a notification to your phone (WhatsApp/Upstox app).
        You approve with one tap, and the token is sent to your webhook.
        
        Returns:
            Response with authorization_expiry and notifier_url info.
        """
        if not self.api_key or not self.api_secret:
            return {"success": False, "error": "API credentials not configured"}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.TOKEN_REQUEST_URL}/{self.api_key}",
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={"client_secret": self.api_secret},
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self._pending_token_request = True
                    logger.info(
                        "📱 Token request sent! Check your phone:\n"
                        "   • WhatsApp notification from Upstox\n"
                        "   • Upstox app notification\n"
                        "   Tap to approve, token will be delivered to webhook."
                    )
                    return {
                        "success": True,
                        "message": "Token request sent. Approve on your phone.",
                        "authorization_expiry": data.get("data", {}).get("authorization_expiry"),
                        "notifier_url": data.get("data", {}).get("notifier_url"),
                    }
                else:
                    logger.error(f"Token request failed: {response.status_code} - {response.text}")
                    return {"success": False, "error": response.text}
                    
            except Exception as e:
                logger.error(f"Token request error: {e}")
                return {"success": False, "error": str(e)}
    
    async def receive_token_from_webhook(self, payload: Dict[str, Any]) -> Optional[str]:
        """
        Process token received from Upstox webhook.
        
        Call this from your webhook endpoint when Upstox delivers the token.
        
        Args:
            payload: Webhook payload from Upstox containing access_token
            
        Returns:
            Access token or None.
        """
        if payload.get("message_type") != "access_token":
            logger.warning(f"Unexpected webhook message type: {payload.get('message_type')}")
            return None
        
        self._access_token = payload.get("access_token")
        if self._access_token:
            self._save_token({
                "access_token": self._access_token,
                "user_id": payload.get("user_id"),
                "client_id": payload.get("client_id"),
                "token_type": payload.get("token_type"),
                "expires_at": payload.get("expires_at"),
                "issued_at": payload.get("issued_at"),
            })
            self._pending_token_request = False
            logger.info(f"✅ Token received from webhook! User: {payload.get('user_id')}")
        
        return self._access_token
    
    # =========================================================================
    # TOTP MODE (Third-party library, fully automated)
    # =========================================================================
    
    async def auto_login_totp(self) -> Optional[str]:
        """
        Perform automatic TOTP-based login using upstox-totp library.
        
        ⚠️ Uses third-party library - credentials are handled by that library.
        
        Returns:
            Access token or None if failed.
        """
        if not UPSTOX_TOTP_AVAILABLE:
            logger.warning("upstox-totp library not installed. pip install upstox-totp")
            return None
        
        if not self._check_totp_config():
            logger.warning(
                "TOTP not configured. Required env vars: "
                "UPSTOX_USERNAME, UPSTOX_PASSWORD, UPSTOX_PIN_CODE, UPSTOX_TOTP_SECRET"
            )
            return None
        
        try:
            logger.info("🔐 Attempting Upstox TOTP auto-login...")
            
            upx = UpstoxTOTP()
            response = upx.app_token.get_access_token()
            
            if response.success and response.data:
                self._access_token = response.data.access_token
                self._save_token({
                    "access_token": self._access_token,
                    "user_id": response.data.user_id,
                    "user_name": response.data.user_name,
                    "email": response.data.email,
                    "auth_mode": "totp",
                })
                logger.info(f"✅ TOTP auto-login successful! User: {response.data.user_name}")
                return self._access_token
            else:
                logger.error("TOTP auto-login failed")
                return None
                
        except Exception as e:
            logger.error(f"TOTP auto-login error: {e}")
            return None
    
    # =========================================================================
    # MANUAL MODE (Browser OAuth)
    # =========================================================================
    
    def get_authorization_url(self) -> str:
        """Generate the OAuth authorization URL for manual flow."""
        params = {
            "client_id": self.api_key,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"
    
    async def exchange_code_for_token(self, auth_code: str) -> Optional[str]:
        """Exchange authorization code for access token (manual OAuth flow)."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.TOKEN_URL,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                    data={
                        "code": auth_code,
                        "client_id": self.api_key,
                        "client_secret": self.api_secret,
                        "redirect_uri": self.redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                
                if response.status_code != 200:
                    logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                    return None
                
                data = response.json()
                self._access_token = data.get("access_token")
                
                if self._access_token:
                    self._save_token(data)
                    logger.info("✓ Upstox access token obtained via manual OAuth")
                
                return self._access_token
                
            except Exception as e:
                logger.error(f"Token exchange error: {e}")
                return None
    
    def start_auth_flow(self) -> str:
        """Start interactive OAuth flow - opens browser."""
        auth_url = self.get_authorization_url()
        logger.info(f"Opening Upstox login: {auth_url}")
        webbrowser.open(auth_url)
        return auth_url
    
    # =========================================================================
    # Common Methods
    # =========================================================================
    
    def _save_token(self, token_data: Dict[str, Any]) -> None:
        """Save token to file for reuse."""
        try:
            self.TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            token_data["saved_at"] = datetime.now().isoformat()
            token_data["auth_mode"] = self.auth_mode.value
            self.TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
        except Exception as e:
            logger.warning(f"Could not save token: {e}")
    
    def load_saved_token(self) -> Optional[str]:
        """Load previously saved token if still valid today."""
        try:
            if not self.TOKEN_FILE.exists():
                return None
            
            data = json.loads(self.TOKEN_FILE.read_text())
            saved_at = datetime.fromisoformat(data.get("saved_at", "2000-01-01"))
            
            # Upstox tokens expire at end of day
            if saved_at.date() < date.today():
                logger.info("Saved Upstox token expired (new day)")
                return None
            
            self._access_token = data.get("access_token")
            logger.info(f"✓ Loaded saved Upstox token (mode: {data.get('auth_mode', 'unknown')})")
            return self._access_token
            
        except Exception as e:
            logger.warning(f"Could not load saved token: {e}")
            return None
    
    async def authenticate(self, mode: Optional[UpstoxAuthMode] = None) -> Optional[str]:
        """
        Authenticate with Upstox using specified or configured mode.
        
        Args:
            mode: Override the configured auth mode
            
        Returns:
            Access token or None.
        """
        # Try saved token first (any mode)
        token = self.load_saved_token()
        if token:
            return token
        
        use_mode = mode or self.auth_mode
        
        if use_mode == UpstoxAuthMode.NOTIFICATION:
            # For notification mode, we request and wait for webhook
            result = await self.request_token_notification()
            if result.get("success"):
                logger.info("Token requested. Waiting for approval on your phone...")
                return None  # Token will arrive via webhook
            return None
            
        elif use_mode == UpstoxAuthMode.TOTP:
            return await self.auto_login_totp()
            
        else:  # MANUAL
            logger.info("Manual OAuth required. Call start_auth_flow() to open browser.")
            return None
    
    def set_mode(self, mode: UpstoxAuthMode) -> None:
        """Switch authentication mode."""
        self.auth_mode = mode
        logger.info(f"Upstox auth mode set to: {mode.value}")
    
    @property
    def access_token(self) -> Optional[str]:
        """Get current access token."""
        return self._access_token
    
    @access_token.setter
    def access_token(self, token: str) -> None:
        """Set access token manually."""
        self._access_token = token
    
    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        return self._access_token is not None
    
    @property
    def supports_totp(self) -> bool:
        """Check if TOTP mode is available."""
        return self._totp_available
    
    @property
    def has_pending_request(self) -> bool:
        """Check if there's a pending notification token request."""
        return self._pending_token_request
    
    def get_status(self) -> Dict[str, Any]:
        """Get authentication status summary."""
        return {
            "authenticated": self.is_authenticated,
            "auth_mode": self.auth_mode.value,
            "totp_available": self._totp_available,
            "pending_request": self._pending_token_request,
            "api_configured": bool(self.api_key and self.api_secret),
        }


class UpstoxDataService:
    """
    Upstox data service for batch market data fetching.
    
    Features:
    - Batch quote API (500 symbols per request)
    - Historical data downloads
    - Rate limiting to respect API limits
    - Automatic token refresh
    - Event bus integration
    """
    
    BASE_URL = "https://api.upstox.com/v2"
    BATCH_QUOTE_SIZE = 500  # Max symbols per batch request
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        on_quote: Optional[Callable[[UpstoxQuote], Coroutine[Any, Any, None]]] = None,
        publish_to_event_bus: bool = True,
    ):
        """
        Initialize Upstox data service.
        
        Args:
            access_token: Upstox API access token
            on_quote: Callback for quote data
            publish_to_event_bus: Whether to publish to event bus
        """
        self._access_token = access_token
        self._on_quote = on_quote
        self._publish_to_event_bus = publish_to_event_bus
        
        self._auth_state = UpstoxAuthState.NOT_AUTHENTICATED
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limiter = RateLimiter(
            per_second=settings.upstox.rate_limit_quotes,
            per_minute=settings.upstox.rate_limit_historical * 60,
        )
        
        # Event bus
        self._event_bus: Optional[EventBus] = None
        
        # Stats
        self._request_count = 0
        self._error_count = 0
        self._last_request_time: Optional[datetime] = None
        
        # Symbol mapping cache
        self._symbol_map: Dict[str, str] = {}  # internal -> upstox
        self._reverse_map: Dict[str, str] = {}  # upstox -> internal
    
    async def initialize(self) -> bool:
        """
        Initialize the service.
        
        Returns:
            True if initialization successful.
        """
        try:
            # Create HTTP client
            self._client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
            
            # Set up event bus
            if self._publish_to_event_bus:
                self._event_bus = await get_event_bus()
            
            # Validate token if provided
            if self._access_token:
                is_valid = await self._validate_token()
                self._auth_state = (
                    UpstoxAuthState.AUTHENTICATED if is_valid 
                    else UpstoxAuthState.ERROR
                )
            
            logger.info(f"✓ Upstox data service initialized (auth: {self._auth_state.value})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Upstox service: {e}")
            return False
    
    async def close(self) -> None:
        """Close the service and release resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("Upstox data service closed")
    
    def set_access_token(self, token: str) -> None:
        """Set the access token."""
        self._access_token = token
        self._auth_state = UpstoxAuthState.NOT_AUTHENTICATED
    
    async def _validate_token(self) -> bool:
        """Validate the access token by making a profile request."""
        try:
            response = await self._make_request("GET", "/user/profile")
            return response is not None and response.get("status") == "success"
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return False
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Make an authenticated API request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            json_data: JSON body data
            
        Returns:
            Response data or None on error.
        """
        if not self._client:
            logger.error("HTTP client not initialized")
            return None
        
        if not self._access_token:
            logger.error("Access token not set")
            return None
        
        # Acquire rate limit token
        await self._rate_limiter.acquire()
        
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            self._request_count += 1
            self._last_request_time = datetime.now(timezone.utc)
            
            response = await self._client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
            )
            
            if response.status_code == 401:
                self._auth_state = UpstoxAuthState.TOKEN_EXPIRED
                logger.error("Upstox token expired")
                return None
            
            if response.status_code == 429:
                logger.warning("Upstox rate limit hit, backing off")
                await asyncio.sleep(5)
                return None
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            self._error_count += 1
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            self._error_count += 1
            logger.error(f"Request error: {e}")
            return None
    
    async def get_quotes(
        self,
        instrument_keys: List[str],
    ) -> Dict[str, UpstoxQuote]:
        """
        Get quotes for multiple instruments.
        
        Args:
            instrument_keys: List of Upstox instrument keys
                (e.g., "NSE_EQ|INE002A01018")
            
        Returns:
            Dictionary mapping instrument key to quote data.
        """
        if not instrument_keys:
            return {}
        
        results: Dict[str, UpstoxQuote] = {}
        
        # Split into batches
        for i in range(0, len(instrument_keys), self.BATCH_QUOTE_SIZE):
            batch = instrument_keys[i:i + self.BATCH_QUOTE_SIZE]
            
            # Join instruments for API call
            instruments_param = ",".join(batch)
            
            response = await self._make_request(
                "GET",
                "/market-quote/quotes",
                params={"instrument_key": instruments_param},
            )
            
            if not response or response.get("status") != "success":
                continue
            
            data = response.get("data", {})
            
            for key, quote_data in data.items():
                try:
                    ohlc = quote_data.get("ohlc", {})
                    depth = quote_data.get("depth", {})
                    
                    # Get best bid/ask
                    best_bid = 0.0
                    best_ask = 0.0
                    if depth:
                        buy_depth = depth.get("buy", [])
                        sell_depth = depth.get("sell", [])
                        if buy_depth:
                            best_bid = buy_depth[0].get("price", 0.0)
                        if sell_depth:
                            best_ask = sell_depth[0].get("price", 0.0)
                    
                    quote = UpstoxQuote(
                        symbol=quote_data.get("symbol", ""),
                        instrument_key=key,
                        ltp=quote_data.get("last_price", 0.0),
                        open=ohlc.get("open", 0.0),
                        high=ohlc.get("high", 0.0),
                        low=ohlc.get("low", 0.0),
                        close=ohlc.get("close", 0.0),
                        volume=quote_data.get("volume", 0),
                        oi=quote_data.get("oi", 0),
                        change=quote_data.get("net_change", 0.0),
                        change_percent=quote_data.get("percentage_change", 0.0),
                        bid=best_bid,
                        ask=best_ask,
                        timestamp=datetime.now(timezone.utc),
                    )
                    
                    results[key] = quote
                    
                    # Callback
                    if self._on_quote:
                        await self._on_quote(quote)
                    
                    # Publish to event bus
                    if self._event_bus:
                        event = TickEvent(
                            event_type=EventType.TICK_RECEIVED,
                            instrument_id=key,
                            symbol=quote.symbol,
                            ltp=quote.ltp,
                            bid=quote.bid,
                            ask=quote.ask,
                            volume=quote.volume,
                            oi=quote.oi,
                            source="upstox_batch",
                        )
                        await self._event_bus.publish(event)
                        
                except Exception as e:
                    logger.error(f"Error processing quote for {key}: {e}")
        
        return results
    
    async def get_historical_data(
        self,
        instrument_key: str,
        interval: str,
        from_date: date,
        to_date: date,
    ) -> List[HistoricalCandle]:
        """
        Get historical candle data.
        
        Args:
            instrument_key: Upstox instrument key
            interval: Candle interval (1minute, 5minute, 15minute, 30minute, 
                     60minute, day, week, month)
            from_date: Start date
            to_date: End date
            
        Returns:
            List of historical candles.
        """
        candles: List[HistoricalCandle] = []
        
        # Upstox limits: max 1 year for intraday, unlimited for daily
        is_intraday = interval in ["1minute", "5minute", "15minute", "30minute", "60minute"]
        
        # Chunk the date range for intraday data
        if is_intraday:
            # Max 100 trading days per request for intraday
            chunk_days = 90
        else:
            chunk_days = 365
        
        current_from = from_date
        
        while current_from <= to_date:
            current_to = min(current_from + timedelta(days=chunk_days), to_date)
            
            response = await self._make_request(
                "GET",
                f"/historical-candle/{instrument_key}/{interval}/{current_to.isoformat()}/{current_from.isoformat()}",
            )
            
            if not response or response.get("status") != "success":
                current_from = current_to + timedelta(days=1)
                continue
            
            data = response.get("data", {})
            candle_data = data.get("candles", [])
            
            for candle in candle_data:
                try:
                    # Upstox format: [timestamp, open, high, low, close, volume, oi]
                    candles.append(HistoricalCandle(
                        timestamp=datetime.fromisoformat(candle[0].replace("Z", "+00:00")),
                        open=float(candle[1]),
                        high=float(candle[2]),
                        low=float(candle[3]),
                        close=float(candle[4]),
                        volume=int(candle[5]),
                        oi=int(candle[6]) if len(candle) > 6 else 0,
                    ))
                except Exception as e:
                    logger.error(f"Error parsing candle: {e}")
            
            current_from = current_to + timedelta(days=1)
            
            # Small delay between chunks
            await asyncio.sleep(0.1)
        
        # Sort by timestamp
        candles.sort(key=lambda x: x.timestamp)
        
        return candles
    
    async def get_option_chain(
        self,
        instrument_key: str,
        expiry_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Get option chain for an underlying.
        
        Args:
            instrument_key: Underlying instrument key
            expiry_date: Optional specific expiry date
            
        Returns:
            Option chain data.
        """
        params = {"instrument_key": instrument_key}
        if expiry_date:
            params["expiry_date"] = expiry_date.isoformat()
        
        response = await self._make_request(
            "GET",
            "/option/chain",
            params=params,
        )
        
        if not response or response.get("status") != "success":
            return {}
        
        return response.get("data", {})
    
    async def scan_universe(
        self,
        instrument_keys: List[str],
        interval_seconds: int = 60,
    ) -> None:
        """
        Continuously scan a universe of instruments.
        
        Args:
            instrument_keys: List of instrument keys to scan
            interval_seconds: Interval between scans
        """
        logger.info(f"Starting universe scan: {len(instrument_keys)} instruments, {interval_seconds}s interval")
        
        while True:
            try:
                start_time = time.monotonic()
                
                quotes = await self.get_quotes(instrument_keys)
                
                elapsed = time.monotonic() - start_time
                logger.info(
                    f"Universe scan complete: {len(quotes)} quotes in {elapsed:.2f}s"
                )
                
                # Wait for next interval
                sleep_time = max(0, interval_seconds - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except asyncio.CancelledError:
                logger.info("Universe scan cancelled")
                break
            except Exception as e:
                logger.error(f"Universe scan error: {e}")
                await asyncio.sleep(5)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "auth_state": self._auth_state.value,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "last_request_time": self._last_request_time.isoformat() if self._last_request_time else None,
        }


# =============================================================================
# Factory Function
# =============================================================================

async def create_upstox_service(
    access_token: Optional[str] = None,
    auto_auth: bool = True,
    auth_mode: Optional[UpstoxAuthMode] = None,
) -> UpstoxDataService:
    """
    Factory function to create and initialize Upstox data service.
    
    Args:
        access_token: Optional Upstox access token (skips auth if provided)
        auto_auth: If True, attempt authentication based on configured mode
        auth_mode: Override the configured auth mode
        
    Returns:
        Initialized UpstoxDataService instance.
    """
    token = access_token
    
    if not token and auto_auth:
        auth = UpstoxAuth(auth_mode=auth_mode)
        token = await auth.authenticate()
        
        if not token:
            mode = auth.auth_mode.value
            if mode == "notification":
                logger.info(
                    "📱 Upstox: Token requested via notification.\n"
                    "   Check your phone and approve to receive token."
                )
            elif mode == "totp":
                logger.warning(
                    "Upstox TOTP login failed. Check credentials in .env"
                )
            else:
                logger.warning(
                    "Upstox: Manual OAuth required. Call start_auth_flow()"
                )
    
    service = UpstoxDataService(access_token=token)
    await service.initialize()
    return service


def get_upstox_auth(auth_mode: Optional[UpstoxAuthMode] = None) -> UpstoxAuth:
    """Get Upstox auth handler instance."""
    return UpstoxAuth(auth_mode=auth_mode)


__all__ = [
    "UpstoxAuthMode",
    "UpstoxAuthState",
    "UpstoxAuth",
    "UpstoxQuote",
    "HistoricalCandle",
    "RateLimiter",
    "UpstoxDataService",
    "create_upstox_service",
    "get_upstox_auth",
]
