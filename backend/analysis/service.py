"""Runs every deterministic detector over the parsed steps."""

from __future__ import annotations

import logging
from typing import Callable, Sequence

from backend.parser import AGENT, USER, Step

from . import failures, idle, interventions, repeated_calls, reverts, tokens
from .models import AnalysisConfig, AnalysisResult, Finding, SessionMetrics

__all__ = ["analyze_steps", "rank_findings", "DETECTORS"]

logger = logging.getLogger(__name__)

Detector = Callable[[Sequence[Step], AnalysisConfig], list[Finding]]

# Adding a detector here is all it takes to extend the analysis.
DETECTORS: tuple[tuple[str, Detector], ...] = (
    ("repeated_tool_call", repeated_calls.detect),
    ("failures", failures.detect),
    ("human_intervention", interventions.detect),
    ("idle_period", idle.detect),
    ("reverted_edit", reverts.detect),
    ("token_hotspot", tokens.detect),
)


def rank_findings(findings: Sequence[Finding]) -> list[Finding]:
    """Most severe first; stable by the first step id within a severity."""
    return sorted(findings, key=lambda finding: (finding.rank, finding.steps))


def analyze_steps(steps: Sequence[Step], config: AnalysisConfig | None = None) -> AnalysisResult:
    """Deterministic analysis. Never raises: a broken detector is logged and skipped."""
    steps = list(steps)
    config = (config or AnalysisConfig()).for_session(len(steps))

    findings: list[Finding] = []
    for name, detector in DETECTORS:
        try:
            findings.extend(detector(steps, config))
        except Exception:  # noqa: BLE001 - one detector must not break the report
            logger.exception("detector %s failed", name)

    result = AnalysisResult(metrics=_metrics(steps, config), findings=rank_findings(findings))
    logger.info("analysis produced %s findings from %s steps", len(result.findings), len(steps))
    return result


def _metrics(steps: Sequence[Step], config: AnalysisConfig) -> SessionMetrics:
    stamps = [step.timestamp for step in steps if step.timestamp]
    duration = (max(stamps) - min(stamps)).total_seconds() if len(stamps) > 1 else 0.0
    return SessionMetrics(
        total_steps=len(steps),
        total_tokens=sum(step.tokens for step in steps),
        total_cost=round(sum(step.cost for step in steps), 6),
        duration_seconds=round(duration, 1),
        tool_calls=sum(1 for step in steps if step.is_tool_call and step.tool_name),
        tool_errors=sum(1 for step in steps if step.status == "error"),
        user_messages=sum(1 for step in steps if step.actor == USER),
        token_buckets=tokens.build_buckets(steps, config.bucket_size),
    )
