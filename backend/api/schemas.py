"""HTTP contract.

The analyze response is ``SessionReport`` from the pipeline itself - one schema
for pipeline, API, CLI and frontend, so they cannot drift apart.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.llm import IssueExplanation
from backend.services.report import FindingOut, SessionReport, StepOut, SummaryOut

__all__ = [
    "SessionReport", "SummaryOut", "FindingOut", "StepOut",
    "HealthResponse", "AgentsMdRequest", "AgentsMdResponse", "ErrorResponse",
]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.0.0"
    llm_configured: bool = False
    provider: str = "mock"
    model: str = ""
    fallback_to_mock: bool = False


class AgentsMdRequest(BaseModel):
    explanations: list[IssueExplanation] = Field(default_factory=list)


class AgentsMdResponse(BaseModel):
    agents_md: str


class ErrorResponse(BaseModel):
    detail: str
