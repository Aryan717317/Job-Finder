from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class InternshalaScraper(BaseScraper):
    platform = "internshala"
    start_url = "https://internshala.com/jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        target_url = f"{self.start_url}/keywords-{quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(5):
            await page.mouse.wheel(0, 1550)
            await self.human_pause(0.45, 1.05)

        cards = []
        for selector in [".individual_internship", ".internship_meta", "article", "div:has(a[href*='/job/detail/'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, ["h3", "h2", ".job-internship-name", "[data-testid*='title']"])
            company = await self.pick_text(card, [".company-name", ".company", "[data-testid*='company']"])
            location = await self.pick_text(card, [".locations", ".location_link", "[data-testid*='location']"])
            description = await self.pick_text(card, ["p", ".description", ".other_detail_item", "[data-testid*='description']"])
            posted_at = await self.pick_text(card, [".status-success", ".posted-date", ".detail-row-1 .item_body", "time"])
            experience_text = await self.pick_text(card, [".item_body", ".experience", "[data-testid*='experience']"])
            salary_text = await self.pick_text(card, [".stipend", ".salary", "[data-testid*='salary']"])

            anchor = await card.query_selector("a[href*='/job/detail/'], a[href]")
            href = await anchor.get_attribute("href") if anchor else None
            if not title or not href:
                continue

            tag_nodes = await card.query_selector_all(".label_container span, .tags span, .individual_skill")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            score = semantic_match_score(query=query, title=title, description=description)
            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company or "Unknown",
                    location=location or "India/Unknown",
                    url=urljoin("https://internshala.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    employment_type="Internship",
                    salary_text=salary_text,
                    experience_text=experience_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
