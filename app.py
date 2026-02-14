from __future__ import annotations

import asyncio
import os
import secrets
import threading
import time
from functools import wraps
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFProtect

from notifier import send_new_jobs_email
from services.scraper.app import db
from services.scraper.app.maintenance import load_latest_maintenance_report, run_and_save_maintenance
from services.scraper.app.preflight import load_latest_preflight_report, run_and_save_preflight
from services.scraper.app.runner import list_platform_support, run_scrape
from services.scraper.app.self_test import load_latest_self_test_report, run_and_save_self_test
from services.scraper.app.smoke import load_latest_smoke_report, run_and_save_smoke_test

_JOBS_PER_PAGE = 50

_CYCLE_LOCK = threading.Lock()
_SCHEDULER_START_LOCK = threading.Lock()


def _implemented_platforms() -> list[str]:
    support = list_platform_support()
    return [item["platform"] for item in support if item["implemented"]]


def _run_manual_scrape(query: str) -> tuple[int, str]:
    platforms = _implemented_platforms()
    run_id = db.create_run(query=query, platforms=platforms, headless=True)
    db.mark_run_started(run_id)
    db.add_run_event(run_id, "run.started", "Manual scrape triggered from dashboard", {"platforms": platforms})

    try:
        jobs = asyncio.run(
            run_scrape(
                query=query,
                run_id=run_id,
                platforms=platforms,
                headless=True,
                event_hook=lambda event_type, message, payload=None: db.add_run_event(
                    run_id, event_type, message, payload
                ),
            )
        )
        db.insert_jobs([job.to_dict() for job in jobs])
        db.mark_run_completed(run_id, len(jobs))
        db.add_run_event(run_id, "run.completed", "Manual scrape completed", {"jobs_collected": len(jobs)})
        return len(jobs), run_id
    except Exception as exc:
        db.mark_run_failed(run_id, str(exc))
        db.add_run_event(run_id, "run.failed", "Manual scrape failed", {"error": str(exc)})
        raise


def _run_full_cycle_once(query: str, mode: str) -> tuple[int, str, int]:
    cycle_id = db.create_cycle_run(mode=mode, query=query, enforce_singleton=True)
    if cycle_id is None:
        raise RuntimeError("Another cycle is already running (database lock).")
    run_id: str | None = None
    jobs_processed = 0
    notified_count = 0
    final_status = "completed"
    error_message: str | None = None

    try:
        jobs_processed, run_id = _run_manual_scrape(query)
        notified_count = send_new_jobs_email()
        return jobs_processed, run_id, notified_count
    except Exception as exc:
        final_status = "failed"
        error_message = str(exc)
        raise
    finally:
        db.complete_cycle_run(
            cycle_id=cycle_id,
            status=final_status,
            jobs_processed=jobs_processed,
            notified_count=notified_count,
            run_id=run_id,
            error_message=error_message,
        )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _auto_cycle_minutes() -> int:
    raw = os.getenv("AUTO_CYCLE_MINUTES", "60").strip()
    try:
        minutes = int(raw)
    except ValueError:
        minutes = 60
    return max(1, minutes)


def _auto_cycle_query() -> str:
    return os.getenv("AUTO_CYCLE_QUERY", "AI/ML Engineer").strip() or "AI/ML Engineer"


def _iso_utc_from_epoch(epoch_seconds: float | None) -> str:
    if epoch_seconds is None:
        return ""
    return datetime.fromtimestamp(epoch_seconds, timezone.utc).isoformat()


def _run_auto_cycle_scheduler(app: Flask) -> None:
    next_run_at: float | None = None
    while True:
        enabled = _env_bool("AUTO_CYCLE_ENABLED", False)
        interval_seconds = _auto_cycle_minutes() * 60
        query = _auto_cycle_query()

        if not enabled:
            app.config["AUTO_CYCLE_STATE"] = "disabled"
            app.config["AUTO_CYCLE_NEXT_RUN_AT"] = ""
            next_run_at = None
            time.sleep(10)
            continue

        now = time.time()
        if next_run_at is None:
            next_run_at = now + interval_seconds

        app.config["AUTO_CYCLE_STATE"] = "waiting"
        app.config["AUTO_CYCLE_NEXT_RUN_AT"] = _iso_utc_from_epoch(next_run_at)

        if now < next_run_at:
            time.sleep(min(5, max(0.5, next_run_at - now)))
            continue

        if not _CYCLE_LOCK.acquire(blocking=False):
            app.config["AUTO_CYCLE_STATE"] = "skipped_busy"
            next_run_at = time.time() + interval_seconds
            continue

        try:
            app.config["AUTO_CYCLE_STATE"] = "running"
            app.config["AUTO_CYCLE_LAST_RUN_AT"] = datetime.now(timezone.utc).isoformat()
            jobs_processed, run_id, notified_count = _run_full_cycle_once(query=query, mode="scheduled")
            app.config["AUTO_CYCLE_STATE"] = (
                f"completed run={run_id} jobs={jobs_processed} notified={notified_count}"
            )
        except Exception as exc:
            app.config["AUTO_CYCLE_STATE"] = f"failed: {exc}"
        finally:
            _CYCLE_LOCK.release()
            next_run_at = time.time() + interval_seconds
            app.config["AUTO_CYCLE_NEXT_RUN_AT"] = _iso_utc_from_epoch(next_run_at)


