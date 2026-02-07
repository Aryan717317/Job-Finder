from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class RelocateMeScraper(BaseScraper):
    platform = "relocate_me"
    start_url = "https://relocate.me/search"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}?query={quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(5):
            await page.mouse.wheel(0, 1500)
            await self.human_pause(0.45, 1.0)

        cards = []
        for selector in [".job-card", ".job-item", "article", "li:has(a[href*='/jobs/'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:120]:
            title = await self.pick_text(card, [".job-card__title", ".title", "h2", "h3"])
            company = await self.pick_text(card, [".job-card__company", ".company", ".company-name"])
            location = await self.pick_text(card, [".job-card__location", ".location", ".city"])
            description = await self.pick_text(card, [".job-card__description", ".description", "p"])
            posted_at = await self.pick_text(card, [".job-card__date", ".date", "time"])
            salary_text = await self.pick_text(card, [".salary", ".compensation", ".reward"])
            experience_text = await self.pick_text(card, [".experience", ".seniority"])

            tag_nodes = await card.query_selector_all(".tag, .badge, .chips span")
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
                    location=location or "Relocation/Unknown",
                    url=urljoin("https://relocate.me", href),
                    description=description,
                    posted_at=posted_at or None,
                    employment_type=employment_type,
                    salary_text=salary_text,
                    experience_text=experience_text,
                    tags=tags,
                    semantic_score=semantic_match_score(query=query, title=title, description=description),
                )
            )
        return jobs
