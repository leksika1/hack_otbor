"""Environment-driven configuration. No secrets in the repository."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

__all__ = ["Settings", "get_settings", "load_env"]

_TRUE = {"1", "true", "yes", "on"}


def load_env() -> None:
    """Load ``.env`` when python-dotenv is available. Existing vars win."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional dependency
        return
    load_dotenv(override=False)


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    api_key: str | None = None
    base_url: str | None = None
    model: str = "gpt-4o-mini"
    # Mock output must never be passed off as a real LLM answer: off by default.
    fallback_to_mock: bool = False
    max_issues: int = 5
    context_radius: int = 2
    concurrency: int = 4
    max_upload_bytes: int = 25 * 1024 * 1024

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key and self.api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env()
    return Settings(
        api_key=(os.getenv("LLM_API_KEY") or "").strip() or None,
        base_url=(os.getenv("LLM_BASE_URL") or "").strip() or None,
        model=(os.getenv("LLM_MODEL") or "").strip() or "gpt-4o-mini",
        fallback_to_mock=_flag("LLM_FALLBACK_TO_MOCK", False),
        max_issues=max(1, _int("LLM_MAX_ISSUES", 5)),
        context_radius=max(0, _int("LLM_CONTEXT_RADIUS", 2)),
        concurrency=max(1, _int("LLM_CONCURRENCY", 4)),
        max_upload_bytes=max(1024, _int("MAX_UPLOAD_BYTES", 25 * 1024 * 1024)),
    )
