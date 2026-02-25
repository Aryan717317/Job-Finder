from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import uuid

from .config import settings


def _db_path_from_url(url: str) -> Path:
    if not url.startswith("sqlite:///"):
        raise ValueError("Only sqlite URLs are supported in the initial scaffold")
    return Path(url.replace("sqlite:///", "", 1))


DB_PATH = _db_path_from_url(settings.database_url)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_DB_INITIALIZED = False


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl_type: str, default_sql: str | None = None) -> None:
    if _column_exists(conn, table, column):
        return
    if default_sql is None:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    else:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type} DEFAULT {default_sql}")


def _table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if not row or not row["sql"]:
        return ""
    return str(row["sql"])


def _migrate_applications_table(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "applications").lower()
    if not sql:
        return

    # Upgrade legacy schema to include "Not Applied" and applied_at.
    if "not applied" in sql and "applied_at" in sql:
        return

    conn.execute("ALTER TABLE applications RENAME TO applications_legacy")
    conn.execute(
        """
        CREATE TABLE applications (
            application_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Not Applied'
                CHECK (status IN ('Not Applied', 'Applied', 'Interviewing', 'Rejected', 'Offer')),
            applied_at TEXT,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(job_id),
            FOREIGN KEY (job_id) REFERENCES jobs(external_id)
        )
        """
    )

    has_applied_at = _column_exists(conn, "applications_legacy", "applied_at")
    has_applied_date = _column_exists(conn, "applications_legacy", "applied_date")
    has_created_at = _column_exists(conn, "applications_legacy", "created_at")
    has_updated_at = _column_exists(conn, "applications_legacy", "updated_at")

    if has_applied_at and has_applied_date:
        source_applied_expr = "COALESCE(applied_at, applied_date)"
    elif has_applied_at:
        source_applied_expr = "applied_at"
    elif has_applied_date:
        source_applied_expr = "applied_date"
    else:
        source_applied_expr = "NULL"

    created_expr = "created_at" if has_created_at else "NULL"
    updated_expr = "updated_at" if has_updated_at else "NULL"
    order_expr_parts = [source_applied_expr]
    if has_created_at:
        order_expr_parts.append("created_at")
    if has_updated_at:
        order_expr_parts.append("updated_at")
    order_expr = ", ".join(order_expr_parts + ["'1970-01-01T00:00:00+00:00'"])

    conn.execute(
        f"""
        INSERT OR REPLACE INTO applications (job_id, status, applied_at, notes, created_at, updated_at)
        SELECT
            job_id,
            CASE
                WHEN status IN ('Not Applied', 'Applied', 'Interviewing', 'Rejected', 'Offer') THEN status
                ELSE 'Not Applied'
            END AS status,
            {source_applied_expr} AS applied_at,
            COALESCE(notes, '') AS notes,
            COALESCE({created_expr}, '{_now_iso()}') AS created_at,
            COALESCE({updated_expr}, '{_now_iso()}') AS updated_at
        FROM applications_legacy
        WHERE job_id IS NOT NULL AND TRIM(job_id) <> ''
        ORDER BY COALESCE({order_expr}) ASC
        """
    )
    conn.execute("DROP TABLE applications_legacy")


