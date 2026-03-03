from __future__ import annotations

import json
import logging
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper

logger = logging.getLogger("cycle_runner")


class RemotiveScraper(BaseScraper):
    """Remotive scraper using their free public JSON API.

    API: https://remotive.com/api/remote-jobs
    No auth required. Returns up to 100 jobs per request.
    """

    platform = "remotive"
    start_url = "https://remotive.com/api/remote-jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()

        api_url = f"{self.start_url}?search={quote_plus(query)}&limit=100"
        logger.info("[remotive] Fetching API: %s", api_url)

        try:
            response = await page.goto(api_url, wait_until="domcontentloaded")
            if not response or response.status != 200:
                logger.warning("[remotive] API returned status %s", response.status if response else "None")
                return []

            body = await page.inner_text("body")
            data = json.loads(body)
        except Exception as exc:
            logger.warning("[remotive] API request failed: %s", exc)
            return []

        raw_jobs = data.get("jobs", [])
        logger.info("[remotive] API returned %d jobs", len(raw_jobs))

        jobs: list[JobRecord] = []
        for item in raw_jobs:
            title = (item.get("title") or "").strip()
            company = (item.get("company_name") or "").strip()
            location = (item.get("candidate_required_location") or "Worldwide").strip()
            description = (item.get("description") or "").strip()[:500]
            url = (item.get("url") or "").strip()
            posted_at = (item.get("publication_date") or "").strip()
            salary = (item.get("salary") or "").strip()
            job_type = (item.get("job_type") or "").strip()
            category = (item.get("category") or "").strip()

            tags: list[str] = []
            if category:
                tags.append(category)
            if job_type:
                tags.append(job_type)
            for tag_item in item.get("tags", []):
                if isinstance(tag_item, str) and tag_item.strip():
                    tags.append(tag_item.strip())

            if not title or not url:
                continue

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
                    employment_type=job_type,
                    salary_text=salary,
                    tags=tags[:8],
                    semantic_score=score,
                )
            )
        logger.info("[remotive] Parsed %d valid jobs", len(jobs))
        return jobs
