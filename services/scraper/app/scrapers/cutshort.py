from __future__ import annotations

from urllib.parse import urljoin
from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class CutshortScraper(BaseScraper):
    platform = "cutshort"
    start_url = "https://cutshort.io/jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(self.start_url, wait_until="domcontentloaded")
        await self.human_pause()

        search_selectors = [
            "input[placeholder*='Search']",
            "input[type='search']",
            "input",
        ]
        search_applied = False
        for selector in search_selectors:
            boxes = await page.query_selector_all(selector)
            for box in boxes[:5]:
                try:
                    if not await box.is_visible():
                        continue
                    await box.fill("")
                    await box.fill(query)
                    await box.press("Enter")
                    search_applied = True
                    break
                except Exception:
                    continue
            if search_applied:
                break

        for _ in range(6):
            await page.mouse.wheel(0, 1600)
            await self.human_pause(0.5, 1.2)

        cards = []
        for selector in [".job-card", "article", "[data-testid*='job']"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:60]:
            title = await self.pick_text(card, ["h2", "h3", "[data-testid*='title']"])
            company = await self.pick_text(card, [".company", "[data-testid*='company']"])
            location = await self.pick_text(card, [".location", "[data-testid*='location']"])
            description = await self.pick_text(card, ["p", ".description", "[data-testid*='description']"])

            anchor = await card.query_selector("a[href]")
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
                    location=location or "Unknown",
                    url=urljoin(self.start_url, href),
                    description=description,
                    semantic_score=score,
                )
            )
        return jobs
