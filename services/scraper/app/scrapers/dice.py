from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class DiceScraper(BaseScraper):
    platform = "dice"
    start_url = "https://www.dice.com/jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = (
            f"{self.start_url}?q={quote_plus(query)}"
            "&countryCode=US&radius=30&radiusUnit=mi&page=1&pageSize=20"
            "&postedDate=THREE&sort=date"
        )
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause(1.0, 2.0)

        # Wait for React SPA to render search cards
        try:
            await page.wait_for_selector(
                "[data-cy='search-card'], dhi-search-card, .card-job, article",
                timeout=12000,
            )
        except Exception:
            pass

        for _ in range(6):
            await page.mouse.wheel(0, 1550)
            await self.human_pause(0.5, 1.1)

        cards = []
        for selector in [
            "[data-cy='search-card']",
            "dhi-search-card",
            ".card-job",
            "article",
        ]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, [
                "[data-cy='card-title']", "a[data-cy='card-title-link']",
                "h5", ".card-title-link", "h2", "h3",
            ])
            company = await self.pick_text(card, [
                "[data-cy='search-result-company-name']", ".card-company",
                "a[data-cy='card-company-link']", ".company",
            ])
            location = await self.pick_text(card, [
                "[data-cy='search-result-location']", ".card-location",
                "span[data-cy='location']", ".location",
            ])
            description = await self.pick_text(card, [
                "[data-cy='card-summary']", ".card-description", "p", ".description",
            ])
            posted_at = await self.pick_text(card, [
                "[data-cy='card-posted-date']", ".posted-date", "time", ".date",
            ])
            salary_text = await self.pick_text(card, [
                "[data-cy='compensationText']", ".compensation-text", ".salary",
            ])
            experience_text = await self.pick_text(card, [
                "[data-cy='experience']", ".experience",
            ])

            tag_nodes = await card.query_selector_all(".chip, .badge, .skill-badge, .tag")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector(
                "a[href*='/job-detail/'], a[data-cy='card-title-link'], a[href]"
            )
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
                    url=urljoin("https://www.dice.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    employment_type=employment_type,
                    salary_text=salary_text,
                    experience_text=experience_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
