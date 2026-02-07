from __future__ import annotations

import json
import os

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    def load_dotenv(*_args, **_kwargs):
        return False

from cycle_runner import _configure_logging, _implemented_platforms, _run_cycle, _validate_platforms


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _list_env(name: str) -> list[str] | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    load_dotenv("services/scraper/.env", override=False)
    logger = _configure_logging()

    try:
        implemented = _implemented_platforms()
        platforms = _validate_platforms(_list_env("JOB_PLATFORMS"), implemented)
        query = (os.getenv("JOB_QUERY", "ML Engineer").strip() or "ML Engineer")
        send_email = _bool_env("SEND_EMAIL", True)
        # Explicit CI policy: always headless in GitHub automation.
        headless = True

        exit_code, summary = _run_cycle(
            logger=logger,
            query=query,
            platforms=platforms,
            headless=headless,
            send_email=send_email,
            mode="github_actions",
        )
        print(json.dumps(summary, ensure_ascii=False))
        return exit_code
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
