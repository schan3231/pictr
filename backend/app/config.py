"""
Application configuration loaded from environment variables.

Usage:
    from backend.app.config import settings

All secrets (API keys, etc.) must be supplied via environment variables or a
local .env file (git-ignored).  Never hard-code secrets in this file.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # CORS — restrict to specific origins; never use ["*"] in this codebase.
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    log_level: str = "INFO"

    # Placeholder for future image-generation API key.
    # image_api_key: str = ""  # uncomment when needed

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: object) -> object:
        """Accept a comma-separated string from the environment variable."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton (re-read from env on first call)."""
    return Settings()


# Convenience alias used by the rest of the app.
settings = get_settings()
