from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from .base import BaseScraper
from .stealth import apply_stealth


class FounditScraper(BaseScraper):
    platform = "foundit"
    start_url = "https://www.foundit.in/srp/results"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}?query={quote_plus(query)}&locations=India"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(6):
            await page.mouse.wheel(0, 1650)
            await self.human_pause(0.45, 1.05)

        cards = []
        for selector in [".cardContainer", ".srpResultCard", "article", "li:has(a[href*='/job/'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:120]:
            title = await self.pick_text(card, [".title", "h2", "h3"])
            company = await self.pick_text(card, [".companyName", ".company"])
            location = await self.pick_text(card, [".loc", ".location"])
            description = await self.pick_text(card, [".jobDesc", ".description", "p"])
            posted_at = await self.pick_text(card, [".posted-time", ".time", "time"])
            experience_text = await self.pick_text(card, [".exp", ".experience"])
            salary_text = await self.pick_text(card, [".salary", ".package"])

            tag_nodes = await card.query_selector_all(".skill, .tag, .badge")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("a[href*='/job/'], a[href]")
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
                    url=urljoin("https://www.foundit.in", href),
                    description=description,
                    posted_at=posted_at or None,
                    salary_text=salary_text,
                    experience_text=experience_text,
                    tags=tags,
                    semantic_score=0.0,
                )
            )
        return jobs
