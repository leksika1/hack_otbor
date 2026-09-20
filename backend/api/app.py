"""FastAPI application factory.

    uvicorn backend.api.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import Settings, get_settings
from backend.core.logging import setup_logging

from .routes import analysis, health

__all__ = ["create_app", "app"]

logger = logging.getLogger(__name__)

DESCRIPTION = """
Post-mortem analysis of Codex / Claude Code sessions.

Python code finds what happened; the LLM only explains why it is inefficient.
Every finding points at concrete step ids from the uploaded log.
""".strip()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=DESCRIPTION,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # The frontend talks to /api/*; the bare paths stay as convenient aliases.
    application.include_router(health.router)
    application.include_router(health.router, prefix="/api")
    application.include_router(analysis.router, prefix="/api")
    application.include_router(analysis.router, include_in_schema=False)

    @application.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError) -> JSONResponse:
        logger.warning("bad request on %s: %s", request.url.path, exc)
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @application.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never leak a stack trace to the client; the log keeps the detail.
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    logger.info("application ready (version=%s, llm_configured=%s)", settings.version, settings.has_api_key)
    return application


app = create_app()
