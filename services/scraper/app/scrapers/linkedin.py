from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from .base import BaseScraper
from .stealth import apply_stealth


class LinkedInScraper(BaseScraper):
    platform = "linkedin"
    start_url = "https://www.linkedin.com/jobs/search"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}/?keywords={quote_plus(query)}&location=India"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(7):
            await page.mouse.wheel(0, 1700)
            await self.human_pause(0.45, 1.1)

        cards = []
        for selector in [".base-card", ".job-search-card", "li:has(a[href*='/jobs/view/'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:120]:
            title = await self.pick_text(card, [".base-search-card__title", ".job-search-card__title", "h3"])
            company = await self.pick_text(card, [".base-search-card__subtitle", ".job-search-card__subtitle", "h4"])
            location = await self.pick_text(card, [".job-search-card__location", ".base-search-card__metadata"])
            posted_at = await self.pick_text(card, ["time", ".job-search-card__listdate"])

            tag_nodes = await card.query_selector_all(".job-search-card__benefits li, .base-search-card__metadata span")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("a.base-card__full-link, a[href*='/jobs/view/'], a[href]")
            href = await anchor.get_attribute("href") if anchor else None
            if not title or not href:
                continue

            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company or "Unknown",
                    location=location or "India/Unknown",
                    url=urljoin("https://www.linkedin.com", href),
                    description="",
                    posted_at=posted_at or None,
                    tags=tags,
                    semantic_score=0.0,
                )
            )
        return jobs
