"""Liveness endpoint. Also reports which LLM provider is configured."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.schemas import HealthResponse
from backend.core.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health")
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.version,
        llm_configured=settings.has_api_key,
        provider="openai-compatible" if settings.has_api_key else "mock",
        model=settings.llm_model,
        fallback_to_mock=settings.llm_fallback_to_mock,
    )
