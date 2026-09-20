"""The one pipeline. API, CLI and tests all call ``analyze_session``.

    bytes / path / lines
        -> parse            (backend.parser)
        -> analyze          (backend.analysis)
        -> rank + select    (top issues only)
        -> local context    (a few steps around each finding, never the whole log)
        -> LLM explain      (backend.llm)
        -> report           (backend.services.report)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Iterable

from backend.analysis import (
    AnalysisConfig,
    Finding,
    analyze_steps,
    enrich_issues_with_context,
    findings_to_issues,
    select_top_issues,
)
from backend.core.config import Settings, get_settings
from backend.llm import IssueExplanation, LLMService, generate_agents_md
from backend.llm.artifacts import build_artifacts
from backend.parser import ParseResult, SessionParser, Step

from .report import FindingOut, SessionReport, StepOut, SummaryOut

__all__ = ["analyze_session", "analyze_session_sync"]

logger = logging.getLogger(__name__)


async def analyze_session(
    source: Any,
    *,
    file_name: str = "",
    log_format: str = "auto",
    service: LLMService | None = None,
    settings: Settings | None = None,
    max_issues: int | None = None,
    context_radius: int | None = None,
    include_agents_md: bool = True,
) -> SessionReport:
    """Analyze one session log end to end.

    ``source`` may be bytes, text, a path or an iterable of lines. Bad input is
    never fatal: malformed lines become warnings and an LLM outage leaves the
    deterministic part of the report intact.
    """
    settings = settings or get_settings()
    max_issues = settings.llm_max_issues if max_issues is None else max_issues
    context_radius = settings.llm_context_radius if context_radius is None else context_radius

    # Parsing and the detectors are CPU-bound (seconds on a multi-megabyte log);
    # run them in a worker thread so the API keeps answering other requests.
    parsed = await asyncio.to_thread(_parse, source, log_format)
    analysis = await asyncio.to_thread(analyze_steps, parsed.steps, AnalysisConfig())
    warnings = [str(warning) for warning in parsed.warnings[:50]]
    if not parsed.steps:
        warnings.append("No readable JSON lines were found in the uploaded file.")

    issues = findings_to_issues(analysis.findings, parsed.steps)
    selected = enrich_issues_with_context(
        select_top_issues(issues, max_issues), parsed.steps, context_radius
    )

    service = service or LLMService()
    explanations: list[IssueExplanation] = []
    if selected:
        logger.info("sending %s issue(s) to provider %s", len(selected), service.provider_name)
        try:
            explanations = await service.explain_issues(selected, sort_by_severity=True)
        except Exception as exc:  # noqa: BLE001 - the report is still useful without the LLM
            logger.exception("LLM stage failed")
            warnings.append(f"LLM stage failed: {type(exc).__name__}: {exc}")
        failed = int(service.stats.get("failures", 0) or 0)
        reason = f" Reason: {service.last_error}." if getattr(service, "last_error", "") else ""
        if not explanations:
            warnings.append(
                f"No explanations were produced; the deterministic findings are unaffected.{reason}"
            )
        elif failed:
            warnings.append(f"{failed} issue(s) were not explained.{reason}")
    if service.stats.get("mock_fallbacks"):
        warnings.append(
            f"{service.stats['mock_fallbacks']} explanation(s) came from the mock provider "
            "after a real LLM failure."
        )

    return SessionReport(
        summary=_summary(parsed, analysis, explanations, file_name),
        findings=[_finding_out(finding) for finding in analysis.findings],
        explanations=explanations,
        steps=_steps_out(parsed.steps, analysis.findings, settings.max_steps_in_response),
        steps_truncated=len(parsed.steps) > settings.max_steps_in_response,
        agents_md=_agents_md(explanations, selected, len(analysis.findings)) if include_agents_md else "",
        artifacts=build_artifacts(explanations, file_name) if include_agents_md else [],
        provider=service.provider_name,
        llm_model="" if service.used_mock else str(getattr(service.provider, "model", "")),
        provider_is_mock=service.used_mock,
        warnings=warnings,
    )


def analyze_session_sync(source: Any, **kwargs: Any) -> SessionReport:
    """Blocking helper for the CLI and for scripts."""
    return asyncio.run(analyze_session(source, **kwargs))


# --------------------------------------------------------------------------- #

def _parse(source: Any, log_format: str) -> ParseResult:
    parser = SessionParser(log_format)
    if isinstance(source, (bytes, bytearray)):
        return parser.parse_bytes(bytes(source))
    if isinstance(source, Path):
        return parser.parse_file(source)
    if isinstance(source, str):
        candidate = Path(source)
        if "\n" not in source and len(source) < 4096:
            try:
                if candidate.is_file():
                    return parser.parse_file(candidate)
            except OSError:
                pass
        return parser.parse_bytes(source)
    if isinstance(source, Iterable):
        return parser.parse_lines(source)
    raise ValueError(f"unsupported log source: {type(source).__name__}")


def _agents_md(explanations: list[IssueExplanation], selected: list, findings: int = 0) -> str:
    if findings and not selected:
        return (
            "# Agent Rules\n\n_Rules were not generated: explanations are switched off "
            "(explain=false or LLM_MAX_ISSUES=0). The findings are listed in the report._\n"
        )
    if selected and not explanations:
        # Issues were found but nothing explained them - do not claim a clean session.
        return (
            "# Agent Rules\n\n_Rules could not be generated: the LLM stage produced no "
            "explanations. See `warnings`; the deterministic findings are unaffected._\n"
        )
    return generate_agents_md(explanations)


def _summary(parsed: ParseResult, analysis, explanations, file_name: str) -> SummaryOut:
    metrics = analysis.metrics
    return SummaryOut(
        file_name=file_name,
        log_format=parsed.log_format,
        steps=metrics.total_steps,
        tokens=metrics.total_tokens,
        cost=metrics.total_cost,
        cost_estimated=parsed.log_format == "claude" and metrics.total_cost > 0,
        duration_seconds=metrics.duration_seconds,
        tool_calls=metrics.tool_calls,
        tool_errors=metrics.tool_errors,
        user_messages=metrics.user_messages,
        issues_total=len(analysis.findings),
        issues_explained=len(explanations),
        invalid_lines=parsed.invalid_lines,
        ignored_lines=parsed.ignored_lines,
        parse_warnings=len(parsed.warnings),
    )


def _finding_out(finding: Finding) -> FindingOut:
    return FindingOut(
        type=finding.type,
        severity=finding.severity,
        steps=list(finding.steps),
        message=finding.message,
        evidence=finding.evidence,
    )


def _steps_out(steps: list[Step], findings: list[Finding], limit: int) -> list[StepOut]:
    types_by_step: dict[int, list[str]] = {}
    for finding in findings:
        for step_id in finding.steps:
            bucket = types_by_step.setdefault(step_id, [])
            if finding.type not in bucket:
                bucket.append(finding.type)

    return [
        StepOut(
            id=step.id,
            line=step.line,
            timestamp=step.timestamp.isoformat() if step.timestamp else None,
            event_type=step.event_type,
            actor=step.actor,
            tool_name=step.tool_name,
            status=step.status,
            text=(step.text or "")[:300] or None,
            tokens=step.tokens,
            cost=step.cost,
            details=step.raw_preview,
            issue_types=types_by_step.get(step.id, []),
        )
        for step in steps[:limit]
    ]
