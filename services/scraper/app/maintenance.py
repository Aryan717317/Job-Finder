from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import settings
from .db import DB_PATH


@dataclass(slots=True)
class CleanupStats:
    files_deleted: int = 0
    bytes_freed: int = 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report_dir() -> Path:
    path = settings.data_dir / "maintenance_reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _delete_old_files(path: Path, cutoff: datetime) -> CleanupStats:
    stats = CleanupStats()
    if not path.exists() or not path.is_dir():
        return stats

    for item in path.iterdir():
        if not item.is_file():
            continue
        if item.name.lower() == "latest.json":
            continue

        modified = datetime.fromtimestamp(item.stat().st_mtime, timezone.utc)
        if modified >= cutoff:
            continue

        size = item.stat().st_size
        item.unlink(missing_ok=True)
        stats.files_deleted += 1
        stats.bytes_freed += size

    return stats


def _vacuum_db() -> dict:
    before = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("VACUUM")
    after = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    return {
        "before_bytes": before,
        "after_bytes": after,
        "bytes_reclaimed": max(0, before - after),
    }


def run_maintenance(report_retention_days: int = 30, log_retention_days: int = 14, vacuum: bool = True) -> dict:
    started_at = _now_iso()
    now = datetime.now(timezone.utc)
    report_cutoff = now - timedelta(days=max(1, int(report_retention_days)))
    log_cutoff = now - timedelta(days=max(1, int(log_retention_days)))

    report_dirs = [
        settings.data_dir / "smoke_reports",
        settings.data_dir / "preflight_reports",
        settings.data_dir / "self_test_reports",
        settings.data_dir / "readiness_reports",
        settings.data_dir / "maintenance_reports",
    ]
    log_dirs = [
        settings.data_dir / "logs",
    ]

    deleted = CleanupStats()
    cleanup_details: list[dict] = []

    for folder in report_dirs:
        stats = _delete_old_files(folder, report_cutoff)
        deleted.files_deleted += stats.files_deleted
        deleted.bytes_freed += stats.bytes_freed
        cleanup_details.append(
            {
                "path": str(folder),
                "category": "reports",
                "files_deleted": stats.files_deleted,
                "bytes_freed": stats.bytes_freed,
            }
        )

    for folder in log_dirs:
        stats = _delete_old_files(folder, log_cutoff)
        deleted.files_deleted += stats.files_deleted
        deleted.bytes_freed += stats.bytes_freed
        cleanup_details.append(
            {
                "path": str(folder),
                "category": "logs",
                "files_deleted": stats.files_deleted,
                "bytes_freed": stats.bytes_freed,
            }
        )

    db_maintenance = {"vacuum_ran": False}
    if vacuum and DB_PATH.exists():
        db_maintenance = {"vacuum_ran": True, **_vacuum_db()}

    return {
        "started_at": started_at,
        "finished_at": _now_iso(),
        "status": "completed",
        "retention": {
            "report_retention_days": max(1, int(report_retention_days)),
            "log_retention_days": max(1, int(log_retention_days)),
        },
        "cleanup_summary": asdict(deleted),
        "cleanup_details": cleanup_details,
        "db_maintenance": db_maintenance,
    }


def run_and_save_maintenance(
    report_retention_days: int = 30,
    log_retention_days: int = 14,
    vacuum: bool = True,
) -> tuple[dict, Path]:
    report = run_maintenance(
        report_retention_days=report_retention_days,
        log_retention_days=log_retention_days,
        vacuum=vacuum,
    )
    out_dir = _report_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stamped_path = out_dir / f"{stamp}.json"
    latest_path = out_dir / "latest.json"
    text = json.dumps(report, indent=2, ensure_ascii=False)
    stamped_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return report, latest_path


def load_latest_maintenance_report() -> dict | None:
    path = _report_dir() / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
