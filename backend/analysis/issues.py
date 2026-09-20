"""Finding -> Issue: the hand-off from deterministic analysis to the LLM.

``Finding`` is what the analyzers produce; ``Issue`` is what the LLM is allowed
to see. They share one vocabulary (``ISSUE_TYPES``), so this is a plain
projection plus de-duplication - there is no type translation table to drift.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from backend.llm.schemas import Issue
from backend.parser import Step

from .models import Finding, severity_rank

__all__ = ["finding_to_issue", "findings_to_issues", "select_top_issues"]


def finding_to_issue(finding: Finding, steps: Sequence[Step] | None = None) -> Issue:
    """Project one finding into the LLM input contract."""
    evidence = {key: value for key, value in (finding.evidence or {}).items()
                if value not in (None, "", [], {})}
    evidence.setdefault("detector_message", finding.message)

    if "tool" not in evidence and steps:
        by_id = {step.id: step for step in steps}
        tools = [by_id[step_id].tool_name for step_id in finding.steps
                 if step_id in by_id and by_id[step_id].tool_name]
        if tools:
            evidence["tool"] = tools[0]

    return Issue(
        type=finding.type,
        severity=finding.severity,
        steps=list(finding.steps),
        evidence=evidence,
        context=None,
    )


def findings_to_issues(findings: Iterable[Finding], steps: Sequence[Step] | None = None) -> list[Issue]:
    return [finding_to_issue(finding, steps) for finding in findings or []]


def select_top_issues(issues: Sequence[Issue], limit: int) -> list[Issue]:
    """Pick the issues worth an LLM call.

    Near-duplicates (same type and tool) collapse into one representative with an
    ``occurrences`` counter, so a session with fifty identical loops costs one
    request instead of fifty.
    """
    if limit <= 0:
        return []

    representatives: dict[tuple[str, str], Issue] = {}
    counts: dict[tuple[str, str], int] = {}
    for issue in issues:
        evidence = issue.evidence.as_dict()
        key = (issue.type, str(evidence.get("tool") or ""))
        counts[key] = counts.get(key, 0) + 1
        current = representatives.get(key)
        if current is None or severity_rank(issue.severity) < severity_rank(current.severity):
            representatives[key] = issue

    selected: list[Issue] = []
    for key, issue in representatives.items():
        if counts[key] > 1:
            evidence = issue.evidence.as_dict()
            evidence["occurrences"] = counts[key]
            issue = issue.model_copy(update={"evidence": type(issue.evidence).model_validate(evidence)})
        selected.append(issue)

    selected.sort(key=lambda item: (severity_rank(item.severity), item.steps[:1] or [0]))
    return selected[:limit]
