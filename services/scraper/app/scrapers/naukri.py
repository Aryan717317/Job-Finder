from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class NaukriScraper(BaseScraper):
    platform = "naukri"
    start_url = "https://www.naukri.com"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}/{quote_plus(query).replace('+', '-')}-jobs"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(6):
            await page.mouse.wheel(0, 1650)
            await self.human_pause(0.5, 1.15)

        cards = []
        for selector in [".srp-jobtuple-wrapper", ".jobTuple"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break
                
        if not cards:
            title = await page.title()
            html_snippet = (await page.content())[:800]
            raise Exception(f"NAUKRI ZERO CARDS. Title: {title} | HTML Snippet: {html_snippet}")

        jobs: list[JobRecord] = []
        for card in cards[:120]:
            title = await self.pick_text(card, [".title", "a.title", "h2", "h3"])
            company = await self.pick_text(card, [".comp-name", ".companyName", ".subTitle"])
            location = await self.pick_text(card, [".locWdth", ".location", ".loc"])
            description = await self.pick_text(card, [".job-desc", ".jobDescription", "p"])
            posted_at = await self.pick_text(card, [".job-post-day", ".posted-date", "time"])
            experience_text = await self.pick_text(card, [".exp-wrap", ".experience", ".exp"])
            salary_text = await self.pick_text(card, [".sal-wrap", ".salary", ".package"])

            tag_nodes = await card.query_selector_all(".tags-gt li, .tag-li, .skills li")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("a.title, a[href*='job-listings'], a[href]")
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
