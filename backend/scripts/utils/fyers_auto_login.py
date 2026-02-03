import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import pyotp
from fyers_apiv3 import fyersModel
from app.core.config import settings
from loguru import logger
from playwright.async_api import async_playwright
import urllib.parse


async def automate_login():
    logger.info("Starting Fyers Fully Automated Login...")

    if not settings.FYERS_TOTP_KEY or not settings.FYERS_PIN or not settings.FYERS_USER_ID:
        logger.error("Missing User ID, PIN, or TOTP Key in config.")
        return

    # 1. Generate Auth URL
    session = fyersModel.SessionModel(
        client_id=settings.FYERS_CLIENT_ID,
        secret_key=settings.FYERS_SECRET_KEY,
        redirect_uri=settings.FYERS_REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code"
    )
    auth_url = session.generate_authcode()
    logger.info(f"Auth URL Generated. Launching Browser...")

    # 2. Launch Browser & Perform Login
    async with async_playwright() as p:
        # Launch headless browser
        browser = await p.chromium.launch(headless=True) 
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Go to Auth URL
            await page.goto(auth_url)
            
            # Wait for Login Page
            logger.info("Waiting for Login Page...")
            # Fyers Login Flow: 
            # 1. Mobile Number / Client ID Input
            # Selectors might need adjustment if Fyers changes UI
            await page.wait_for_selector("input[id='mobile-code']", timeout=10000) # Usually the ID input
            # Sometimes it asks for mobile, sometimes Client ID. 
            # Let's assume Client ID flow or click "Login with Client ID" if needed.
            
            # NOTE: Fyers often defaults to Mobile Number. We might need to click "Login with Client ID"
            # Let's try to fill the input. If it expects mobile, this might fail if we pass ID.
            # But usually the input accepts both or there is a toggle.
            
            # Actually, looking at recent Fyers Web, there is often a "Login with Client ID" link.
            # Let's check for that link.
            login_with_client_id = page.get_by_text("Login with Client ID")
            if await login_with_client_id.is_visible():
                await login_with_client_id.click()
            
            # Fill Client ID
            await page.fill("input[id='fy_client_id']", settings.FYERS_USER_ID)
            await page.click("button[id='clientIdSubmit']")
            
            # Fill PIN (OTP field usually appears after ID)
            # Wait for PIN input. It might be a different screen.
            # Fyers V3 flow: ID -> OTP/PIN -> TOTP
            # Actually, Fyers often asks for Mobile OTP first if not using Client ID.
            # With Client ID, it usually asks for Password/PIN.
            
            # Let's wait for the next input.
            # Note: Selectors are tricky without seeing the page. 
            # We will try generic selectors or wait for text.
            
            # Assuming standard flow: ID -> PIN -> TOTP
            logger.info("Entering PIN...")
            # Wait for PIN input (often type='password' or id='verify-pin-page')
            await page.wait_for_selector("input[type='password']", timeout=10000)
            await page.fill("input[type='password']", settings.FYERS_PIN)
            await page.click("button[id='verifyPinSubmit']")
            
            # Fill TOTP
            logger.info("Entering TOTP...")
            await page.wait_for_selector("input[id='first']", timeout=10000) # 6-digit inputs usually
            
            # Generate TOTP
            totp = pyotp.TOTP(settings.FYERS_TOTP_KEY)
            current_totp = totp.now()
            
            # Fyers often has 6 separate inputs for TOTP or one.
            # If it's 6 inputs, we need to fill them one by one.
            # If it's one, just fill.
            # Let's try filling the container or finding the inputs.
            
            # Strategy: Type the TOTP keystrokes.
            for digit in current_totp:
                await page.keyboard.type(digit)
                await asyncio.sleep(0.1)
            
            # Click Submit if needed (often auto-submits)
            # await page.click("button[id='verifyTotpSubmit']") 
            
            # Wait for Redirect
            logger.info("Waiting for Redirect...")
            # We wait for the page URL to start with our redirect URI
            async with page.expect_navigation(url=lambda u: u.startswith(settings.FYERS_REDIRECT_URI), timeout=15000):
                pass
                
            # Extract Code
            final_url = page.url
            logger.info(f"Redirected to: {final_url}")
            
            parsed = urllib.parse.urlparse(final_url)
            params = urllib.parse.parse_qs(parsed.query)
            
            if 'auth_code' in params:
                auth_code = params['auth_code'][0]
                logger.success(f"Auth Code Extracted: {auth_code}")
                
                # Generate Token
                session.set_token(auth_code)
                response = session.generate_token()
                
                if response.get("code") == 200:
                    access_token = response["access_token"]
                    logger.success(f"Access Token Generated: {access_token}")
                    with open("access_token.txt", "w") as f:
                        f.write(access_token)
                else:
                    logger.error(f"Token Generation Failed: {response}")
            else:
                logger.error("Auth Code not found in URL parameters.")

        except Exception as e:
            logger.error(f"Automation Failed: {e}")
            # Take screenshot for debugging
            await page.screenshot(path="login_error.png")
            logger.info("Screenshot saved to login_error.png")

        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(automate_login())
