from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class JobgetherScraper(BaseScraper):
    platform = "jobgether"
    start_url = "https://jobgether.com/search"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}?q={quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause(1.5, 3.0)

        # Wait for content to load past any anti-bot check
        try:
            await page.wait_for_selector(
                "article, .job-card, a[href*='/offer/'], li:has(a[href])",
                timeout=15000,
            )
        except Exception:
            pass

        for _ in range(7):
            await page.mouse.wheel(0, 1500)
            await self.human_pause(0.5, 1.2)

        cards = []
        for selector in [
            "a[href*='/offer/']",
            "article",
            ".job-card",
            "[data-testid='job-card']",
            "li:has(a[href*='/offer/'])",
        ]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, ["h2", "h3", ".job-title", "[data-testid*='title']"])
            company = await self.pick_text(card, [".company", ".company-name", "[data-testid*='company']"])
            location = await self.pick_text(card, [".location", "[data-testid*='location']"])
            description = await self.pick_text(card, ["p", ".description"])
            posted_at = await self.pick_text(card, ["time", ".date", ".posted"])
            salary_text = await self.pick_text(card, [".salary", "[data-testid*='salary']"])

            tag_nodes = await card.query_selector_all(".tag, .badge, .chip")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            # Card itself may be the anchor
            href: str | None = None
            if card_href := await card.get_attribute("href"):
                href = card_href
            else:
                anchor = await card.query_selector("a[href*='/offer/'], a[href]")
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
                    url=urljoin("https://jobgether.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    employment_type=employment_type,
                    salary_text=salary_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
