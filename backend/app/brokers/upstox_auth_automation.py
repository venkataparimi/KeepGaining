"""
Upstox Automated Authentication Service
KeepGaining Trading Platform

Automated OAuth flow for Upstox using Playwright browser automation.
Features:
- Fully automated login with mobile/email + PIN
- TOTP support for 2FA
- Automatic code capture and token exchange
- Token persistence and refresh
- FastAPI endpoint for triggering auth

Usage:
    # Option 1: CLI
    python -m app.brokers.upstox_auth_automation

    # Option 2: API endpoint
    POST /api/upstox/auth/automated
    {
        "mobile_or_email": "your_mobile_or_email",
        "pin": "your_pin",
        "totp_secret": "your_totp_secret"  # Optional
    }
"""

import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlencode, urlparse, parse_qs

import httpx
from loguru import logger

# Playwright is optional - check availability
try:
    from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not available. Install with: pip install playwright && playwright install chromium")

# Optional: TOTP for 2FA
try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False


class UpstoxAuthAutomation:
    """
    Automated Upstox OAuth authentication using Playwright.
    
    This class handles the complete OAuth flow:
    1. Navigate to Upstox login page
    2. Enter mobile/email and PIN
    3. Handle TOTP if enabled
    4. Capture authorization code
    5. Exchange code for access token
    6. Save token to file
    
    Usage:
        auth = UpstoxAuthAutomation(
            client_id="YOUR_API_KEY",
            client_secret="YOUR_API_SECRET",
            redirect_uri="YOUR_REDIRECT_URI"
        )
        
        token = await auth.authenticate(
            mobile_or_email="9876543210",
            pin="123456",
            totp_secret="YOUR_TOTP_SECRET"  # Optional
        )
    """
    
    # Upstox URLs
    AUTH_BASE_URL = "https://api.upstox.com/v2/login/authorization/dialog"
    TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
    
    # Default token file path
    DEFAULT_TOKEN_PATH = Path("data/upstox_token.json")
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        token_path: Optional[Path] = None,
    ):
        """
        Initialize Upstox auth automation.
        
        Args:
            client_id: Upstox API key (or from env UPSTOX_API_KEY)
            client_secret: Upstox API secret (or from env UPSTOX_API_SECRET)
            redirect_uri: OAuth redirect URI (or from env UPSTOX_REDIRECT_URI)
            token_path: Path to save token file
        """
        from app.core.config import settings
        self.client_id = client_id or os.getenv("UPSTOX_API_KEY") or settings.UPSTOX_API_KEY
        self.client_secret = client_secret or os.getenv("UPSTOX_API_SECRET") or settings.UPSTOX_API_SECRET
        self.redirect_uri = redirect_uri or os.getenv("UPSTOX_REDIRECT_URI") or settings.UPSTOX_REDIRECT_URI or "http://127.0.0.1:8080/callback"
        self.token_path = token_path or self.DEFAULT_TOKEN_PATH
        
        # Browser instance
        self._browser: Optional[Browser] = None
        self._playwright = None
        
        # State
        self._current_token: Optional[Dict[str, Any]] = None
        self._load_saved_token()
    
    def _load_saved_token(self) -> None:
        """Load saved token from file if exists."""
        if self.token_path.exists():
            try:
                with open(self.token_path, "r") as f:
                    self._current_token = json.load(f)
                logger.info(f"Loaded saved token from {self.token_path}")
            except Exception as e:
                logger.warning(f"Failed to load saved token: {e}")
    
    def _save_token(self, token_data: Dict[str, Any]) -> None:
        """Save token to file."""
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Add metadata
        token_data["saved_at"] = datetime.now(timezone.utc).isoformat()
        
        with open(self.token_path, "w") as f:
            json.dump(token_data, f, indent=2)
        
        self._current_token = token_data
        logger.info(f"Token saved to {self.token_path}")
    
    def get_auth_url(self) -> str:
        """Get the OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
        }
        return f"{self.AUTH_BASE_URL}?{urlencode(params)}"
    
    async def authenticate(
        self,
        mobile_or_email: str,
        pin: str,
        totp_secret: Optional[str] = None,
        headless: bool = True,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """
        Perform automated authentication.
        
        Args:
            mobile_or_email: Upstox login (mobile number or email)
            pin: 6-digit PIN
            totp_secret: TOTP secret for 2FA (if enabled)
            headless: Run browser in headless mode
            timeout: Total timeout in seconds
            
        Returns:
            Token data dictionary with access_token, refresh_token, etc.
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright not available. Install with:\n"
                "pip install playwright\n"
                "playwright install chromium"
            )
        
        logger.info("Starting automated Upstox authentication...")
        
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            
            page = await context.new_page()
            
            try:
                # Navigate to auth URL
                auth_url = self.get_auth_url()
                logger.info(f"Navigating to: {auth_url}")
                await page.goto(auth_url, wait_until="networkidle", timeout=30000)
                
                # Wait for login form
                await asyncio.sleep(2)
                
                # Step 1: Enter mobile/email
                logger.info("Entering mobile/email...")
                mobile_input = await page.wait_for_selector(
                    'input[type="text"], input[id*="mobile"], input[id*="email"], input[name*="mobile"]',
                    timeout=10000
                )
                await mobile_input.fill(mobile_or_email)
                
                # Click continue/next button
                continue_btn = await page.wait_for_selector(
                    'button[type="submit"], button:has-text("Continue"), button:has-text("Get OTP"), button:has-text("Next")',
                    timeout=5000
                )
                await continue_btn.click()
                await asyncio.sleep(2)
                
                # Step 2: Enter PIN
                logger.info("Entering PIN...")
                
                # Wait for PIN input (may be multiple inputs or single)
                try:
                    # Try single PIN input first
                    pin_input = await page.wait_for_selector(
                        'input[type="password"], input[id*="pin"], input[name*="pin"]',
                        timeout=5000
                    )
                    await pin_input.fill(pin)
                except PlaywrightTimeout:
                    # Try multiple PIN digit inputs
                    pin_inputs = await page.query_selector_all('input[type="tel"], input[maxlength="1"]')
                    if pin_inputs and len(pin_inputs) >= 6:
                        for i, digit in enumerate(pin[:6]):
                            await pin_inputs[i].fill(digit)
                    else:
                        raise RuntimeError("Could not find PIN input fields")
                
                # Click submit/continue
                submit_btn = await page.wait_for_selector(
                    'button[type="submit"], button:has-text("Continue"), button:has-text("Submit"), button:has-text("Login")',
                    timeout=5000
                )
                await submit_btn.click()
                await asyncio.sleep(2)
                
                # Step 3: Handle TOTP if required
                try:
                    totp_input = await page.wait_for_selector(
                        'input[id*="totp"], input[id*="otp"], input[name*="totp"], input[placeholder*="TOTP"]',
                        timeout=5000
                    )
                    
                    if totp_secret:
                        if not PYOTP_AVAILABLE:
                            raise RuntimeError("pyotp not available. Install with: pip install pyotp")
                        
                        totp = pyotp.TOTP(totp_secret)
                        totp_code = totp.now()
                        logger.info(f"Entering TOTP: {totp_code}")
                        await totp_input.fill(totp_code)
                        
                        # Submit TOTP
                        totp_submit = await page.wait_for_selector(
                            'button[type="submit"], button:has-text("Continue"), button:has-text("Verify")',
                            timeout=5000
                        )
                        await totp_submit.click()
                        await asyncio.sleep(2)
                    else:
                        raise RuntimeError("TOTP required but no secret provided")
                        
                except PlaywrightTimeout:
                    logger.info("No TOTP required, continuing...")
                
                # Step 4: Wait for redirect with authorization code
                logger.info("Waiting for authorization code...")
                
                # Wait for redirect to callback URL
                start_time = asyncio.get_event_loop().time()
                auth_code = None
                
                while asyncio.get_event_loop().time() - start_time < timeout:
                    current_url = page.url
                    
                    if self.redirect_uri.split("://")[1].split("/")[0] in current_url:
                        # Parse authorization code from URL
                        parsed = urlparse(current_url)
                        params = parse_qs(parsed.query)
                        
                        if "code" in params:
                            auth_code = params["code"][0]
                            logger.info(f"Got authorization code: {auth_code[:20]}...")
                            break
                    
                    # Check for errors
                    if "error" in current_url:
                        parsed = urlparse(current_url)
                        params = parse_qs(parsed.query)
                        error = params.get("error", ["Unknown"])[0]
                        error_desc = params.get("error_description", [""])[0]
                        raise RuntimeError(f"OAuth error: {error} - {error_desc}")
                    
                    await asyncio.sleep(0.5)
                
                if not auth_code:
                    # Take screenshot for debugging
                    await page.screenshot(path="auth_debug.png")
                    raise RuntimeError(
                        f"Timeout waiting for authorization code. "
                        f"Current URL: {page.url}"
                    )
                
                # Step 5: Exchange code for token
                logger.info("Exchanging code for token...")
                token_data = await self._exchange_code_for_token(auth_code)
                
                # Save token
                self._save_token(token_data)
                
                logger.info("Authentication successful!")
                return token_data
                
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                # Take screenshot for debugging
                try:
                    await page.screenshot(path="auth_error.png")
                    logger.info("Debug screenshot saved to auth_error.png")
                except Exception:
                    pass
                raise
            finally:
                await browser.close()
    
    async def _exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
            )
            
            if response.status_code != 200:
                raise RuntimeError(
                    f"Token exchange failed: {response.status_code} - {response.text}"
                )
            
            return response.json()
    
    async def authenticate_with_code(self, code: str) -> Dict[str, Any]:
        """
        Authenticate using a manually obtained authorization code.
        
        Use this if you already have the code from browser.
        
        Args:
            code: Authorization code from OAuth redirect
            
        Returns:
            Token data dictionary
        """
        logger.info("Exchanging authorization code for token...")
        token_data = await self._exchange_code_for_token(code)
        self._save_token(token_data)
        logger.info("Authentication successful!")
        return token_data
    
    def get_access_token(self) -> Optional[str]:
        """Get current access token if available."""
        if self._current_token:
            return self._current_token.get("access_token")
        return None
    
    def is_token_valid(self) -> bool:
        """Check if current token is still valid."""
        if not self._current_token:
            return False
        
        # Check if we have saved_at timestamp
        saved_at_str = self._current_token.get("saved_at")
        if not saved_at_str:
            return False
        
        try:
            saved_at = datetime.fromisoformat(saved_at_str.replace("Z", "+00:00"))
            # Upstox tokens typically valid for 1 day
            expires_at = saved_at + timedelta(hours=23)
            return datetime.now(timezone.utc) < expires_at
        except Exception:
            return False

    async def validate_token(self) -> bool:
        """
        Check if current token is actually valid by making a lightweight API call.
        """
        token = self.get_access_token()
        if not token:
            return False
            
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://api.upstox.com/v2/user/profile",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
                )
                return response.status_code == 200
            except Exception:
                return False

    async def get_fresh_token(self, force: bool = False) -> str:
        """
        Get a valid access token, automatically refreshing if needed.
        
        Args:
            force: If True, bypass time check and perform fresh login
            
        Returns:
            Valid access token string
        """
        if not force and self.is_token_valid():
            return self.get_access_token()
            
        logger.info(f"Upstox token {'force-refresh requested' if force else 'expired or missing'}. Attempting auto-login...")
        
        from app.core.config import settings
        if not settings.upstox.is_auth_configured:
            raise RuntimeError(
                "Cannot auto-refresh token: UPSTOX_MOBILE and UPSTOX_PIN not set in environment/config. "
                "Please add them to .env file."
            )
            
        try:
            token_data = await self.authenticate(
                mobile_or_email=settings.upstox.mobile,
                pin=settings.upstox.pin,
                totp_secret=settings.upstox.totp_secret,
                headless=True
            )
            return token_data.get("access_token")
        except Exception as e:
            logger.error(f"Auto-login failed: {e}")
            raise RuntimeError(f"Failed to refresh Upstox token: {e}")


