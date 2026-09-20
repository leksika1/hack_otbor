"""View-model for the React dashboard in ``frontend/``.

The dashboard was built in parallel against its own field names. Instead of
rewriting it (or the canonical API), this module renders the same analysis
result in the shape it expects, and ``POST /api/analyze`` serves it.
"""

from __future__ import annotations

from typing import Any, Sequence

from backend.pipeline import AnalyzeResponse

__all__ = ["to_dashboard_payload", "MAX_TIMELINE_STEPS"]

MAX_TIMELINE_STEPS = 300

_LOOP_TYPES = {"repeated_tool_call"}
_ERROR_TYPES = {"tool_failure", "retry", "session_error"}
_HUMAN_TYPES = {"human_intervention"}


def _duration(steps: Sequence[Any]) -> str:
    stamps = [step.timestamp for step in steps if getattr(step, "timestamp", None)]
    if len(stamps) < 2:
        return "N/A"
    seconds = int((max(stamps) - min(stamps)).total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m"


def _step_type(step: Any, loops: set[int], errors: set[int]) -> str:
    if getattr(step, "actor", "") == "user":
        return "human"
    if getattr(step, "status", "") == "error" or step.index in errors:
        return "error"
    if step.index in loops:
        return "loop"
    if getattr(step, "status", "") == "success":
        return "success"
    return getattr(step, "event_type", "") or "info"


def _action(step: Any) -> str:
    text = (getattr(step, "text", None) or "").strip()
    if not text:
        arguments = getattr(step, "tool_arguments", None)
        text = "" if arguments is None else str(arguments)
    text = " ".join(text.split())
    if not text:
        text = getattr(step, "event_type", "") or "step"
    return text[:200]


def to_dashboard_payload(
    result: AnalyzeResponse,
    steps: Sequence[Any],
    filename: str | None = None,
) -> dict[str, Any]:
    """Canonical report + the aliases the React dashboard reads."""
    loops = {index for f in result.findings if f.type in _LOOP_TYPES for index in f.steps}
    errors = {index for f in result.findings if f.type in _ERROR_TYPES for index in f.steps}
    humans = sum(1 for f in result.findings if f.type in _HUMAN_TYPES)
    high = sum(1 for f in result.findings if f.severity == "high")

    visible = list(steps)[:MAX_TIMELINE_STEPS]
    width = f"{100 / max(1, len(visible)):.4f}%"

    log_steps = [
        {
            "id": step.index,
            "type": _step_type(step, loops, errors),
            "tool": getattr(step, "tool_name", None) or "",
            "action": _action(step),
            "time": step.timestamp.strftime("%H:%M:%S") if getattr(step, "timestamp", None) else "",
            "cost": f"${getattr(step, 'cost', 0.0):.3f}",
            "tokens": getattr(step, "tokens", 0),
            "width": width,
        }
        for step in visible
    ]

    metrics = [
        {"label": "Шаги", "value": str(result.summary.steps), "status": "ok"},
        {
            "label": "Проблемы",
            "value": str(result.summary.issues_total),
            "status": "critical" if high else ("warning" if result.summary.issues_total else "ok"),
        },
        {
            "label": "Повторы",
            "value": str(sum(1 for f in result.findings if f.type in _LOOP_TYPES)),
            "status": "warning" if loops else "ok",
        },
        {
            "label": "Вмешательства",
            "value": str(humans),
            "status": "warning" if humans else "ok",
        },
    ]

    payload = result.model_dump()
    payload["summary"] = {
        **payload["summary"],
        "fileName": filename or "log.jsonl",
        "duration": _duration(steps),
        "totalTokens": f"{result.summary.tokens:,}".replace(",", " "),
        "totalCost": f"${result.summary.cost:.2f}",
    }
    payload["metrics"] = metrics
    payload["logSteps"] = log_steps
    payload["artifactText"] = result.agents_md
    return payload
