"""Context builder.

The LLM must never receive the whole session log - only a small window of steps
around the ones a deterministic detector flagged.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from backend.llm.schemas import Issue

__all__ = ["build_issue_context", "enrich_issues_with_context", "DEFAULT_RADIUS"]

DEFAULT_RADIUS = 2
MAX_TEXT_CHARS = 400
MAX_CONTEXT_CHARS = 3000


def _get(step: Any, name: str, default: Any = None) -> Any:
    if isinstance(step, Mapping):
        return step.get(name, default)
    return getattr(step, name, default)


def _step_id(step: Any) -> Any:
    return _get(step, "id", _get(step, "index"))


def _label(step: Any) -> str:
    event_type = str(_get(step, "event_type", "") or "")
    tool = _get(step, "tool_name")
    actor = str(_get(step, "actor", "unknown") or "unknown")
    status = str(_get(step, "status", "unknown") or "unknown")

    if "output" in event_type or "result" in event_type:
        label = "tool_result"
        if tool:
            label = f"tool_result: {tool}"
        return f"{label} ({status})" if status in {"error", "cancelled"} else label
    if tool:
        return f"tool_call: {tool}" + (f" ({status})" if status == "error" else "")
    if actor == "user":
        return "user"
    if actor == "agent":
        return "assistant"
    return event_type or actor


def _body(step: Any) -> str:
    text = _get(step, "text")
    if text and str(text).strip():
        body = str(text).strip()
    else:
        arguments = _get(step, "tool_arguments")
        body = "" if arguments is None else str(arguments)
    body = " ".join(body.split())
    if len(body) > MAX_TEXT_CHARS:
        body = body[: MAX_TEXT_CHARS - 1] + "…"
    tokens = _get(step, "tokens")
    if not body and isinstance(tokens, int) and tokens:
        body = f"({tokens} tokens)"
    return body


def _merge_windows(indices: Iterable[int], radius: int, low: int, high: int) -> list[tuple[int, int]]:
    """Windows around each step, with overlapping ranges merged."""
    windows = sorted(
        (max(low, index - radius), min(high, index + radius))
        for index in sorted(set(indices))
    )
    merged: list[tuple[int, int]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def build_issue_context(
    issue: Issue,
    steps: Sequence[Any] | None,
    radius: int = DEFAULT_RADIUS,
    *,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> str:
    """Compact text fragment around the steps referenced by ``issue``.

    Missing step ids are skipped; overlapping windows are merged; the result is
    truncated to ``max_chars``. Returns ``""`` when nothing can be rendered.
    """
    by_index: dict[int, Any] = {}
    for step in steps or []:
        index = _step_id(step)
        if isinstance(index, int):
            by_index[index] = step
    if not by_index or not issue.steps:
        return ""

    low, high = min(by_index), max(by_index)
    radius = max(0, int(radius))
    blocks: list[str] = []
    for window_index, (start, end) in enumerate(_merge_windows(issue.steps, radius, low, high)):
        if window_index:
            blocks.append("...")
        for index in range(start, end + 1):
            step = by_index.get(index)
            if step is None:
                continue
            marker = " <-- flagged" if index in issue.steps else ""
            blocks.append(f"Step {index} [{_label(step)}]{marker}:\n{_body(step)}".rstrip())

    context = "\n\n".join(blocks).strip()
    if len(context) > max_chars:
        context = context[: max_chars - 1].rstrip() + "…"
    return context


def enrich_issues_with_context(
    issues: Sequence[Issue] | Iterable[Issue] | None,
    steps: Sequence[Any] | None,
    radius: int = DEFAULT_RADIUS,
) -> list[Issue]:
    """Return copies of ``issues`` with a rendered ``context`` fragment."""
    enriched: list[Issue] = []
    for issue in issues or []:
        context = build_issue_context(issue, steps, radius)
        enriched.append(issue.model_copy(update={"context": context or issue.context}))
    return enriched
