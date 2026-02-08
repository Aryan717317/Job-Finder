from __future__ import annotations

import json
import os

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    def load_dotenv(*_args, **_kwargs):
        return False

from cycle_runner import _configure_logging, _implemented_platforms, _run_cycle, _validate_platforms


DEFAULT_SEARCH_QUERIES = [
    "ML Engineer",
    "Prompt Engineer",
    "LLM Specialist",
    "Generative AI",
]


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


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        token = item.strip()
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(token)
    return result


def _query_list_from_env() -> list[str]:
    explicit_list = _list_env("JOB_QUERY_LIST")
    if explicit_list:
        return _dedupe(explicit_list)

    single_query = (os.getenv("JOB_QUERY", "").strip() or "")
    if single_query:
        return _dedupe([single_query])

    return list(DEFAULT_SEARCH_QUERIES)


def main() -> int:
    load_dotenv("services/scraper/.env", override=False)
    logger = _configure_logging()

    try:
        implemented = _implemented_platforms()
        platforms = _validate_platforms(_list_env("JOB_PLATFORMS"), implemented)
        query_list = _query_list_from_env()
        send_email = _bool_env("SEND_EMAIL", True)
        # Explicit CI policy: always headless in GitHub automation.
        headless = True

        run_summaries: list[dict] = []
        final_exit_code = 0
        total_jobs_processed = 0
        total_notified = 0

        for index, query in enumerate(query_list):
            run_send_email = send_email and index == (len(query_list) - 1)
            exit_code, summary = _run_cycle(
                logger=logger,
                query=query,
                platforms=platforms,
                headless=headless,
                send_email=run_send_email,
                mode="github_actions",
            )
            run_summaries.append(summary)
            total_jobs_processed += int(summary.get("jobs_processed", 0) or 0)
            total_notified += int(summary.get("notified_count", 0) or 0)

            if exit_code == 1:
                final_exit_code = 1
            elif exit_code != 0 and final_exit_code == 0:
                final_exit_code = exit_code

        print(
            json.dumps(
                {
                    "status": "completed" if final_exit_code == 0 else "failed",
                    "queries": query_list,
                    "runs": run_summaries,
                    "jobs_processed_total": total_jobs_processed,
                    "notified_total": total_notified,
                    "exit_code": final_exit_code,
                },
                ensure_ascii=False,
            )
        )
        return final_exit_code
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
