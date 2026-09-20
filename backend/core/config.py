"""Environment-driven configuration. No secrets live in the repository."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

__all__ = ["Settings", "get_settings", "load_env"]

_TRUE = {"1", "true", "yes", "on"}
_DEFAULT_CORS = ("http://localhost:3000", "http://localhost:5173")


def load_env() -> None:
    """Load a local ``.env`` when python-dotenv is installed. Real env wins."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional dependency
        return
    load_dotenv(override=False)


def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or "").strip() or default


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE


def _int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name) or default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name) or default))
    except (TypeError, ValueError):
        return default


def _fallbacks(raw: str) -> tuple[tuple[str | None, str, str], ...]:
    """``base_url|model|api_key`` entries separated by ``;``. A local server needs any non-empty key."""
    entries = []
    for chunk in raw.split(";"):
        parts = [part.strip() for part in chunk.split("|")]
        if len(parts) == 3 and parts[1] and parts[2]:
            entries.append((parts[0] or None, parts[1], parts[2]))
    return tuple(entries)


@dataclass(frozen=True)
class Settings:
    """Everything the service reads from the environment."""

    app_name: str = "Coding-agent session analyzer"
    version: str = "1.0.0"
    log_level: str = "INFO"

    # LLM provider
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    llm_concurrency: int = 4
    # Mock output must never be passed off as a real answer, so this is off.
    llm_fallback_to_mock: bool = False
    llm_max_issues: int = 5
    llm_context_radius: int = 2

    # API
    max_upload_bytes: int = 50 * 1024 * 1024
    max_steps_in_response: int = 3000
    cors_origins: tuple[str, ...] = field(default_factory=lambda: _DEFAULT_CORS)

    # (base_url, model, api_key) endpoints tried after every LLM_API_KEY failed.
    llm_fallbacks: tuple[tuple[str | None, str, str], ...] = ()

    @property
    def llm_api_keys(self) -> tuple[str, ...]:
        """LLM_API_KEY may hold several comma-separated keys for the same endpoint."""
        return tuple(key.strip() for key in (self.llm_api_key or "").split(",") if key.strip())

    @property
    def has_api_key(self) -> bool:
        return bool(self.llm_api_key and self.llm_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env()
    origins = _str("CORS_ORIGINS")
    return Settings(
        log_level=_str("LOG_LEVEL", "INFO").upper(),
        llm_api_key=_str("LLM_API_KEY") or None,
        llm_base_url=_str("LLM_BASE_URL") or None,
        llm_model=_str("LLM_MODEL", "gpt-4o-mini"),
        llm_timeout_seconds=_float("LLM_TIMEOUT_SECONDS", 60.0, 1.0),
        llm_concurrency=_int("LLM_CONCURRENCY", 4, 1),
        llm_fallback_to_mock=_flag("LLM_FALLBACK_TO_MOCK", False),
        llm_max_issues=_int("LLM_MAX_ISSUES", 5, 0),
        llm_context_radius=_int("LLM_CONTEXT_RADIUS", 2, 0),
        max_upload_bytes=_int("MAX_UPLOAD_BYTES", 50 * 1024 * 1024, 1024),
        max_steps_in_response=_int("MAX_STEPS_IN_RESPONSE", 3000, 1),
        llm_fallbacks=_fallbacks(_str("LLM_FALLBACKS")),
        cors_origins=tuple(part.strip() for part in origins.split(",") if part.strip()) or _DEFAULT_CORS,
    )
