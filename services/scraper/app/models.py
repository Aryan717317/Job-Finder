from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import hashlib
import re


_FRESHER_PATTERNS = (
    re.compile(r"\b0\s*(?:-|/|to)\s*1\s*(?:yr|yrs|year|years)\b", re.IGNORECASE),
    re.compile(r"\b(?:entry[\s-]*level|fresher|freshers)\b", re.IGNORECASE),
    re.compile(r"\b20(?:24|25|26)\s*batch\b", re.IGNORECASE),
    re.compile(r"\b(?:2024|2025|2026)(?:\s*[/,-]\s*(?:2024|2025|2026)){1,2}\s*batch\b", re.IGNORECASE),
)
_PROMPT_PATTERNS = (
    re.compile(r"\bprompt\s+(?:engineering|engineer|design|writing)\b", re.IGNORECASE),
    re.compile(r"\bllm\s+prompt", re.IGNORECASE),
)
_GENAI_PATTERNS = (
    re.compile(r"\bgenerative\s+ai\b", re.IGNORECASE),
    re.compile(r"\bgenai\b", re.IGNORECASE),
    re.compile(r"\blarge\s+language\s+model\b", re.IGNORECASE),
    re.compile(r"\bllm\b", re.IGNORECASE),
)


def _normalize_unique(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in values or []:
        text = str(item).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def infer_category_tags(title: str, description: str, experience_text: str, raw_tags: list[str] | None = None) -> list[str]:
    text = " ".join(
        part.strip()
        for part in (title, description, experience_text, " ".join(raw_tags or []))
        if part and part.strip()
    )
    if not text:
        return []

    labels: list[str] = []
    if any(pattern.search(text) for pattern in _FRESHER_PATTERNS):
        labels.append("Fresher")
    if any(pattern.search(text) for pattern in _PROMPT_PATTERNS):
        labels.append("Prompt Engineering")
    if any(pattern.search(text) for pattern in _GENAI_PATTERNS):
        labels.append("Generative AI")
    return labels


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    category_tags: list[str] | None = None
    semantic_score: float = 0.0
    scraped_at: str = field(default_factory=_now_iso)

    @property
    def external_id(self) -> str:
        payload = f"{self.platform}:{self.url}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:24]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["external_id"] = self.external_id
        data["tags"] = _normalize_unique(data.get("tags"))
        derived_category_tags = infer_category_tags(
            title=data.get("title", ""),
            description=data.get("description", ""),
            experience_text=data.get("experience_text", ""),
            raw_tags=data["tags"],
        )
        data["category_tags"] = _normalize_unique((data.get("category_tags") or []) + derived_category_tags)
        return data
