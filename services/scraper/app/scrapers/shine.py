from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class ShineScraper(BaseScraper):
    platform = "shine"
    start_url = "https://www.shine.com/job-search"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        slug = quote_plus(query).replace("+", "-")
        target_url = f"{self.start_url}/{slug}-jobs"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(5):
            await page.mouse.wheel(0, 1500)
            await self.human_pause(0.5, 1.05)

        cards = []
        for selector in [".jobCard", ".search_listing", "article", "li:has(a[href*='/job-search/'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:120]:
            title = await self.pick_text(card, ["h2", "h3", ".jobCardTitle", "[data-test*='title']"])
            company = await self.pick_text(card, [".jobCard_companyName", ".companyName", ".company"])
            location = await self.pick_text(card, [".jobCard_location", ".job-location", ".location"])
            description = await self.pick_text(card, [".jobCardDesc", "p", ".description"])
            posted_at = await self.pick_text(card, [".jobCard_days", ".posted-date", "time"])
            experience_text = await self.pick_text(card, [".jobCard_jobDetailText", ".experience", "[data-test*='experience']"])

            tag_nodes = await card.query_selector_all(".jobCard_jobDetailText, .tag, .badge")
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
                    location=location or "India/Unknown",
                    url=urljoin("https://www.shine.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    experience_text=experience_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
