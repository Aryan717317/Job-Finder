from __future__ import annotations

from playwright.async_api import BrowserContext

from .base import BaseScraper


class StubPlatformScraper(BaseScraper):
    """Non-implemented adapter placeholder for planned platform coverage."""

    def __init__(self, platform: str, start_url: str) -> None:
        self.platform = platform
        self.start_url = start_url

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(self.start_url, wait_until="domcontentloaded")
        await self.human_pause(0.4, 0.9)
        return []


STUB_SCRAPER_CONFIG: dict[str, str] = {
}
