from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
import inspect
import random

from playwright.async_api import async_playwright

from .config import settings
from .models import JobRecord
from .scrapers import build_scraper_registry


EventHook = Callable[[str, str, dict | None], None | Awaitable[None]]

SCRAPER_REGISTRY = build_scraper_registry()
IMPLEMENTED_PLATFORMS = {
    "arc_dev",
    "cutshort",
    "flexjobs",
    "foundit",
    "hirect",
    "hirist",
    "indeed",
    "internshala",
    "linkedin",
    "naukri",
    "remote_co",
    "relocate_me",
    "remotive",
    "we_work_remotely",
    "wellfound",
    "working_nomads",
}


def list_platform_support() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for platform in sorted(SCRAPER_REGISTRY.keys()):
        rows.append(
            {
                "platform": platform,
                "implemented": platform in IMPLEMENTED_PLATFORMS,
            }
        )
    return rows


async def _emit_event(event_hook: EventHook | None, event_type: str, message: str, payload: dict | None = None) -> None:
    if event_hook is None:
        return
    maybe_awaitable = event_hook(event_type, message, payload)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable


def _is_captcha_or_challenge_error(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "captcha",
        "verify you are human",
        "challenge required",
        "access denied",
        "cloudflare",
        "bot detected",
    )
    return any(marker in lowered for marker in markers)


def _is_rate_limit_or_transient_error(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "timeout",
        "timed out",
        "net::err",
        "connection reset",
        "connection closed",
        "temporarily unavailable",
        "429",
        "503",
        "rate limit",
    )
    return any(marker in lowered for marker in markers)


def _retry_delay_seconds(attempt: int) -> float:
    # attempt is 1-based; applies bounded exponential backoff with jitter.
    exp = max(0, attempt - 1)
    raw = settings.retry_backoff_base_seconds * (2 ** exp)
    capped = min(settings.retry_backoff_cap_seconds, raw)
    jitter = random.uniform(0.0, max(0.15, capped * 0.2))
    return round(capped + jitter, 2)


async def run_scrape(
    query: str,
    run_id: str,
    platforms: Iterable[str],
    headless: bool = True,
    event_hook: EventHook | None = None,
) -> list[JobRecord]:
    results: list[JobRecord] = []
    async with async_playwright() as p:
        for platform in platforms:
            scraper = SCRAPER_REGISTRY.get(platform)
            if scraper is None:
                await _emit_event(event_hook, "platform.skipped", "No scraper implementation for platform", {"platform": platform})
                continue

            profile_dir = settings.profile_dir / platform
            profile_dir.mkdir(parents=True, exist_ok=True)

            await _emit_event(event_hook, "platform.started", "Platform scrape started", {"platform": platform})

            if platform not in IMPLEMENTED_PLATFORMS:
                await _emit_event(
                    event_hook,
                    "platform.stub_mode",
                    "Using placeholder adapter; extraction not implemented yet",
                    {"platform": platform},
                )

            max_attempts = max(1, settings.max_platform_retries + 1)
            attempt = 1
            while attempt <= max_attempts:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=headless,
                    locale=settings.default_locale,
                    timezone_id=settings.default_timezone,
                    viewport={"width": 1366, "height": 768},
                    args=["--disable-blink-features=AutomationControlled"],
                )
                await context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                )

                try:
                    jobs = await scraper.scrape(context=context, query=query, run_id=run_id)
                    results.extend(jobs)
                    await _emit_event(
                        event_hook,
                        "platform.completed",
                        "Platform scrape completed",
                        {"platform": platform, "jobs_collected": len(jobs), "attempt": attempt},
                    )
                    break
                except Exception as exc:
                    error_text = str(exc)

                    if _is_captcha_or_challenge_error(error_text):
                        await _emit_event(
                            event_hook,
                            "platform.captcha_required",
                            "Captcha or challenge detected; human handoff required",
                            {"platform": platform, "error": error_text, "attempt": attempt},
                        )
                        break

                    if _is_rate_limit_or_transient_error(error_text) and attempt < max_attempts:
                        delay = _retry_delay_seconds(attempt)
                        await _emit_event(
                            event_hook,
                            "platform.retry_scheduled",
                            "Transient platform error; retry scheduled",
                            {
                                "platform": platform,
                                "attempt": attempt,
                                "next_attempt": attempt + 1,
                                "delay_seconds": delay,
                                "error": error_text,
                            },
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue

                    event_type = "platform.rate_limited" if _is_rate_limit_or_transient_error(error_text) else "platform.failed"
                    await _emit_event(
                        event_hook,
                        event_type,
                        "Platform scrape failed",
                        {"platform": platform, "error": error_text, "attempt": attempt},
                    )
                    break
                finally:
                    await context.close()

    return results
