from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class HirectScraper(BaseScraper):
    platform = "hirect"
    start_url = "https://hirect.in"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}/jobs?q={quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(6):
            await page.mouse.wheel(0, 1600)
            await self.human_pause(0.45, 1.05)

        cards = []
        for selector in [".job-card", ".jobItem", "article", "li:has(a[href*='/job/'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:120]:
            title = await self.pick_text(card, [".title", "h2", "h3"])
            company = await self.pick_text(card, [".company", ".company-name"])
            location = await self.pick_text(card, [".location", ".loc"])
            description = await self.pick_text(card, [".description", "p"])
            posted_at = await self.pick_text(card, [".time", ".posted", "time"])
            experience_text = await self.pick_text(card, [".experience", ".exp"])
            salary_text = await self.pick_text(card, [".salary", ".package"])

            tag_nodes = await card.query_selector_all(".tag, .skill, .badge")
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
                    url=urljoin(self.start_url, href),
                    description=description,
                    posted_at=posted_at or None,
                    salary_text=salary_text,
                    experience_text=experience_text,
                    tags=tags,
                    semantic_score=semantic_match_score(query=query, title=title, description=description),
                )
            )
        return jobs
