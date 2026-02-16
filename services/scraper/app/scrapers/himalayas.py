from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class HimalayasScraper(BaseScraper):
    platform = "himalayas"
    start_url = "https://himalayas.app/jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}?q={quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause(1.0, 2.5)

        # Wait for JS hydration
        try:
            await page.wait_for_selector(
                "a[href*='/jobs/'], article, .job-card",
                timeout=12000,
            )
        except Exception:
            pass

        for _ in range(7):
            await page.mouse.wheel(0, 1500)
            await self.human_pause(0.5, 1.2)

        # Himalayas uses React with hashed classes; prefer semantic selectors
        cards = []
        for selector in [
            "a[href*='/jobs/']:has(h2)",
            "a[href*='/jobs/']:has(h3)",
            "article",
            ".job-card",
            "li:has(a[href*='/jobs/'])",
        ]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, ["h2", "h3", "[data-testid*='title']"])
            company = await self.pick_text(card, [
                "span", ".company", "[data-testid*='company']",
            ])
            location = await self.pick_text(card, [".location", ".region", "[data-testid*='location']"])
            description = await self.pick_text(card, ["p", ".description"])
            salary_text = await self.pick_text(card, [".salary", "[data-testid*='salary']"])

            tag_nodes = await card.query_selector_all(".tag, .badge, .chip")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            # Card itself may be the anchor link
            href: str | None = None
            if card_href := await card.get_attribute("href"):
                href = card_href
            else:
                anchor = await card.query_selector("a[href*='/jobs/'], a[href]")
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
                    location=location or "Remote/Unknown",
                    url=urljoin("https://himalayas.app", href),
                    description=description,
                    salary_text=salary_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