class UpstoxCodeServer:
    """
    Simple HTTP server to capture OAuth callback.
    
    Runs a temporary server on localhost to capture the authorization code.
    """
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.code: Optional[str] = None
        self._server = None
    
    async def start_and_wait_for_code(self, timeout: int = 120) -> str:
        """
        Start server and wait for authorization code.
        
        Args:
            timeout: Maximum seconds to wait
            
        Returns:
            Authorization code
        """
        from aiohttp import web
        
        async def handle_callback(request):
            code = request.query.get("code")
            error = request.query.get("error")
            
            if error:
                self.code = None
                return web.Response(
                    text=f"<h1>Authentication Failed</h1><p>Error: {error}</p>",
                    content_type="text/html"
                )
            
            if code:
                self.code = code
                return web.Response(
                    text="<h1>Authentication Successful!</h1><p>You can close this window.</p>",
                    content_type="text/html"
                )
            
            return web.Response(text="Invalid callback", status=400)
        
        app = web.Application()
        app.router.add_get("/callback", handle_callback)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, "localhost", self.port)
        await site.start()
        
        logger.info(f"Callback server listening on http://localhost:{self.port}/callback")
        
        try:
            start = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start < timeout:
                if self.code is not None:
                    return self.code
                await asyncio.sleep(0.5)
            
            raise TimeoutError("Timeout waiting for authorization code")
        finally:
            await runner.cleanup()


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """CLI for Upstox authentication."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Upstox Authentication Automation")
    parser.add_argument("--mobile", help="Mobile number or email")
    parser.add_argument("--pin", help="6-digit PIN")
    parser.add_argument("--totp-secret", help="TOTP secret for 2FA")
    parser.add_argument("--code", help="Use existing authorization code")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Show browser")
    
    args = parser.parse_args()
    
    auth = UpstoxAuthAutomation()
    
    if args.code:
        # Use provided code
        token = await auth.authenticate_with_code(args.code)
    elif args.mobile and args.pin:
        # Automated auth
        token = await auth.authenticate(
            mobile_or_email=args.mobile,
            pin=args.pin,
            totp_secret=args.totp_secret,
            headless=args.headless,
        )
    else:
        # Interactive mode
        print("\n=== Upstox Authentication ===\n")
        print("Options:")
        print("1. Automated login (requires mobile/PIN)")
        print("2. Manual browser login (get code from callback)")
        print("3. Use existing authorization code")
        
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == "1":
            mobile = input("Mobile/Email: ").strip()
            pin = input("PIN: ").strip()
            totp = input("TOTP Secret (press Enter to skip): ").strip() or None
            
            token = await auth.authenticate(
                mobile_or_email=mobile,
                pin=pin,
                totp_secret=totp,
                headless=False,  # Show browser for interactive
            )
        elif choice == "2":
            # Open browser and start callback server
            auth_url = auth.get_auth_url()
            print(f"\nOpening browser to: {auth_url}")
            print("Please complete login in browser...")
            
            import webbrowser
            webbrowser.open(auth_url)
            
            # Wait for code input
            code = input("\nPaste the authorization code from the callback URL: ").strip()
            token = await auth.authenticate_with_code(code)
        elif choice == "3":
            code = input("Authorization code: ").strip()
            token = await auth.authenticate_with_code(code)
        else:
            print("Invalid option")
            return
    
    print(f"\n✅ Authentication successful!")
    print(f"Access Token: {token.get('access_token', '')[:50]}...")
    print(f"Token saved to: {auth.token_path}")


if __name__ == "__main__":
    asyncio.run(main())
