from __future__ import annotations

import argparse
import json

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    def load_dotenv(*_args, **_kwargs):
        return False

from services.scraper.app.maintenance import run_and_save_maintenance


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run maintenance cleanup and optional SQLite vacuum.")
    parser.add_argument("--report-retention-days", type=int, default=30)
    parser.add_argument("--log-retention-days", type=int, default=14)
    parser.add_argument("--skip-vacuum", action="store_true")
    return parser.parse_args()


def main() -> int:
    load_dotenv("services/scraper/.env", override=False)
    args = _parse_args()
    try:
        report, path = run_and_save_maintenance(
            report_retention_days=max(1, int(args.report_retention_days)),
            log_retention_days=max(1, int(args.log_retention_days)),
            vacuum=not args.skip_vacuum,
        )
        print(json.dumps({"report": report, "path": str(path)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
