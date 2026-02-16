from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class JoobleScraper(BaseScraper):
    platform = "jooble"
    start_url = "https://jooble.org"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}/SearchResult?ukw={quote_plus(query)}"
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            return []
        await self.human_pause(1.5, 3.0)

        # Wait for vacancy cards to render
        try:
            await page.wait_for_selector(
                "[data-test-name='vacancy-card'], .vacancy_wrapper, article, div[data-id]",
                timeout=12000,
            )
        except Exception:
            pass

        for _ in range(6):
            await page.mouse.wheel(0, 1500)
            await self.human_pause(1.0, 2.0)

        cards = []
        for selector in [
            "[data-test-name='vacancy-card']",
            ".vacancy_wrapper",
            "article",
            "div[data-id]",
        ]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, [
                "[data-test-name='vacancy-title']", "h2 a",
                ".vacancy__header a", "h2", "h3",
            ])
            company = await self.pick_text(card, [
                "[data-test-name='vacancy-company']", ".vacancy__company",
                ".company-name", ".company",
            ])
            location = await self.pick_text(card, [
                "[data-test-name='vacancy-location']", ".vacancy__location", ".location",
            ])
            description = await self.pick_text(card, [
                "[data-test-name='vacancy-description']", ".vacancy__body",
                "p", ".description",
            ])
            posted_at = await self.pick_text(card, [
                "[data-test-name='vacancy-date']", "time", ".date",
            ])
            salary_text = await self.pick_text(card, [
                "[data-test-name='vacancy-salary']", ".vacancy__salary", ".salary",
            ])

            tag_nodes = await card.query_selector_all(".tag, .badge, .vacancy__tag")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector(
                "a[href*='/desc/'], a[data-test-name='vacancy-title'], a[href]"
            )
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
                    url=urljoin(self.start_url, href),
                    description=description,
                    posted_at=posted_at or None,
                    salary_text=salary_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
