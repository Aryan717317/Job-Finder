from __future__ import annotations

import argparse
import json

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    def load_dotenv(*_args, **_kwargs):
        return False

from services.scraper.app.preflight import run_and_save_preflight


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scraper preflight diagnostics.")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    load_dotenv("services/scraper/.env", override=False)
    args = _parse_args()
    try:
        report, path = run_and_save_preflight(timeout_seconds=max(1.0, float(args.timeout_seconds)))
        print(json.dumps({"report": report, "path": str(path)}, ensure_ascii=False))
        return 0 if report.get("overall_status") in {"pass", "warning"} else 1
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
