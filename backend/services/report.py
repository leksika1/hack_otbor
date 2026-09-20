"""The report produced by the pipeline.

This is also the API response contract: one schema, used by the HTTP layer, the
CLI and the frontend, so the three cannot drift apart.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.llm import IssueExplanation
from backend.llm.artifacts import Artifact

__all__ = ["SummaryOut", "FindingOut", "StepOut", "SessionReport"]


class SummaryOut(BaseModel):
    file_name: str = ""
    log_format: str = "unknown"
    steps: int = 0
    tokens: int = 0
    cost: float = 0.0
    # True when cost was priced from token usage rather than read from the log.
    cost_estimated: bool = False
    duration_seconds: float = 0.0
    tool_calls: int = 0
    tool_errors: int = 0
    user_messages: int = 0
    issues_total: int = 0
    issues_explained: int = 0
    invalid_lines: int = 0
    ignored_lines: int = 0
    parse_warnings: int = 0


class FindingOut(BaseModel):
    """A deterministic finding. Always points at real step ids."""

    type: str
    severity: str
    steps: list[int] = Field(default_factory=list)
    message: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class StepOut(BaseModel):
    """A normalized step, trimmed for transport."""

    id: int
    line: int = 0
    timestamp: str | None = None
    event_type: str = "unknown"
    actor: str = "unknown"
    tool_name: str | None = None
    status: str = "unknown"
    text: str | None = None
    tokens: int = 0
    cost: float = 0.0
    details: str = ""
    issue_types: list[str] = Field(default_factory=list)


class SessionReport(BaseModel):
    """Everything the UI needs for one uploaded session."""

    summary: SummaryOut = Field(default_factory=SummaryOut)
    findings: list[FindingOut] = Field(default_factory=list)
    explanations: list[IssueExplanation] = Field(default_factory=list)
    steps: list[StepOut] = Field(default_factory=list)
    steps_truncated: bool = False
    agents_md: str = ""
    # Ready-to-use files: CLAUDE.md block, skill drafts, next-session checklist.
    artifacts: list[Artifact] = Field(default_factory=list)
    provider: str = "mock"
    # Model that actually answered (after any key/endpoint failover).
    llm_model: str = ""
    provider_is_mock: bool = True
    warnings: list[str] = Field(default_factory=list)
