from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class WeWorkRemotelyScraper(BaseScraper):
    platform = "we_work_remotely"
    start_url = "https://weworkremotely.com/remote-jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        target_url = f"{self.start_url}/search?term={quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(5):
            await page.mouse.wheel(0, 1500)
            await self.human_pause(0.45, 1.0)

        cards = []
        for selector in ["li:has(a[href*='/remote-jobs/'])", ".jobs li", "article"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, [".title", "h2", "h3", "[data-testid*='title']"])
            company = await self.pick_text(card, [".company", ".company-name", "[data-testid*='company']"])
            location = await self.pick_text(card, [".region", ".location", "[data-testid*='location']"])
            description = await self.pick_text(card, [".description", "p"])
            posted_at = await self.pick_text(card, [".date", "time"])

            tag_nodes = await card.query_selector_all(".tag, .badge, .new-listing__category")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("a[href*='/remote-jobs/'], a[href]")
            href = await anchor.get_attribute("href") if anchor else None
            if not title or not href:
                continue

            employment_type = ""
            for tag in tags:
                lowered = tag.lower()
                if any(token in lowered for token in ("full", "part", "contract", "freelance", "intern")):
                    employment_type = tag
                    break

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
                    posted_at=posted_at or None,
                    employment_type=employment_type,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
