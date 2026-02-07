from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    app_name: str = "ajh-scraper"
    environment: str = os.getenv("AJH_ENV", "dev")
    database_url: str = os.getenv("AJH_DATABASE_URL", "sqlite:///./data/ajh.db")
    data_dir: Path = Path(os.getenv("AJH_DATA_DIR", "./data"))
    profile_dir: Path = Path(os.getenv("AJH_PROFILE_DIR", "./profiles"))
    default_timeout_ms: int = int(os.getenv("AJH_TIMEOUT_MS", "45000"))
    default_locale: str = os.getenv("AJH_LOCALE", "en-IN")
    default_timezone: str = os.getenv("AJH_TIMEZONE", "Asia/Kolkata")
    max_parallel_runs: int = int(os.getenv("AJH_MAX_PARALLEL_RUNS", "2"))
    max_platform_retries: int = int(os.getenv("AJH_MAX_PLATFORM_RETRIES", "2"))
    retry_backoff_base_seconds: float = float(os.getenv("AJH_RETRY_BACKOFF_BASE_SECONDS", "1.2"))
    retry_backoff_cap_seconds: float = float(os.getenv("AJH_RETRY_BACKOFF_CAP_SECONDS", "12.0"))


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.profile_dir.mkdir(parents=True, exist_ok=True)
