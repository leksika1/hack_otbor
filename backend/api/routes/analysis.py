"""Session analysis endpoints."""

from __future__ import annotations

import logging
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from backend.api.schemas import AgentsMdRequest, AgentsMdResponse, SessionReport
from backend.core.config import Settings, get_settings
from backend.llm import LLMService, generate_agents_md
from backend.parser import LOG_FORMATS
from backend.services import analyze_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analysis"])

_CHUNK = 1024 * 1024


@router.post("/analyze", response_model=SessionReport, summary="Analyze a session log")
async def analyze(
    file: UploadFile = File(..., description="Coding-agent session log in JSONL format"),
    log_format: str = Query("auto", description=f"One of {', '.join(LOG_FORMATS)}"),
    max_issues: int | None = Query(None, ge=0, le=50, description="How many issues go to the LLM"),
    explain: bool = Query(True, description="Set to false for a deterministic-only report"),
    settings: Settings = Depends(get_settings),
) -> SessionReport:
    if log_format not in LOG_FORMATS:
        raise HTTPException(status_code=400, detail=f"log_format must be one of {', '.join(LOG_FORMATS)}")

    payload = await _read_upload(file, settings.max_upload_bytes)
    # The uploaded name is echoed back only as a label - never used as a path.
    name = PurePath(file.filename or "session.jsonl").name
    logger.info("upload accepted: %s (%s bytes)", name, len(payload))

    report = await analyze_session(
        payload,
        file_name=name,
        log_format=log_format,
        service=LLMService(),
        settings=settings,
        max_issues=0 if not explain else max_issues,
    )

    if report.summary.steps and report.summary.steps == report.summary.invalid_lines:
        raise HTTPException(status_code=422, detail="No valid JSON lines found - is this a JSONL session log?")
    if not report.summary.steps:
        raise HTTPException(
            status_code=422,
            detail="No session steps could be read from this file. Expected a Codex or Claude Code JSONL log.",
        )
    logger.info(
        "analysis complete: %s steps, %s findings, %s explanations, provider=%s",
        report.summary.steps, report.summary.issues_total, report.summary.issues_explained, report.provider,
    )
    return report


@router.post("/agents-md", response_model=AgentsMdResponse, summary="Render AGENTS.md rules")
async def agents_md(request: AgentsMdRequest) -> AgentsMdResponse:
    return AgentsMdResponse(agents_md=generate_agents_md(request.explanations))


async def _read_upload(file: UploadFile, limit: int) -> bytes:
    """Read an upload in chunks, refusing anything above the configured limit."""
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await file.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise HTTPException(
                    status_code=413,
                    detail=f"File is larger than the {limit} byte limit.",
                )
            chunks.append(chunk)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - a broken upload is a client error
        logger.warning("upload could not be read: %s", exc)
        raise HTTPException(status_code=400, detail="The upload could not be read.") from exc

    payload = b"".join(chunks)
    if not payload.strip():
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    return payload
