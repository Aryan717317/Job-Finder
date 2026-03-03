from __future__ import annotations

import logging
from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth

logger = logging.getLogger("cycle_runner")


class LinkedInScraper(BaseScraper):
    """LinkedIn public jobs scraper.

    Performs TWO searches:
    1. India-based jobs (original behavior)
    2. Remote/WFH jobs globally using f_WT=2 (remote filter)
    """

    platform = "linkedin"
    start_url = "https://www.linkedin.com/jobs/search"

    async def _scrape_url(self, page, target_url: str, query: str, run_id: str, default_location: str) -> list[JobRecord]:
        """Scrape a single LinkedIn search URL."""
        logger.info("[linkedin] Scraping: %s", target_url)
        try:
            await page.goto(target_url, wait_until="domcontentloaded")
        except Exception as exc:
            logger.warning("[linkedin] Failed to load %s: %s", target_url, exc)
            return []
        await self.human_pause(1.5, 2.5)

        for _ in range(8):
            await page.mouse.wheel(0, 1700)
            await self.human_pause(0.45, 1.1)

        # Try to click "Show more" button if present
        for _ in range(3):
            try:
                show_more = await page.query_selector("button.infinite-scroller__show-more-button, button[aria-label*='more jobs']")
                if show_more:
                    await show_more.click()
                    await self.human_pause(1.0, 2.0)
                    for _ in range(3):
                        await page.mouse.wheel(0, 1500)
                        await self.human_pause(0.3, 0.7)
            except Exception:
                break

        cards = []
        for selector in [".base-card", ".job-search-card", "li:has(a[href*='/jobs/view/'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        logger.info("[linkedin] Found %d job cards on %s", len(cards), target_url[:80])

        jobs: list[JobRecord] = []
        for card in cards[:120]:
            title = await self.pick_text(card, [".base-search-card__title", ".job-search-card__title", "h3"])
            company = await self.pick_text(card, [".base-search-card__subtitle", ".job-search-card__subtitle", "h4"])
            location = await self.pick_text(card, [".job-search-card__location", ".base-search-card__metadata"])
            posted_at = await self.pick_text(card, ["time", ".job-search-card__listdate"])

            tag_nodes = await card.query_selector_all(".job-search-card__benefits li, .base-search-card__metadata span")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("a.base-card__full-link, a[href*='/jobs/view/'], a[href]")
            href = await anchor.get_attribute("href") if anchor else None
            if not title or not href:
                continue

            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company or "Unknown",
                    location=location or default_location,
                    url=urljoin("https://www.linkedin.com", href),
                    description="",
                    posted_at=posted_at or None,
                    tags=tags,
                    semantic_score=semantic_match_score(query=query, title=title, description=""),
                )
            )
        return jobs

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        all_jobs: list[JobRecord] = []

        # 1. Search India-based jobs
        india_url = f"{self.start_url}/?keywords={quote_plus(query)}&location=India"
        india_jobs = await self._scrape_url(page, india_url, query, run_id, "India/Unknown")
        all_jobs.extend(india_jobs)

        await self.human_pause(2.0, 3.5)

        # 2. Search remote/WFH jobs globally (f_WT=2 = Remote filter)
        remote_url = f"{self.start_url}/?keywords={quote_plus(query)}&f_WT=2"
        remote_jobs = await self._scrape_url(page, remote_url, query, run_id, "Remote/Worldwide")
        all_jobs.extend(remote_jobs)

        # 3. Also try India + Remote specifically
        await self.human_pause(2.0, 3.5)
        india_remote_url = f"{self.start_url}/?keywords={quote_plus(query)}&location=India&f_WT=2"
        india_remote_jobs = await self._scrape_url(page, india_remote_url, query, run_id, "Remote/India")
        all_jobs.extend(india_remote_jobs)

        # Deduplicate by normalized title+company (LinkedIn assigns different IDs to same postings)
        seen_keys: set[str] = set()
        deduped: list[JobRecord] = []
        for job in all_jobs:
            title_norm = " ".join((job.title or "").strip().lower().split())
            company_norm = " ".join((job.company or "").strip().lower().split())
            key = f"{title_norm}|{company_norm}"
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(job)

        logger.info("[linkedin] Total: %d India + %d global remote + %d India remote = %d unique",
                     len(india_jobs), len(remote_jobs), len(india_remote_jobs), len(deduped))
        return deduped
