import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
import time

# Add backend directory to sys.path to resolve imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.brokers.upstox_data import create_upstox_service, UpstoxAuthMode, UpstoxAuth
from loguru import logger

TOKEN_FILE = Path("data/upstox_token.json")

def check_token_updated(since_time: datetime) -> bool:
    if not TOKEN_FILE.exists():
        return False
    
    # Check modification time
    mtime = datetime.fromtimestamp(TOKEN_FILE.stat().st_mtime)
    if mtime > since_time:
        return True
        
    return False

async def main():
    logger.info("Triggering Upstox Authentication...")
    
    start_time = datetime.now()
    
    # Initialize auth handler
    auth = UpstoxAuth()
    
    # Attempt 1: Notification Mode (if configured)
    if auth.auth_mode == UpstoxAuthMode.NOTIFICATION:
        logger.info("Attempting Notification Auth...")
        result = await auth.request_token_notification()
        
        if result.get("success"):
            logger.info("📱 Notification sent! Please check your phone and approve.")
            logger.info("Waiting for token update (30 seconds)...")
            
            # Poll for token update
            poll_start = datetime.now()
            while (datetime.now() - poll_start).seconds < 30:
                if check_token_updated(start_time):
                    logger.success("✅ Upstox Authenticated Successfully via Notification!")
                    return
                await asyncio.sleep(1)
            
            logger.warning("❌ Notification auth timed out or not received.")
        else:
            logger.warning(f"Notification request failed: {result.get('error')}")

    # Attempt 2: Manual Mode (Fallback)
    logger.info("Falling back to Manual Browser Auth...")
    auth.set_mode(UpstoxAuthMode.MANUAL)
    
    auth_url = auth.get_authorization_url()
    logger.info(f"Opening browser for login: {auth_url}")
    
    import webbrowser
    webbrowser.open(auth_url)
    
    logger.info("Waiting for callback and token update (60 seconds)...")
    logger.info("Ensure the backend API is running to handle the callback!")
    
    poll_start = datetime.now()
    while (datetime.now() - poll_start).seconds < 60:
        if check_token_updated(start_time):
            logger.success("✅ Upstox Authenticated Successfully via Manual OAuth!")
            return
        await asyncio.sleep(1)
        
    logger.error("❌ Authentication timed out. Check if backend is running and REDIRECT_URI is correct.")

if __name__ == "__main__":
    current_dir = os.getcwd()
    # Ensure we are running from backend dir or adjust path
    if not os.path.exists("data"):
         # Try to find data dir
         if os.path.exists("backend/data"):
             os.chdir("backend")
    
    asyncio.run(main())
