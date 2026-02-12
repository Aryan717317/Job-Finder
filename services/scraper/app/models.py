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
_SENIOR_EXP_PATTERNS = (
    re.compile(r"\b([2-9]|[1-9]\d+)\s*(?:\+|or\s+more)\s*(?:yr|yrs|year|years)\b", re.IGNORECASE),
    re.compile(r"\b([2-9]|[1-9]\d+)\s*(?:-|/|to)\s*\d+\s*(?:yr|yrs|year|years)\b", re.IGNORECASE),
    re.compile(r"\b(?:minimum|min|at\s+least)\s+([2-9]|[1-9]\d+)\s*(?:yr|yrs|year|years)\b", re.IGNORECASE),
    re.compile(r"\b(?:senior|staff|lead|principal|sr\.?)\s+(?:software|data|ml|ai|machine\s+learning)\b", re.IGNORECASE),
)
_PROMPT_PATTERNS = (
    re.compile(r"\bprompt\s+(?:engineering|engineer|design|writing)\b", re.IGNORECASE),
    re.compile(r"\bllm\s+(?:specialist|engineer|prompt)\b", re.IGNORECASE),
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


def _has_senior_experience(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SENIOR_EXP_PATTERNS)


def scan_fresher_keywords(description: str, experience_text: str, title: str = "") -> bool:
    text = " ".join(part.strip() for part in (title, description, experience_text) if part and part.strip())
    if not text:
        return False
    if _has_senior_experience(text):
        return False
    return any(pattern.search(text) for pattern in _FRESHER_PATTERNS)


def infer_role_type(title: str, description: str, raw_tags: list[str] | None = None) -> str:
    text = " ".join(
        part.strip() for part in (title, description, " ".join(raw_tags or [])) if part and part.strip()
    )
    if not text:
        return "ML"
    if any(pattern.search(text) for pattern in _PROMPT_PATTERNS):
        return "Prompt Engineering"
    if any(pattern.search(text) for pattern in _GENAI_PATTERNS):
        return "Generative AI"
    return "ML"


def infer_category_tags(title: str, description: str, experience_text: str, raw_tags: list[str] | None = None) -> list[str]:
    labels: list[str] = []
    if scan_fresher_keywords(description=description, experience_text=experience_text, title=title):
        labels.append("Fresher")
    role_type = infer_role_type(title=title, description=description, raw_tags=raw_tags)
    if role_type == "Prompt Engineering":
        labels.append(role_type)
    elif role_type == "Generative AI":
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
    is_fresher: bool = False
    role_type: str = "ML"
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
        detected_is_fresher = scan_fresher_keywords(
            description=data.get("description", ""),
            experience_text=data.get("experience_text", ""),
            title=data.get("title", ""),
        )
        detected_role_type = infer_role_type(
            title=data.get("title", ""),
            description=data.get("description", ""),
            raw_tags=data["tags"],
        )
        derived_category_tags = infer_category_tags(
            title=data.get("title", ""),
            description=data.get("description", ""),
            experience_text=data.get("experience_text", ""),
            raw_tags=data["tags"],
        )
        data["category_tags"] = _normalize_unique((data.get("category_tags") or []) + derived_category_tags)
        data["is_fresher"] = bool(data.get("is_fresher", False) or detected_is_fresher)
        data["role_type"] = str(data.get("role_type") or detected_role_type)
        return data
