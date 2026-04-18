from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "dev")
    backend_host: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))
    allowed_origins: list[str] = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    ).split(",")
    allowed_origin_regex: str | None = os.getenv(
        "ALLOWED_ORIGIN_REGEX",
        r"http://(localhost|127\.0\.0\.1):517[3-9]",
    )
    model_provider: str = os.getenv("MODEL_PROVIDER", "heuristic")
    model_base_url: str = os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1")
    model_api_key: str = os.getenv("MODEL_API_KEY", "")
    model_name: str = os.getenv("MODEL_NAME", "gpt-4o-mini")
    model_timeout_sec: float = Field(default=float(os.getenv("MODEL_TIMEOUT_SEC", "8")))
    model_max_retries: int = Field(default=int(os.getenv("MODEL_MAX_RETRIES", "2")))


@lru_cache
def get_settings() -> Settings:
    return Settings()
