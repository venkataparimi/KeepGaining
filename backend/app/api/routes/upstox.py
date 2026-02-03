"""
Upstox API endpoints
Authentication and data service management

Supports multiple authentication modes:
- NOTIFICATION (default): Semi-automated, approve on phone
- TOTP: Fully automated using third-party library  
- MANUAL: Browser-based OAuth
- AUTOMATED: Playwright browser automation (new!)
"""
from fastapi import APIRouter, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from loguru import logger

from app.brokers.upstox_data import (
    UpstoxAuth,
    UpstoxAuthMode,
    UpstoxDataService,
    create_upstox_service,
    get_upstox_auth,
)
from app.core.config import settings

# Import automation (optional)
try:
    from app.brokers.upstox_auth_automation import UpstoxAuthAutomation, PLAYWRIGHT_AVAILABLE
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


router = APIRouter()

# Global service instance
_upstox_service: Optional[UpstoxDataService] = None
_upstox_auth: Optional[UpstoxAuth] = None
_upstox_auto_auth: Optional["UpstoxAuthAutomation"] = None


def get_auth() -> UpstoxAuth:
    """Get Upstox auth handler."""
    global _upstox_auth
    if _upstox_auth is None:
        _upstox_auth = get_upstox_auth()
    return _upstox_auth


async def get_service() -> UpstoxDataService:
    """Get Upstox data service."""
    global _upstox_service
    if _upstox_service is None:
        _upstox_service = await create_upstox_service()
    return _upstox_service


# =============================================================================
# Response Models
# =============================================================================

class AuthStatusResponse(BaseModel):
    """Authentication status response."""
    authenticated: bool
    auth_mode: str
    api_configured: bool
    totp_available: bool
    pending_request: bool
    message: str
    auth_url: Optional[str] = None


class AuthCallbackResponse(BaseModel):
    """OAuth callback response."""
    success: bool
    message: str


class QuoteResponse(BaseModel):
    """Quote data response."""
    symbol: str
    ltp: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    change_percent: float


class ServiceStatsResponse(BaseModel):
    """Service statistics response."""
    auth_state: str
    request_count: int
    error_count: int
    last_request_time: Optional[str]


# =============================================================================
# Authentication Endpoints
# =============================================================================

@router.get("/auth/status", response_model=AuthStatusResponse)
async def get_auth_status():
    """
    Check Upstox authentication status.
    
    Returns current auth mode, token status, and available options.
    """
    auth = get_auth()
    status = auth.get_status()
    
    if not status["api_configured"]:
        return AuthStatusResponse(
            authenticated=False,
            auth_mode=status["auth_mode"],
            api_configured=False,
            totp_available=False,
            pending_request=False,
            message="Upstox API credentials not configured. Set UPSTOX_CLIENT_ID and UPSTOX_CLIENT_SECRET in .env",
        )
    
    # Try to load saved token
    token = auth.load_saved_token()
    
    if token:
        return AuthStatusResponse(
            authenticated=True,
            auth_mode=status["auth_mode"],
            api_configured=True,
            totp_available=status["totp_available"],
            pending_request=False,
            message="Authenticated with saved token",
        )
    
    # Not authenticated
    mode_instructions = {
        "notification": "Call /auth/request-token to request token (approve on phone)",
        "totp": "Call /auth/totp-login for automatic login" if status["totp_available"] else "TOTP not configured",
        "manual": "Use auth_url to login via browser",
    }
    
    return AuthStatusResponse(
        authenticated=False,
        auth_mode=status["auth_mode"],
        api_configured=True,
        totp_available=status["totp_available"],
        pending_request=status["pending_request"],
        message=mode_instructions.get(status["auth_mode"], "Unknown mode"),
        auth_url=auth.get_authorization_url(),
    )


@router.post("/auth/set-mode")
async def set_auth_mode(mode: str = Query(..., description="Auth mode: notification, totp, or manual")):
    """
    Switch authentication mode.
    
    Modes:
    - notification: Semi-automated (default, official) - approve on phone
    - totp: Fully automated - requires credentials in env
    - manual: Browser-based OAuth
    """
    auth = get_auth()
    
    try:
        new_mode = UpstoxAuthMode(mode.lower())
        auth.set_mode(new_mode)
        return {
            "success": True,
            "mode": new_mode.value,
            "message": f"Auth mode set to {new_mode.value}"
        }
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Use: notification, totp, or manual"
        )