def _start_auto_cycle_scheduler(app: Flask) -> None:
    with _SCHEDULER_START_LOCK:
        if app.config.get("AUTO_CYCLE_SCHEDULER_STARTED", False):
            return
        app.config["AUTO_CYCLE_SCHEDULER_STARTED"] = True
        app.config["AUTO_CYCLE_STATE"] = "initializing"
        app.config["AUTO_CYCLE_LAST_RUN_AT"] = ""
        app.config["AUTO_CYCLE_NEXT_RUN_AT"] = ""

        thread = threading.Thread(
            target=_run_auto_cycle_scheduler,
            args=(app,),
            name="auto-cycle-scheduler",
            daemon=True,
        )
        thread.start()


def _is_authorized() -> bool:
    expected_user = os.getenv("DASHBOARD_USERNAME", "").strip()
    expected_pass = os.getenv("DASHBOARD_PASSWORD", "").strip()
    if not expected_user or not expected_pass:
        return True

    auth = request.authorization
    if auth is None:
        return False
    return auth.username == expected_user and auth.password == expected_pass


def _auth_response() -> Response:
    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": 'Basic realm="JobAggregatorDashboard"'},
    )


def require_auth(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not _is_authorized():
            return _auth_response()
        return fn(*args, **kwargs)

    return wrapped


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")

    configured_key = os.getenv("FLASK_SECRET_KEY", "").strip()
    if configured_key:
        app.secret_key = configured_key
    else:
        app.secret_key = secrets.token_hex(32)

    csrf = CSRFProtect(app)

    db.init_db()

    _start_auto_cycle_scheduler(app)

    @app.get("/")
    @require_auth
    def dashboard():
        page = max(1, request.args.get("page", 1, type=int))
        offset = (page - 1) * _JOBS_PER_PAGE
        jobs = [dict(row) for row in db.list_latest_jobs(limit=_JOBS_PER_PAGE, offset=offset)]
        email_attempts = [dict(row) for row in db.list_email_notifications(limit=20)]
        cycle_runs = [dict(row) for row in db.list_cycle_runs(limit=20)]
        smoke_report = load_latest_smoke_report()
        preflight_report = load_latest_preflight_report()
        self_test_report = load_latest_self_test_report()
        maintenance_report = load_latest_maintenance_report()
        total_jobs = db.count_jobs()
        has_next_page = len(jobs) == _JOBS_PER_PAGE and (offset + _JOBS_PER_PAGE) < total_jobs
        message = request.args.get("message", "")
        query = request.args.get("query", "AI/ML Engineer")
        return render_template(
            "dashboard.html",
            jobs=jobs,
            email_attempts=email_attempts,
            smoke_report=smoke_report,
            preflight_report=preflight_report,
            self_test_report=self_test_report,
            maintenance_report=maintenance_report,
            cycle_runs=cycle_runs,
            total_jobs=total_jobs,
            message=message,
            query=query,
            page=page,
            has_next_page=has_next_page,
            platforms=_implemented_platforms(),
            auto_cycle_enabled=_env_bool("AUTO_CYCLE_ENABLED", False),
            auto_cycle_minutes=_auto_cycle_minutes(),
            auto_cycle_state=app.config.get("AUTO_CYCLE_STATE", "unknown"),
            auto_cycle_next_run_at=app.config.get("AUTO_CYCLE_NEXT_RUN_AT", ""),
            db_active_cycle=db.has_active_cycle_run(),
        )

    @app.get("/healthz")
    @csrf.exempt
    def healthz():
        return jsonify(
            {
                "status": "ok",
                "service": "job-aggregator-dashboard",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "auto_cycle_enabled": _env_bool("AUTO_CYCLE_ENABLED", False),
                "auto_cycle_state": app.config.get("AUTO_CYCLE_STATE", "unknown"),
                "db_active_cycle": db.has_active_cycle_run(),
                "total_jobs": db.count_jobs(),
            }
        )

    @app.post("/manual-scrape")
    @require_auth
    def manual_scrape():
        query = (request.form.get("query") or "AI/ML Engineer").strip() or "AI/ML Engineer"
        if not _CYCLE_LOCK.acquire(blocking=False):
            message = "Manual scrape skipped: another scrape or full-cycle is already running."
            return redirect(url_for("dashboard", message=message, query=query))
        try:
            count, run_id = _run_manual_scrape(query)
            message = f"Manual scrape completed. Run: {run_id}. New/updated rows processed: {count}."
        except Exception as exc:
            message = f"Manual scrape failed: {exc}"
        finally:
            _CYCLE_LOCK.release()
        return redirect(url_for("dashboard", message=message, query=query))

    @app.post("/send-test-email")
    @require_auth
    def send_test_email():
        try:
            sent_count = send_new_jobs_email()
            message = f"Email sent successfully. Jobs marked notified: {sent_count}."
        except Exception as exc:
            message = f"Email send failed: {exc}"
        return redirect(url_for("dashboard", message=message))

    @app.post("/run-full-cycle")
    @require_auth
    def run_full_cycle():
        query = (request.form.get("query") or "AI/ML Engineer").strip() or "AI/ML Engineer"
        if not _CYCLE_LOCK.acquire(blocking=False):
            message = "Full cycle skipped: another scrape or full-cycle is already running."
            return redirect(url_for("dashboard", message=message, query=query))
        try:
            count, run_id, sent_count = _run_full_cycle_once(query=query, mode="manual")
            message = (
                f"Full cycle completed. Run: {run_id}. "
                f"Rows processed: {count}. Jobs notified by email: {sent_count}."
            )
        except Exception as exc:
            message = f"Full cycle failed: {exc}"
        finally:
            _CYCLE_LOCK.release()
        return redirect(url_for("dashboard", message=message, query=query))

    @app.post("/run-smoke-test")
    @require_auth
    def run_smoke_test():
        query = (request.form.get("query") or "AI/ML Engineer").strip() or "AI/ML Engineer"
        try:
            report, path = run_and_save_smoke_test(query=query, headless=True, per_platform_timeout_seconds=90)
            summary = report["summary"]
            message = (
                f"Smoke test completed. pass={summary['pass']} "
                f"warning={summary['warning']} fail={summary['fail']}. "
                f"Report: {path}"
            )
        except Exception as exc:
            message = f"Smoke test failed: {exc}"
        return redirect(url_for("dashboard", message=message, query=query))

    @app.post("/run-preflight")
    @require_auth
    def run_preflight():
        try:
            report, path = run_and_save_preflight(timeout_seconds=30.0)
            message = (
                f"Preflight completed. overall={report['overall_status']} "
                f"pass={report['summary']['pass']} "
                f"warning={report['summary']['warning']} "
                f"fail={report['summary']['fail']}. "
                f"Report: {path}"
            )
        except Exception as exc:
            message = f"Preflight failed: {exc}"
        return redirect(url_for("dashboard", message=message))

    @app.post("/run-self-test")
    @require_auth
    def run_self_test():
        query = (request.form.get("query") or "AI/ML Engineer").strip() or "AI/ML Engineer"
        if not _CYCLE_LOCK.acquire(blocking=False):
            message = "Self-test skipped: another scrape or full-cycle is already running."
            return redirect(url_for("dashboard", message=message, query=query))
        try:
            report, path = run_and_save_self_test(
                query=query,
                platforms=["cutshort", "wellfound"],
                headless=True,
                send_email=False,
                preflight_timeout_seconds=30.0,
                stop_on_preflight_fail=True,
            )
            message = (
                f"Self-test completed. status={report['status']} "
                f"jobs={report['jobs_processed']} notified={report['notified_count']}. "
                f"Report: {path}"
            )
        except Exception as exc:
            message = f"Self-test failed: {exc}"
        finally:
            _CYCLE_LOCK.release()
        return redirect(url_for("dashboard", message=message, query=query))

    @app.post("/run-maintenance")
    @require_auth
    def run_maintenance():
        try:
            report, path = run_and_save_maintenance(report_retention_days=30, log_retention_days=14, vacuum=True)
            summary = report["cleanup_summary"]
            message = (
                f"Maintenance completed. files_deleted={summary['files_deleted']} "
                f"bytes_freed={summary['bytes_freed']}. Report: {path}"
            )
        except Exception as exc:
            message = f"Maintenance failed: {exc}"
        return redirect(url_for("dashboard", message=message))

    return app


app = create_app()


if __name__ == "__main__":
    os.environ.setdefault("TZ", "UTC")
    port = int(os.getenv("DASHBOARD_PORT", "5000"))
    print(f"Starting dashboard at {datetime.now(timezone.utc).isoformat()} UTC")
    app.run(host="127.0.0.1", port=port, debug=True)
