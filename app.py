from __future__ import annotations

import asyncio
import os
import threading
import time
from functools import wraps
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, redirect, render_template_string, request, url_for

from notifier import send_new_jobs_email
from services.scraper.app import db
from services.scraper.app.maintenance import load_latest_maintenance_report, run_and_save_maintenance
from services.scraper.app.preflight import load_latest_preflight_report, run_and_save_preflight
from services.scraper.app.runner import list_platform_support, run_scrape
from services.scraper.app.self_test import load_latest_self_test_report, run_and_save_self_test
from services.scraper.app.smoke import load_latest_smoke_report, run_and_save_smoke_test


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Job Aggregator Dashboard</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 24px; background: #f7f8fa; color: #222; }
      h1 { margin-top: 0; }
      .row { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
      form { display: inline-block; }
      input[type=text] { padding: 8px; min-width: 280px; }
      button { padding: 8px 12px; cursor: pointer; }
      .meta { margin: 10px 0 20px 0; color: #444; }
      table { width: 100%; border-collapse: collapse; background: white; }
      th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
      th { background: #f0f0f0; }
      .status { margin: 10px 0; padding: 10px; background: #eef7ff; border: 1px solid #c9e5ff; }
    </style>
  </head>
  <body>
    <h1>Job Aggregator & Notifier</h1>
    {% if message %}<div class="status">{{ message }}</div>{% endif %}

    <div class="row">
      <form method="post" action="{{ url_for('manual_scrape') }}">
        <input type="text" name="query" value="{{ query }}" />
        <button type="submit">Manual Scrape</button>
      </form>

      <form method="post" action="{{ url_for('send_test_email') }}">
        <button type="submit">Send Test Email</button>
      </form>

      <form method="post" action="{{ url_for('run_full_cycle') }}">
        <input type="hidden" name="query" value="{{ query }}" />
        <button type="submit">Run Full Cycle (Scrape + Notify)</button>
      </form>

      <form method="post" action="{{ url_for('run_smoke_test') }}">
        <input type="hidden" name="query" value="{{ query }}" />
        <button type="submit">Run Selector Smoke Test</button>
      </form>

      <form method="post" action="{{ url_for('run_preflight') }}">
        <button type="submit">Run Preflight</button>
      </form>

      <form method="post" action="{{ url_for('run_self_test') }}">
        <input type="hidden" name="query" value="{{ query }}" />
        <button type="submit">Run E2E Self-Test</button>
      </form>

      <form method="post" action="{{ url_for('run_maintenance') }}">
        <button type="submit">Run Maintenance</button>
      </form>
    </div>

    <div class="meta">
      <strong>Implemented Platforms:</strong> {{ platforms|join(", ") }}<br>
      <strong>Total Jobs in DB:</strong> {{ total_jobs }}<br>
      <strong>Auto Cycle:</strong> {{ "Enabled" if auto_cycle_enabled else "Disabled" }} (every {{ auto_cycle_minutes }} min)<br>
      <strong>Scheduler State:</strong> {{ auto_cycle_state }}<br>
      <strong>Next Auto Run (UTC):</strong> {{ auto_cycle_next_run_at or "n/a" }}<br>
      <strong>DB Active Cycle:</strong> {{ "Yes" if db_active_cycle else "No" }}
    </div>

    <h2>Latest 20 Jobs</h2>
    <table>
      <thead>
        <tr>
          <th>Platform</th>
          <th>Title</th>
          <th>Company</th>
          <th>Location</th>
          <th>Link</th>
          <th>Notified</th>
          <th>Scraped At</th>
        </tr>
      </thead>
      <tbody>
        {% for job in jobs %}
        <tr>
          <td>{{ job["platform"] }}</td>
          <td>{{ job["title"] }}</td>
          <td>{{ job["company"] }}</td>
          <td>{{ job["location"] }}</td>
          <td><a href="{{ job['url'] }}" target="_blank" rel="noreferrer">Open</a></td>
          <td>{{ "Yes" if job["is_notified"] else "No" }}</td>
          <td>{{ job["scraped_at"] }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>

    <h2 style="margin-top: 24px;">Latest Smoke Test</h2>
    {% if smoke_report %}
    <div class="meta">
      <strong>Started:</strong> {{ smoke_report["started_at"] }}<br>
      <strong>Finished:</strong> {{ smoke_report["finished_at"] }}<br>
      <strong>Summary:</strong>
      pass={{ smoke_report["summary"]["pass"] }},
      warning={{ smoke_report["summary"]["warning"] }},
      fail={{ smoke_report["summary"]["fail"] }}
    </div>
    <table>
      <thead>
        <tr>
          <th>Platform</th>
          <th>Status</th>
          <th>Jobs</th>
          <th>Captcha</th>
          <th>Duration (ms)</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody>
        {% for row in smoke_report["results"] %}
        <tr>
          <td>{{ row["platform"] }}</td>
          <td>{{ row["status"] }}</td>
          <td>{{ row["jobs_count"] }}</td>
          <td>{{ "Yes" if row["captcha_detected"] else "No" }}</td>
          <td>{{ row["duration_ms"] }}</td>
          <td>{{ row["error"] or "" }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="meta">No smoke test report yet.</div>
    {% endif %}

    <h2 style="margin-top: 24px;">Latest Preflight</h2>
    {% if preflight_report %}
    <div class="meta">
      <strong>Started:</strong> {{ preflight_report["started_at"] }}<br>
      <strong>Finished:</strong> {{ preflight_report["finished_at"] }}<br>
      <strong>Overall:</strong> {{ preflight_report["overall_status"] }}<br>
      <strong>Summary:</strong>
      pass={{ preflight_report["summary"]["pass"] }},
      warning={{ preflight_report["summary"]["warning"] }},
      fail={{ preflight_report["summary"]["fail"] }}
    </div>
    <table>
      <thead>
        <tr>
          <th>Check</th>
          <th>Status</th>
          <th>Message</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        {% for row in preflight_report["results"] %}
        <tr>
          <td>{{ row["check"] }}</td>
          <td>{{ row["status"] }}</td>
          <td>{{ row["message"] }}</td>
          <td>{{ row["details"] }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="meta">No preflight report yet.</div>
    {% endif %}

    <h2 style="margin-top: 24px;">Latest E2E Self-Test</h2>
    {% if self_test_report %}
    <div class="meta">
      <strong>Started:</strong> {{ self_test_report["started_at"] }}<br>
      <strong>Finished:</strong> {{ self_test_report["finished_at"] }}<br>
      <strong>Status:</strong> {{ self_test_report["status"] }}<br>
      <strong>Run ID:</strong> {{ self_test_report["run_id"] or "n/a" }}<br>
      <strong>Platforms:</strong> {{ self_test_report["selected_platforms"]|join(", ") if self_test_report["selected_platforms"] else "n/a" }}<br>
      <strong>Jobs Processed:</strong> {{ self_test_report["jobs_processed"] }}<br>
      <strong>Notified:</strong> {{ self_test_report["notified_count"] }}<br>
      <strong>Error:</strong> {{ self_test_report["error"] or "" }}
    </div>
    {% else %}
    <div class="meta">No self-test report yet.</div>
    {% endif %}

    <h2 style="margin-top: 24px;">Latest Maintenance</h2>
    {% if maintenance_report %}
    <div class="meta">
      <strong>Started:</strong> {{ maintenance_report["started_at"] }}<br>
      <strong>Finished:</strong> {{ maintenance_report["finished_at"] }}<br>
      <strong>Status:</strong> {{ maintenance_report["status"] }}<br>
      <strong>Files Deleted:</strong> {{ maintenance_report["cleanup_summary"]["files_deleted"] }}<br>
      <strong>Bytes Freed:</strong> {{ maintenance_report["cleanup_summary"]["bytes_freed"] }}<br>
      <strong>DB Vacuum:</strong> {{ "Yes" if maintenance_report["db_maintenance"]["vacuum_ran"] else "No" }}
    </div>
    {% else %}
    <div class="meta">No maintenance report yet.</div>
    {% endif %}

    <h2 style="margin-top: 24px;">Recent Email Attempts</h2>
    <table>
      <thead>
        <tr>
          <th>Status</th>
          <th>Job Count</th>
          <th>Recipient</th>
          <th>Subject</th>
          <th>Error</th>
          <th>Created At</th>
        </tr>
      </thead>
      <tbody>
        {% for item in email_attempts %}
        <tr>
          <td>{{ item["status"] }}</td>
          <td>{{ item["job_count"] }}</td>
          <td>{{ item["recipient"] }}</td>
          <td>{{ item["subject"] }}</td>
          <td>{{ item["error_message"] or "" }}</td>
          <td>{{ item["created_at"] }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>

    <h2 style="margin-top: 24px;">Recent Full-Cycle Runs</h2>
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Mode</th>
          <th>Query</th>
          <th>Status</th>
          <th>Run ID</th>
          <th>Jobs Processed</th>
          <th>Notified</th>
          <th>Error</th>
          <th>Started At</th>
          <th>Ended At</th>
        </tr>
      </thead>
      <tbody>
        {% for cycle in cycle_runs %}
        <tr>
          <td>{{ cycle["cycle_id"] }}</td>
          <td>{{ cycle["mode"] }}</td>
          <td>{{ cycle["query"] }}</td>
          <td>{{ cycle["status"] }}</td>
          <td>{{ cycle["run_id"] or "" }}</td>
          <td>{{ cycle["jobs_processed"] }}</td>
          <td>{{ cycle["notified_count"] }}</td>
          <td>{{ cycle["error_message"] or "" }}</td>
          <td>{{ cycle["started_at"] }}</td>
          <td>{{ cycle["ended_at"] or "" }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </body>
</html>
"""

_CYCLE_LOCK = threading.Lock()
_SCHEDULER_START_LOCK = threading.Lock()


def _implemented_platforms() -> list[str]:
    support = list_platform_support()
    return [item["platform"] for item in support if item["implemented"]]


def _run_manual_scrape(query: str) -> tuple[int, str]:
    db.init_db()
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
    db.init_db()
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
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "job-aggregator-secret")

    _start_auto_cycle_scheduler(app)

    @app.get("/")
    @require_auth
    def dashboard():
        db.init_db()
        jobs = [dict(row) for row in db.list_latest_jobs(limit=20)]
        email_attempts = [dict(row) for row in db.list_email_notifications(limit=20)]
        cycle_runs = [dict(row) for row in db.list_cycle_runs(limit=20)]
        smoke_report = load_latest_smoke_report()
        preflight_report = load_latest_preflight_report()
        self_test_report = load_latest_self_test_report()
        maintenance_report = load_latest_maintenance_report()
        total_jobs = db.count_jobs()
        message = request.args.get("message", "")
        query = request.args.get("query", "AI/ML Engineer")
        return render_template_string(
            DASHBOARD_HTML,
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
            platforms=_implemented_platforms(),
            auto_cycle_enabled=_env_bool("AUTO_CYCLE_ENABLED", False),
            auto_cycle_minutes=_auto_cycle_minutes(),
            auto_cycle_state=app.config.get("AUTO_CYCLE_STATE", "unknown"),
            auto_cycle_next_run_at=app.config.get("AUTO_CYCLE_NEXT_RUN_AT", ""),
            db_active_cycle=db.has_active_cycle_run(),
        )

    @app.get("/healthz")
    def healthz():
        db.init_db()
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
