from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class BuiltInScraper(BaseScraper):
    platform = "builtin"
    start_url = "https://builtin.com/jobs/remote"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        target_url = f"{self.start_url}?search={quote_plus(query)}&datePosted=3"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(6):
            await page.mouse.wheel(0, 1550)
            await self.human_pause(0.45, 1.05)

        cards = []
        for selector in [".job-card", "[data-id='job-card']", "article", ".views-row", "li:has(a[href*='/job/'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, ["h2 a", ".job-title", "h2", "h3"])
            company = await self.pick_text(card, [".company-title", ".company-name", "[data-testid='company']"])
            location = await self.pick_text(card, [".job-location", ".location", "[data-testid='location']"])
            description = await self.pick_text(card, [".description", "p", "[data-testid='description']"])
            posted_at = await self.pick_text(card, ["time", ".date", ".posted"])
            salary_text = await self.pick_text(card, [".salary-range", ".salary", ".compensation"])
            experience_text = await self.pick_text(card, [".experience", ".seniority", "[data-testid='experience']"])

            tag_nodes = await card.query_selector_all(".skill-tag, .tag, .badge")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("a[href*='/job/'], a[href]")
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
                    salary_text=salary_text,
                    experience_text=experience_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
