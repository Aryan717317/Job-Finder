from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Platform(str, Enum):
    naukri = "naukri"
    linkedin = "linkedin"
    cutshort = "cutshort"
    hirist = "hirist"
    foundit = "foundit"
    hirect = "hirect"
    internshala = "internshala"
    indeed = "indeed"
    wellfound = "wellfound"
    remote_co = "remote_co"
    flexjobs = "flexjobs"
    arc_dev = "arc_dev"
    we_work_remotely = "we_work_remotely"
    remotive = "remotive"
    working_nomads = "working_nomads"
    relocate_me = "relocate_me"


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class CreateRunRequest(BaseModel):
    query: str = Field(default="AI/ML Engineer", min_length=2, max_length=120)
    platforms: list[Platform] = Field(
        default_factory=lambda: [
            Platform.cutshort,
            Platform.wellfound,
        ]
    )
    headless: bool = True


class RunResponse(BaseModel):
    run_id: str
    status: RunStatus
    query: str
    platforms: list[Platform]
    created_at: datetime


class RunListItem(BaseModel):
    run_id: str
    status: RunStatus
    query: str
    platforms: list[Platform]
    jobs_collected: int
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None


class RunDetail(BaseModel):
    run_id: str
    status: RunStatus
    query: str
    platforms: list[Platform]
    jobs_collected: int
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_message: str | None = None


class JobOut(BaseModel):
    external_id: str
    run_id: str
    platform: Platform
    title: str
    company: str
    location: str
    url: str
    posted_at: str | None = None
    employment_type: str = ""
    salary_text: str = ""
    experience_text: str = ""
    tags: list[str] = Field(default_factory=list)
    category_tags: list[str] = Field(default_factory=list)
    is_fresher: bool = False
    role_type: str = "ML"
    semantic_score: float


class RunEventOut(BaseModel):
    event_id: int
    run_id: str
    event_type: str
    message: str
    payload: dict[str, Any] | None = None
    created_at: datetime


class PlatformSupportOut(BaseModel):
    platform: Platform
    implemented: bool
