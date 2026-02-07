from __future__ import annotations

from urllib.parse import urljoin
from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class WellfoundScraper(BaseScraper):
    platform = "wellfound"
    start_url = "https://wellfound.com/jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(self.start_url, wait_until="domcontentloaded")
        await self.human_pause()

        search_selectors = [
            "input[placeholder*='Search']",
            "input[type='search']",
            "input",
        ]
        for selector in search_selectors:
            box = await page.query_selector(selector)
            if box:
                await box.click()
                await box.fill(query)
                await box.press("Enter")
                break

        for _ in range(7):
            await page.mouse.wheel(0, 1700)
            await self.human_pause(0.5, 1.25)

        cards = []
        for selector in ["[data-test*='job-listing']", "article", "li:has(a[href*='/jobs/'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:80]:
            title = await self.pick_text(card, ["h2", "h3", "[data-test*='title']"])
            company = await self.pick_text(card, [".company", "[data-test*='company']"])
            location = await self.pick_text(card, [".location", "[data-test*='location']"])
            description = await self.pick_text(card, ["p", ".description", "[data-test*='description']"])

            anchor = await card.query_selector("a[href*='/jobs/'], a[href]")
            href = await anchor.get_attribute("href") if anchor else None
            if not title or not href:
                continue

            score = semantic_match_score(query=query, title=title, description=description)
            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company or "Unknown",
                    location=location or "Remote/Unknown",
                    url=urljoin(self.start_url, href),
                    description=description,
                    semantic_score=score,
                )
            )
        return jobs
