from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TrendlyneScraper:
    """
    Scraper for Trendlyne F&O data.
    """
    
    BASE_URL = "https://smartoptions.trendlyne.com/heatmap/all/price/latest/?defaultStockgroup=others%2Ffno-stocks%2F"

    async def get_fno_heatmap(self, headless: bool = True) -> Optional[Dict[str, Any]]:
        """
        Fetch the F&O Heatmap data.
        """
        data = {"timestamp": datetime.now().isoformat(), "stocks": []}
        
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )
                page = await context.new_page()
                
                logger.info(f"Trendlyne: Navigating to {self.BASE_URL}")
                await page.goto(self.BASE_URL, timeout=60000)
                
                # Wait for hydration/API calls
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except:
                    logger.warning("Trendlyne: Network idle timeout, proceeding...")

                # Heatmap usually renders as boxes or a table. 
                # Strategy: Extract text content for now as a robust first pass, 
                # or snapshot the HTML to debug structure if needed.
                # For a "Heatmap", usually there are elements with class wrapping 'ticker' or 'percent'.
                
                # Let's try to capture the main container. 
                # Based on URL 'heatmap', we look for a container.
                
                # Debug: Take screenshot to confirm load
                # await page.screenshot(path="trendlyne_debug.png")
                
                # Simplest robust extraction: Get all text looks like "SYMBOL %Change"
                # But to be useful, we want structured data.
                # Let's assume there's a specific API call we can intercept, similar to NSE.
                # We'll attach a listener.
                
                api_data = []
                
                async def handle_response(response):
                    if "api" in response.url and "heatmap" in response.url and response.status == 200:
                        try:
                            json_data = await response.json()
                            logger.info(f"Trendlyne: Captured potential API data from {response.url}")
                            # Dump to file for inspection
                            import json
                            with open("trendlyne_api_dump.json", "w") as f:
                                json.dump(json_data, f, indent=2)
                            api_data.append(json_data)
                        except: pass

                page.on("response", handle_response)
                
                # Reload to trigger requests
                if not api_data:
                    logger.info("Trendlyne: Reloading to capture API data...")
                    await page.reload()
                
                # Reload to force API call if not initially captured, or wait if it's polling
                if not api_data:
                    logger.info("Trendlyne: Waiting for API data...")
                    # Wait up to 10s for data
                    for _ in range(10):
                        if api_data: break
                        await page.wait_for_timeout(1000)

                # Parse captured data
                for json_data in api_data:
                    if not isinstance(json_data, dict) or 'body' not in json_data:
                        continue
                        
                    body = json_data['body']
                    if not isinstance(body, dict):
                        continue
                        
                    # primary data source seems to be body['all']['series']
                    sources = []
                    if 'all' in body and isinstance(body['all'], dict):
                        sources.append(body['all'].get('series', []))
                    
                    # Check other keys just in case
                    for k in ['long', 'short', 'shortcovering', 'longunwinding']:
                        if k in body and isinstance(body[k], list):
                            sources.append(body[k])
                            
                    for source_list in sources:
                        if not isinstance(source_list, list): continue
                        
                        for item in source_list:
                            if isinstance(item, dict):
                                std_item = {
                                    "symbol": item.get('code'),
                                    "name": item.get('name'),
                                    "price": item.get('current_price'),
                                    "price_change": item.get('current_change'),
                                    "oi_change": item.get('oi_change'),
                                    "analysis_status": item.get('builtup_str'),
                                    "sector": item.get('sector'),
                                    "raw_data": item
                                }
                                data['stocks'].append(std_item)

                await browser.close()
                
                # Deduplicate by symbol
                unique_stocks = {}
                for s in data['stocks']:
                    if s.get('symbol'):
                        unique_stocks[s['symbol']] = s
                
                if unique_stocks:
                    data['stocks'] = list(unique_stocks.values())
                
                logger.info(f"Trendlyne: Extracted {len(data['stocks'])} unique stocks")
                
        except Exception as e:
            logger.error(f"Trendlyne: Scrape failed: {e}")
            return None
            
        return data

    async def get_stock_details(self, stock_url: str, headless: bool = True) -> Optional[str]:
        """
        Fetch stock details page content for DVM analysis.
        """
        html_content = ""
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                logger.info(f"Trendlyne: Navigating to {stock_url}")
                await page.goto(stock_url, timeout=60000)
                await page.wait_for_load_state("domcontentloaded")
                
                # Wait for DVM widget (heuristic)
                try:
                    await page.wait_for_selector(".dvm-score", timeout=5000)
                except: pass
                
                # Dump HTML
                html_content = await page.content()
                with open("trendlyne_stock_dump.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                await browser.close()
        except Exception as e:
            logger.error(f"Trendlyne: Stock detail fetch failed: {e}")
            return None
        return html_content
