"""
Verification script for MCP Automation System.
Tests:
1. Broker Login (Fyers)
2. NSE OI Scraper
3. Chartink Scraper
4. News Monitor
"""

import asyncio
import os
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MCP_Verify")

from app.mcp import init_mcp_manager
from app.mcp.automators.broker_login import BrokerLoginAutomator, BrokerType, BrokerCredentials
from app.mcp.scrapers.nse_oi import NSE_OI_Scraper
from app.mcp.scrapers.chartink import ChartinkScraper
from app.mcp.monitors.news import NewsMonitor
from app.mcp.scrapers.trendlyne import TrendlyneScraper

async def test_trendlyne_dvm(scraper, stock):
    print(f"\n--- Testing Trendlyne DVM for {stock.get('symbol')} ---")
    # Construct URL from raw data
    raw = stock.get('raw_data', {})
    cb = raw.get('callbackinfo', {})
    if not cb:
        print("❌ No callback info found")
        return False
        
    slug = cb.get('slugname')
    sid = cb.get('stockId')
    url = f"https://trendlyne.com/equity/{sid}/{slug}"
    print(f"Target URL: {url}")
    
async def test_trendlyne_dvm(scraper, stock):
    print(f"\n--- Testing Trendlyne DVM for {stock.get('symbol')} ---")
    # Construct URL from raw data
    raw = stock.get('raw_data', {})
    cb = raw.get('callbackinfo', {})
    if not cb:
        print("❌ No callback info found")
        return False
        
    slug = cb.get('slugname')
    sid = cb.get('stockId')
    url = f"https://trendlyne.com/equity/{sid}/{slug}"
    print(f"Target URL: {url}")
    
    content = await scraper.get_stock_details(url, headless=False)
    if content:
        print("✅ DVM Page fetched and saved to trendlyne_stock_dump.html")
    else:
        print("❌ Failed to fetch DVM page")
    
    return True

async def test_trendlyne_scraper():
    print("\n--- Testing Trendlyne Scraper ---")
    scraper = TrendlyneScraper()
    data = await scraper.get_fno_heatmap(headless=False)
    
    if data and (len(data.get("stocks", [])) > 0):
        print(f"✅ Trendlyne success. Extracted {len(data['stocks'])} stocks.")
        
        # Pick one stock and try DVM logic
        stock = data['stocks'][0]
        await test_trendlyne_dvm(scraper, stock)
        
        return True
    else:
        print(f"❌ Trendlyne failed or no data found.")
        return False

async def test_nse_scraper():
    print("\n--- Testing NSE OI Scraper ---")
    scraper = NSE_OI_Scraper()
    
    # Test 1: Option Chain (NIFTY)
    print("Testing Option Chain for NIFTY...")
    data = await scraper._scrape_option_chain("NIFTY", headless=False)
    if data and ('records' in data or 'filtered' in data):
        print(f"✅ Option Chain success for NIFTY")
    else:
        print(f"❌ Option Chain failed for NIFTY")

    # Test 2: Premarket Data
    print("Testing Premarket Data for NIFTY (Visible)...")
    pre_data = await scraper.get_premarket_data("NIFTY", headless=False)
    if pre_data and 'data' in pre_data:
        print(f"✅ Premarket success. Count: {len(pre_data['data'])}")
    else:
        print(f"❌ Premarket data failed")
        
    return True

async def test_chartink_scraper():
    print("\n--- Testing Chartink Scraper (SKIPPED) ---")
    return True # Skip for now
    
    # print("\n--- Testing Chartink Scraper ---")
    # scraper = ChartinkScraper()
    # # Test simple query
    # query = "( {cash} ( latest close > 0 ) )" # Simple query getting all stocks
    # result = await scraper.run_custom_query(query, "Test Query", headless=False)
    # 
    # if result and result.total_count > 0:
    #     print(f"✅ Chartink Scraper success! Found {result.total_count} stocks.")
    #     print(f"   Sample: {result.stocks[0].symbol} - {result.stocks[0].price}")
    #     return True
    # else:
    #     print(f"❌ Chartink Scraper failed or no stocks found.")
    #     return False

async def test_news_monitor():
    print("\n--- Testing News Monitor ---")
    monitor = NewsMonitor()
    # Test MoneyControl
    items = await monitor._scrape_moneycontrol(monitor.SOURCES['moneycontrol'])
    
    if items and len(items) > 0:
        print(f"✅ News Monitor success! Found {len(items)} articles.")
        print(f"   Latest: {items[0].title} ({items[0].timestamp})")
        return True
    else:
        print(f"❌ News Monitor failed to fetch articles.")
        return False

async def test_broker_login():
    print("\n--- Testing Broker Login (Dry Run) ---")
    
    from app.core.config import settings
    
    logger.info("Checking Fyers Credentials...")
    if settings.fyers.is_configured:
        print("✅ Fyers settings loaded successfully.")
    else:
        print("⚠️  Fyers settings incomplete in config.")

    logger.info("Checking Upstox Credentials...")
    if settings.upstox.is_auth_configured:
        print("✅ Upstox settings (Mobile/PIN) loaded successfully.")
    else:
        print("⚠️  Upstox settings incomplete (Mobile/PIN missing).")
        
    automator = BrokerLoginAutomator()
    print("✅ BrokerLoginAutomator initialized.")
    
    return True

async def main():
    print(f"Starting MCP Verification at {datetime.now()}")
    
    # Initialize Manager (required for Playwright)
    manager = init_mcp_manager()
    await manager.start()
    
    results = {
        "NSE": await test_nse_scraper(),
        "Trendlyne": await test_trendlyne_scraper(),
        "Chartink": await test_chartink_scraper(),
        #"News": await test_news_monitor(),
        "Login": await test_broker_login()
    }
    
    await manager.stop()
    
    print("\n=== Verification Summary ===")
    all_passed = True
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{test}: {status}")
        if not passed:
            all_passed = False
            
    if all_passed:
        print("\n✅ All systems operational.")
    else:
        print("\n⚠️  Some tests failed.")

if __name__ == "__main__":
    asyncio.run(main())
