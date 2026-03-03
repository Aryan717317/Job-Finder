from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    def load_dotenv(*_args, **_kwargs):
        return False

from notifier import send_new_jobs_email
from services.scraper.app import db


_CS_TITLE_WHITELIST = (
    "sde",
    "software",
    "developer",
    "engineer",
    "ai",
    "ml",
    "machine learning",
    "data science",
    "data analyst",
    "prompt engineering",
    "llm",
    "fullstack",
    "backend",
    "frontend",
    # Additional titles common on remote/international job boards
    "python",
    "java",
    "javascript",
    "typescript",
    "golang",
    "rust",
    "cloud",
    "devops",
    "sre",
    "data engineer",
    "deep learning",
    "nlp",
    "computer vision",
    "generative ai",
    "genai",
    "automation",
    "qa",
    "security engineer",
    "platform engineer",
    "infrastructure",
)

# Remote-only job platforms that do not use 'fresher'/'batch' language.
# The fresher filter is relaxed for these: any entry-level or junior title passes.
_REMOTE_PLATFORMS = frozenset({
    "remotive",
    "remote_ok",
    "himalayas",
    "jobicy",
    "arbeitnow",
    "working_nomads",
    "we_work_remotely",
    "remote_co",
    "just_remote",
    "jobgether",
    "flexjobs",
    "arc_dev",
    "builtin",
    "relocate_me",
})

_ENTRY_LEVEL_TITLE_HINTS = (
    "junior",
    "jr.",
    "jr ",
    "entry",
    "entry-level",
    "associate",
    "trainee",
    "intern",
    "graduate",
    "fresher",
    "sde-1",
    "sde 1",
    "level 1",
    "l1 ",
    "new grad",
    "early career",
)

_NON_TECH_BLACKLIST = (
    "accountant",
    "sales",
    "marketing",
    "manager",
    "bpo",
    "content writer",
    "hr",
    "civil",
    "mechanical",
    "electrical",
)