@router.post("/auth/request-token", response_model=AuthCallbackResponse)
async def request_token_notification():
    """
    Request access token via notification mode (default, official method).
    
    This sends a notification to your phone (WhatsApp/Upstox app).
    Tap to approve, and the token will be delivered to your webhook.
    
    No credentials stored in third-party libraries!
    """
    auth = get_auth()
    
    result = await auth.request_token_notification()
    
    if result.get("success"):
        return AuthCallbackResponse(
            success=True,
            message="📱 Token request sent! Check your phone (WhatsApp/Upstox app) and tap to approve."
        )
    else:
        return AuthCallbackResponse(
            success=False,
            message=f"Token request failed: {result.get('error', 'Unknown error')}"
        )


@router.post("/auth/webhook")
async def token_webhook(request: Request):
    """
    Webhook endpoint to receive token from Upstox.
    
    Configure this URL as your notifier_url in Upstox Developer Console.
    Upstox will POST the access token here after you approve the request.
    """
    auth = get_auth()
    
    try:
        payload = await request.json()
        logger.info(f"Received webhook payload: {payload.get('message_type')}")
        
        token = await auth.receive_token_from_webhook(payload)
        
        if token:
            # Reinitialize service with new token
            global _upstox_service
            _upstox_service = None
            
            return {"success": True, "message": "Token received and stored"}
        else:
            return {"success": False, "message": "Invalid webhook payload"}
            
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/auth/totp-login", response_model=AuthCallbackResponse)
async def totp_login():
    """
    Perform automatic TOTP-based login (fallback method).
    
    ⚠️ Uses third-party upstox-totp library.
    Requires: UPSTOX_USERNAME, UPSTOX_PASSWORD, UPSTOX_PIN_CODE, UPSTOX_TOTP_SECRET in .env
    """
    auth = get_auth()
    
    if not auth.supports_totp:
        return AuthCallbackResponse(
            success=False,
            message="TOTP not available. Install upstox-totp and configure credentials in .env"
        )
    
    try:
        token = await auth.auto_login_totp()
        
        if token:
            global _upstox_service
            _upstox_service = None
            
            return AuthCallbackResponse(
                success=True,
                message="✅ TOTP auto-login successful!"
            )
        else:
            return AuthCallbackResponse(
                success=False,
                message="TOTP login failed. Check credentials."
            )
            
    except Exception as e:
        logger.error(f"TOTP login error: {e}")
        return AuthCallbackResponse(
            success=False,
            message=f"TOTP login error: {str(e)}"
        )


@router.get("/auth/login")
async def start_login():
    """
    Start Upstox OAuth login flow (manual method).
    
    Redirects to Upstox login page.
    """
    auth = get_auth()
    
    if not auth.api_key:
        raise HTTPException(
            status_code=400,
            detail="Upstox API key not configured"
        )
    
    auth_url = auth.get_authorization_url()
    return RedirectResponse(url=auth_url)


@router.get("/auth/callback", response_model=AuthCallbackResponse)
async def auth_callback(code: str = Query(..., description="Authorization code from Upstox")):
    """
    OAuth callback endpoint.
    
    Exchanges authorization code for access token.
    """
    auth = get_auth()
    
    try:
        token = await auth.exchange_code_for_token(code)
        
        if token:
            # Reinitialize service with new token
            global _upstox_service
            _upstox_service = None
            
            return AuthCallbackResponse(
                success=True,
                message="Successfully authenticated with Upstox"
            )
        else:
            return AuthCallbackResponse(
                success=False,
                message="Failed to exchange authorization code for token"
            )
            
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        return AuthCallbackResponse(
            success=False,
            message=f"Authentication error: {str(e)}"
        )


