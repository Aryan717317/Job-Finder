from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class TheMuseScraper(BaseScraper):
    platform = "the_muse"
    start_url = "https://www.themuse.com/search"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}?keyword={quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause(1.0, 2.0)

        # Wait past loading skeletons for real content
        try:
            await page.wait_for_selector(
                "[data-testid='job-card'], .job-card, article",
                timeout=15000,
            )
        except Exception:
            pass

        # Extra scrolls for cursor-based infinite scroll
        for _ in range(10):
            await page.mouse.wheel(0, 1500)
            await self.human_pause(0.5, 1.2)

        cards = []
        for selector in [
            "[data-testid='job-card']",
            ".job-card",
            "article",
            "li:has(a[href*='/jobs/'])",
        ]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, ["h2", "h3", "[data-testid='job-title']", ".job-title"])
            company = await self.pick_text(card, [
                "a[href*='/profiles/']", ".company-name",
                "[data-testid='company-name']", ".company",
            ])
            location = await self.pick_text(card, [
                ".location", "[data-testid='job-location']", ".job-location",
            ])
            description = await self.pick_text(card, ["p", ".description", "[data-testid='description']"])
            posted_at = await self.pick_text(card, ["time", ".date", ".posted"])

            tag_nodes = await card.query_selector_all(".tag, .badge, .chip")
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

            score = semantic_match_score(query=query, title=title, description=description)
            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company or "Unknown",
                    location=location or "Remote/Unknown",
                    url=urljoin("https://www.themuse.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    employment_type=employment_type,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
