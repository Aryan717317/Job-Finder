from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class IndeedScraper(BaseScraper):
    platform = "indeed"
    start_url = "https://in.indeed.com/jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        target_url = f"{self.start_url}?q={quote_plus(query)}&l=India&sort=date&fromage=3"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(6):
            await page.mouse.wheel(0, 1500)
            await self.human_pause(0.45, 1.05)

        cards = []
        for selector in ["[data-testid='jobSeenBeacon']", ".job_seen_beacon", "article", "li:has(a[href*='/viewjob'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, ["h2", "h3", "[data-testid='jobTitle']", "[data-testid*='title']"])
            company = await self.pick_text(card, ["[data-testid='company-name']", ".companyName", "[data-testid*='company']"])
            location = await self.pick_text(card, ["[data-testid='text-location']", ".companyLocation", "[data-testid*='location']"])
            description = await self.pick_text(card, [".job-snippet", "[data-testid='job-snippet']", "p"])
            posted_at = await self.pick_text(card, ["[data-testid='myJobsStateDate']", ".date", "time"])

            tag_nodes = await card.query_selector_all(".attribute_snippet, .benefits, .metadata, .tag")
            tags: list[str] = []
            for node in tag_nodes[:6]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("a[href*='/viewjob'], a[href]")
            href = await anchor.get_attribute("href") if anchor else None
            if not title or not href:
                continue

            employment_type = ""
            for tag in tags:
                lowered = tag.lower()
                if any(token in lowered for token in ("full", "part", "contract", "intern", "temporary")):
                    employment_type = tag
                    break

            score = semantic_match_score(query=query, title=title, description=description)
            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company or "Unknown",
                    location=location or "India/Unknown",
                    url=urljoin("https://in.indeed.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    employment_type=employment_type,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