def _normalize_title(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _dedup_key(job) -> str:
    """Normalize title+company+platform into a stable dedup key."""
    title = _normalize_title(getattr(job, "title", "") or "")
    company = " ".join((getattr(job, "company", "") or "").strip().lower().split())
    platform = (getattr(job, "platform", "") or "").strip().lower()
    return f"{platform}|{title}|{company}"


def _deduplicate_jobs(jobs: list, logger: logging.Logger) -> list:
    """Drop duplicate jobs with the same title+company+platform, keeping the highest score."""
    best: dict[str, object] = {}
    for job in jobs:
        key = _dedup_key(job)
        existing = best.get(key)
        if existing is None or (getattr(job, "semantic_score", 0) > getattr(existing, "semantic_score", 0)):
            best[key] = job
    deduped = list(best.values())
    removed = len(jobs) - len(deduped)
    if removed:
        logger.info("[Dedup] Removed %d duplicate job(s) (title+company+platform).", removed)
    return deduped


def _is_cs_ai_ml_title(title: str) -> bool:
    normalized = _normalize_title(title)
    if not normalized:
        return False
    return any(keyword in normalized for keyword in _CS_TITLE_WHITELIST)


def _is_blacklisted_title(title: str) -> bool:
    normalized = _normalize_title(title)
    if not normalized:
        return True

    if "engineering manager" in normalized:
        manager_blacklisted = False
    else:
        manager_blacklisted = "manager" in normalized

    for keyword in _NON_TECH_BLACKLIST:
        if keyword == "manager":
            if manager_blacklisted:
                return True
            continue
        if keyword in normalized:
            return True
    return False


def _filter_cs_jobs(jobs: list, logger: logging.Logger) -> list:
    filtered: list = []
    for job in jobs:
        title = getattr(job, "title", "") or ""
        if _is_blacklisted_title(title):
            logger.info("[Filtered Out] Non-CS role: %s", title)
            continue
        if not _is_cs_ai_ml_title(title):
            logger.info("[Filtered Out] Non-CS role: %s", title)
            continue
        filtered.append(job)
    return filtered


def _is_entry_level_title(title: str) -> bool:
    """True when the title itself signals a junior/entry-level role."""
    normalized = _normalize_title(title)
    return any(hint in normalized for hint in _ENTRY_LEVEL_TITLE_HINTS)


def _filter_fresher_jobs(jobs: list, logger: logging.Logger) -> list:
    from services.scraper.app.models import scan_fresher_keywords

    filtered: list = []
    for job in jobs:
        platform = getattr(job, "platform", "") or ""
        title = getattr(job, "title", "") or ""
        description = getattr(job, "description", "") or ""
        experience_text = getattr(job, "experience_text", "") or ""

        # For remote/international platforms: accept any entry-level title
        # since they don't use Indian 'fresher'/'batch' terminology.
        if platform in _REMOTE_PLATFORMS:
            if _is_entry_level_title(title) or scan_fresher_keywords(
                description=description, experience_text=experience_text, title=title
            ):
                filtered.append(job)
            else:
                logger.info("[Filtered Out] Non-entry-level remote role: %s", title)
            continue

        # For India-centric platforms: original fresher keyword filter applies.
        if not scan_fresher_keywords(description=description, experience_text=experience_text, title=title):
            logger.info("[Filtered Out] Non-fresher role: %s", title)
            continue
        filtered.append(job)
    return filtered


def _configure_logging() -> logging.Logger:
    log_path = Path(os.getenv("AJH_CYCLE_LOG_PATH", "services/scraper/data/logs/cycle_runner.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("cycle_runner")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def _implemented_platforms() -> list[str]:
    try:
        from services.scraper.app.runner import list_platform_support
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing runtime dependency. Install scraper requirements first: "
            "pip install -r services/scraper/requirements.txt"
        ) from exc

    support = list_platform_support()
    return [item["platform"] for item in support if item["implemented"]]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one full job aggregation cycle (scrape + optional notify).")
    parser.add_argument("--query", default=os.getenv("AUTO_CYCLE_QUERY", "AI/ML Engineer"))
    parser.add_argument("--platform", action="append", dest="platforms", default=None)
    parser.add_argument("--headful", action="store_true", help="Run browser in headful mode.")
    parser.add_argument("--no-email", action="store_true", help="Skip email notification.")
    parser.add_argument("--mode", default="cli", help="Cycle mode label stored in DB (default: cli).")
    return parser.parse_args()


def _validate_platforms(requested: list[str] | None, implemented: list[str]) -> list[str]:
    if not requested:
        return implemented
    allowed = set(implemented)
    invalid = [name for name in requested if name not in allowed]
    if invalid:
        raise ValueError(f"Unknown or non-implemented platform(s): {', '.join(invalid)}")
    return requested


def _run_cycle(
    logger: logging.Logger,
    query: str,
    platforms: list[str],
    headless: bool,
    send_email: bool,
    mode: str,
) -> tuple[int, dict]:
    db.init_db()
    try:
        from services.scraper.app.runner import run_scrape
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing runtime dependency. Install scraper requirements first: "
            "pip install -r services/scraper/requirements.txt"
        ) from exc

    cycle_id = db.create_cycle_run(mode=mode, query=query, enforce_singleton=True)
    if cycle_id is None:
        summary = {
            "status": "skipped_busy",
            "reason": "Another cycle is already marked running.",
            "query": query,
            "platforms": platforms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.warning("Cycle skipped because another active cycle exists in DB.")
        return 2, summary

    run_id: str | None = None
    jobs_processed = 0
    notified_count = 0
    cycle_status = "completed"
    error_message: str | None = None

    try:
        run_id = db.create_run(query=query, platforms=platforms, headless=headless)
        db.mark_run_started(run_id)
        db.add_run_event(run_id, "run.started", "CLI cycle run started", {"platforms": platforms, "headless": headless})
        logger.info("Run started. run_id=%s platforms=%s query=%s", run_id, ",".join(platforms), query)

        jobs = asyncio.run(
            run_scrape(
                query=query,
                run_id=run_id,
                platforms=platforms,
                headless=headless,
                event_hook=lambda event_type, message, payload=None: db.add_run_event(
                    run_id, event_type, message, payload
                ),
            )
        )
        jobs = _filter_cs_jobs(jobs, logger)
        jobs = _filter_fresher_jobs(jobs, logger)
        jobs = _deduplicate_jobs(jobs, logger)
        jobs_processed = len(jobs)
        db.insert_jobs([job.to_dict() for job in jobs])
        db.mark_run_completed(run_id, jobs_collected=jobs_processed)
        db.add_run_event(run_id, "run.completed", "CLI cycle scrape completed", {"jobs_collected": jobs_processed})
        logger.info("Scrape completed. run_id=%s jobs_processed=%s", run_id, jobs_processed)

        if send_email:
            try:
                notified_count = send_new_jobs_email()
                logger.info("Email notification completed. notified_count=%s", notified_count)
            except Exception as email_exc:
                logger.warning("Email notification failed (non-fatal): %s", email_exc)
                notified_count = 0
        else:
            logger.info("Email step skipped (--no-email).")

        summary = {
            "status": "completed",
            "cycle_id": cycle_id,
            "run_id": run_id,
            "query": query,
            "platforms": platforms,
            "headless": headless,
            "jobs_processed": jobs_processed,
            "notified_count": notified_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return 0, summary
    except Exception as exc:
        cycle_status = "failed"
        error_message = str(exc)
        if run_id:
            db.mark_run_failed(run_id, error_message)
            db.add_run_event(run_id, "run.failed", "CLI cycle failed", {"error": error_message})
        logger.exception("Cycle failed: %s", error_message)

        summary = {
            "status": "failed",
            "cycle_id": cycle_id,
            "run_id": run_id,
            "query": query,
            "platforms": platforms,
            "headless": headless,
            "jobs_processed": jobs_processed,
            "notified_count": notified_count,
            "error": error_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return 1, summary
    finally:
        db.complete_cycle_run(
            cycle_id=cycle_id,
            status=cycle_status,
            jobs_processed=jobs_processed,
            notified_count=notified_count,
            run_id=run_id,
            error_message=error_message,
        )


def main() -> int:
    load_dotenv("services/scraper/.env", override=False)
    args = _parse_args()
    logger = _configure_logging()

    try:
        implemented = _implemented_platforms()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1
    try:
        platforms = _validate_platforms(args.platforms, implemented)
    except ValueError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1

    exit_code, summary = _run_cycle(
        logger=logger,
        query=(args.query or "AI/ML Engineer").strip() or "AI/ML Engineer",
        platforms=platforms,
        headless=not args.headful,
        send_email=not args.no_email,
        mode=(args.mode or "cli").strip() or "cli",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
