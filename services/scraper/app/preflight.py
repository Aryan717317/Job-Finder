from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from . import db
from .config import settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


def _check_db() -> tuple[str, str, dict]:
    started = perf_counter()
    try:
        db.init_db()
        total_jobs = db.count_jobs()
        elapsed_ms = int((perf_counter() - started) * 1000)
        return "pass", "SQLite initialized", {"duration_ms": elapsed_ms, "jobs_count": total_jobs}
    except Exception as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        return "fail", "SQLite check failed", {"duration_ms": elapsed_ms, "error": _safe_error(exc)}


def _check_env() -> tuple[str, str, dict]:
    required_for_email = ["GMAIL_SENDER", "GMAIL_APP_PASSWORD", "GMAIL_RECIPIENT"]
    missing = [key for key in required_for_email if not os.getenv(key, "").strip()]
    if missing:
        return "warning", "Email env vars missing (email step will fail)", {"missing": missing}
    return "pass", "Email env vars configured", {"missing": []}


def _check_platform_registry() -> tuple[str, str, dict]:
    started = perf_counter()
    try:
        from .runner import list_platform_support

        support = list_platform_support()
        implemented = [item["platform"] for item in support if item["implemented"]]
        elapsed_ms = int((perf_counter() - started) * 1000)
        if len(implemented) < 20:
            return (
                "warning",
                "Not all target platforms are implemented",
                {"implemented_count": len(implemented), "duration_ms": elapsed_ms},
            )
        return "pass", "Platform registry loaded", {"implemented_count": len(implemented), "duration_ms": elapsed_ms}
    except Exception as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        return "fail", "Platform registry check failed", {"duration_ms": elapsed_ms, "error": _safe_error(exc)}


async def _check_playwright_async(timeout_seconds: float = 30.0) -> tuple[str, str, dict]:
    started = perf_counter()
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("about:blank", wait_until="domcontentloaded", timeout=int(timeout_seconds * 1000))
            await page.close()
            await browser.close()
        elapsed_ms = int((perf_counter() - started) * 1000)
        return "pass", "Playwright Chromium launch OK", {"duration_ms": elapsed_ms}
    except Exception as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        return "fail", "Playwright Chromium launch failed", {"duration_ms": elapsed_ms, "error": _safe_error(exc)}


def _check_playwright(timeout_seconds: float = 30.0) -> tuple[str, str, dict]:
    return asyncio.run(_check_playwright_async(timeout_seconds=timeout_seconds))


def run_preflight(timeout_seconds: float = 30.0) -> dict:
    started_at = _now_iso()
    results: list[dict] = []

    for name, check_fn in [
        ("database", _check_db),
        ("environment", _check_env),
        ("platform_registry", _check_platform_registry),
    ]:
        try:
            status, message, details = check_fn()
        except Exception as exc:
            status = "fail"
            message = "Unexpected check failure"
            details = {"error": _safe_error(exc)}
        results.append({"check": name, "status": status, "message": message, "details": details})

    pw_status, pw_message, pw_details = _check_playwright(timeout_seconds=timeout_seconds)
    results.append({"check": "playwright", "status": pw_status, "message": pw_message, "details": pw_details})

    summary = {
        "pass": sum(1 for row in results if row["status"] == "pass"),
        "warning": sum(1 for row in results if row["status"] == "warning"),
        "fail": sum(1 for row in results if row["status"] == "fail"),
    }
    overall = "pass" if summary["fail"] == 0 and summary["warning"] == 0 else ("warning" if summary["fail"] == 0 else "fail")

    return {
        "started_at": started_at,
        "finished_at": _now_iso(),
        "overall_status": overall,
        "summary": summary,
        "results": results,
    }


def _report_dir() -> Path:
    path = settings.data_dir / "preflight_reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_and_save_preflight(timeout_seconds: float = 30.0) -> tuple[dict, Path]:
    report = run_preflight(timeout_seconds=timeout_seconds)
    out_dir = _report_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stamped_path = out_dir / f"{stamp}.json"
    latest_path = out_dir / "latest.json"
    text = json.dumps(report, indent=2, ensure_ascii=False)
    stamped_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return report, latest_path


def load_latest_preflight_report() -> dict | None:
    path = _report_dir() / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