@router.post("/auth/set-token")
async def set_access_token(token: str = Query(..., description="Upstox access token")):
    """
    Manually set access token.
    
    Use this if you have a token from another source.
    """
    try:
        global _upstox_service
        
        # Create new service with token
        _upstox_service = UpstoxDataService(access_token=token)
        await _upstox_service.initialize()
        
        # Also save it
        auth = get_auth()
        auth._access_token = token
        auth._save_token({"access_token": token})
        
        return {"success": True, "message": "Access token set successfully"}
        
    except Exception as e:
        logger.error(f"Error setting token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Automated Browser Authentication (Playwright)
# =============================================================================

class AutomatedAuthRequest(BaseModel):
    """Request model for automated authentication."""
    mobile_or_email: str
    pin: str
    totp_secret: Optional[str] = None
    headless: bool = True


class AutomatedAuthResponse(BaseModel):
    """Response model for automated authentication."""
    success: bool
    message: str
    access_token: Optional[str] = None


@router.get("/auth/automated/status")
async def get_automated_auth_status():
    """
    Check if Playwright-based automation is available.
    """
    return {
        "playwright_available": PLAYWRIGHT_AVAILABLE,
        "message": (
            "Playwright automation available. Use POST /auth/automated to login."
            if PLAYWRIGHT_AVAILABLE
            else "Playwright not installed. Run: pip install playwright && playwright install chromium"
        ),
    }


@router.post("/auth/automated", response_model=AutomatedAuthResponse)
async def automated_browser_auth(request: AutomatedAuthRequest, background_tasks: BackgroundTasks):
    """
    Perform fully automated browser-based authentication using Playwright.
    
    This will:
    1. Open a browser (headless by default)
    2. Navigate to Upstox login page
    3. Enter mobile/email and PIN
    4. Handle TOTP if enabled
    5. Capture authorization code
    6. Exchange for access token
    
    Required:
    - mobile_or_email: Your Upstox login (mobile number or email)
    - pin: Your 6-digit PIN
    
    Optional:
    - totp_secret: Your TOTP secret if 2FA is enabled
    - headless: Run browser in headless mode (default: true)
    
    ⚠️ Requires Playwright:
    pip install playwright pyotp
    playwright install chromium
    """
    if not PLAYWRIGHT_AVAILABLE:
        return AutomatedAuthResponse(
            success=False,
            message="Playwright not available. Install with: pip install playwright && playwright install chromium"
        )
    
    try:
        global _upstox_auto_auth, _upstox_service
        
        if _upstox_auto_auth is None:
            _upstox_auto_auth = UpstoxAuthAutomation()
        
        logger.info(f"Starting automated auth for: {request.mobile_or_email[:4]}***")
        
        # Perform authentication
        token_data = await _upstox_auto_auth.authenticate(
            mobile_or_email=request.mobile_or_email,
            pin=request.pin,
            totp_secret=request.totp_secret,
            headless=request.headless,
        )
        
        if token_data and token_data.get("access_token"):
            # Reset service to use new token
            _upstox_service = None
            
            return AutomatedAuthResponse(
                success=True,
                message="✅ Automated authentication successful!",
                access_token=token_data["access_token"][:50] + "...",  # Truncate for safety
            )
        else:
            return AutomatedAuthResponse(
                success=False,
                message="Authentication completed but no token received",
            )
            
    except Exception as e:
        logger.error(f"Automated auth error: {e}")
        return AutomatedAuthResponse(
            success=False,
            message=f"Authentication failed: {str(e)}",
        )


@router.post("/auth/code", response_model=AutomatedAuthResponse)
async def exchange_auth_code(code: str = Query(..., description="Authorization code from Upstox callback URL")):
    """
    Exchange an authorization code for access token.
    
    Use this if you:
    1. Completed login in browser manually
    2. Got redirected to callback URL with ?code=XXX
    3. Copy the code and paste here
    
    This is useful when automated auth fails but you can login manually.
    """
    try:
        global _upstox_auto_auth, _upstox_service
        
        if _upstox_auto_auth is None:
            _upstox_auto_auth = UpstoxAuthAutomation()
        
        token_data = await _upstox_auto_auth.authenticate_with_code(code)
        
        if token_data and token_data.get("access_token"):
            _upstox_service = None
            
            return AutomatedAuthResponse(
                success=True,
                message="✅ Token exchange successful!",
                access_token=token_data["access_token"][:50] + "...",
            )
        else:
            return AutomatedAuthResponse(
                success=False,
                message="Code exchange completed but no token received",
            )
            
    except Exception as e:
        logger.error(f"Code exchange error: {e}")
        return AutomatedAuthResponse(
            success=False,
            message=f"Code exchange failed: {str(e)}",
        )


@router.get("/auth/url")
async def get_auth_url():
    """
    Get the Upstox authorization URL for manual browser login.
    
    Use this to:
    1. Copy the URL
    2. Open in browser
    3. Complete login
    4. Copy the code from callback URL
    5. Use POST /auth/code to exchange for token
    """
    global _upstox_auto_auth
    
    if _upstox_auto_auth is None:
        _upstox_auto_auth = UpstoxAuthAutomation()
    
    return {
        "auth_url": _upstox_auto_auth.get_auth_url(),
        "instructions": [
            "1. Open the auth_url in your browser",
            "2. Complete the Upstox login",
            "3. You'll be redirected to callback URL with ?code=XXX",
            "4. Copy the code value",
            "5. Use POST /api/upstox/auth/code?code=XXX to get token",
        ],
    }


# =============================================================================
# Data Endpoints
# =============================================================================

@router.get("/quotes", response_model=Dict[str, QuoteResponse])
async def get_quotes(
    instruments: str = Query(..., description="Comma-separated instrument keys (e.g., NSE_EQ|INE002A01018)")
):
    """
    Get quotes for multiple instruments.
    
    Max 500 instruments per request.
    """
    service = await get_service()
    
    if not service._access_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    instrument_list = [i.strip() for i in instruments.split(",")]
    
    if len(instrument_list) > 500:
        raise HTTPException(
            status_code=400,
            detail="Maximum 500 instruments per request"
        )
    
    try:
        quotes = await service.get_quotes(instrument_list)
        
        return {
            key: QuoteResponse(
                symbol=q.symbol,
                ltp=q.ltp,
                open=q.open,
                high=q.high,
                low=q.low,
                close=q.close,
                volume=q.volume,
                change_percent=q.change_percent,
            )
            for key, q in quotes.items()
        }
        
    except Exception as e:
        logger.error(f"Error fetching quotes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/historical")
async def get_historical_data(
    instrument_key: str = Query(..., description="Upstox instrument key"),
    interval: str = Query("day", description="Candle interval: 1minute, 5minute, 15minute, 30minute, 60minute, day, week, month"),
    from_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    to_date: str = Query(..., description="End date (YYYY-MM-DD)"),
):
    """
    Get historical candle data.
    """
    from datetime import datetime
    
    service = await get_service()
    
    if not service._access_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )
    
    try:
        candles = await service.get_historical_data(
            instrument_key=instrument_key,
            interval=interval,
            from_date=from_dt,
            to_date=to_dt,
        )
        
        return {
            "instrument_key": instrument_key,
            "interval": interval,
            "from_date": from_date,
            "to_date": to_date,
            "count": len(candles),
            "candles": [
                {
                    "timestamp": c.timestamp.isoformat(),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "oi": c.oi,
                }
                for c in candles
            ]
        }
        
    except Exception as e:
        logger.error(f"Error fetching historical data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/option-chain")
async def get_option_chain(
    instrument_key: str = Query(..., description="Underlying instrument key"),
    expiry_date: Optional[str] = Query(None, description="Expiry date (YYYY-MM-DD)"),
):
    """
    Get option chain for an underlying.
    """
    from datetime import datetime
    
    service = await get_service()
    
    if not service._access_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    expiry = None
    if expiry_date:
        try:
            expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid expiry date format. Use YYYY-MM-DD"
            )
    
    try:
        chain = await service.get_option_chain(
            instrument_key=instrument_key,
            expiry_date=expiry,
        )
        return chain
        
    except Exception as e:
        logger.error(f"Error fetching option chain: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=ServiceStatsResponse)
async def get_service_stats():
    """
    Get Upstox data service statistics.
    """
    service = await get_service()
    stats = service.get_stats()
    
    return ServiceStatsResponse(
        auth_state=stats["auth_state"],
        request_count=stats["request_count"],
        error_count=stats["error_count"],
        last_request_time=stats["last_request_time"],
    )
