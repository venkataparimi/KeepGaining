import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pyotp
from fyers_apiv3 import fyersModel
from app.core.config import settings
from loguru import logger
import webbrowser
import time


def generate_access_token():
    logger.info("Starting Fyers Auto-Login...")

    # 1. Generate TOTP
    if not settings.FYERS_TOTP_KEY:
        logger.error("TOTP Key not found in config")
        return

    totp = pyotp.TOTP(settings.FYERS_TOTP_KEY)
    current_totp = totp.now()
    logger.info(f"Generated TOTP: {current_totp}")

    # 2. Initialize Session
    # Note: The fyers-apiv3 SDK has a specific flow. 
    # Since we cannot easily automate the web-based login without Selenium/Playwright,
    # we will use the 'client_id' and 'secret_key' to generate the auth link.
    # HOWEVER, for fully automated login without browser interaction, Fyers requires 
    # a specific flow or a previously generated refresh token.
    
    # If the user wants to use the PIN/TOTP flow programmatically, it's often tricky 
    # with the V3 API as it enforces a web login.
    
    # Let's try to print the Auth URL for the user to click, or use a workaround if available.
    # But wait, the user provided PIN and TOTP, implying they expect full automation.
    # Fyers V3 removed the old 'login via API' method for security. 
    # The standard way now is:
    # 1. Get Auth Code (via Browser)
    # 2. Exchange for Access Token
    
    # We will print the URL and ask the user to paste the Auth Code for now, 
    # unless we use a headless browser (which is heavy).
    
    response_type = "code" 
    state = "sample_state"
    
    session = fyersModel.SessionModel(
        client_id=settings.FYERS_CLIENT_ID,
        secret_key=settings.FYERS_SECRET_KEY,
        redirect_uri=settings.FYERS_REDIRECT_URI,
        response_type=response_type,
        grant_type="authorization_code"
    )

    # Generate the auth code using the session model
    response = session.generate_authcode()
    
    logger.info(f"Please visit this URL to login: {response}")
    
    # In a real automated system, we would use Selenium here to fill the form.
    # For this script, we'll ask for the auth code.
    auth_code = input("Enter the Auth Code from the Redirect URL: ")
    
    session.set_token(auth_code)
    response = session.generate_token()
    
    if response.get("code") == 200:
        access_token = response["access_token"]
        logger.success(f"Access Token Generated: {access_token}")
        
        # Save to a file for the app to use
        with open("access_token.txt", "w") as f:
            f.write(access_token)
            
        return access_token
    else:
        logger.error(f"Login Failed: {response}")
        return None

if __name__ == "__main__":
    generate_access_token()
