from __future__ import annotations

from datetime import datetime, timezone
import html
import re
from typing import Any

from playwright.async_api import BrowserContext, Page

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_MAX_JOBS_PER_ORG = 120
_MAX_TOTAL_JOBS = 300

# Curated IT organizations whose public careers are exposed via Greenhouse.
_GREENHOUSE_BOARDS: tuple[dict[str, str], ...] = (
    {"company": "BrowserStack", "board": "browserstack"},
    {"company": "Chargebee", "board": "chargebee"},
    {"company": "CRED", "board": "cred"},
    {"company": "Freshworks", "board": "freshworks"},
    {"company": "InMobi", "board": "inmobi"},
    {"company": "Meesho", "board": "meesho"},
    {"company": "Mindtickle", "board": "mindtickle"},
    {"company": "PhonePe", "board": "phonepe"},
    {"company": "Razorpay", "board": "razorpaysoftwareprivatelimited"},
    {"company": "ShareChat", "board": "sharechat"},
    {"company": "Swiggy", "board": "swiggy"},
    {"company": "Whatfix", "board": "whatfix"},
    {"company": "Cloudflare", "board": "cloudflare"},
    {"company": "Datadog", "board": "datadog"},
    {"company": "Databricks", "board": "databricks"},
    {"company": "MongoDB", "board": "mongodb"},
    {"company": "Postman", "board": "postman"},
    {"company": "Coinbase", "board": "coinbase"},
    {"company": "Snyk", "board": "snyk"},
)

# Curated IT organizations whose public careers are exposed via Lever.
_LEVER_SITES: tuple[dict[str, str], ...] = (
    {"company": "Hasura", "site": "hasura"},
    {"company": "Interview Kickstart", "site": "interviewkickstart"},
    {"company": "Observe.AI", "site": "observeai"},
    {"company": "Tekion", "site": "tekion"},
    {"company": "Unacademy", "site": "unacademy"},
    {"company": "Canonical", "site": "canonical"},
    {"company": "Redis", "site": "redis"},
    {"company": "DigitalOcean", "site": "digitalocean98"},
    {"company": "Miro", "site": "miro"},
    {"company": "Airtable", "site": "airtable"},
)


