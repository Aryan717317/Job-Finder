from __future__ import annotations

import json
import logging
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper

logger = logging.getLogger("cycle_runner")


class WorkingNomadsScraper(BaseScraper):
    """WorkingNomads scraper using their public JSON API.

    API: https://www.workingnomads.com/api/exposed_jobs/
    Returns all jobs as a JSON array. We filter client-side by query.
    Category-based site, does not support keyword URL search.
    """

    platform = "working_nomads"
    start_url = "https://www.workingnomads.com/api/exposed_jobs/"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()

        logger.info("[working_nomads] Fetching API: %s", self.start_url)

        try:
            response = await page.goto(self.start_url, wait_until="domcontentloaded")
            if not response or response.status != 200:
                logger.warning("[working_nomads] API returned status %s", response.status if response else "None")
                return []

            body = await page.inner_text("body")
            data = json.loads(body)
        except Exception as exc:
            logger.warning("[working_nomads] API request failed: %s", exc)
            return []

        raw_jobs = data if isinstance(data, list) else data.get("jobs", [])
        logger.info("[working_nomads] API returned %d total jobs", len(raw_jobs))

        # Client-side keyword filter since API doesn't support search
        query_terms = [t.lower() for t in query.split() if len(t) > 2]

        jobs: list[JobRecord] = []
        for item in raw_jobs:
            if not isinstance(item, dict):
                continue

            title = (item.get("title") or "").strip()
            company = (item.get("company_name") or item.get("company") or "").strip()
            location = (item.get("location") or "Remote").strip()
            description = (item.get("description") or "").strip()[:500]
            url = (item.get("url") or "").strip()
            posted_at = (item.get("pub_date") or item.get("published") or "").strip()
            category = (item.get("category_name") or item.get("category") or "").strip()

            if not title or not url:
                continue

            # Filter by query relevance
            searchable = f"{title} {company} {description} {category}".lower()
            if not any(term in searchable for term in query_terms):
                continue

            tags: list[str] = ["Remote"]
            if category:
                tags.append(category)

            score = semantic_match_score(query=query, title=title, description=description)
            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company or "Unknown",
                    location=location or "Remote/Worldwide",
                    url=url,
                    description=description,
                    posted_at=posted_at or None,
                    tags=tags[:8],
                    semantic_score=score,
                )
            )
        logger.info("[working_nomads] Parsed %d matching jobs from %d total", len(jobs), len(raw_jobs))
        return jobs
