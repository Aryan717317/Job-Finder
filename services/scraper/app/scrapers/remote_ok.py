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


class RemoteOkScraper(BaseScraper):
    """RemoteOK scraper using their public JSON API.

    API: https://remoteok.com/api (returns JSON array).
    The first element is metadata, the rest are job objects.
    Cloudflare blocks browser scraping, so the API is far more reliable.
    """

    platform = "remote_ok"
    start_url = "https://remoteok.com/api"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        # RemoteOK API accepts tag-based filtering
        query_slug = query.lower().replace(" ", "-").replace("/", "-")
        api_url = f"{self.start_url}?tag={query_slug}"
        logger.info("[remote_ok] Fetching API: %s", api_url)

        # Set headers to look like a normal request
        await page.set_extra_http_headers({
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        try:
            response = await page.goto(api_url, wait_until="domcontentloaded")
            if not response or response.status != 200:
                logger.warning("[remote_ok] API returned status %s", response.status if response else "None")
                return []

            body = await page.inner_text("body")
            data = json.loads(body)
        except Exception as exc:
            logger.warning("[remote_ok] API request failed: %s", exc)
            return []

        # First element is metadata/legal notice, skip it
        raw_jobs = data[1:] if isinstance(data, list) and len(data) > 1 else []
        logger.info("[remote_ok] API returned %d jobs", len(raw_jobs))

        query_lower = query.lower()
        jobs: list[JobRecord] = []
        for item in raw_jobs:
            if not isinstance(item, dict):
                continue

            position = (item.get("position") or "").strip()
            company = (item.get("company") or "").strip()
            location = (item.get("location") or "Remote").strip()
            description = (item.get("description") or "").strip()[:500]
            slug = (item.get("slug") or "").strip()
            epoch = item.get("epoch")
            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            raw_tags = item.get("tags") or []

            url = f"https://remoteok.com/remote-jobs/{slug}" if slug else (item.get("url") or "")
            if not position or not url:
                continue

            salary_text = ""
            if salary_min and salary_max:
                salary_text = f" - "
            elif salary_min:
                salary_text = f"+"

            tags: list[str] = []
            for tag in raw_tags:
                if isinstance(tag, str) and tag.strip():
                    tags.append(tag.strip())

            posted_at = ""
            if epoch:
                try:
                    from datetime import datetime, timezone
                    posted_at = datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
                except Exception:
                    pass

            score = semantic_match_score(query=query, title=position, description=description)
            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=position,
                    company=company or "Unknown",
                    location=location or "Remote/Worldwide",
                    url=url,
                    description=description,
                    posted_at=posted_at or None,
                    salary_text=salary_text,
                    tags=tags[:8],
                    semantic_score=score,
                )
            )
        logger.info("[remote_ok] Parsed %d valid jobs", len(jobs))
        return jobs
