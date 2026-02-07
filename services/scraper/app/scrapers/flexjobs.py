from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from .base import BaseScraper
from .stealth import apply_stealth


class FlexJobsScraper(BaseScraper):
    platform = "flexjobs"
    start_url = "https://www.flexjobs.com/search"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}?search={quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(5):
            await page.mouse.wheel(0, 1550)
            await self.human_pause(0.45, 1.0)

        cards = []
        for selector in [".job", ".job-result", "article", "li:has(a[href*='/jobs/'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:120]:
            title = await self.pick_text(card, [".job-title", ".title", "h2", "h3"])
            company = await self.pick_text(card, [".company", ".company-name"])
            location = await self.pick_text(card, [".location", ".job-location"])
            description = await self.pick_text(card, [".description", ".summary", "p"])
            posted_at = await self.pick_text(card, [".posted", ".date", "time"])
            salary_text = await self.pick_text(card, [".salary", ".compensation"])

            tag_nodes = await card.query_selector_all(".tag, .badge, .job-tag")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("a[href*='/jobs/'], a[href]")
            href = await anchor.get_attribute("href") if anchor else None
            if not title or not href:
                continue

            employment_type = ""
            for tag in tags:
                lowered = tag.lower()
                if any(token in lowered for token in ("full", "part", "contract", "freelance", "intern")):
                    employment_type = tag
                    break

            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company or "Unknown",
                    location=location or "Remote/Unknown",
                    url=urljoin("https://www.flexjobs.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    employment_type=employment_type,
                    salary_text=salary_text,
                    tags=tags,
                    semantic_score=0.0,
                )
            )
        return jobs
