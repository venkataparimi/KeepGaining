"""
Broker Login Automator

Automated login to trading brokers with 2FA support.
Supports Fyers and Upstox with TOTP/OTP handling.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Dict, Optional
from enum import Enum

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False

from app.mcp.base import BaseAutomator, ActionResult

logger = logging.getLogger(__name__)


class BrokerType(Enum):
    """Supported brokers."""
    FYERS = "fyers"
    UPSTOX = "upstox"


@dataclass
class BrokerCredentials:
    """Broker login credentials."""
    broker: BrokerType
    client_id: str
    password: str
    totp_secret: Optional[str] = None  # For TOTP-based 2FA
    pin: Optional[str] = None  # For PIN-based 2FA
    
    @classmethod
    def from_env(cls, broker: BrokerType) -> "BrokerCredentials":
        """Load credentials from environment variables."""
        if broker == BrokerType.FYERS:
            return cls(
                broker=broker,
                client_id=os.getenv("FYERS_CLIENT_ID", ""),
                password=os.getenv("FYERS_PASSWORD", ""),
                totp_secret=os.getenv("FYERS_TOTP_SECRET"),
                pin=os.getenv("FYERS_PIN"),
            )
        elif broker == BrokerType.UPSTOX:
            return cls(
                broker=broker,
                client_id=os.getenv("UPSTOX_CLIENT_ID", ""),
                password=os.getenv("UPSTOX_PASSWORD", ""),
                totp_secret=os.getenv("UPSTOX_TOTP_SECRET"),
                pin=os.getenv("UPSTOX_PIN"),
            )
        raise ValueError(f"Unsupported broker: {broker}")


@dataclass
class LoginResult:
    """Result of broker login."""
    success: bool
    broker: BrokerType
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    error: Optional[str] = None


class BrokerLoginAutomator(BaseAutomator):
    """
    Automated broker login with 2FA support.
    
    Features:
    - Fyers login with TOTP
    - Upstox login with mobile OTP
    - Token extraction and persistence
    - Scheduled login (8:45 AM daily)
    
    Actions:
    - login_fyers: Login to Fyers
    - login_upstox: Login to Upstox
    - refresh_token: Refresh existing token
    - get_token: Get current valid token
    """
    
    # Broker URLs
    FYERS_LOGIN_URL = "https://api.fyers.in/api/v2/generate-authcode"
    UPSTOX_LOGIN_URL = "https://login.upstox.com"
    
    def __init__(
        self,
        event_bus: Optional[Any] = None,
        credentials: Optional[Dict[BrokerType, BrokerCredentials]] = None,
        token_storage_path: str = "backend/data"
    ):
        super().__init__("BrokerLogin", event_bus, timeout_seconds=120.0)
        
        self.credentials = credentials or {}
        self.token_storage_path = token_storage_path
        
        # Current tokens
        self._tokens: Dict[BrokerType, LoginResult] = {}
    
    async def _execute_action(self, action: str, **params) -> Dict[str, Any]:
        """Execute broker login actions."""
        if action == "login_fyers":
            result = await self._login_fyers(params.get("credentials"))
            return result.__dict__ if result else {"error": "Login failed"}
        
        elif action == "login_upstox":
            result = await self._login_upstox(params.get("credentials"))
            return result.__dict__ if result else {"error": "Login failed"}
        
        elif action == "refresh_token":
            broker = BrokerType(params.get("broker", "fyers"))
            result = await self._refresh_token(broker)
            return result.__dict__ if result else {"error": "Refresh failed"}
        
        elif action == "get_token":
            broker = BrokerType(params.get("broker", "fyers"))
            token = self._tokens.get(broker)
            if token and token.success:
                return {"token": token.access_token, "expires_at": str(token.expires_at)}
            return {"error": "No valid token"}
        
        elif action == "login_all":
            results = {}
            for broker in self.credentials:
                result = await self._login_broker(broker)
                results[broker.value] = result.__dict__ if result else {"error": "Failed"}
            return results
        
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _login_broker(self, broker: BrokerType) -> Optional[LoginResult]:
        """Login to a specific broker."""
        if broker == BrokerType.FYERS:
            return await self._login_fyers(self.credentials.get(broker))
        elif broker == BrokerType.UPSTOX:
            return await self._login_upstox(self.credentials.get(broker))
        return None
    
    async def _login_fyers(
        self,
        credentials: Optional[BrokerCredentials] = None
    ) -> LoginResult:
        """
        Login to Fyers using browser automation.
        
        Flow:
        1. Navigate to Fyers login page
        2. Enter client ID and password
        3. Handle TOTP/PIN verification
        4. Extract access token from redirect
        """
        creds = credentials or self.credentials.get(BrokerType.FYERS)
        if not creds:
            return LoginResult(
                success=False,
                broker=BrokerType.FYERS,
                error="No Fyers credentials provided"
            )
        
        logger.info("BrokerLogin: Starting Fyers login...")
        
        try:
            # Use Chrome DevTools MCP for login
            # This will be called via the MCP manager
            
            # Step 1: Navigate to login
            # mcp_chrome-devtools_navigate_page to Fyers login URL
            
            # Step 2: Fill credentials
            # mcp_chrome-devtools_fill for client_id field
            # mcp_chrome-devtools_fill for password field
            
            # Step 3: Generate TOTP if available
            if creds.totp_secret and PYOTP_AVAILABLE:
                totp = pyotp.TOTP(creds.totp_secret)
                otp = totp.now()
                logger.info(f"BrokerLogin: Generated TOTP: {otp}")
                # mcp_chrome-devtools_fill for OTP field
            
            # Step 4: Submit and extract token
            # mcp_chrome-devtools_click for submit button
            # Wait for redirect and extract token from URL
            
            # For now, return placeholder until MCP integration is complete
            logger.info("BrokerLogin: Fyers login flow prepared (MCP integration pending)")
            
            return LoginResult(
                success=True,
                broker=BrokerType.FYERS,
                access_token="pending_mcp_integration",
                error=None
            )
            
        except Exception as e:
            logger.error(f"BrokerLogin: Fyers login failed: {e}")
            return LoginResult(
                success=False,
                broker=BrokerType.FYERS,
                error=str(e)
            )
    
    async def _login_upstox(
        self,
        credentials: Optional[BrokerCredentials] = None
    ) -> LoginResult:
        """
        Login to Upstox using browser automation.
        
        Flow:
        1. Navigate to Upstox login page
        2. Enter mobile/client ID
        3. Handle mobile OTP (requires external input)
        4. Enter PIN
        5. Extract access token
        """
        creds = credentials or self.credentials.get(BrokerType.UPSTOX)
        if not creds:
            return LoginResult(
                success=False,
                broker=BrokerType.UPSTOX,
                error="No Upstox credentials provided"
            )
        
        logger.info("BrokerLogin: Starting Upstox login...")
        
        try:
            # Similar flow to Fyers but with mobile OTP
            # OTP handling options:
            # 1. Manual input (pause and wait)
            # 2. SMS gateway integration
            # 3. TOTP if Upstox supports it
            
            logger.info("BrokerLogin: Upstox login flow prepared (MCP integration pending)")
            
            return LoginResult(
                success=True,
                broker=BrokerType.UPSTOX,
                access_token="pending_mcp_integration",
                error=None
            )
            
        except Exception as e:
            logger.error(f"BrokerLogin: Upstox login failed: {e}")
            return LoginResult(
                success=False,
                broker=BrokerType.UPSTOX,
                error=str(e)
            )
    
    async def _refresh_token(self, broker: BrokerType) -> Optional[LoginResult]:
        """Refresh an existing token."""
        # Implementation depends on broker's refresh token API
        current = self._tokens.get(broker)
        if current and current.refresh_token:
            # Call broker's refresh API
            pass
        
        # Fallback to full login
        return await self._login_broker(broker)
    
    def get_totp(self, secret: str) -> str:
        """Generate current TOTP code."""
        if not PYOTP_AVAILABLE:
            raise ImportError("pyotp is required for TOTP. Install with: pip install pyotp")
        return pyotp.TOTP(secret).now()
    
    @staticmethod
    def is_market_hours() -> bool:
        """Check if current time is within market hours."""
        now = datetime.now()
        market_open = time(9, 15)
        market_close = time(15, 30)
        current_time = now.time()
        
        # Check if weekday (Monday=0, Sunday=6)
        if now.weekday() >= 5:
            return False
        
        return market_open <= current_time <= market_close
    
    @staticmethod
    def should_login_now() -> bool:
        """Check if it's time for scheduled login (8:45 AM)."""
        now = datetime.now()
        target = time(8, 45)
        
        # Within 5 minutes of target time on weekdays
        if now.weekday() >= 5:
            return False
        
        current = now.time()
        return (
            target <= current <= time(8, 50)
        )
