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


class JobicyScraper(BaseScraper):
    """Jobicy scraper using their free public JSON API.

    API: https://jobicy.com/api/v2/remote-jobs
    Params: ?count=50&tag=python&geo=anywhere
    Returns only remote/WFH jobs. Free, no auth required.
    """

    platform = "jobicy"
    start_url = "https://jobicy.com/api/v2/remote-jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        # Jobicy uses "tag" for keyword search; use simpler keywords
        tag = quote_plus(query)
        api_url = f"{self.start_url}?count=50&tag={tag}"
        logger.info("[jobicy] Fetching API: %s", api_url)

        # Set proper headers to avoid 403 blocks
        await page.set_extra_http_headers({
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })

        try:
            response = await page.goto(api_url, wait_until="domcontentloaded")
            if not response or response.status != 200:
                logger.warning("[jobicy] API returned status %s", response.status if response else "None")
                return []

            body = await page.inner_text("body")
            data = json.loads(body)
        except Exception as exc:
            logger.warning("[jobicy] API request failed: %s", exc)
            return []

        raw_jobs = data.get("jobs", [])
        logger.info("[jobicy] API returned %d jobs", len(raw_jobs))

        jobs: list[JobRecord] = []
        for item in raw_jobs:
            if not isinstance(item, dict):
                continue

            def _safe_str(val, default="") -> str:
                if val is None:
                    return default
                if isinstance(val, (list, dict)):
                    return default
                return str(val).strip() or default

            title = _safe_str(item.get("jobTitle"))
            company = _safe_str(item.get("companyName"))
            location = _safe_str(item.get("jobGeo"), "Remote/Worldwide")
            raw_desc = item.get("jobExcerpt") or item.get("jobDescription") or ""
            description = _safe_str(raw_desc)[:500]
            url = _safe_str(item.get("url"))
            posted_at = _safe_str(item.get("pubDate"))
            salary_min = item.get("salaryMin") or item.get("annualSalaryMin")
            salary_max = item.get("salaryMax") or item.get("annualSalaryMax")
            salary_currency = _safe_str(item.get("salaryCurrency"), "USD")
            # jobType can be a stringified list like "['Full-Time']"
            raw_job_type = item.get("jobType") or ""
            if isinstance(raw_job_type, list):
                job_type = raw_job_type[0] if raw_job_type else ""
            else:
                job_type = str(raw_job_type).strip("[]' \"")
            raw_industry = item.get("jobIndustry") or []
            if isinstance(raw_industry, str):
                # Handle stringified list like "['Data Science']"
                raw_industry = raw_industry.strip("[]")
                industry = [s.strip("' \"&amp;") for s in raw_industry.split(",") if s.strip("' \"")]
            elif isinstance(raw_industry, list):
                industry = raw_industry
            else:
                industry = []

            if not title or not url:
                continue

            salary_text = ""
            try:
                if salary_min and salary_max:
                    salary_text = f"{salary_currency} {int(salary_min):,} - {int(salary_max):,}/yr"
                elif salary_min:
                    salary_text = f"{salary_currency} {int(salary_min):,}+/yr"
            except (ValueError, TypeError):
                pass

            tags: list[str] = ["Remote"]
            if job_type:
                tags.append(job_type)
            for ind in industry:
                if isinstance(ind, str) and ind.strip():
                    tags.append(ind.strip())

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
                    salary_text=salary_text,
                    tags=tags[:8],
                    semantic_score=score,
                )
            )
        logger.info("[jobicy] Parsed %d valid jobs", len(jobs))
        return jobs
