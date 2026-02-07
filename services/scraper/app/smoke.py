from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import time

from playwright.async_api import async_playwright

from .config import settings
from .scrapers import build_scraper_registry
from .scrapers.stealth import apply_stealth


CAPTCHA_MARKERS = (
    "captcha",
    "verify you are human",
    "challenge",
    "cloudflare",
    "access denied",
)


def _report_dir() -> Path:
    path = settings.data_dir / "smoke_reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _contains_captcha(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in CAPTCHA_MARKERS)


async def run_smoke_test(
    query: str = "AI/ML Engineer",
    platforms: list[str] | None = None,
    headless: bool = True,
    per_platform_timeout_seconds: int = 120,
) -> dict:
    registry = build_scraper_registry()
    selected = sorted(platforms) if platforms else sorted(registry.keys())

    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            for platform in selected:
                scraper = registry.get(platform)
                if scraper is None:
                    results.append(
                        {
                            "platform": platform,
                            "status": "fail",
                            "jobs_count": 0,
                            "captcha_detected": False,
                            "duration_ms": 0,
                            "error": "No scraper registered",
                        }
                    )
                    continue

                context = await browser.new_context(
                    locale=settings.default_locale,
                    timezone_id=settings.default_timezone,
                    viewport={"width": 1366, "height": 768},
                )
                page = await context.new_page()
                await apply_stealth(page)

                start = time.perf_counter()
                status = "pass"
                jobs_count = 0
                captcha_detected = False
                error: str | None = None

                try:
                    jobs = await asyncio.wait_for(
                        scraper.scrape(context=context, query=query, run_id="smoke-test"),
                        timeout=max(30, per_platform_timeout_seconds),
                    )
                    jobs_count = len(jobs)
                    page_text = await page.content()
                    captcha_detected = _contains_captcha(page_text)

                    if captcha_detected:
                        status = "warning"
                    elif jobs_count == 0:
                        status = "warning"
                except Exception as exc:
                    status = "fail"
                    error = str(exc)
                    try:
                        page_text = await page.content()
                        captcha_detected = _contains_captcha(page_text)
                        if captcha_detected:
                            status = "warning"
                    except Exception:
                        pass
                finally:
                    duration_ms = int((time.perf_counter() - start) * 1000)
                    await context.close()

                results.append(
                    {
                        "platform": platform,
                        "status": status,
                        "jobs_count": jobs_count,
                        "captcha_detected": captcha_detected,
                        "duration_ms": duration_ms,
                        "error": error,
                    }
                )
        finally:
            await browser.close()

    summary = {
        "pass": sum(1 for item in results if item["status"] == "pass"),
        "warning": sum(1 for item in results if item["status"] == "warning"),
        "fail": sum(1 for item in results if item["status"] == "fail"),
    }

    report = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "headless": headless,
        "summary": summary,
        "results": results,
    }
    return report


def save_smoke_report(report: dict) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = _report_dir()
    path = directory / f"smoke_{stamp}.json"
    latest = directory / "latest.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_latest_smoke_report() -> dict | None:
    latest = _report_dir() / "latest.json"
    if not latest.exists():
        return None
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return None


def run_and_save_smoke_test(
    query: str = "AI/ML Engineer",
    platforms: list[str] | None = None,
    headless: bool = True,
    per_platform_timeout_seconds: int = 120,
) -> tuple[dict, Path]:
    report = asyncio.run(
        run_smoke_test(
            query=query,
            platforms=platforms,
            headless=headless,
            per_platform_timeout_seconds=per_platform_timeout_seconds,
        )
    )
    path = save_smoke_report(report)
    return report, path
