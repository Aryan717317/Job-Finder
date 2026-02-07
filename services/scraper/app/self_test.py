from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from notifier import send_new_jobs_email

from . import db
from .config import settings
from .preflight import run_preflight


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_platform_subset(implemented: list[str]) -> list[str]:
    preferred = ["cutshort", "wellfound"]
    subset = [name for name in preferred if name in implemented]
    if subset:
        return subset
    return implemented[:2]


def _report_dir() -> Path:
    path = settings.data_dir / "self_test_reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_runner():
    from .runner import list_platform_support, run_scrape

    return list_platform_support, run_scrape


def run_self_test(
    query: str = "AI/ML Engineer",
    platforms: list[str] | None = None,
    headless: bool = True,
    send_email: bool = False,
    preflight_timeout_seconds: float = 30.0,
    stop_on_preflight_fail: bool = True,
) -> dict:
    started_at = _now_iso()
    db.init_db()

    preflight = run_preflight(timeout_seconds=preflight_timeout_seconds)
    report: dict = {
        "started_at": started_at,
        "finished_at": "",
        "status": "running",
        "query": query,
        "requested_platforms": platforms or [],
        "selected_platforms": [],
        "headless": headless,
        "send_email": send_email,
        "preflight": preflight,
        "cycle_id": None,
        "run_id": None,
        "jobs_processed": 0,
        "notified_count": 0,
        "error": None,
    }

    cycle_id = db.create_cycle_run(mode="self-test", query=query, enforce_singleton=True)
    if cycle_id is None:
        report["status"] = "skipped_busy"
        report["error"] = "Another cycle is already running."
        report["finished_at"] = _now_iso()
        return report
    report["cycle_id"] = cycle_id

    final_status = "completed"
    run_id: str | None = None
    jobs_processed = 0
    notified_count = 0
    error_message: str | None = None

    try:
        if stop_on_preflight_fail and preflight["overall_status"] == "fail":
            report["status"] = "skipped_preflight_fail"
            report["error"] = "Preflight failed; scrape step skipped."
            return report

        try:
            list_platform_support, run_scrape = _load_runner()
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing runtime dependency. Install scraper requirements first: "
                "pip install -r services/scraper/requirements.txt"
            ) from exc

        implemented = [item["platform"] for item in list_platform_support() if item["implemented"]]
        if not implemented:
            raise RuntimeError("No implemented platforms available for self-test.")

        if platforms:
            invalid = [name for name in platforms if name not in implemented]
            if invalid:
                raise ValueError(f"Unknown/non-implemented platform(s): {', '.join(invalid)}")
            selected_platforms = platforms
        else:
            selected_platforms = _default_platform_subset(implemented)

        report["selected_platforms"] = selected_platforms

        run_id = db.create_run(query=query, platforms=selected_platforms, headless=headless)
        report["run_id"] = run_id
        db.mark_run_started(run_id)
        db.add_run_event(
            run_id,
            "run.started",
            "Self-test scrape started",
            {"platforms": selected_platforms, "headless": headless},
        )

        jobs = asyncio.run(
            run_scrape(
                query=query,
                run_id=run_id,
                platforms=selected_platforms,
                headless=headless,
                event_hook=lambda event_type, message, payload=None: db.add_run_event(
                    run_id, event_type, message, payload
                ),
            )
        )
        jobs_processed = len(jobs)
        db.insert_jobs([job.to_dict() for job in jobs])
        db.mark_run_completed(run_id, jobs_collected=jobs_processed)
        db.add_run_event(run_id, "run.completed", "Self-test scrape completed", {"jobs_collected": jobs_processed})
        report["jobs_processed"] = jobs_processed

        if send_email:
            notified_count = send_new_jobs_email()
            report["notified_count"] = notified_count

        report["status"] = "completed"
        return report
    except Exception as exc:
        final_status = "failed"
        error_message = str(exc)
        report["status"] = "failed"
        report["error"] = error_message
        if run_id:
            db.mark_run_failed(run_id, error_message)
            db.add_run_event(run_id, "run.failed", "Self-test failed", {"error": error_message})
        return report
    finally:
        report["finished_at"] = _now_iso()
        db.complete_cycle_run(
            cycle_id=cycle_id,
            status=final_status if report["status"] == "failed" else report["status"],
            jobs_processed=jobs_processed,
            notified_count=notified_count,
            run_id=run_id,
            error_message=error_message or report["error"],
        )


def run_and_save_self_test(
    query: str = "AI/ML Engineer",
    platforms: list[str] | None = None,
    headless: bool = True,
    send_email: bool = False,
    preflight_timeout_seconds: float = 30.0,
    stop_on_preflight_fail: bool = True,
) -> tuple[dict, Path]:
    report = run_self_test(
        query=query,
        platforms=platforms,
        headless=headless,
        send_email=send_email,
        preflight_timeout_seconds=preflight_timeout_seconds,
        stop_on_preflight_fail=stop_on_preflight_fail,
    )
    out_dir = _report_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stamped_path = out_dir / f"{stamp}.json"
    latest_path = out_dir / "latest.json"
    text = json.dumps(report, indent=2, ensure_ascii=False)
    stamped_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return report, latest_path


def load_latest_self_test_report() -> dict | None:
    path = _report_dir() / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
