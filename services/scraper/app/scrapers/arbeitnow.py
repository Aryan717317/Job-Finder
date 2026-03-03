from __future__ import annotations

import json
import logging
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth

logger = logging.getLogger("cycle_runner")


class ArbeitnowScraper(BaseScraper):
    """Arbeitnow scraper using their free public JSON API.

    API: https://www.arbeitnow.com/api/job-board-api
    Supports remote filter. Free, no auth. Returns paginated results.
    """

    platform = "arbeitnow"
    start_url = "https://www.arbeitnow.com/api/job-board-api"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        # Set proper headers
        await page.set_extra_http_headers({
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })

        api_url = f"{self.start_url}?search={quote_plus(query)}&remote=true&page=1"
        logger.info("[arbeitnow] Fetching API: %s", api_url)

        all_raw_jobs: list[dict] = []
        for page_num in range(1, 4):  # Fetch up to 3 pages
            paginated_url = f"{self.start_url}?search={quote_plus(query)}&remote=true&page={page_num}"
            try:
                response = await page.goto(paginated_url, wait_until="domcontentloaded")
                if not response or response.status != 200:
                    logger.warning("[arbeitnow] API returned status %s on page %d", response.status if response else "None", page_num)
                    break

                body = await page.inner_text("body")
                data = json.loads(body)
                page_jobs = data.get("data", [])
                if not page_jobs:
                    break
                all_raw_jobs.extend(page_jobs)
                await self.human_pause(0.3, 0.7)
            except Exception as exc:
                logger.warning("[arbeitnow] API request failed on page %d: %s", page_num, exc)
                break

        logger.info("[arbeitnow] API returned %d total jobs", len(all_raw_jobs))

        jobs: list[JobRecord] = []
        for item in all_raw_jobs:
            if not isinstance(item, dict):
                continue

            title = (item.get("title") or "").strip()
            company = (item.get("company_name") or "").strip()
            location = (item.get("location") or "Remote").strip()
            description = (item.get("description") or "").strip()[:500]
            url = (item.get("url") or "").strip()
            raw_posted = item.get("created_at") or ""
            posted_at = str(raw_posted).strip() if raw_posted else ""
            remote = item.get("remote", False)
            job_types = item.get("job_types") or []
            raw_tags = item.get("tags") or []

            if not title or not url:
                continue

            tags: list[str] = []
            if remote:
                tags.append("Remote")
            for jt in job_types:
                if isinstance(jt, str) and jt.strip():
                    tags.append(jt.strip())
            for tag in raw_tags:
                if isinstance(tag, str) and tag.strip():
                    tags.append(tag.strip())

            employment_type = ""
            for jt in job_types:
                if isinstance(jt, str):
                    employment_type = jt.strip()
                    break

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
                    employment_type=employment_type,
                    tags=tags[:8],
                    semantic_score=score,
                )
            )
        logger.info("[arbeitnow] Parsed %d valid jobs", len(jobs))
        return jobs
