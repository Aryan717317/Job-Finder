from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from . import db
from .config import settings
from .models import is_cs_ai_ml_role, normalize_fresher_query, scan_fresher_keywords
from .runner import list_platform_support, run_scrape
from .schemas import (
    CreateRunRequest,
    JobOut,
    Platform,
    PlatformSupportOut,
    RunDetail,
    RunEventOut,
    RunListItem,
    RunResponse,
    RunStatus,
)


limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    app.state.run_tasks = {}
    app.state.run_semaphore = asyncio.Semaphore(max(1, settings.max_parallel_runs))
    yield
    # Cleanup: cancel pending tasks on shutdown
    for task in app.state.run_tasks.values():
        task.cancel()


app = FastAPI(title="AJH Scraper Service", version="0.9.0", lifespan=lifespan)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _platforms_from_csv(value: str) -> list[Platform]:
    valid = {platform.value for platform in Platform}
    result: list[Platform] = []
    for token in value.split(","):
        platform = token.strip()
        if platform in valid:
            result.append(Platform(platform))
    return result


def _run_row_to_detail(row) -> RunDetail:
    return RunDetail(
        run_id=row["run_id"],
        status=RunStatus(row["status"]),
        query=row["query"],
        platforms=_platforms_from_csv(row["platforms"]),
        jobs_collected=row["jobs_collected"],
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=_parse_dt(row["started_at"]),
        ended_at=_parse_dt(row["ended_at"]),
        error_message=row["error_message"],
    )


@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request) -> dict:
    return {
        "status": "ok",
        "service": "ajh-scraper",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "max_parallel_runs": settings.max_parallel_runs,
    }


async def _execute_run(run_id: str, query: str, platforms: list[str], headless: bool) -> None:
    try:
        async with app.state.run_semaphore:
            db.mark_run_started(run_id)
            db.add_run_event(
                run_id,
                "run.started",
                "Run execution started",
                {"query": query, "platforms": platforms, "headless": headless},
            )

            def on_event(event_type: str, message: str, payload: dict | None = None) -> None:
                db.add_run_event(run_id, event_type, message, payload)

            jobs = await run_scrape(
                query=query,
                run_id=run_id,
                platforms=platforms,
                headless=headless,
                event_hook=on_event,
            )
            jobs = [
                job for job in jobs
                if is_cs_ai_ml_role(
                    title=getattr(job, "title", "") or "",
                    description=getattr(job, "description", "") or "",
                )
                and scan_fresher_keywords(
                    description=getattr(job, "description", "") or "",
                    experience_text=getattr(job, "experience_text", "") or "",
                    title=getattr(job, "title", "") or "",
                )
            ]
            db.insert_jobs([job.to_dict() for job in jobs])
            db.mark_run_completed(run_id, jobs_collected=len(jobs))
            db.add_run_event(
                run_id,
                "run.completed",
                "Run execution completed",
                {"jobs_collected": len(jobs)},
            )
    except Exception as exc:
        db.mark_run_failed(run_id, str(exc))
        db.add_run_event(run_id, "run.failed", "Run execution failed", {"error": str(exc)})
    finally:
        app.state.run_tasks.pop(run_id, None)


@app.get("/v1/platforms", response_model=list[PlatformSupportOut])
@limiter.limit("30/minute")
async def list_platforms(request: Request) -> list[PlatformSupportOut]:
    support = list_platform_support()
    return [
        PlatformSupportOut(
            platform=Platform(item["platform"]),
            implemented=bool(item["implemented"]),
        )
        for item in support
    ]


@app.post("/v1/runs", response_model=RunResponse)
@limiter.limit("5/minute")
async def create_run(request: Request, payload: CreateRunRequest) -> RunResponse:
    query = normalize_fresher_query(payload.query)
    platforms = [platform.value for platform in payload.platforms]
    run_id = db.create_run(query=query, platforms=platforms, headless=payload.headless)
    db.add_run_event(run_id, "run.queued", "Run added to queue", {"platforms": platforms, "query": query})

    task = asyncio.create_task(
        _execute_run(
            run_id=run_id,
            query=query,
            platforms=platforms,
            headless=payload.headless,
        )
    )
    app.state.run_tasks[run_id] = task

    row = db.get_run(run_id)
    assert row is not None
    return RunResponse(
        run_id=row["run_id"],
        status=RunStatus(row["status"]),
        query=row["query"],
        platforms=_platforms_from_csv(row["platforms"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


@app.get("/v1/runs", response_model=list[RunListItem])
@limiter.limit("30/minute")
async def list_runs(request: Request, limit: int = Query(default=25, ge=1, le=100)) -> list[RunListItem]:
    rows = db.list_runs(limit=limit)
    return [
        RunListItem(
            run_id=row["run_id"],
            status=RunStatus(row["status"]),
            query=row["query"],
            platforms=_platforms_from_csv(row["platforms"]),
            jobs_collected=row["jobs_collected"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=_parse_dt(row["started_at"]),
            ended_at=_parse_dt(row["ended_at"]),
        )
        for row in rows
    ]


@app.get("/v1/runs/{run_id}", response_model=RunDetail)
@limiter.limit("30/minute")
async def get_run(request: Request, run_id: str) -> RunDetail:
    row = db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_row_to_detail(row)


@app.get("/v1/runs/{run_id}/jobs", response_model=list[JobOut])
@limiter.limit("30/minute")
async def get_run_jobs(request: Request, run_id: str) -> list[JobOut]:
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    rows = db.list_jobs_by_run(run_id)
    return [
        JobOut(
            external_id=row["external_id"],
            run_id=row["run_id"],
            platform=Platform(row["platform"]),
            title=row["title"],
            company=row["company"],
            location=row["location"],
            url=row["url"],
            posted_at=row["posted_at"],
            employment_type=row["employment_type"] or "",
            salary_text=row["salary_text"] or "",
            experience_text=row["experience_text"] or "",
            tags=_parse_json_list(row["tags_json"]),
            category_tags=_parse_json_list(row["category_tags_json"]),
            is_fresher=bool(row["is_fresher"]),
            role_type=row["role_type"] or "ML",
            semantic_score=row["semantic_score"],
        )
        for row in rows
    ]


@app.get("/v1/runs/{run_id}/events", response_model=list[RunEventOut])
@limiter.limit("60/minute")
async def get_run_events(
    request: Request,
    run_id: str,
    since_id: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[RunEventOut]:
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    rows = db.list_run_events(run_id=run_id, since_id=since_id, limit=limit)
    events: list[RunEventOut] = []
    for row in rows:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else None
        events.append(
            RunEventOut(
                event_id=row["event_id"],
                run_id=row["run_id"],
                event_type=row["event_type"],
                message=row["message"],
                payload=payload,
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        )
    return events