def _clean_text(value: str | None) -> str:
    text = html.unescape(str(value or ""))
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _to_iso_from_epoch_ms(value: int | float | None) -> str | None:
    if value is None:
        return None
    try:
        epoch_s = float(value) / 1000.0
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(epoch_s, timezone.utc).isoformat()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        text = _clean_text(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _select_meta_value(metadata: list[dict[str, Any]], keywords: tuple[str, ...]) -> str:
    for row in metadata:
        name = _clean_text(str(row.get("name") or row.get("label") or ""))
        value = _clean_text(str(row.get("value") or row.get("content") or ""))
        if not name or not value:
            continue
        lowered = name.casefold()
        if any(key in lowered for key in keywords):
            return value
    return ""


class ITOrgCareersScraper(BaseScraper):
    platform = "it_org_careers"
    start_url = "https://boards-api.greenhouse.io"

    async def _request_json(self, page: Page, url: str) -> Any:
        try:
            response = await page.request.get(url, timeout=45_000)
        except Exception:
            return None
        if not response.ok:
            return None
        try:
            return await response.json()
        except Exception:
            return None

    def _from_greenhouse(
        self,
        run_id: str,
        query: str,
        company: str,
        payload: dict[str, Any],
    ) -> list[JobRecord]:
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            return []

        out: list[JobRecord] = []
        for raw_item in jobs[:_MAX_JOBS_PER_ORG]:
            if not isinstance(raw_item, dict):
                continue
            item = raw_item
            title = _clean_text(str(item.get("title") or ""))
            url = _clean_text(str(item.get("absolute_url") or ""))
            if not title or not url:
                continue

            location_obj = item.get("location") or {}
            location = _clean_text(str(location_obj.get("name") or "")) or "Remote/Unknown"
            description = _clean_text(str(item.get("content") or ""))
            posted_at = _clean_text(str(item.get("updated_at") or item.get("first_published") or "")) or None

            departments = item.get("departments") or []
            offices = item.get("offices") or []
            metadata = item.get("metadata") or []
            departments = departments if isinstance(departments, list) else []
            offices = offices if isinstance(offices, list) else []
            metadata = metadata if isinstance(metadata, list) else []

            tags: list[str] = []
            for row in departments:
                if not isinstance(row, dict):
                    continue
                name = _clean_text(str((row or {}).get("name") or ""))
                if name:
                    tags.append(name)
            for row in offices:
                if not isinstance(row, dict):
                    continue
                name = _clean_text(str((row or {}).get("name") or ""))
                if name:
                    tags.append(name)
            for row in metadata:
                if not isinstance(row, dict):
                    continue
                value = _clean_text(str((row or {}).get("value") or ""))
                if value:
                    tags.append(value)

            employment_type = _select_meta_value(
                metadata,
                ("employment", "job type", "time type", "commitment"),
            )
            experience_text = _select_meta_value(metadata, ("experience", "years"))
            salary_text = _select_meta_value(metadata, ("salary", "compensation", "pay"))

            score = semantic_match_score(query=query, title=title, description=description)
            if score <= 0.0:
                continue
            out.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                    description=description,
                    posted_at=posted_at,
                    employment_type=employment_type,
                    salary_text=salary_text,
                    experience_text=experience_text,
                    tags=_dedupe(tags),
                    semantic_score=score,
                )
            )
        return out

    def _from_lever(
        self,
        run_id: str,
        query: str,
        company: str,
        payload: list[dict[str, Any]],
    ) -> list[JobRecord]:
        out: list[JobRecord] = []
        for raw_item in payload[:_MAX_JOBS_PER_ORG]:
            if not isinstance(raw_item, dict):
                continue
            item = raw_item
            title = _clean_text(str(item.get("text") or item.get("title") or ""))
            url = _clean_text(str(item.get("hostedUrl") or item.get("applyUrl") or ""))
            if not title or not url:
                continue

            categories = item.get("categories") or {}
            categories = categories if isinstance(categories, dict) else {}
            location = _clean_text(str(categories.get("location") or "")) or "Remote/Unknown"
            description = _clean_text(
                " ".join(
                    [
                        str(item.get("descriptionPlain") or ""),
                        str(item.get("additionalPlain") or ""),
                        str(item.get("lists") or ""),
                    ]
                )
            )
            posted_at = _to_iso_from_epoch_ms(item.get("createdAt"))
            employment_type = _clean_text(str(categories.get("commitment") or ""))

            tags = _dedupe(
                [
                    str(categories.get("team") or ""),
                    str(categories.get("department") or ""),
                    str(categories.get("location") or ""),
                ]
            )

            score = semantic_match_score(query=query, title=title, description=description)
            if score <= 0.0:
                continue
            out.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                    description=description,
                    posted_at=posted_at,
                    employment_type=employment_type,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return out

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        jobs: list[JobRecord] = []
        seen_urls: set[str] = set()

        for board in _GREENHOUSE_BOARDS:
            endpoint = f"https://boards-api.greenhouse.io/v1/boards/{board['board']}/jobs?content=true"
            payload = await self._request_json(page, endpoint)
            if not isinstance(payload, dict):
                continue
            for job in self._from_greenhouse(run_id=run_id, query=query, company=board["company"], payload=payload):
                if job.url in seen_urls:
                    continue
                seen_urls.add(job.url)
                jobs.append(job)
            await self.human_pause(0.2, 0.5)

        for site in _LEVER_SITES:
            endpoint = f"https://api.lever.co/v0/postings/{site['site']}?mode=json"
            payload = await self._request_json(page, endpoint)
            if not isinstance(payload, list):
                continue
            for job in self._from_lever(run_id=run_id, query=query, company=site["company"], payload=payload):
                if job.url in seen_urls:
                    continue
                seen_urls.add(job.url)
                jobs.append(job)
            await self.human_pause(0.2, 0.5)

        jobs.sort(key=lambda row: row.semantic_score, reverse=True)
        return jobs[:_MAX_TOTAL_JOBS]
