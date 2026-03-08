from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class TimesJobsScraper(BaseScraper):
    platform = "timesjobs"
    start_url = "https://www.timesjobs.com/candidate/job-search.html"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        target_url = (
            f"{self.start_url}?from=submit&searchType=personalizedSearch&txtKeywords={quote_plus(query)}"
            "&cType=1&sort=D"
        )
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(5):
            await page.mouse.wheel(0, 1450)
            await self.human_pause(0.45, 1.0)

        cards = []
        for selector in [".new-joblist", ".job-bx", "li.clearfix.job-bx", "article"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:120]:
            title = await self.pick_text(card, ["h2 a", "h3 a", ".heading-trun a", "[data-testid*='title']"])
            company = await self.pick_text(card, [".joblist-comp-name", ".company-name", ".company"])
            location = await self.pick_text(card, [".loc", ".job-location", ".location"])
            description = await self.pick_text(card, [".job-description", ".job-desc", "p"])
            posted_at = await self.pick_text(card, [".sim-posted", ".posted-date", "time"])
            experience_text = await self.pick_text(card, [".expwdth", ".exp", ".experience"])
            salary_text = await self.pick_text(card, [".sal-wrap", ".salary", ".salary-text"])

            tag_nodes = await card.query_selector_all(".key-skill span, .srp-skills span, .tag, .badge")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("h2 a[href], h3 a[href], a[href]")
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
                    url=urljoin(self.start_url, href),
                    description=description,
                    posted_at=posted_at or None,
                    salary_text=salary_text,
                    experience_text=experience_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
