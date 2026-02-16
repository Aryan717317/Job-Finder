from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class JustRemoteScraper(BaseScraper):
    platform = "just_remote"
    start_url = "https://justremote.co/remote-jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        target_url = f"{self.start_url}?search={quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(7):
            await page.mouse.wheel(0, 1550)
            await self.human_pause(0.5, 1.1)

        cards = []
        for selector in [
            "a[href*='/remote-jobs/']",
            "article",
            ".job-card",
            "li:has(a[href*='/remote-jobs/'])",
        ]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, ["h2", "h3", "[data-testid*='title']"])
            company = await self.pick_text(card, [".company", "span", "[data-testid*='company']"])
            location = await self.pick_text(card, [".location", ".region", "[data-testid*='location']"])
            description = await self.pick_text(card, ["p", ".description"])
            posted_at = await self.pick_text(card, ["time", ".date"])

            tag_nodes = await card.query_selector_all(".tag, .chip, .badge")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            # For link-based cards the card itself may be the anchor
            href: str | None = None
            if card_href := await card.get_attribute("href"):
                href = card_href
            else:
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
                    url=urljoin("https://justremote.co", href),
                    description=description,
                    posted_at=posted_at or None,
                    employment_type=employment_type,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
