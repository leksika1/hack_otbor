"""Deterministic analysis output.

``Finding`` is produced by Python code only. The LLM never invents one and can
never change its ``type``, ``severity`` or ``steps``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Finding", "SessionMetrics", "AnalysisResult", "AnalysisConfig",
    "SEVERITY_RANK", "ISSUE_TYPES", "severity_rank",
]

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

# The canonical vocabulary shared by the analyzers, the LLM layer and the API.
ISSUE_TYPES = (
    "repeated_tool_call",
    "tool_failure",
    "retry",
    "session_error",
    "human_intervention",
    "idle_period",
    "reverted_edit",
    "token_hotspot",
)


def severity_rank(severity: str | None) -> int:
    return SEVERITY_RANK.get((severity or "").strip().lower(), len(SEVERITY_RANK))


@dataclass(frozen=True)
class Finding:
    """One inefficiency, always tied to concrete step ids."""

    type: str
    severity: str
    steps: tuple[int, ...]
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def rank(self) -> int:
        return severity_rank(self.severity)


@dataclass
class SessionMetrics:
    total_steps: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    duration_seconds: float = 0.0
    tool_calls: int = 0
    tool_errors: int = 0
    user_messages: int = 0
    token_buckets: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AnalysisResult:
    metrics: SessionMetrics = field(default_factory=SessionMetrics)
    findings: list[Finding] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisConfig:
    """Thresholds of the deterministic detectors - all explainable, no ML."""

    similarity_threshold: float = 0.88
    repeat_window: int = 8
    idle_seconds: float = 120.0
    idle_high_multiplier: float = 5.0
    bucket_size: int = 50
    hotspot_ratio: float = 2.0

    def for_session(self, step_count: int) -> "AnalysisConfig":
        """Token buckets must stay small enough for a short session to have several."""
        from dataclasses import replace

        return replace(self, bucket_size=max(5, min(self.bucket_size, step_count // 10 or 5)))
