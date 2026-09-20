"""Pydantic contracts for the LLM layer.

These models are the *integration contract* between the deterministic
analyzers (written by another developer) and the LLM layer.

Design notes
------------
* ``Issue`` is intentionally permissive: analyzers will grow new issue types
  and new evidence fields, and none of that should break this module.
* ``IssueExplanation`` is the only thing this module promises to return.
* Fields that can be verified deterministically (``issue_type``, ``severity``,
  ``steps``) are never taken from the model - see ``IssueExplanation.from_issue``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "SEVERITY_ORDER",
    "KNOWN_ISSUE_TYPES",
    "IssueEvidence",
    "Issue",
    "LLMOutput",
    "IssueExplanation",
    "severity_rank",
]

# Order used for sorting only. Unknown severities sort last.
SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}

# Informational only - NOT an enum. Analyzers may add new types at any time.
KNOWN_ISSUE_TYPES: tuple[str, ...] = (
    "repeated_tool_call",
    "tool_failure",
    "retry",
    "token_hotspot",
    "human_intervention",
    "idle_period",
)


def severity_rank(severity: str | None) -> int:
    """Sort key for a severity string. Unknown values sort after known ones."""
    return SEVERITY_ORDER.get((severity or "").strip().lower(), len(SEVERITY_ORDER))


def _try_int(value: Any) -> int | None:
    try:
        if isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _try_float(value: Any) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class IssueEvidence(BaseModel):
    """Evidence attached to an issue by a deterministic analyzer.

    Every field is optional. Anything the analyzer sends that is not declared
    here is preserved in ``extra`` instead of being dropped or raising, so new
    analyzers never break the LLM layer.
    """

    model_config = ConfigDict(extra="ignore")

    tool: str | None = None
    count: int | None = None
    args: Any | None = None
    error: str | None = None
    token_count: int | None = None
    duration_seconds: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _absorb_unknown_fields(cls, data: Any) -> Any:
        if isinstance(data, IssueEvidence):
            return data
        if data is None:
            return {}
        if not isinstance(data, dict):
            # e.g. a bare string or list coming from an early analyzer draft
            return {"extra": {"value": data}}

        declared = set(cls.model_fields) - {"extra"}
        raw_extra = data.get("extra")
        extra: dict[str, Any] = dict(raw_extra) if isinstance(raw_extra, dict) else {}
        if raw_extra is not None and not isinstance(raw_extra, dict):
            extra["extra"] = raw_extra

        out: dict[str, Any] = {}
        for key, value in data.items():
            if key == "extra":
                continue
            if key not in declared:
                extra[key] = value
                continue
            if key in ("count", "token_count"):
                coerced = _try_int(value)
            elif key == "duration_seconds":
                coerced = _try_float(value)
            else:
                coerced = value
            if coerced is None and value is not None:
                # Unparseable value: keep it rather than silently losing it.
                extra[key] = value
            else:
                out[key] = coerced
        out["extra"] = extra
        return out

    def as_dict(self) -> dict[str, Any]:
        """Flat, prompt-friendly dict without empty values."""
        data = self.model_dump(exclude_none=True)
        extra = data.pop("extra", {}) or {}
        for key, value in extra.items():
            if value is not None:
                data.setdefault(key, value)
        return data


class Issue(BaseModel):
    """A single inefficiency already detected by a deterministic analyzer."""

    model_config = ConfigDict(extra="allow")

    type: str
    severity: str = "medium"
    steps: list[int] = Field(default_factory=list)
    evidence: IssueEvidence = Field(default_factory=IssueEvidence)
    context: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or "unknown"
        return value

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, value: Any) -> Any:
        if value is None:
            return "medium"
        if isinstance(value, str):
            return value.strip().lower() or "medium"
        return value

    @field_validator("steps", mode="before")
    @classmethod
    def _normalize_steps(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return [int(value)]
        if isinstance(value, (list, tuple, set)):
            steps = [_try_int(item) for item in value]
            return [step for step in steps if step is not None]
        return []

    @property
    def severity_rank(self) -> int:
        return severity_rank(self.severity)

    def to_prompt_dict(self) -> dict[str, Any]:
        """Exactly what is sent to the model. Never the whole log."""
        payload: dict[str, Any] = {
            "type": self.type,
            "severity": self.severity,
            "steps": self.steps,
            "evidence": self.evidence.as_dict(),
        }
        if self.context:
            payload["context"] = self.context
        return payload


class LLMOutput(BaseModel):
    """The only fields the model is allowed to produce."""

    model_config = ConfigDict(extra="ignore")

    title: str
    explanation: str
    impact: str
    recommendation: str
    agent_rule: str

    @field_validator("*", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> Any:
        if isinstance(value, list):  # some models wrap strings in a list
            value = " ".join(str(item) for item in value)
        if isinstance(value, str):
            return value.strip().lstrip("-*").strip()
        return value

    @field_validator("title", "explanation", "impact", "recommendation", "agent_rule")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()


class IssueExplanation(BaseModel):
    """LLM output for one issue, with verifiable fields restored from the Issue."""

    issue_type: str
    severity: str
    steps: list[int]

    title: str
    explanation: str
    impact: str
    recommendation: str
    agent_rule: str

    @classmethod
    def from_issue(cls, issue: Issue, output: LLMOutput) -> "IssueExplanation":
        """Build the result, taking deterministic fields from ``issue`` only.

        The model never decides ``issue_type``, ``severity`` or ``steps``.
        """
        return cls(
            issue_type=issue.type,
            severity=issue.severity,
            steps=list(issue.steps),
            **output.model_dump(),
        )

    @property
    def severity_rank(self) -> int:
        return severity_rank(self.severity)
