from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib


@dataclass(slots=True)
class JobRecord:
    run_id: str
    platform: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    posted_at: str | None = None
    employment_type: str = ""
    salary_text: str = ""
    experience_text: str = ""
    tags: list[str] | None = None
    semantic_score: float = 0.0
    scraped_at: str = datetime.now(timezone.utc).isoformat()

    @property
    def external_id(self) -> str:
        payload = f"{self.platform}:{self.url}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:24]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["external_id"] = self.external_id
        data["tags"] = data.get("tags") or []
        return data
