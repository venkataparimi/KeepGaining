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
        Login to Fyers using Playwright.
        
        Flow:
        1. Generate Auth URL (using FyersModel or manually constructed)
        2. Navigate to URL
        3. Enter Client ID -> Submit
        4. Enter PIN -> Submit (or Password if different flow)
        5. Enter TOTP -> Submit
        6. Capture Redirect -> Auth Code
        """
        try:
            from app.core.config import settings
            from playwright.async_api import async_playwright
            import urllib.parse
            
            # Use settings if no specific credentials passed
            client_id = credentials.client_id if credentials else settings.FYERS_CLIENT_ID
            # Note: broker_login.py uses generic 'password' field, but Fyers uses PIN. 
            # We map PIN to password in credentials object or use settings directly.
            pin = credentials.password if credentials else settings.FYERS_PIN 
            totp_key = credentials.totp_secret if credentials else settings.FYERS_TOTP_KEY
            user_id = settings.FYERS_USER_ID
            redirect_uri = settings.FYERS_REDIRECT_URI
            
            if not (client_id and pin and totp_key and user_id):
                return LoginResult(success=False, broker=BrokerType.FYERS, error="Missing Fyers credentials in settings")

            # Construct Auth URL (simpler than importing fyersModel just for this string)
            # Or use the one from settings/logic if available. 
            # Standard V3 Auth URL construction:
            state = "mcp_login"
            auth_url = (
                f"https://api-t1.fyers.in/api/v3/generate-authcode?"
                f"client_id={client_id}&redirect_uri={redirect_uri}&"
                f"response_type=code&state={state}"
            )
            
            logger.info(f"BrokerLogin: Starting Fyers login for {user_id}")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--disable-http2"])
                context = await browser.new_context(
                     user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, right Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                await page.goto(auth_url)
                
                # Screen 1: Mobile or Client ID (Login with Client ID)
                # Check if we need to switch to Client ID view
                try:
                    login_client_id_btn = page.locator("text='Login with Client ID'")
                    if await login_client_id_btn.is_visible():
                         await login_client_id_btn.click()
                except:
                    pass
                
                # Enter Client ID
                await page.fill("input[name='fy_client_id'], input[id='fy_client_id']", user_id)
                await page.click("button[id='clientIdSubmit']")
                
                # Screen 2: PIN (Wait for it)
                # Fyers V3 usually asks for PIN next
                try:
                    await page.wait_for_selector("input[type='password']", timeout=10000)
                    await page.fill("input[type='password']", pin)
                    await page.click("button[id='verifyPinSubmit']")
                except Exception as e:
                    # Fallback: maybe it asked for password (rare now)
                    logger.warning(f"BrokerLogin: PIN entry issue: {e}. Checking for error.")
                
                # Screen 3: TOTP
                await page.wait_for_selector("input[id='first'], input[class*='otp']", timeout=10000)
                
                if totp_key and PYOTP_AVAILABLE:
                    totp = pyotp.TOTP(totp_key)
                    otp = totp.now()
                    
                    # Fyers might have 6 inputs or 1
                    inputs = await page.locator("input[type='number']").all()
                    if len(inputs) >= 6:
                         for i, char in enumerate(otp):
                             await inputs[i].fill(char)
                    else:
                         await page.fill("input[id='first']", otp)
                         
                    # Auto-submit or click button
                    try:
                        await page.click("button[id='verifyTotpSubmit']", timeout=2000)
                    except:
                        pass # Might auto submit
                
                # Wait for Redirect
                async with page.expect_navigation(url_predicate=lambda url: "auth_code=" in url.url, timeout=20000):
                     pass
                
                final_url = page.url
                parsed = urllib.parse.urlparse(final_url)
                params = urllib.parse.parse_qs(parsed.query)
                auth_code = params.get("auth_code", [None])[0]
                
                await browser.close()
                
                if not auth_code:
                    return LoginResult(success=False, broker=BrokerType.FYERS, error="Auth code not in redirect URL")
                
                return LoginResult(
                    success=True,
                    broker=BrokerType.FYERS,
                    access_token=auth_code, # Needs exchange
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
        Login to Upstox using the dedicated UpstoxAuthAutomation service.
        """
        try:
            from app.brokers.upstox_auth_automation import UpstoxAuthAutomation
            from app.core.config import settings
            
            # Initialize automation service
            # We use the settings from config by default if credentials not passed
            auth = UpstoxAuthAutomation()
            
            # Determine credentials
            mobile = credentials.client_id if credentials else settings.upstox.mobile
            pin = credentials.password if credentials else settings.upstox.pin
            totp = credentials.totp_secret if credentials else settings.upstox.totp_secret
            
            if not (mobile and pin):
                return LoginResult(
                    success=False, 
                    broker=BrokerType.UPSTOX, 
                    error="Missing Upstox Mobile or PIN in settings"
                )
            
            logger.info(f"BrokerLogin: Starting Upstox login for {mobile}")
            
            # Run authentication
            # Note: UpstoxAuthAutomation manages its own Playwright instance
            token_data = await auth.authenticate(
                mobile_or_email=mobile,
                pin=pin,
                totp_secret=totp,
                headless=True,
                timeout=60
            )
            
            access_token = token_data.get("access_token")
            
            if access_token:
                return LoginResult(
                    success=True,
                    broker=BrokerType.UPSTOX,
                    access_token=access_token,
                    error=None
                )
            else:
                return LoginResult(
                    success=False,
                    broker=BrokerType.UPSTOX,
                    error="Login info returned but no access token found"
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