def init_db() -> None:
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scrape_runs (
                run_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                query TEXT NOT NULL,
                platforms TEXT NOT NULL,
                headless INTEGER NOT NULL DEFAULT 1,
                jobs_collected INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                external_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT NOT NULL,
                posted_at TEXT,
                employment_type TEXT NOT NULL DEFAULT '',
                salary_text TEXT NOT NULL DEFAULT '',
                experience_text TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                category_tags_json TEXT NOT NULL DEFAULT '[]',
                is_fresher INTEGER NOT NULL DEFAULT 0,
                role_type TEXT NOT NULL DEFAULT 'ML',
                is_notified INTEGER NOT NULL DEFAULT 0,
                semantic_score REAL NOT NULL,
                scraped_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES scrape_runs(run_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                application_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Not Applied'
                    CHECK (status IN ('Not Applied', 'Applied', 'Interviewing', 'Rejected', 'Offer')),
                applied_at TEXT,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(job_id),
                FOREIGN KEY (job_id) REFERENCES jobs(external_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES scrape_runs(run_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_notifications (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                job_count INTEGER NOT NULL DEFAULT 0,
                recipient TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                error_message TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cycle_runs (
                cycle_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                query TEXT NOT NULL,
                status TEXT NOT NULL,
                run_id TEXT,
                jobs_processed INTEGER NOT NULL DEFAULT 0,
                notified_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT
            )
            """
        )

        _migrate_applications_table(conn)

        _ensure_column(conn, "scrape_runs", "headless", "INTEGER", "1")
        _ensure_column(conn, "scrape_runs", "started_at", "TEXT")
        _ensure_column(conn, "scrape_runs", "ended_at", "TEXT")
        _ensure_column(conn, "jobs", "posted_at", "TEXT")
        _ensure_column(conn, "jobs", "employment_type", "TEXT", "''")
        _ensure_column(conn, "jobs", "salary_text", "TEXT", "''")
        _ensure_column(conn, "jobs", "experience_text", "TEXT", "''")
        _ensure_column(conn, "jobs", "tags_json", "TEXT", "'[]'")
        _ensure_column(conn, "jobs", "category_tags_json", "TEXT", "'[]'")
        _ensure_column(conn, "jobs", "is_fresher", "INTEGER", "0")
        _ensure_column(conn, "jobs", "role_type", "TEXT", "'ML'")
        _ensure_column(conn, "jobs", "is_notified", "INTEGER", "0")
        _ensure_column(conn, "applications", "applied_at", "TEXT")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs (scraped_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_is_notified ON jobs (is_notified)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_fresher_role ON jobs (is_fresher, role_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_platform ON jobs (platform)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_run_id ON jobs (run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_status_date ON applications (status, applied_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications (job_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events (run_id, event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scrape_runs_created ON scrape_runs (created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cycle_runs_status ON cycle_runs (status, ended_at)")

    _DB_INITIALIZED = True


def create_run(query: str, platforms: list[str], headless: bool) -> str:
    run_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO scrape_runs (
                run_id, status, query, platforms, headless, jobs_collected, error_message, created_at, started_at, ended_at
            )
            VALUES (?, 'queued', ?, ?, ?, 0, NULL, ?, NULL, NULL)
            """,
            (run_id, query, ",".join(platforms), int(headless), _now_iso()),
        )
    return run_id


def add_run_event(run_id: str, event_type: str, message: str, payload: dict | None = None) -> int:
    payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO run_events (run_id, event_type, message, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, event_type, message, payload_json, _now_iso()),
        )
        return int(cur.lastrowid)


def mark_run_started(run_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE scrape_runs
            SET status = 'running',
                started_at = COALESCE(started_at, ?),
                error_message = NULL
            WHERE run_id = ?
            """,
            (_now_iso(), run_id),
        )


def mark_run_completed(run_id: str, jobs_collected: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE scrape_runs
            SET status = 'completed',
                jobs_collected = ?,
                ended_at = ?,
                error_message = NULL
            WHERE run_id = ?
            """,
            (jobs_collected, _now_iso(), run_id),
        )


def mark_run_failed(run_id: str, error_message: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE scrape_runs
            SET status = 'failed',
                ended_at = ?,
                error_message = ?
            WHERE run_id = ?
            """,
            (_now_iso(), error_message, run_id),
        )


def insert_jobs(rows: list[dict]) -> None:
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO jobs (
                external_id, run_id, platform, title, company, location, url, description, posted_at,
                employment_type, salary_text, experience_text, tags_json, category_tags_json,
                is_fresher, role_type, is_notified, semantic_score, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(external_id) DO UPDATE SET
                run_id = excluded.run_id,
                platform = excluded.platform,
                title = excluded.title,
                company = excluded.company,
                location = excluded.location,
                url = excluded.url,
                description = excluded.description,
                posted_at = excluded.posted_at,
                employment_type = excluded.employment_type,
                salary_text = excluded.salary_text,
                experience_text = excluded.experience_text,
                tags_json = excluded.tags_json,
                category_tags_json = excluded.category_tags_json,
                is_fresher = excluded.is_fresher,
                role_type = excluded.role_type,
                semantic_score = excluded.semantic_score,
                scraped_at = excluded.scraped_at,
                is_notified = jobs.is_notified
            """,
            [
                (
                    row["external_id"],
                    row["run_id"],
                    row["platform"],
                    row["title"],
                    row["company"],
                    row["location"],
                    row["url"],
                    row.get("description", ""),
                    row.get("posted_at"),
                    row.get("employment_type", ""),
                    row.get("salary_text", ""),
                    row.get("experience_text", ""),
                    json.dumps(row.get("tags", []), ensure_ascii=False),
                    json.dumps(row.get("category_tags", []), ensure_ascii=False),
                    int(bool(row.get("is_fresher", False))),
                    row.get("role_type", "ML"),
                    int(row.get("is_notified", 0)),
                    row.get("semantic_score", 0.0),
                    row["scraped_at"],
                )
                for row in rows
            ],
        )


def log_email_notification(
    status: str,
    job_count: int,
    recipient: str,
    subject: str,
    error_message: str | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO email_notifications (
                status, job_count, recipient, subject, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (status, max(0, int(job_count)), recipient, subject, error_message, _now_iso()),
        )
        return int(cur.lastrowid)


def list_email_notifications(limit: int = 20) -> list[sqlite3.Row]:
    safe_limit = max(1, min(limit, 500))
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM email_notifications
            ORDER BY notification_id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()


def has_active_cycle_run() -> bool:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT cycle_id
            FROM cycle_runs
            WHERE status = 'running' AND ended_at IS NULL
            ORDER BY cycle_id DESC
            LIMIT 1
            """
        ).fetchone()
        return row is not None


def _expire_stale_cycles(conn: sqlite3.Connection, stale_hours: int = 2) -> int:
    """Auto-expire cycles stuck as 'running' for longer than *stale_hours*."""
    cur = conn.execute(
        """
        UPDATE cycle_runs
        SET status = 'failed',
            error_message = 'Auto-expired: exceeded stale cycle timeout',
            ended_at = ?
        WHERE status = 'running'
          AND ended_at IS NULL
          AND created_at <= datetime('now', ? || ' hours')
        """,
        (_now_iso(), f"-{stale_hours}"),
    )
    return cur.rowcount if cur.rowcount else 0


def create_cycle_run(mode: str, query: str, enforce_singleton: bool = False) -> int | None:
    now = _now_iso()
    with get_conn() as conn:
        if enforce_singleton:
            conn.execute("BEGIN IMMEDIATE")
            _expire_stale_cycles(conn)
            active = conn.execute(
                """
                SELECT cycle_id
                FROM cycle_runs
                WHERE status = 'running' AND ended_at IS NULL
                ORDER BY cycle_id DESC
                LIMIT 1
                """
            ).fetchone()
            if active is not None:
                return None

        cur = conn.execute(
            """
            INSERT INTO cycle_runs (
                mode, query, status, run_id, jobs_processed, notified_count, error_message, created_at, started_at, ended_at
            ) VALUES (?, ?, 'running', NULL, 0, 0, NULL, ?, ?, NULL)
            """,
            (mode, query, now, now),
        )
        return int(cur.lastrowid)


def complete_cycle_run(
    cycle_id: int,
    status: str,
    jobs_processed: int,
    notified_count: int,
    run_id: str | None = None,
    error_message: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE cycle_runs
            SET status = ?,
                run_id = ?,
                jobs_processed = ?,
                notified_count = ?,
                error_message = ?,
                ended_at = ?
            WHERE cycle_id = ?
            """,
            (
                status,
                run_id,
                max(0, int(jobs_processed)),
                max(0, int(notified_count)),
                error_message,
                _now_iso(),
                int(cycle_id),
            ),
        )


def list_cycle_runs(limit: int = 20) -> list[sqlite3.Row]:
    safe_limit = max(1, min(limit, 500))
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM cycle_runs
            ORDER BY cycle_id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()


def get_run(run_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM scrape_runs WHERE run_id = ?", (run_id,)).fetchone()


def list_runs(limit: int = 25) -> list[sqlite3.Row]:
    safe_limit = max(1, min(limit, 100))
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM scrape_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()


def list_jobs_by_run(run_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE run_id = ? ORDER BY semantic_score DESC, scraped_at DESC",
            (run_id,),
        ).fetchall()


def list_latest_jobs(limit: int = 20, offset: int = 0) -> list[sqlite3.Row]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM jobs
            WHERE is_fresher = 1
            ORDER BY scraped_at DESC
            LIMIT ? OFFSET ?
            """,
            (safe_limit, safe_offset),
        ).fetchall()


def count_jobs() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(1) AS cnt FROM jobs WHERE is_fresher = 1").fetchone()
        return int(row["cnt"]) if row else 0


def list_unnotified_jobs(limit: int = 500) -> list[sqlite3.Row]:
    safe_limit = max(1, min(limit, 2000))
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM jobs
            WHERE is_notified = 0 AND is_fresher = 1
            ORDER BY scraped_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()


def mark_jobs_notified(external_ids: list[str]) -> int:
    ids = [item for item in external_ids if item]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE jobs SET is_notified = 1 WHERE external_id IN ({placeholders})",
            tuple(ids),
        )
        return cur.rowcount if cur.rowcount is not None else 0


def list_run_events(run_id: str, since_id: int = 0, limit: int = 200) -> list[sqlite3.Row]:
    safe_limit = max(1, min(limit, 500))
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM run_events
            WHERE run_id = ? AND event_id > ?
            ORDER BY event_id ASC
            LIMIT ?
            """,
            (run_id, since_id, safe_limit),
        ).fetchall()
