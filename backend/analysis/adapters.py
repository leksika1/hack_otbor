"""Finding -> Issue adapter.

The analyzer and the LLM layer were written independently and use different
vocabularies. Rather than renaming types on either side (both are used by other
contributors), this module translates between them.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from backend.llm.schemas import Issue

__all__ = ["FINDING_TYPE_MAP", "finding_to_issue", "findings_to_issues"]

# analyzer ``Finding.kind``  ->  LLM ``Issue.type``
FINDING_TYPE_MAP: dict[str, str] = {
    "loop": "repeated_tool_call",
    "tool_error": "tool_failure",
    "tool_retry": "retry",
    "session_error": "session_error",
    "human_intervention": "human_intervention",
    "idle_period": "idle_period",
    "reverted_edit": "reverted_edit",
    "token_hotspot": "token_hotspot",
}


def _get(finding: Any, name: str, default: Any = None) -> Any:
    if isinstance(finding, Mapping):
        return finding.get(name, default)
    return getattr(finding, name, default)


def _step_lookup(steps: Sequence[Any] | None) -> dict[int, Any]:
    if not steps:
        return {}
    lookup: dict[int, Any] = {}
    for step in steps:
        index = _get(step, "index")
        if isinstance(index, int):
            lookup[index] = step
    return lookup


def finding_to_issue(finding: Any, steps: Sequence[Any] | None = None) -> Issue:
    """Convert one analyzer ``Finding`` into an LLM ``Issue``.

    Preserves type (mapped), severity, steps, evidence and the detector message.
    Unknown kinds pass through unchanged instead of being dropped, so a new
    analyzer detector works without touching this file.
    """
    kind = str(_get(finding, "kind", "unknown") or "unknown")
    indices = [int(i) for i in (_get(finding, "step_indices") or ()) if isinstance(i, (int, float))]

    evidence: dict[str, Any] = {}
    raw_evidence = _get(finding, "evidence") or {}
    if isinstance(raw_evidence, Mapping):
        evidence.update(raw_evidence)
    else:
        evidence["value"] = raw_evidence

    evidence = {k: v for k, v in evidence.items() if v not in (None, "", [], {})}

    message = _get(finding, "message")
    if message:
        evidence.setdefault("detector_message", str(message))
    evidence.setdefault("detector_kind", kind)

    # Deterministic enrichment: the analyzer does not always repeat the tool
    # name in the evidence, but the parsed steps know it.
    lookup = _step_lookup(steps)
    if "tool" not in evidence:
        tools = [t for t in (_get(lookup.get(i), "tool_name") for i in indices) if t]
        if tools:
            evidence["tool"] = tools[0]

    return Issue(
        type=FINDING_TYPE_MAP.get(kind, kind),
        severity=str(_get(finding, "severity", "medium") or "medium"),
        steps=indices,
        evidence=evidence,
        context=None,
    )


def findings_to_issues(findings: Iterable[Any] | None, steps: Sequence[Any] | None = None) -> list[Issue]:
    """Convert a list of findings, skipping anything that cannot be adapted."""
    issues: list[Issue] = []
    for finding in findings or []:
        try:
            issues.append(finding_to_issue(finding, steps))
        except Exception:  # noqa: BLE001 - a single bad finding must not break the run
            continue
    return issues
