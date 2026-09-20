"""Orchestration: JSONL -> parser -> findings -> issues -> LLM -> report.

This is the only module the API (or a CLI, or a test) needs to call.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, Sequence

from pydantic import BaseModel, Field

from backend.analysis import enrich_issues_with_context, findings_to_issues
from backend.config import get_settings
from backend.llm import IssueExplanation, LLMService, generate_agents_md
from backend.llm.schemas import Issue, severity_rank
from backend.parser import LogStep, SessionParser

__all__ = [
    "build_parser",
    "SessionSummary",
    "FindingOut",
    "AnalyzeResponse",
    "analyze_session",
    "analyze_session_sync",
    "select_top_issues",
]

logger = logging.getLogger(__name__)

# Steps the parser produced for lines it could not read at all.
_BROKEN_STEP_TYPES = {"invalid_json", "unparseable_event"}


class SessionSummary(BaseModel):
    steps: int = 0
    tokens: int = 0
    cost: float = 0.0
    issues_total: int = 0
    issues_explained: int = 0
    parse_warnings: int = 0
    invalid_lines: int = 0


class FindingOut(BaseModel):
    type: str
    severity: str
    steps: list[int] = Field(default_factory=list)
    message: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class AnalyzeResponse(BaseModel):
    summary: SessionSummary
    findings: list[FindingOut] = Field(default_factory=list)
    explanations: list[IssueExplanation] = Field(default_factory=list)
    agents_md: str = ""
    provider: str = "mock"
    provider_is_mock: bool = True
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Input handling
# --------------------------------------------------------------------------- #

def _to_lines(source: Any) -> list[str]:
    """Accept a path, raw bytes/str content, or an iterable of lines."""
    if source is None:
        return []
    if isinstance(source, (bytes, bytearray)):
        return bytes(source).decode("utf-8", "replace").splitlines()
    if isinstance(source, Path):
        try:
            return Path(source).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            raise ValueError(f"could not read log file: {exc}") from exc
    if isinstance(source, str):
        # A short single-line string that exists on disk is treated as a path.
        candidate = Path(source)
        if "\n" not in source and len(source) < 4096:
            try:
                if candidate.is_file():
                    return candidate.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                pass
        return source.splitlines()
    if isinstance(source, Iterable):
        return [str(line) for line in source]
    raise ValueError(f"unsupported log source: {type(source).__name__}")


def build_parser(line_count: int) -> SessionParser:
    """Parser tuned to the session length.

    Token buckets must be small enough that a short session still has several
    of them, otherwise "above the session average" cannot be computed at all.
    """
    return SessionParser(bucket_size=max(5, min(50, line_count // 10)))


# --------------------------------------------------------------------------- #
# Issue selection
# --------------------------------------------------------------------------- #

def select_top_issues(issues: Sequence[Issue], limit: int) -> list[Issue]:
    """Pick the most significant issues for the LLM.

    Near-duplicates (same type and tool) are collapsed into one representative
    carrying an ``occurrences`` counter, so a session with fifty identical loops
    costs one LLM call, not fifty.
    """
    if limit <= 0:
        return []

    grouped: dict[tuple[str, str], Issue] = {}
    counts: dict[tuple[str, str], int] = {}
    for issue in issues:
        evidence = issue.evidence.as_dict()
        key = (issue.type, str(evidence.get("tool") or ""))
        counts[key] = counts.get(key, 0) + 1
        current = grouped.get(key)
        if current is None or severity_rank(issue.severity) < severity_rank(current.severity):
            grouped[key] = issue

    representatives: list[Issue] = []
    for key, issue in grouped.items():
        occurrences = counts[key]
        if occurrences > 1:
            evidence = issue.evidence.as_dict()
            evidence["occurrences"] = occurrences
            issue = issue.model_copy(update={"evidence": type(issue.evidence).model_validate(evidence)})
        representatives.append(issue)

    representatives.sort(key=lambda item: (severity_rank(item.severity), item.steps[:1] or [0]))
    return representatives[:limit]


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #

async def analyze_session(
    source: Any,
    *,
    service: LLMService | None = None,
    max_issues: int | None = None,
    context_radius: int | None = None,
    include_agents_md: bool = True,
    parser: SessionParser | None = None,
) -> AnalyzeResponse:
    """Run the full pipeline on one session log.

    Never raises for bad log content: malformed lines become parse warnings and
    an LLM outage becomes a warning plus an empty ``explanations`` list.
    """
    settings = get_settings()
    max_issues = settings.max_issues if max_issues is None else max_issues
    context_radius = settings.context_radius if context_radius is None else context_radius

    lines = _to_lines(source)
    parser = parser or build_parser(len(lines))
    steps: list[LogStep] = parser.parse_lines(lines)
    metrics = parser.analyze(steps)

    invalid_lines = sum(1 for step in steps if step.event_type in _BROKEN_STEP_TYPES)
    findings = metrics.findings
    warnings: list[str] = list(metrics.parse_warnings[:50])
    if not steps:
        warnings.append("The uploaded log contained no readable JSON lines.")

    issues = findings_to_issues(findings, steps)
    selected = enrich_issues_with_context(
        select_top_issues(issues, max_issues), steps, context_radius
    )

    service = service or LLMService()
    explanations: list[IssueExplanation] = []
    if selected:
        try:
            explanations = await service.explain_issues(selected, sort_by_severity=True)
        except Exception as exc:  # noqa: BLE001 - the report is still useful without the LLM
            logger.exception("LLM stage failed")
            warnings.append(f"LLM stage failed: {type(exc).__name__}: {exc}")
    if selected and not explanations:
        warnings.append(
            "No explanations were produced; the deterministic findings below are unaffected."
        )
    if service.stats.get("mock_fallbacks"):
        warnings.append(
            f"{service.stats['mock_fallbacks']} explanation(s) came from the mock provider "
            "after a real LLM failure."
        )

    return AnalyzeResponse(
        summary=SessionSummary(
            steps=metrics.total_steps,
            tokens=metrics.total_tokens,
            cost=round(metrics.total_cost, 6),
            issues_total=len(findings),
            issues_explained=len(explanations),
            parse_warnings=len(metrics.parse_warnings),
            invalid_lines=invalid_lines,
        ),
        findings=[
            FindingOut(
                type=issue.type,
                severity=issue.severity,
                steps=issue.steps,
                message=str(issue.evidence.as_dict().get("detector_message", "")),
                evidence=issue.evidence.as_dict(),
            )
            for issue in issues
        ],
        explanations=explanations,
        agents_md=generate_agents_md(explanations) if include_agents_md else "",
        provider=service.provider_name,
        provider_is_mock=service.used_mock,
        warnings=warnings,
    )


def analyze_session_sync(source: Any, **kwargs: Any) -> AnalyzeResponse:
    """Blocking helper for scripts and the CLI."""
    import asyncio

    return asyncio.run(analyze_session(source, **kwargs))
