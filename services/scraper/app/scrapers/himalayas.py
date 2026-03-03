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


class HimalayasScraper(BaseScraper):
    """Himalayas scraper using their public JSON API.

    API: https://himalayas.app/jobs/api
    Accepts ?q=query parameter. Returns JSON with jobs array.
    Far more reliable than scraping their React SPA.
    """

    platform = "himalayas"
    start_url = "https://himalayas.app/jobs/api"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        api_url = f"{self.start_url}?q={quote_plus(query)}&limit=100"
        logger.info("[himalayas] Fetching API: %s", api_url)

        try:
            response = await page.goto(api_url, wait_until="domcontentloaded")
            if not response or response.status != 200:
                logger.warning("[himalayas] API returned status %s", response.status if response else "None")
                return []

            body = await page.inner_text("body")
            data = json.loads(body)
        except Exception as exc:
            logger.warning("[himalayas] API request failed: %s", exc)
            return []

        raw_jobs = data.get("jobs", [])
        if not raw_jobs and isinstance(data, list):
            raw_jobs = data
        logger.info("[himalayas] API returned %d jobs", len(raw_jobs))

        jobs: list[JobRecord] = []
        for item in raw_jobs:
            if not isinstance(item, dict):
                continue

            title = (item.get("title") or "").strip()
            company = (item.get("companyName") or "").strip()
            # locationRestrictions is a list like ['United States']
            loc_raw = item.get("locationRestrictions") or []
            if isinstance(loc_raw, list):
                location = ", ".join(str(l) for l in loc_raw[:3]) if loc_raw else "Remote/Worldwide"
            else:
                location = str(loc_raw).strip() or "Remote/Worldwide"
            description = (item.get("excerpt") or "").strip()[:500]
            # Use applicationLink or guid as URL
            url = (item.get("applicationLink") or item.get("guid") or "").strip()
            raw_posted = item.get("pubDate") or ""
            posted_at = ""
            if raw_posted:
                try:
                    from datetime import datetime, timezone
                    posted_at = datetime.fromtimestamp(int(raw_posted), tz=timezone.utc).isoformat()
                except Exception:
                    posted_at = str(raw_posted).strip()
            employment_type = (item.get("employmentType") or "").strip()
            salary_min = item.get("minSalary")
            salary_max = item.get("maxSalary")
            currency = (item.get("currency") or "USD").strip()
            categories = item.get("categories") or []

            if not title or not url:
                continue

            salary_text = ""
            try:
                if salary_min and str(salary_min) != "None" and salary_max and str(salary_max) != "None":
                    salary_text = f"{currency} {int(salary_min):,} - {int(salary_max):,}/yr"
                elif salary_min and str(salary_min) != "None":
                    salary_text = f"{currency} {int(salary_min):,}+/yr"
            except (ValueError, TypeError):
                pass

            tags: list[str] = ["Remote"]
            if employment_type:
                tags.append(employment_type)
            if isinstance(categories, list):
                for cat in categories:
                    if isinstance(cat, str) and cat.strip():
                        tags.append(cat.strip().replace("-", " "))

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
                    salary_text=salary_text,
                    tags=tags[:8],
                    semantic_score=score,
                )
            )
        logger.info("[himalayas] Parsed %d valid jobs", len(jobs))
        return jobs
