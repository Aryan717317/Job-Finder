from __future__ import annotations

import argparse
import json
import sys

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    def load_dotenv(*_args, **_kwargs):
        return False

from services.scraper.app.self_test import run_and_save_self_test


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an end-to-end preflight + scrape self-test.")
    parser.add_argument("--query", default="AI/ML Engineer")
    parser.add_argument("--platform", action="append", dest="platforms", default=None)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--send-email", action="store_true")
    parser.add_argument("--allow-preflight-fail", action="store_true")
    parser.add_argument("--preflight-timeout-seconds", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    load_dotenv("services/scraper/.env", override=False)
    args = _parse_args()
    try:
        report, path = run_and_save_self_test(
            query=(args.query or "AI/ML Engineer").strip() or "AI/ML Engineer",
            platforms=args.platforms,
            headless=not args.headful,
            send_email=args.send_email,
            preflight_timeout_seconds=max(1.0, args.preflight_timeout_seconds),
            stop_on_preflight_fail=not args.allow_preflight_fail,
        )
        print(json.dumps({"report": report, "path": str(path)}, ensure_ascii=False))
        status = report.get("status")
        return 0 if status in {"completed", "skipped_preflight_fail", "skipped_busy"} else 1
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
