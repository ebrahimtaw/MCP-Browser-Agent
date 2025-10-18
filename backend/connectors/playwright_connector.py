import asyncio
from playwright.async_api import async_playwright

class PlaywrightConnector:
    def __init__(self, headless: bool = True):
        self.playwright = None
        self.browser = None
        self.page = None
        self.headless = headless  # ✅ store headless mode

    async def start(self):
        """Start Playwright and open a browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.page = await self.browser.new_page()

    async def goto(self, url: str):
        """Navigate to a given URL."""
        if not self.page:
            raise RuntimeError("Playwright browser not started.")
        await self.page.goto(url, wait_until="load")

    async def extract_text(self):
        """Extract visible text from the current page."""
        if not self.page:
            raise RuntimeError("Playwright browser not started.")
        return await self.page.inner_text("body")

    async def close(self):
        """Close the browser and stop Playwright."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()