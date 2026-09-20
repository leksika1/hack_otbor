"""FastAPI application.

    uvicorn backend.api:app --reload

Endpoints:
    GET  /health              - liveness + which LLM provider is configured
    POST /analyze             - upload a .jsonl session log, get the full report
    POST /api/analyze         - same report plus the fields frontend/ expects
    POST /generate-agents-md  - turn explanations into an AGENTS.md document
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.dashboard import to_dashboard_payload
from backend.llm import IssueExplanation, LLMService, generate_agents_md
from backend.pipeline import AnalyzeResponse, analyze_session, build_parser

__all__ = ["app"]

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Coding-agent session analyzer",
    version="0.1.0",
    description=(
        "Deterministic analysis of Codex / Claude Code session logs, with an "
        "LLM layer that only explains problems the Python code already found."
    ),
)

# A frontend may be added later by another contributor; keep it simple.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class HealthResponse(BaseModel):
    status: str = "ok"
    llm_configured: bool = False
    provider: str = "mock"
    model: str = ""
    fallback_to_mock: bool = False


class AgentsMdRequest(BaseModel):
    explanations: list[IssueExplanation] = Field(default_factory=list)


class AgentsMdResponse(BaseModel):
    agents_md: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        llm_configured=settings.has_api_key,
        provider="openai-compatible" if settings.has_api_key else "mock",
        model=settings.model,
        fallback_to_mock=settings.fallback_to_mock,
    )


async def _run(file: UploadFile, max_issues: int | None, explain: bool):
    """Read the upload and run the pipeline. Returns (result, parsed steps)."""
    settings = get_settings()
    try:
        payload = await file.read()
    except Exception as exc:  # noqa: BLE001 - upload problems are client errors
        raise HTTPException(status_code=400, detail=f"Could not read the upload: {exc}") from exc

    if not payload or not payload.strip():
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File is larger than the {settings.max_upload_bytes} byte limit.",
        )

    service = LLMService()
    parser = build_parser(payload.count(b"\n") + 1)
    try:
        result = await analyze_session(
            payload,
            service=service,
            parser=parser,
            max_issues=(0 if not explain else max_issues),
        )
    except Exception as exc:  # noqa: BLE001 - never leak a stack trace to the client
        logger.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {type(exc).__name__}") from exc

    if result.summary.steps and result.summary.steps == result.summary.invalid_lines:
        raise HTTPException(
            status_code=422,
            detail="No valid JSON lines found - is this a JSONL session log?",
        )
    return result, parser.steps


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    file: UploadFile = File(..., description="Session log in JSONL format"),
    max_issues: int | None = Query(None, ge=1, le=50, description="How many issues go to the LLM"),
    explain: bool = Query(True, description="Set to false for a deterministic-only report"),
) -> AnalyzeResponse:
    result, _ = await _run(file, max_issues, explain)
    return result


@app.post("/api/analyze")
async def analyze_for_dashboard(
    file: UploadFile = File(..., description="Session log in JSONL format"),
    max_issues: int | None = Query(None, ge=1, le=50),
    explain: bool = Query(True),
) -> dict:
    """Compatibility endpoint for the React dashboard in ``frontend/``.

    Same analysis as ``/analyze``; the response additionally carries the
    camelCase aliases that frontend/src/App.jsx reads.
    """
    result, steps = await _run(file, max_issues, explain)
    return to_dashboard_payload(result, steps, filename=file.filename)


@app.post("/generate-agents-md", response_model=AgentsMdResponse)
async def agents_md(request: AgentsMdRequest) -> AgentsMdResponse:
    return AgentsMdResponse(agents_md=generate_agents_md(request.explanations))
