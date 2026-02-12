import asyncio
from playwright.async_api import async_playwright

async def main():
    print("Launching browser...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=False)
            print("Browser launched.")
            page = await browser.new_page()
            print("Page created. Navigating to google.com...")
            await page.goto("https://google.com")
            print("Opened Google successfully.")
            await asyncio.sleep(5)
            await browser.close()
            print("Closed browser.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
