from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class SimplyHiredScraper(BaseScraper):
    platform = "simplyhired"
    start_url = "https://www.simplyhired.com/search"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        target_url = f"{self.start_url}?q={quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(5):
            await page.mouse.wheel(0, 1400)
            await self.human_pause(0.45, 1.0)

        cards = []
        for selector in ["[data-testid='searchSerpJob']", ".SerpJob-jobCard", "article", "li:has(a[href])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, ["h2", "h3", "[data-testid*='title']", ".jobposting-title"])
            company = await self.pick_text(card, [".jobposting-company", "[data-testid*='company']", ".company"])
            location = await self.pick_text(card, [".jobposting-location", "[data-testid*='location']", ".location"])
            description = await self.pick_text(card, [".jobposting-snippet", "p", ".description"])
            posted_at = await self.pick_text(card, ["time", ".jobposting-age", ".date"])
            experience_text = await self.pick_text(card, [".experience", ".jobposting-metadata", "[data-testid*='experience']"])

            tag_nodes = await card.query_selector_all(".tag, .badge, .jobposting-metadata span")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

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
                    url=urljoin("https://www.simplyhired.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    experience_text=experience_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
